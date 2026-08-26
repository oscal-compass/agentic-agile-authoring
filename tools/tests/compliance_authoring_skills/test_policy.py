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

"""Unit tests for the bespoke policy layer (selection, manifest validation, prereqs)."""

from __future__ import annotations

from pathlib import Path

import pytest

from compliance_authoring_skills import policy

# --- default source (bundled / dev fallback) ---------------------------------


def test_default_source_root_prefers_bundled(monkeypatch, tmp_path):
    # simulate a wheel install: compliance_authoring_skills/_bundled/skills exists next to the package.
    pkg = tmp_path / "compliance_authoring_skills"
    (pkg / policy._BUNDLED_DIRNAME / "skills" / "x").mkdir(parents=True)
    monkeypatch.setattr(policy.importlib_resources, "files", lambda _pkg: pkg)
    assert policy.default_source_root() == pkg / policy._BUNDLED_DIRNAME


def test_default_source_root_dev_fallback(monkeypatch):
    # no bundle → fall back to the repo checkout the package lives in (this repo).
    monkeypatch.setattr(policy.importlib_resources, "files", lambda _pkg: Path("/nonexistent"))
    root = policy.default_source_root()
    assert (root / "skills").is_dir()


# --- selection ---------------------------------------------------------------


def test_resolve_selection_default_is_all(source_repo):
    assert policy.resolve_selection(source_repo) == [
        "assessment",
        "catalog-authoring",
        "component-definition",
    ]


def test_resolve_selection_demo(source_repo):
    assert policy.resolve_selection(source_repo, demo="catalog-to-assessment") == [
        "catalog-authoring",
        "component-definition",
        "assessment",
    ]


def test_resolve_selection_exclude(source_repo):
    assert policy.resolve_selection(source_repo, exclude=["assessment"]) == [
        "catalog-authoring",
        "component-definition",
    ]


def test_resolve_selection_typo_errors(source_repo):
    with pytest.raises(policy.PolicyError, match="unknown skill"):
        policy.resolve_selection(source_repo, picks=["catalog-authorng"])


def test_resolve_selection_no_skills_dir(tmp_path):
    with pytest.raises(policy.PolicyError, match="no skills/ directory"):
        policy.resolve_selection(tmp_path)


# --- manifest validation -----------------------------------------------------


def test_validate_manifest_ok(source_repo):
    data = policy.validate_skill_manifest(source_repo / "skills" / "catalog-authoring")
    assert data["name"] == "catalog-authoring"
    assert data["version"] == "1.0.0"


def test_validate_manifest_missing_apm_yml(source_repo):
    (source_repo / "skills" / "assessment" / "apm.yml").unlink()
    with pytest.raises(policy.PolicyError, match="missing apm.yml"):
        policy.validate_skill_manifest(source_repo / "skills" / "assessment")


def test_validate_manifest_missing_version(source_repo):
    d = source_repo / "skills" / "assessment"
    (d / "apm.yml").write_text("name: assessment\n", encoding="utf-8")
    with pytest.raises(policy.PolicyError, match="required field 'version'"):
        policy.validate_skill_manifest(d)


def test_validate_manifest_rejects_target_field(source_repo):
    d = source_repo / "skills" / "assessment"
    (d / "apm.yml").write_text(
        'name: assessment\nversion: "1.0.0"\ntarget: claude\n', encoding="utf-8"
    )
    with pytest.raises(policy.PolicyError, match="must not declare 'target"):
        policy.validate_skill_manifest(d)


# --- prerequisite policy -----------------------------------------------------


def _which_factory(present):
    present = set(present)
    return lambda cmd: f"/usr/bin/{cmd}" if cmd in present else None


def test_prereqs_uv_missing_is_hard_error(source_repo):
    manifests = [policy.validate_skill_manifest(source_repo / "skills" / "catalog-authoring")]
    report = policy.check_prerequisites(manifests, which=_which_factory([]))
    assert not report.ok
    assert report.missing_baseline == ["uv"]


def test_prereqs_uvx_command_not_flagged(source_repo):
    # trestle uses `uvx`, which the uv baseline provides — must not warn.
    manifests = [policy.validate_skill_manifest(source_repo / "skills" / "catalog-authoring")]
    report = policy.check_prerequisites(manifests, which=_which_factory(["uv"]))
    assert report.ok
    assert report.missing_optional == []


def test_prereqs_optional_runtime_warns_not_errors(source_repo, tmp_path):
    # a skill whose MCP needs npx → warn (optional), still ok.
    from tests.conftest import _write_skill

    _write_skill(
        source_repo / "skills",
        "needs-npx",
        mcp={"name": "srv", "command": "npx", "args": ["-y", "some-server"]},
    )
    manifests = [policy.validate_skill_manifest(source_repo / "skills" / "needs-npx")]
    report = policy.check_prerequisites(manifests, which=_which_factory(["uv"]))
    assert report.ok
    assert report.missing_optional == ["npx"]
