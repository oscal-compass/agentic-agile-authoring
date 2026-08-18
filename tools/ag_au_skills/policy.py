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

"""Policy: the bespoke decisions APM doesn't make for us (design-spec §3.2, §3.5).

Three concerns, all pure/deterministic so they're unit-testable without touching APM:

* **selection** — turn ``--skill`` / ``--exclude`` / ``--scenario`` into an explicit, validated
  list of local skill packages (delegates the resolution to :mod:`.selection`);
* **manifest validation** — each selected skill must be a well-formed APM package
  (``SKILL.md`` + an ``apm.yml`` carrying ``name`` + ``version`` and no ``target:`` field);
* **prerequisite policy** — ``uv`` is the guaranteed baseline; other per-MCP runtimes
  (``npx`` / ``docker``) are the environment's responsibility — we only check presence and warn.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .selection import (
    list_all_skills,
    resolve_skill_list,
    scenario_skills,
    unknown_names,
)


class PolicyError(ValueError):
    """A selection / manifest / prerequisite violation the user must fix."""


# --- selection ---------------------------------------------------------------


def resolve_selection(
    source_root: Path,
    *,
    picks: list[str] | None = None,
    scenario: str | None = None,
    exclude: list[str] | None = None,
) -> list[str]:
    """Resolve a selection against *source_root*'s ``skills/`` into an explicit skill list.

    Raises :class:`PolicyError` on an empty ``skills/`` dir, a typo (a referenced name that
    doesn't exist), or a selection that resolves to zero skills.
    """
    if not (source_root / "skills").is_dir():
        raise PolicyError(f"source has no skills/ directory: {source_root}")

    all_skills = list_all_skills(source_root)
    if not all_skills:
        raise PolicyError(f"no skills found under {source_root / 'skills'}")

    scenario_set = scenario_skills(source_root, scenario) if scenario else None
    bad = unknown_names(all_skills, picks=picks, scenario=scenario_set, exclude=exclude)
    if bad:
        raise PolicyError(f"unknown skill(s) for source {source_root}: {', '.join(bad)}")

    skills = resolve_skill_list(
        all_skills, picks=picks, scenario=scenario_set, exclude=exclude
    )
    if not skills:
        raise PolicyError("selection resolved to zero skills")
    return skills


# --- manifest validation -----------------------------------------------------


def skill_dir(source_root: Path, name: str) -> Path:
    """Absolute path to a skill package directory in *source_root*."""
    return (source_root / "skills" / name).resolve()


def validate_skill_manifest(pkg_dir: Path) -> dict:
    """Validate a skill package's ``apm.yml`` at the wrapper level and return its parsed dict.

    We enforce the invariants the wrapper (and APM) depend on, up front, with a friendlier error
    than APM's parse failure:

    * ``SKILL.md`` and ``apm.yml`` both present (the hybrid package shape, §2.2);
    * ``apm.yml`` carries non-empty ``name`` + ``version`` (APM requires both, verified @ 0.28.0);
    * ``apm.yml`` declares **no** ``target:`` / ``targets:`` — an unknown target token there is
      rejected by APM at parse time and would break MyHarness reuse (§2.3).
    """
    if not (pkg_dir / "SKILL.md").is_file():
        raise PolicyError(f"{pkg_dir}: not a skill package (missing SKILL.md)")
    apm_yml = pkg_dir / "apm.yml"
    if not apm_yml.is_file():
        raise PolicyError(f"{pkg_dir}: missing apm.yml (skills are hybrid SKILL.md + apm.yml)")

    try:
        data = yaml.safe_load(apm_yml.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise PolicyError(f"{apm_yml}: invalid YAML: {e}") from e
    if not isinstance(data, dict):
        raise PolicyError(f"{apm_yml}: must contain a YAML mapping")

    for key in ("name", "version"):
        val = data.get(key)
        if not isinstance(val, str) or not val.strip():
            raise PolicyError(f"{apm_yml}: missing/empty required field '{key}'")
    if "target" in data or "targets" in data:
        raise PolicyError(
            f"{apm_yml}: must not declare 'target:'/'targets:' — targets are chosen at install "
            "time (APM rejects unknown target tokens at parse time; see design-spec §2.3)"
        )
    return data


# --- prerequisite policy -----------------------------------------------------


@dataclass
class PrereqReport:
    """Outcome of a prerequisite check (§3.5)."""

    ok: bool
    missing_baseline: list[str] = field(default_factory=list)  # hard error (uv)
    missing_optional: list[str] = field(default_factory=list)  # warn only (npx/docker)


# stdio commands that are the environment's responsibility, not ours to install.
_OPTIONAL_RUNTIMES = {"npx", "node", "docker"}
# commands we treat as already-guaranteed by the uv baseline (don't warn on them).
_BASELINE_PROVIDED = {"uv", "uvx"}


def _mcp_commands(manifests: list[dict]) -> set[str]:
    """The set of stdio ``command`` tokens declared across the given parsed apm.yml dicts."""
    cmds: set[str] = set()
    for data in manifests:
        deps = (data.get("dependencies") or {}).get("mcp") or []
        for dep in deps:
            if isinstance(dep, dict) and isinstance(dep.get("command"), str):
                cmds.add(dep["command"].strip())
    return cmds


def check_prerequisites(
    manifests: list[dict], *, which=shutil.which
) -> PrereqReport:
    """Check runtime prerequisites for a set of selected skill manifests (§3.5).

    * ``uv`` (→ ``uvx``) is the guaranteed baseline: absent ⇒ hard error.
    * Any other stdio ``command`` a skill's MCP needs (``npx``/``docker``/…) is the environment's
      responsibility: absent ⇒ warning, not an error.

    *which* is injectable for tests (defaults to :func:`shutil.which`).
    """
    missing_baseline = [] if which("uv") else ["uv"]

    missing_optional = sorted(
        cmd
        for cmd in _mcp_commands(manifests)
        if cmd not in _BASELINE_PROVIDED and which(cmd) is None
    )
    return PrereqReport(
        ok=not missing_baseline,
        missing_baseline=missing_baseline,
        missing_optional=missing_optional,
    )
