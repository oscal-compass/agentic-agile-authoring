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

"""Selection: resolve ``--skill`` / ``--exclude`` / ``--scenario`` into an explicit skill list."""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

_FRONTMATTER = re.compile(r"^---\r?\n(.*?)\r?\n---", re.DOTALL)


# --- pure resolution (the testable core) ------------------------------------


def resolve_skill_list(
    all_skills: list[str],
    *,
    picks: list[str] | None = None,
    scenario: list[str] | None = None,
    exclude: list[str] | None = None,
) -> list[str]:
    """Resolve a selection into an explicit, de-duplicated, order-preserving skill list.

    Base is the most specific selector present (picks > scenario > all); then ``exclude`` is
    subtracted.
    """
    exclude_set = set(exclude or [])
    if picks:
        base = picks
    elif scenario is not None:
        base = scenario
    else:
        base = all_skills
    seen: set[str] = set()
    out: list[str] = []
    for s in base:
        if s in exclude_set or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def unknown_names(
    all_skills: list[str],
    *,
    picks: list[str] | None = None,
    scenario: list[str] | None = None,
    exclude: list[str] | None = None,
) -> list[str]:
    """Names referenced by a selection that don't exist in the source repo (a typo guard).

    Returns ``[]`` when ``all_skills`` is empty (e.g. a remote source we can't enumerate
    locally), so validation is skipped rather than raising false positives.
    """
    if not all_skills:
        return []
    known = set(all_skills)
    referenced = set((picks or []) + (scenario or []) + (exclude or []))
    return sorted(n for n in referenced if n not in known)


# --- disk readers ------------------------------------------------------------


def list_all_skills(source_root: Path) -> list[str]:
    """Every skill in a source repo's ``skills/`` dir (identified by a ``SKILL.md``)."""
    skills_dir = source_root / "skills"
    if not skills_dir.exists():
        return []
    return sorted(
        n for n in os.listdir(skills_dir) if (skills_dir / n / "SKILL.md").exists()
    )


def parse_frontmatter(text: str) -> dict:
    """Parse the leading ``---``-fenced YAML frontmatter block of a markdown file."""
    m = _FRONTMATTER.match(text)
    if not m:
        return {}
    doc = yaml.safe_load(m.group(1))
    return doc if isinstance(doc, dict) else {}


def scenario_skills(source_root: Path, scenario: str) -> list[str]:
    """The skill set a scenario exercises, from ``scenarios/<name>/steps.md`` frontmatter."""
    steps = source_root / "scenarios" / scenario / "steps.md"
    if not steps.exists():
        raise ValueError(f"scenario not found: {scenario} (expected {steps})")
    fm = parse_frontmatter(steps.read_text(encoding="utf-8"))
    skills = fm.get("skills")
    if not isinstance(skills, list) or not all(isinstance(s, str) for s in skills):
        raise ValueError(
            f"scenario {scenario}: steps.md frontmatter has no valid 'skills:' list"
        )
    return skills
