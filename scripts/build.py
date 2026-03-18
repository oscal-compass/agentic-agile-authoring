#!/usr/bin/env python3
"""
Build script: validates that each skill directory contains a SKILL.md.

Skills are now native Claude Code skills (skills/<name>/SKILL.md) and do not
require code generation. Run this script to verify the skills directory is
well-formed.

    python scripts/build.py
"""

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SKILLS_DIR = REPO_ROOT / "skills"

REQUIRED_FRONTMATTER_FIELDS = {"name", "description"}


def _parse_frontmatter(text: str) -> dict:
    """Extract YAML frontmatter fields (simple key: value parsing)."""
    fields = {}
    if not text.startswith("---"):
        return fields
    end = text.find("---", 3)
    if end == -1:
        return fields
    for line in text[3:end].splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


def main() -> None:
    skill_dirs = sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir())
    if not skill_dirs:
        print("No skill directories found in skills/")
        return

    errors = []
    for skill_dir in skill_dirs:
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            errors.append(f"  ✗ {skill_dir.name}/  — missing SKILL.md")
            continue
        content = skill_md.read_text(encoding="utf-8")
        fields = _parse_frontmatter(content)
        missing = REQUIRED_FRONTMATTER_FIELDS - fields.keys()
        if missing:
            errors.append(
                f"  ✗ {skill_dir.name}/SKILL.md — missing frontmatter: {', '.join(sorted(missing))}"
            )
        else:
            print(f"  ✓ {skill_dir.name}/SKILL.md  (name={fields['name']!r})")

    if errors:
        print("\nErrors:")
        for e in errors:
            print(e)
        raise SystemExit(1)

    print(f"\nValidated {len(skill_dirs)} skill(s).")


if __name__ == "__main__":
    main()
