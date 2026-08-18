# Copyright OSCAL Compass Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Pinned-apm integration spikes (design-spec §5.1) — the primary safety net.

The load-bearing behavior lives in APM, so these drive the real pinned ``apm`` CLI through our
backend and assert the requirement-level outcomes proven by hand during design. Gated on ``apm``
being available (``requires_apm``); re-run before any ``apm-cli`` bump. Offline: self-defined
stdio MCP is *wired* (config written) without launching the server.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ag_au_skills.backends import apm_cli
from tests.conftest import requires_apm

pytestmark = [requires_apm, pytest.mark.integration]


def _dirs(source_repo: Path, *names: str) -> list[Path]:
    return [source_repo / "skills" / n for n in names]


def test_standalone_install_claude_places_skill_and_wires_mcp(source_repo, tmp_path):
    project = tmp_path / "proj"
    apm_cli.install(_dirs(source_repo, "catalog-authoring"), target="claude", project=project)

    assert (project / ".claude" / "skills" / "catalog-authoring" / "SKILL.md").is_file()
    mcp = json.loads((project / ".mcp.json").read_text())
    assert mcp["mcpServers"]["trestle"]["command"] == "uvx"


def test_opencode_native_merge_preserves_user_config(source_repo, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    # a pre-existing user opencode.json with a provider block that must survive.
    (project / "opencode.json").write_text(
        json.dumps({"provider": {"litellm": {"options": {"baseURL": "http://x"}}}}),
        encoding="utf-8",
    )
    apm_cli.install(_dirs(source_repo, "catalog-authoring"), target="opencode", project=project)

    assert (project / ".agents" / "skills" / "catalog-authoring" / "SKILL.md").is_file()
    conf = json.loads((project / "opencode.json").read_text())
    # user provider preserved …
    assert conf["provider"]["litellm"]["options"]["baseURL"] == "http://x"
    # … and the trestle server wired in opencode's native `mcp` shape.
    assert "trestle" in conf["mcp"]


def test_shared_mcp_prune_via_apm(source_repo, tmp_path):
    project = tmp_path / "proj"
    apm_cli.install(
        _dirs(source_repo, "catalog-authoring", "component-definition"),
        target="claude",
        project=project,
    )
    assert "trestle" in json.loads((project / ".mcp.json").read_text())["mcpServers"]

    # uninstall one consumer → trestle stays.
    apm_cli.uninstall(["catalog-authoring"], target="claude", project=project)
    assert "trestle" in json.loads((project / ".mcp.json").read_text())["mcpServers"]

    # uninstall the last consumer → trestle pruned.
    apm_cli.uninstall(["component-definition"], target="claude", project=project)
    remaining = json.loads((project / ".mcp.json").read_text()).get("mcpServers", {})
    assert "trestle" not in remaining


def test_project_scope_tidy_leaves_only_products_and_stash(source_repo, tmp_path):
    project = tmp_path / "proj"
    apm_cli.install(_dirs(source_repo, "catalog-authoring"), target="claude", project=project)

    # products present …
    assert (project / ".claude" / "skills" / "catalog-authoring").is_dir()
    assert (project / ".mcp.json").is_file()
    # … APM's project bookkeeping consolidated into the hidden stash, cache + gitignore gone.
    top = {p.name for p in project.iterdir()}
    assert top == {".claude", ".mcp.json", ".ag-au-skills"}
    assert not (project / "apm_modules").exists()
    assert (project / ".ag-au-skills" / "apm.lock.yaml").is_file()


def test_tidy_stash_restores_for_uninstall_prune(source_repo, tmp_path):
    project = tmp_path / "proj"
    apm_cli.install(
        _dirs(source_repo, "catalog-authoring", "component-definition"),
        target="claude",
        project=project,
    )
    # uninstall must transparently restore the stash, prune correctly, and re-tidy.
    apm_cli.uninstall(["catalog-authoring"], target="claude", project=project)
    assert "trestle" in json.loads((project / ".mcp.json").read_text())["mcpServers"]
    apm_cli.uninstall(["component-definition"], target="claude", project=project)
    assert "trestle" not in json.loads((project / ".mcp.json").read_text()).get("mcpServers", {})
    # still tidy after uninstalls.
    assert not (project / "apm_modules").exists()


def test_keep_apm_files_disables_tidy(source_repo, tmp_path):
    project = tmp_path / "proj"
    apm_cli.install(
        _dirs(source_repo, "catalog-authoring"), target="claude", project=project, tidy=False
    )
    # APM's ledger left in place; no stash created.
    assert (project / "apm.lock.yaml").is_file()
    assert not (project / ".ag-au-skills").exists()


def test_install_dry_run_builds_argv_without_running(source_repo, tmp_path):
    argv = apm_cli.install(
        _dirs(source_repo, "assessment"), target="claude", project=tmp_path / "p", dry_run=True
    )
    assert argv[1] == "install" and "--target" in argv and "claude" in argv
    assert not (tmp_path / "p").exists()
