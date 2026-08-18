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

"""MyHarness deployer tests.

``normalized_mcp`` exercises the real pinned-APM library layer (that's the point of the reuse),
so it's imported at call time; the deploy/prune/merge logic is pure filesystem/JSON and tested
directly. These need apm-cli importable (the pinned dependency), which the test env always has.
"""

from __future__ import annotations

import json
from pathlib import Path

from ag_au_skills.targets import myharness


def _skill_dirs(source_repo: Path, *names: str) -> list[Path]:
    return [source_repo / "skills" / n for n in names]


def test_normalized_mcp_via_apm_library(source_repo):
    servers = myharness.normalized_mcp(source_repo / "skills" / "catalog-authoring")
    assert "trestle" in servers
    assert servers["trestle"]["command"] == "uvx"
    assert servers["trestle"]["transport"] == "stdio"
    # self-defined marker survives normalization.
    assert servers["trestle"]["registry"] is False


def test_normalized_mcp_empty_for_no_mcp_skill(source_repo):
    assert myharness.normalized_mcp(source_repo / "skills" / "assessment") == {}


def test_install_deploys_skills_and_wires_mcp(source_repo, tmp_path):
    root = tmp_path / "mh"
    res = myharness.install(
        _skill_dirs(source_repo, "catalog-authoring", "assessment"), root=root
    )
    assert set(res.skills_deployed) == {"catalog-authoring", "assessment"}
    assert res.mcp_added == ["trestle"]
    assert (root / "skills" / "catalog-authoring" / "SKILL.md").is_file()
    config = json.loads((root / "mcp.json").read_text())
    assert config["mcpServers"]["trestle"]["command"] == "uvx"
    assert config["_ag_au"]["owned_mcp"] == ["trestle"]


def test_install_preserves_user_mcp_server(source_repo, tmp_path):
    root = tmp_path / "mh"
    (root).mkdir()
    (root / "mcp.json").write_text(
        json.dumps({"mcpServers": {"my-own": {"command": "custom"}}}), encoding="utf-8"
    )
    myharness.install(_skill_dirs(source_repo, "catalog-authoring"), root=root)
    config = json.loads((root / "mcp.json").read_text())
    # user server untouched; ours added; not claimed as owned.
    assert config["mcpServers"]["my-own"] == {"command": "custom"}
    assert "trestle" in config["mcpServers"]
    assert config["_ag_au"]["owned_mcp"] == ["trestle"]


def test_shared_mcp_prune_keeps_then_removes(source_repo, tmp_path):
    root = tmp_path / "mh"
    myharness.install(
        _skill_dirs(source_repo, "catalog-authoring", "component-definition"), root=root
    )
    # remove one consumer → trestle stays (the other still needs it).
    res1 = myharness.uninstall(["catalog-authoring"], root=root)
    assert res1.skills_removed == ["catalog-authoring"]
    assert res1.mcp_pruned == []
    assert "trestle" in json.loads((root / "mcp.json").read_text())["mcpServers"]
    # remove the last consumer → trestle pruned.
    res2 = myharness.uninstall(["component-definition"], root=root)
    assert res2.mcp_pruned == ["trestle"]
    assert json.loads((root / "mcp.json").read_text())["mcpServers"] == {}


def test_prune_never_touches_user_server(source_repo, tmp_path):
    root = tmp_path / "mh"
    myharness.install(_skill_dirs(source_repo, "catalog-authoring"), root=root)
    config = json.loads((root / "mcp.json").read_text())
    config["mcpServers"]["my-own"] = {"command": "custom"}
    (root / "mcp.json").write_text(json.dumps(config), encoding="utf-8")
    # removing the only trestle consumer prunes trestle but leaves the user server.
    myharness.uninstall(["catalog-authoring"], root=root)
    servers = json.loads((root / "mcp.json").read_text())["mcpServers"]
    assert "trestle" not in servers
    assert servers["my-own"] == {"command": "custom"}


def test_install_dry_run_makes_no_changes(source_repo, tmp_path):
    root = tmp_path / "mh"
    res = myharness.install(_skill_dirs(source_repo, "catalog-authoring"), root=root, dry_run=True)
    assert res.skills_deployed == ["catalog-authoring"]
    assert res.mcp_added == ["trestle"]
    assert not root.exists()
