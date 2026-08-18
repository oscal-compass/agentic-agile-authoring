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

"""Unit tests for the apm_cli backend's pure helpers (no `apm` CLI needed)."""

from __future__ import annotations

from ag_au_skills.backends import apm_cli


def test_clean_gitignore_removes_only_apm_block(tmp_path):
    gi = tmp_path / ".gitignore"
    gi.write_text("*.log\n\n# APM dependencies\napm_modules/\n", encoding="utf-8")
    apm_cli._clean_gitignore(gi)
    # user entry kept; APM block stripped.
    assert gi.read_text(encoding="utf-8") == "*.log\n"


def test_clean_gitignore_deletes_file_when_only_apm_block(tmp_path):
    gi = tmp_path / ".gitignore"
    gi.write_text("# APM dependencies\napm_modules/\n", encoding="utf-8")
    apm_cli._clean_gitignore(gi)
    assert not gi.exists()


def test_tidy_and_restore_roundtrip(tmp_path):
    project = tmp_path / "proj"
    (project / "apm_modules" / "_local").mkdir(parents=True)
    (project / "apm.yml").write_text("name: x\nversion: '1.0.0'\n", encoding="utf-8")
    (project / "apm.lock.yaml").write_text("lockfile_version: '1'\n", encoding="utf-8")
    (project / ".gitignore").write_text("# APM dependencies\napm_modules/\n", encoding="utf-8")
    (project / ".mcp.json").write_text("{}", encoding="utf-8")

    apm_cli._tidy_project(project)
    top = {p.name for p in project.iterdir()}
    assert top == {".mcp.json", ".ag-au-skills"}
    assert (project / ".ag-au-skills" / "apm.yml").is_file()
    assert (project / ".ag-au-skills" / "apm.lock.yaml").is_file()

    assert apm_cli._restore_project(project) is True
    assert (project / "apm.yml").is_file() and (project / "apm.lock.yaml").is_file()


def test_restore_returns_false_without_stash(tmp_path):
    assert apm_cli._restore_project(tmp_path) is False
