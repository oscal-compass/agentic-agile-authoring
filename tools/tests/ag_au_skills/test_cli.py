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

"""CLI wiring tests — chiefly that ``--source`` is optional and defaults to the bundled skills."""

from __future__ import annotations

import pytest

from ag_au_skills import cli, policy


@pytest.fixture
def _ok_prereqs(monkeypatch):
    """Pretend the uv baseline is satisfied so CLI tests don't depend on uv being installed."""
    monkeypatch.setattr(policy, "check_prerequisites", lambda *_a, **_k: policy.PrereqReport(ok=True))


def test_install_without_source_uses_default(monkeypatch, _ok_prereqs, source_repo, tmp_path, capsys):
    # no --source → the CLI must fall back to policy.default_source_root().
    monkeypatch.setattr(policy, "default_source_root", lambda: source_repo)
    rc = cli.main(
        ["install", "--target", "myharness", "--myharness-root", str(tmp_path / "mh"), "--dry-run"]
    )
    assert rc == 0
    out = capsys.readouterr().out
    # the bundled/default selection (all skills in source_repo) was resolved.
    assert "catalog-authoring" in out and "assessment" in out


def test_install_explicit_source_overrides_default(monkeypatch, _ok_prereqs, source_repo, tmp_path):
    called = {"default": False}
    monkeypatch.setattr(
        policy, "default_source_root", lambda: called.__setitem__("default", True) or source_repo
    )
    rc = cli.main(
        [
            "install", "--source", str(source_repo), "--skill", "assessment",
            "--target", "myharness", "--myharness-root", str(tmp_path / "mh"), "--dry-run",
        ]
    )
    assert rc == 0
    # an explicit --source must NOT consult the bundled default.
    assert called["default"] is False


def test_uninstall_requires_selection(_ok_prereqs):
    assert cli.main(["uninstall", "--target", "myharness"]) == 1  # needs --skill or --all
