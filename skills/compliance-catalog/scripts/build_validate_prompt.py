#!/usr/bin/env python3
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

"""Build a Phase 3 authoring prompt: write `validate.py` only.

Phase 3 runs AFTER Phase 2 has produced generate.py AND the orchestrator
has executed it. That means merged.txt, pages/, and a first-cut
catalog.json already exist on disk when this subagent starts. The
subagent uses them as ground truth for populating `validate.py`'s
CONFIG — especially `required_groups`, which requires knowing every
top-level group actually present in the extracted text.

Written to `<output_dir>/_validate_prompt.txt`. Path echoed to stdout.

Usage:
    python build_validate_prompt.py <output_dir> [--merged-head-lines 400]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


PROMPT_HEADER = """You are the Phase 3 authoring subagent for the compliance-catalog skill.

## What you produce (and only this)

Your single deliverable is ONE small file on disk:

  - <output_dir>/validate_config.py

That file contains one Python dict — `CONFIG` — with roughly 13 keys.
Total file size is ~60–90 lines. Nothing else.

You do NOT write, edit, or copy `validate.py` itself. `validate.py`
is a ~1,700-line body of rule functions maintained by the skill
template; the orchestrator has ALREADY placed a working copy at
`<output_dir>/validate.py` for you. Your job is only to populate the
small companion CONFIG file that `validate.py` will import at runtime.

Why the split matters: previous versions of this skill asked
subagents to rewrite the full 1,700-line validate.py. Under bob and
other harnesses, the LLM's output-token limit truncated the rewrite
partway through, leaving a broken validate.py with a SyntaxError.
This design makes that failure mode structurally impossible — the
file you touch is small enough to always fit in one response.

## What you MUST NOT touch

