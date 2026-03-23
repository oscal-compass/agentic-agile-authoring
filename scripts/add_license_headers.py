#!/usr/bin/env python3
"""Add license headers to source files.

- Python files (.py)       : prepend Apache 2.0 comment block
- YAML files (.yaml/.yml)  : prepend Apache 2.0 comment block
- SKILL.md files           : add 'license' field to frontmatter + copy LICENSE
"""

import re
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

PYTHON_HEADER = """\
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
"""

EXCLUDE_DIRS = {".venv", ".git", "dist", "__pycache__"}
EXCLUDE_FILES = {".pre-commit-config.yaml"}


def _already_has_header(text: str) -> bool:
    return "Apache License" in text or "Copyright" in text


def add_comment_header(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if _already_has_header(text):
        print(f"  skip (already has header): {path.relative_to(REPO_ROOT)}")
        return
    path.write_text(PYTHON_HEADER + "\n" + text, encoding="utf-8")
    print(f"  ✓ {path.relative_to(REPO_ROOT)}")


def add_skill_license(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "license:" in text:
        print(f"  skip (already has license field): {path.relative_to(REPO_ROOT)}")
    else:
        # Insert license field before closing ---
        updated = re.sub(
            r"^(---\n(?:(?!---).)*?)(---)",
            r"\1license: Complete terms in LICENSE.txt\n---",
            text,
            count=1,
            flags=re.DOTALL,
        )
        path.write_text(updated, encoding="utf-8")
        print(f"  ✓ {path.relative_to(REPO_ROOT)}")

    # Copy LICENSE into the skill directory
    license_dst = path.parent / "LICENSE.txt"
    if not license_dst.exists():
        shutil.copy(REPO_ROOT / "LICENSE", license_dst)
        print(f"  ✓ {license_dst.relative_to(REPO_ROOT)}")
    else:
        print(f"  skip (LICENSE.txt exists): {license_dst.relative_to(REPO_ROOT)}")


def iter_files(pattern: str):
    for path in REPO_ROOT.rglob(pattern):
        if any(excluded in path.parts for excluded in EXCLUDE_DIRS):
            continue
        if path.name in EXCLUDE_FILES:
            continue
        yield path


def main() -> None:
    print("=== Python files ===")
    for path in sorted(iter_files("*.py")):
        add_comment_header(path)

    print("\n=== YAML files ===")
    for path in sorted(list(iter_files("*.yaml")) + list(iter_files("*.yml"))):
        add_comment_header(path)

    print("\n=== SKILL.md files ===")
    for path in sorted(iter_files("SKILL.md")):
        add_skill_license(path)


if __name__ == "__main__":
    main()
