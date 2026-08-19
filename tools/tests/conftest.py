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

"""Shared fixtures: a synthetic skill-source repo, and integration gating on the `apm` CLI."""

from __future__ import annotations

import shutil
import textwrap
from pathlib import Path

import pytest


def _write_skill(
    skills_root: Path, name: str, *, mcp: dict | None = None
) -> Path:
    """Create a minimal hybrid skill package (SKILL.md + apm.yml) under *skills_root*."""
    d = skills_root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test skill {name}\n---\n\n# {name}\n",
        encoding="utf-8",
    )
    apm = [f"name: {name}", 'version: "1.0.0"']
    if mcp:
        apm += ["dependencies:", "  mcp:", f"    - name: {mcp['name']}",
                "      registry: false", "      transport: stdio",
                f"      command: {mcp['command']}", "      args:"]
        apm += [f"        - {a}" for a in mcp["args"]]
    (d / "apm.yml").write_text("\n".join(apm) + "\n", encoding="utf-8")
    return d


@pytest.fixture
def source_repo(tmp_path: Path) -> Path:
    """A synthetic skills-source repo mirroring the real one's shape.

    * ``catalog-authoring`` + ``component-definition`` share a ``trestle`` stdio MCP,
    * ``assessment`` has no MCP,
    * plus a ``catalog-to-assessment`` demo declaring the three.
    """
    root = tmp_path / "repo"
    skills = root / "skills"
    trestle = {
        "name": "trestle",
        "command": "uvx",
        "args": ["--from", "git+https://example.invalid/trestle.git", "trestle-mcp"],
    }
    _write_skill(skills, "catalog-authoring", mcp=trestle)
    _write_skill(skills, "component-definition", mcp=trestle)
    _write_skill(skills, "assessment")

    demo = root / "demos" / "catalog-to-assessment"
    demo.mkdir(parents=True)
    (demo / "README.md").write_text(
        textwrap.dedent(
            """\
            ---
            name: catalog-to-assessment
            skills: [catalog-authoring, component-definition, assessment]
            ---

            # Demo
            """
        ),
        encoding="utf-8",
    )
    return root


def _apm_available() -> bool:
    import os

    return bool(os.environ.get("APM_BIN") or shutil.which("apm"))


requires_apm = pytest.mark.skipif(
    not _apm_available(),
    reason="pinned `apm` CLI not on PATH / APM_BIN (integration spike)",
)