- validate.py itself (already correct on disk; leave it alone)
- generate.py (Phase 2's output, not yours)
- catalog.json (Phase 2's output — you read it, not write it)
- merged.txt (Phase 2's output)
- Any script under the skill's `scripts/` directory

If your harness offers a tool that would edit those files, do not
call it on them. Ever.

## Tool-name mapping (harness-agnostic)

Different harnesses expose the file / shell tools under different
names. Below, "your Read tool", "your Write tool", and "your Shell
tool" mean the ones in YOUR toolset with those semantics — do not
look for tools literally named `Read`/`Edit`. Common mappings:

  Read a file:      Read, read_file, view, str_replace_editor (view mode)
  Write a file:     Write, write_to_file, create_file, str_replace_editor
  Edit a file:      Edit, apply_diff, str_replace_editor, patch
  Run a shell cmd:  Bash, execute_command, run, shell

Because validate_config.py is small (~60–90 lines total), use your
write tool once to place the finished file. Do NOT split it across
multiple edit operations; one clean write is fewer moving parts.

## Paths for this run

- Output directory:                              {output_dir}
- Config file YOU write:                         {output_dir}/validate_config.py
- validate.py (ALREADY PLACED — do not edit):    {validate_py_path}
- generate.py (Phase 2 output, read-only):       {generate_py_path}
- catalog.json (Phase 2 output, read-only):      {catalog_json_path}
- merged.txt  (Phase 2 output, read-only):       {merged_txt_path}
- validate_config_template.py (shape reference): {val_config_template_path}
- validate_validate_py.py (final meta-check):    {vvpy_path}

merged.txt and catalog.json REALLY exist on disk right now — Phase 2
ran `python3 generate.py <pdf> <output_dir>` before finishing so you
have concrete artefacts to base your CONFIG on. Use them.

## Current catalog snapshot

The `generate.py` produced by Phase 2 has just been executed. Here is a
summary of what it extracted (source of truth for `required_groups`):

```
{catalog_summary}
```

If the summary shows 0 groups / 0 controls, the Phase 2 output is
broken — but that's not your problem to fix. Populate `required_groups`
with whatever you can enumerate from `{merged_txt_path}` (see the
excerpt below) and let the Phase 4 fix loop repair generate.py.

## Steps

1. Skim the group headers extracted so far (in the "Current catalog
   snapshot" above) AND the `{merged_txt_path}` group-header lines
   (excerpt below). Cross-reference: every group header in merged.txt
   should end up in `required_groups`, even if the current catalog is
   missing some — the missing ones are exactly what Phase 4 needs to
   detect via Rule 6a.

2. Read `{val_config_template_path}` to see the shape of the CONFIG
   dict you are producing. It is small (~60–90 lines) and contains
   exactly one top-level dict called `CONFIG` plus a module docstring.
   Do NOT copy this template file verbatim — write a fresh
   `validate_config.py` at `{output_dir}/validate_config.py` with the
   values filled in for THIS document.

   The file you write must be:
     - A module docstring (short) explaining "CONFIG for <doc name>".
     - One dict literal named `CONFIG` with the keys shown below.
     - Nothing else. No imports, no functions, no classes.

   CONFIG keys to populate:

   - `"name"`: same short identifier as generate.py's name.
   - `"expected_groups"`: LEAVE AS `None`. validate.py now auto-derives
     this from `len(required_groups) - len(excluded_units _groups)`;
     hand-setting it is the #1 cause of an unnecessary Fix Loop iter
     (the count drifts whenever the exclusion list changes). Only
     override for a genuinely exotic document where the derivation is
     wrong.
   - `"expected_controls_min"`, `"expected_controls_max"`: integers
     derived from the catalog snapshot above. If uncertain, leave as
     `None`.
   - `"required_sections"`: usually `[]` unless the PDF has a well-known
     list of top-level section titles you can enumerate from merged.txt.
   - `"required_groups"`: EVERY top-level group header enumerated from
     merged.txt. Leaving this empty triggers Rule 13. Under-populating
     it allows silent data loss.

     **What counts as a top-level group.** Only Part / Schedule /
     Chapter / Annex headings (or their all-caps variants). Never list
     Article / Section / Rule / Principle / Division / Paragraph here
     — those are the CONTROL level, i.e. items INSIDE a group.
     Populating `required_groups` with e.g. "Article 1" through
     "Article 99" for the GDPR is a well-known mistake that creates 99
     false Rule 6a errors and, combined with the same misconfiguration
     of `merged_text_group_patterns`, another 99 Rule 12 errors — a
     121-error explosion on iteration 1 that overwhelms the fix loop.

     **Include whole-group exclusions in this list.** If
     `excluded_units.json`'s `_groups` section declares a chapter/part
     as intentionally omitted from the catalog (e.g. GDPR's Chapter I
     "General provisions"), STILL list it here — Rule 6a and Rule 11
     now automatically cross-reference `excluded_units.json` and
     downgrade the resulting mismatch to INFO. Omitting a real
     top-level group from `required_groups` because it happens to be
     excluded hides the fact that the group existed in the source PDF
     at all, which weakens Rule 13's "you must enumerate every group"
     protection.

   - `"required_controls_in_groups"`: only for hierarchical documents
     (e.g. Principle N inside Schedule N). Default `{{}}`.
   - `"merged_text_group_patterns"`: leave as `None` (the default)
     unless you have **specifically verified** that this PDF places
     control-level units (Article / Section / Rule / …) at the top
     level with no enclosing Part/Chapter/Schedule. The module-level
     default (in validate.py's body) already covers Part / Schedule /
     Chapter / Annex in both mixed-case and all-caps variants.
     Overriding this incorrectly — especially by adding
     `r"^(Article)\\s+(\\d+)\\s*$"` — will make Rule 12 flag every
     Article as a "missing group", exactly the failure mode that
     motivated adding this CONFIG key.
   - `"skip_rule_3_sequential_order"`, `"skip_rule_10_sequential_gaps"`:
     leave `False` unless the PDF is known to have intentional
     numbering gaps (rare; Austria-DSG, NIST profiles, Colorado AI Act
     are the standard exceptions). The fix loop can flip these later
     based on evidence.
   - `"garbage_title_patterns"`, `"prose_contamination_patterns"`,
     `"prose_contamination_patterns_anywhere"`: default lists from the
     template are fine as a starting point. Add PDF-specific header /
     footer / running-title patterns if you see them in the merged.txt
     excerpt below and they would leak into control prose. See
     validate_config_template.py for examples.

   **What NOT to put in validate_config.py:**
   - Imports (`import`, `from`)
   - Functions, classes, `if __name__ == "__main__"` blocks
   - Any code besides the module docstring and the `CONFIG = {{ … }}`
     literal
   - Rule function bodies — those live in validate.py which the
     orchestrator has already placed on disk. Do not attempt to
     duplicate them here.

3. **Verify validate_config.py parses as Python.** Run:

       python3 -c "import ast; ast.parse(open('{output_dir}/validate_config.py').read())"

   Exit code MUST be 0. If it fails with a SyntaxError, one of the
   values in your dict is malformed (unterminated regex, unbalanced
   bracket). Fix it in THIS session.

4. **Verify validate.py can now import your CONFIG.** Run:

       python3 -c "import sys; sys.path.insert(0, '{output_dir}'); from validate_config import CONFIG; print('OK, keys=', sorted(CONFIG))"

   Exit code MUST be 0 and the output must list all expected keys
   including `name`, `required_groups`, `required_controls_in_groups`.
   If it fails, you either mis-named the dict or wrote code outside
   the dict literal — fix it.

5. **Smoke-run validate.py against the current catalog.json.** This
   is what the orchestrator does at the end of Phase 3, and if your
   CONFIG is malformed enough to break Rule 12 or Rule 6, this is
   where you catch it:

       python3 {output_dir}/validate.py {output_dir}/catalog.json --merged {output_dir}/merged.txt

   Two possible outcomes are ACCEPTABLE:

   - Exit code 0 (all rules passed on the first cut — rare but ideal).
   - Exit code 1 with a normal "OSCAL Catalog Validation Report" that
     ends in "❌ VALIDATION FAILED" / "N errors" (the rules found real
     issues in the catalog — that's the fix loop's job, not yours).

   The following outcome is UNACCEPTABLE and means YOUR CONFIG is
   broken (validate.py itself is not — it is skill-managed and known
   good). You must fix it in this session before printing "DONE":

   - Python traceback (`Traceback (most recent call last):`) anywhere
     in the output → CONFIG has a value of the wrong type. Read the
     traceback, find the CONFIG key it complains about, fix that key.

   The report header MUST look like:

       ======================================================================
       OSCAL Catalog Validation Report
       ======================================================================
       Catalog: ...

       Statistics:
         ...

   If this header is missing entirely, the `from validate_config import
   CONFIG` line in validate.py failed. Re-run Step 4 and fix.

6. **Run the 17-rule meta-check on validate.py.** This is a sanity
   check on the ORCHESTRATOR's copy of validate.py — you did not
   change it, so this should pass unconditionally. Run once to
   confirm:

       python3 {vvpy_path} {output_dir}/validate.py

   Exit code MUST be 0. If it fails, the orchestrator's copy of
   validate.py is out of date — report this in your "DONE" message
   with the exit-code output. Do NOT try to repair validate.py
   yourself; the orchestrator will re-copy it.

7. Print "DONE" on its own line and stop.

## Anti-hallucination principle (must-obey)

You do NOT invent required_groups from thin air. Every entry must
correspond to a group header actually present in `merged.txt`. If you
can't verify a group exists in the source, don't add it.

## merged.txt — first {merged_head_lines} lines and group-header scan

```text
{merged_head}
```

Group-header lines detected in `merged.txt` (grepped for common patterns
like `Part N`, `Schedule N`, `Chapter N`, `PART N`, `SCHEDULE N`,
`CHAPTER N`, `Annex N`, and their case variants):

```
{group_headers}
```

Use this as the definitive list of groups when populating `required_groups`.
"""


def _read_text(path: Path, max_lines: int | None = None) -> str:
    if not path.is_file():
        return "(file not found)"
    with path.open("r", encoding="utf-8", errors="replace") as f:
        if max_lines is None:
            return f.read()
        lines = []
        for i, line in enumerate(f):
            if i >= max_lines:
                break
            lines.append(line)
        return "".join(lines)


def _summarise_catalog(catalog_path: Path) -> str:
    if not catalog_path.is_file():
        return "(catalog.json does not exist yet — generate.py may not have run)"
    try:
        c = json.loads(catalog_path.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:
        return f"(catalog.json is not valid JSON: {e})"
    cat = c.get("catalog", {}) or {}
    groups = cat.get("groups", []) or []
    top_controls = cat.get("controls", []) or []
    total_controls = sum(len(g.get("controls") or []) for g in groups) + len(top_controls)
    if len(groups) == 0 or total_controls == 0:
        return (
            f"!! WARNING: catalog.json is structurally empty "
            f"(groups={len(groups)}, total_controls={total_controls}). "
            f"This means Phase 2's generate.py extracted nothing usable — "
            f"the orchestrator should have re-authored generate.py before "
            f"reaching Phase 3. If you're seeing this, treat `required_groups` "
            f"as unfillable from the current catalog; instead scan the "
            f"merged.txt group-header excerpt below and enumerate every "
            f"top-level heading you see there. Do NOT populate `required_groups` "
            f"with fabricated entries."
        )
    groups = cat.get("groups", []) or []
    top_controls = cat.get("controls", []) or []
    total_controls = sum(len(g.get("controls", []) or []) for g in groups) + len(top_controls)
    lines = [
        f"groups: {len(groups)}",
        f"total controls: {total_controls}",
        f"top-level controls (not in a group): {len(top_controls)}",
        "",
        "groups:",
    ]
    for g in groups[:30]:
        gid = g.get("id", "?")
        title = (g.get("title", "") or "")[:70]
        nctrls = len(g.get("controls", []) or [])
        lines.append(f"  - id={gid!r}  title={title!r}  controls={nctrls}")
    if len(groups) > 30:
        lines.append(f"  ... and {len(groups) - 30} more")
    return "\n".join(lines)


def _scan_group_headers(merged_path: Path) -> str:
    if not merged_path.is_file():
        return "(merged.txt does not exist)"
    # Patterns intentionally restricted to TOP-LEVEL group headings only
    # (Part / Schedule / Chapter / Annex). These match the default in
    # validate_template.py's MERGED_TEXT_GROUP_PATTERNS_DEFAULT.
    #
    # Do NOT add "Article N" / "Section N" / "Rule N" / "Division N"
    # here — those are control-level headings and Rule 12 will emit a
    # false-positive error for every one of them when the catalog is
    # correctly extracted with Articles/Sections as controls. See the
    # comment on MERGED_TEXT_GROUP_PATTERNS_DEFAULT in the template for
    # the full rationale.
    import re

    patterns = [
        r"^(Part)\s+(\d+[A-Za-z]?)\s*$",
        r"^(Schedule)\s+(\d+)\s*$",
        r"^(Chapter)\s+([IVXLCDM]+|\d+)\s*$",
        r"^(PART)\s+(\d+[A-Za-z]?)\s*$",
        r"^(SCHEDULE)\s+(\d+)\s*$",
        r"^(CHAPTER)\s+([IVXLCDM]+|\d+)\s*$",
        r"^(Annex)\s+([A-Z]|\d+)\s*$",
        r"^(ANNEX)\s+([A-Z]|\d+)\s*$",
    ]
    found: list[str] = []
    with merged_path.open("r", encoding="utf-8", errors="replace") as f:
        for line_no, line in enumerate(f, start=1):
            stripped = line.rstrip()
            for p in patterns:
                if re.match(p, stripped):
                    found.append(f"line {line_no:>5}: {stripped}")
                    break
    if not found:
        return "(no group-header lines detected by the standard patterns)"
    if len(found) > 40:
        return "\n".join(found[:40]) + f"\n... and {len(found) - 40} more"
    return "\n".join(found)


def build_prompt(output_dir: Path, merged_head_lines: int) -> str:
    generate_py = output_dir / "generate.py"
    catalog_json = output_dir / "catalog.json"
    merged_txt = output_dir / "merged.txt"

    catalog_summary = _summarise_catalog(catalog_json)
    group_headers = _scan_group_headers(merged_txt)
    merged_head = _read_text(merged_txt, max_lines=merged_head_lines)

    subs = {
        "{output_dir}": str(output_dir),
        "{generate_py_path}": str(generate_py),
        "{catalog_json_path}": str(catalog_json),
        "{merged_txt_path}": str(merged_txt),
        "{validate_py_path}": str(output_dir / "validate.py"),
        "{val_config_template_path}": str(SCRIPT_DIR / "validate_config_template.py"),
        "{vvpy_path}": str(SCRIPT_DIR / "validate_validate_py.py"),
        "{catalog_summary}": catalog_summary,
        "{group_headers}": group_headers,
        "{merged_head_lines}": str(merged_head_lines),
        "{merged_head}": merged_head,
    }
    out = PROMPT_HEADER
    for k, v in subs.items():
        out = out.replace(k, v)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path, help="Output directory (must exist)")
    parser.add_argument(
        "--merged-head-lines",
        type=int,
        default=400,
        help="Number of lines from merged.txt to embed (default: 400)",
    )
    args = parser.parse_args()

    if not args.output_dir.is_dir():
        print(f"ERROR: output_dir does not exist: {args.output_dir}", file=sys.stderr)
        return 1

    prompt = build_prompt(args.output_dir, args.merged_head_lines)
    out_path = args.output_dir / "_validate_prompt.txt"
    out_path.write_text(prompt, encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
