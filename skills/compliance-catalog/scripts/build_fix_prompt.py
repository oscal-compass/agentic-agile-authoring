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

"""Build a Phase 4 fix-loop prompt for a per-iteration subagent.

Design principle: the prompt is INSTRUCTIONS + file paths + a small
merged.txt slice around failing rules. The subagent uses Read to pull
in `generate.py` / `validate.py` when it needs them. This keeps the
prompt small (a few KB) so the subagent's input tokens stay reasonable
across an entire fix iteration.

Written to `<output_dir>/_fix_prompt_<iter>.txt`. Path is echoed to stdout.

Usage:
    python build_fix_prompt.py <output_dir> <iteration_n> \
        --input-pdf <path_to_source.pdf> \
        --validate-output <path_to_last_validate_output.txt> \
        [--merged-context-lines 40] \
        [--prev-validate-output <path_to_iter_N-1_validate.txt>]

The `--prev-validate-output` flag enables per-iteration diff summaries
so the fix subagent can see what changed since the previous iteration.
Recommended: point it at `<output_dir>/_validate_${ITER-1}.txt`.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


PROMPT_HEADER = """You are the fix-loop subagent for the compliance-catalog skill.
Iteration: {iter_n}

The orchestrator just ran `python validate.py catalog.json --merged
merged.txt` and got a non-zero exit code. Your job is to make measurable
progress on at least one failing rule and hand the next iteration a
strictly-better catalog. Concretely, that means all of the following
happen in THIS session before you print "DONE":

  1. Edit EXACTLY ONE of these two files (never both in one iteration —
     see the rule-to-file mapping below):
       - `generate.py`         — extraction script; fixes catalog content
       - `validate_config.py`  — small CONFIG dict imported by
                                 validate.py; fixes validator settings
     You must NOT edit `validate.py` itself. It is a ~1,700-line body
     of rule functions maintained by the skill template and placed on
     disk by the orchestrator. Editing it directly is how past runs
     produced truncated / broken validate.py files that made the next
     iteration unusable. If you think a rule function has a real bug,
     say so in your DONE message so the orchestrator can escalate — do
     not attempt to repair validate.py yourself.

  2. Re-run the modified script yourself.
     - Edited generate.py? Re-run `python3 generate.py <pdf> <output_dir>`
       to regenerate `catalog.json`.
     - Edited validate_config.py only? Skip the generate step.
  3. Re-run `python3 validate.py catalog.json --merged merged.txt`
     yourself and confirm the failure signature has changed (fewer
     errors, or the same count but a different failing rule).
  4. If your edit produced a syntax error, a Python exception, or made
     things strictly worse (more errors than before, or `catalog.json`
     dropped to `groups=0` / `controls=0`), you MUST revert or fix it
     in THIS session. Do NOT hand a regression to the next iteration.

Only after 1–4 all succeed, print "DONE" on its own line and stop.

## Tool-name mapping (harness-agnostic)

Different harnesses expose the file / shell tools under different
names. Below, "your Read tool", "your Write tool", "your Edit tool",
and "your Shell tool" mean the ones in YOUR toolset with those
semantics — do not look for tools literally named `Read`/`Edit`. Common
mappings you may see:

  Read a file:      Read, read_file, view, str_replace_editor (view mode)
  Write a file:     Write, write_to_file, create_file, str_replace_editor
  Edit a file:      Edit, apply_diff, str_replace_editor, patch
  Run a shell cmd:  Bash, execute_command, run, shell

Use whichever your harness exposes. What matters is the effect on disk,
not the tool name.

To keep your context small:
- Prefer targeted edits over whole-file rewrites. Only rewrite the whole
  file if the diff would be larger than half the file.
- When you read `generate.py` / `validate.py`, prefer targeted line
  ranges over reading the whole file at once.
- Never read `merged.txt` in one shot — it can be hundreds of KB.
  Instead: (a) rely on the slice already embedded below, or (b) use
  your shell tool with `grep -n <pattern> merged.txt | head` /
  `sed -n 'START,ENDp'` to fetch just the lines you need.

## Paths for this run

- Output directory:                                {output_dir}
- Input PDF (for re-running generate.py):          {input_pdf_path}
- Current generate.py:                             {generate_py_path}
- Current validate_config.py (edit ME if needed):  {validate_config_py_path}
- validate.py (READ-ONLY — do not edit):           {validate_py_path}
- Last validate.py output:                         {validate_output_path}
- merged.txt (full source):                        {merged_txt_path}

## Anti-hallucination principle (must-obey)

Rewriting `PATTERNS["chapter"]`, `PATTERNS["section"]`,
`PATTERNS["nested_control"]`, or `parse_structure()` to fit this
document's actual structure is required work. That is NOT hallucination.

Adding static lookup tables like `PART_TITLES = {...}` IS hallucination
and is forbidden. All titles come from PDF text via regex capture only.

If a title looks wrong in `catalog.json`, the fix is in `parse_structure()`
or `PATTERNS`, not in the JSON itself. Do NOT edit `catalog.json` by hand.

## Do not give up

If the failure looks like it needs a "custom parser" or the "template
can't handle this document", that is wrong. Every PDF's structure is
expressible as some combination of regex + `parse_structure()` logic.
Read the merged.txt slice below, look at how the failing IDs actually
appear in the source, and adjust the regex or the parse logic. That is
the intended work of this loop.

## Control ID naming — invariants you MUST preserve

Before changing anything, verify that `generate.py` produces control IDs
in the form `<prefix>-<article-number>`, e.g. `eu-gdpr-1`, `hk-pdpo-30`,
`nist-800-53-ac-2`.

**If the current `generate.py` produces slug IDs like `gdpr-chapter-i-def-initions`
or `gdpr-chapter-vii-mutual-assist-ance`, that is a critical bug — even if
`validate.py` isn't complaining about it.** The rule that catches this
(Rule 10 numeric-continuity) is neutered by slug IDs, so validation stays
green on top of a broken extraction. Your first priority is to restore
`PATTERNS["section"]` to something that matches bare `Article N` /
`Section N` / `Rule N` lines and captures the number, and rebuild
`generate_control_id()` to use that captured number.

Do NOT "fix" slug IDs by rewriting `generate_control_id()` to sanitize
the slug better — the slug approach itself is wrong. The correct
control ID for GDPR Article 5 is `eu-gdpr-5`, not
`eu-gdpr-principles-relating-to-processing-of-personal-data`.

## Common failure-mode reference (consult if relevant)

- **Broken word spacing** (`"Gener al"`, `"f or"`): pypdf kerning issue.
  Fix: set `CONFIG["use_pdfplumber"] = True` in generate.py. Never turn
  this off — pdfplumber is strictly better than pypdf on every compliance
  PDF tested.
  DO NOT add wildcard regexes like `r'\\b([a-z]+)\\s+([a-z]+)\\b'` →
  `r'\\1\\2'` to `postprocess_text` — they will collapse every legitimate
  space between words and destroy the extraction. Only per-word literal
  fixes are safe (and even those are usually unnecessary once
  pdfplumber is on).

- **Whitespace regex catastrophes in `postprocess_text`** — this is the
  single most destructive class of edit we have seen in the fix loop.
  It always drops the catalog to `control_count=0` and looks harmless
  at first glance.

    **FORBIDDEN** — never write these in `postprocess_text` or anywhere
    that touches merged.txt as a single string:

        re.sub(r'\\s+', ' ', text)      # \\s matches \\n — kills line boundaries
        re.sub(r'\\s+', '', text)       # even worse
        re.sub(r'[\\s\\n]+', ' ', text)  # same failure, explicitly
        re.sub(r'.', '', text, flags=re.S)  # obvious but sometimes tried
        text.replace('\\n', ' ')         # also destroys parse_structure input

    Any of the above turns multi-line merged.txt into a single line;
    `parse_structure()` matches `^Article \\d+$` line-by-line and
    silently produces zero controls when line boundaries are gone.

    **ALLOWED** — safe whitespace tidying that preserves newlines:

        re.sub(r' +', ' ', text)         # runs of spaces only
        re.sub(r'[ \\t]+', ' ', text)     # spaces + tabs only
        re.sub(r'\\n{3,}', '\\n\\n', text)  # collapse triple+ blank lines

    Rule of thumb: if the regex character class in your `re.sub` can
    match `\\n`, and the replacement removes that `\\n`, you are
    destroying merged.txt structure. Add `\\n` to a negative character
    class (`[^\\n]`) or restrict to explicit space/tab.
- **Empty or short titles**: `garbage_line_patterns` filtering out
  legitimate short titles. Loosen the pattern (e.g., `^.{0,5}$` →
  `^.{0,2}$`).
- **Multi-line title not merged**: check `parse_structure()`'s
  title-continuation logic — the template handles preposition/article
  endings and lowercase continuation; document-specific stop conditions
  may be needed.
- **Number-only headings** (e.g. `1.1` followed by prose that gets
  absorbed into the title, causing Rule 15 "newline in title"):
  in `parse_structure()`, use the section number itself as the title
  (`section_title = f"Section {section_num}"`) and skip continuation
  lines for this document's number-only sections.
- **Title contamination** (Division names, reference markers like
  `[ss. 30(1)(d) & 71]` sneaking into a Part/Schedule title): in
  `parse_structure()`, when collecting multi-line titles, break on
  `Division \\d+` and skip lines starting with `[`.
- **`PATTERNS["chapter"]` capturing in-prose cross-references**
  (e.g. matching "Chapter VII, a body …" inside a paragraph and creating
  a phantom group). Fix: make the chapter regex require a **bare** line
  — nothing but the numeral after the keyword:
  `r'^(CHAPTER|Chapter)\\s+([IVXLCDM]+|\\d+)()\\s*$'`. The title comes
  from the NEXT line via the multi-line title extractor. Same principle
  for section: `r'^(?:Article|ARTICLE)\\s+(\\d+)()\\s*$'`.
- **`toc_line_patterns` over-matching**: DO NOT add a generic
  `r'\\s+\\d{1,3}\\s*$'` (trailing page number) pattern to
  `toc_line_patterns` — it silently drops legitimate headings like
  `"CHAPTER II 35"` or article title lines that happen to end in a
  number. Restrict `toc_line_patterns` to explicit dot-leader markers
  (`r'\\.{3,}'`, `r'……'`, `r'…{2,}'`). If a document has no formal
  TOC, leave `toc_line_patterns` nearly empty.
- **Rule 10 intentional vs bug**: look at the merged.txt slice for the
  "missing" IDs. If they exist in merged.txt → extraction bug, fix
  regex. If they don't → intentional gap, set
  `"skip_rule_10_sequential_gaps": True` in `validate_config.py` with
  a comment explaining why.
- **Iteration is making things worse (regression)**: if the current
  catalog has more `duplicate_ids` / `missing_controls` / `content_issues`
  than the previous iteration, or `control_count` swings wildly (0 → 128
  → 115 …), the last edit was harmful. Instead of layering another
  regex on top, look at the previous iteration's `_validate_${N-1}.txt`
  and revert to that state as the starting point, then make a smaller
  change.

## Progress since the previous iteration

{prev_diff_block}

## Missing-group evidence (Rule 12 / Rule 6a)

{missing_group_evidence}

## Last validate.py output (this is what you're fixing)

Read the FIX_GUIDANCE block of each failing rule below — each guidance
line names the specific function in `generate.py` (or CONFIG key in
`validate.py`) to touch.

```
{validate_output}
```

## merged.txt slice — lines around the failing IDs

The following excerpt was auto-selected around identifiers mentioned in
the validate output. Use it to see how the source PDF actually formats
those items. If you need a different range, `grep -n` / `sed -n` on
`{merged_txt_path}` from Bash.

```text
{merged_context}
```

## Which file to edit — STRICT rule-to-file mapping

Failing rules map to exactly ONE file to edit. Do not "improve both to
be safe" — one iteration, one file. If you disagree with the mapping
below because you think a rule needs the other file, that is a signal
you have misdiagnosed; re-read the failing rule and the merged.txt
slice below before touching a file.

**Rules that mean "edit generate.py" (extraction bug):**

- Rule 1  (duplicate IDs)               → `parse_structure()` or `generate_control_id()`
- Rule 2  (empty lists)                 → `parse_structure()` — a group has no controls
- Rule 3  (numeric sort)                → `emit_oscal()` / sort key
- Rule 4  (duplicate group IDs)         → `generate_group_id()` or `parse_structure()`
- Rule 5  (title contamination)         → title-continuation logic in `parse_structure()`
- Rule 7  (garbage content in prose)    → `postprocess_text` / `garbage_line_patterns`
- Rule 8  (balanced structure)          → `parse_structure()` group/control association
- Rule 9  (OSCAL required fields)       → `emit_oscal()`
- Rule 10 (sequential gaps)             → `PATTERNS["section"]` in generate.py (if the ID is really in the PDF); OR set `"skip_rule_10_sequential_gaps": True` in **validate_config.py** if the gap is intentional
- Rule 14 (prose contamination)         → `page_number_patterns` or `postprocess_text` in generate.py
- Rule 15 (NCName / newline in title)   → `generate_control_id()`, `generate_group_id()`, or title assembly in generate.py
- Rule 17 (props missing ns)            → `emit_oscal()` — add `ns` to non-standard props

**Rules that mean "edit validate_config.py" (validator under-specified):**

Remember: you edit `validate_config.py` — the small CONFIG-only file
next to validate.py. You NEVER edit validate.py itself.

- Rule 6  (required sections missing)         → add missing IDs to `CONFIG["required_groups"]` in validate_config.py
- Rule 6a (required group missing entirely)   → **if the group exists in merged.txt, this is a generate.py bug — fix `PATTERNS["chapter"]` in generate.py.** If merged.txt truly does not contain the group, then remove it from `CONFIG["required_groups"]` in validate_config.py.
- Rule 6b (required control missing in group) → add to `CONFIG["required_controls_in_groups"]` in validate_config.py; **do NOT change `parse_structure()` to make the missing control appear**. That is how iteration 2 of past runs destroyed the extraction (article-as-group / chapter-flattened rewrites). The `required_controls_in_groups` CONFIG is exactly the knob for expressing hierarchical expectations.
- Rule 12 (groups in merged.txt but not catalog) → fix `PATTERNS["chapter"]` in generate.py (this is the "extraction under-matched" side of Rule 6a)
- Rule 13 (`required_groups` empty)             → populate `CONFIG["required_groups"]` in validate_config.py

**Rule 16 (trestle fails)**: usually reduces to a Rule 15 issue
underneath. Look at the trestle error — if it names NCName / newline /
special-char, fix in generate.py.

**Anti-pattern from past runs (DO NOT REPEAT):**

Rule 6b failures ("chapter X is missing required control Y") in past
runs have been mis-diagnosed as "the chapter/article hierarchy in
generate.py is wrong". A subagent then rewrites `parse_structure()` to
make Articles into groups (or Chapters into controls), destroying the
correct 2-level hierarchy. **This is always wrong.** The correct 2-level
structure is: top-level groups = Chapters/Parts/Schedules; controls
inside those groups = Articles/Sections/Rules. If Rule 6b reports a
mismatch, populate `CONFIG["required_controls_in_groups"]` in
validate_config.py — that is the knob, not `parse_structure()`.

**Do NOT set a list-valued CONFIG key to `None`.** If you want to
disable a pattern-list check like `prose_contamination_patterns` or
`prose_contamination_patterns_anywhere`, set the value to `[]` (empty
list) — never `None`. Some rule functions iterate over these lists
directly, and `None` crashes them with `TypeError: 'NoneType' object
is not iterable`. That crash looks like a normal validation failure
at the exit-code level but is actually a bug in validate_config.py,
and the outer main agent has been observed to loop 6+ iterations
trying to "fix" it while every subagent inherits the broken config.
Observed 2026-07-23. Applies to at minimum:
`prose_contamination_patterns`, `prose_contamination_patterns_anywhere`,
`garbage_title_patterns`. When in doubt, leave the existing list value
alone.

## Required workflow for this iteration

1. **Diagnose.** Read the "Last validate.py output" below. Identify ONE
   failing rule to attack this iteration (start with the most-impactful:
   Rule 6a > 12 > 15 > 6b > 14 > 5 > 7 > others). Note the count of
   errors for that rule so you can measure progress in step 5.

2. **Locate.** Using the rule-to-file mapping above, decide whether to
   edit `generate.py` or `validate_config.py`. Read only the specific
   function or CONFIG key you plan to touch (targeted line range, not
   the whole file). Never open `validate.py` itself for editing —
   it's read-only for this iteration and you should not need to
   consult it beyond what its output already told you.

3. **Edit.** Make the smallest change that plausibly fixes the chosen
   rule. Do NOT bundle "while I'm here" changes to other functions; a
   focused edit is easier to verify and easier to revert if it
   regresses.

4. **Re-run scripts YOURSELF (mandatory).** In THIS session, run:

   If you edited `generate.py`:

       python3 -c "import ast; ast.parse(open('{generate_py_path}').read())"
       python3 {generate_py_path} {input_pdf_path} {output_dir}
       python3 {validate_py_path} {output_dir}/catalog.json --merged {output_dir}/merged.txt

   If you edited only `validate_config.py`:

       python3 -c "import ast; ast.parse(open('{validate_config_py_path}').read())"
       python3 -c "import sys; sys.path.insert(0, '{output_dir}'); from validate_config import CONFIG; print('OK')"
       python3 {validate_py_path} {output_dir}/catalog.json --merged {output_dir}/merged.txt

   Both syntax / import checks MUST exit 0. If they don't, revert your
   edit and try again — a syntactically-broken generate.py OR
   validate_config.py means the next iteration inherits nothing to
   work with, which is worse than this iteration accomplishing
   nothing.

5. **Verify progress.** Compare the new validate output against the
   input (the "Last validate.py output" block below):

   Acceptable outcomes (print "DONE"):
   - Total ERROR count strictly decreased, OR
   - Same total but the target rule you chose has fewer errors (some
     other rule may now show up more prominently — that's fine).

   Unacceptable outcomes (KEEP FIXING in this session):
   - `catalog.json` dropped to `groups=0` or `controls=0`.
     → Your edit broke the extraction. Revert it and choose a different
       approach. Never let the next iteration inherit an empty catalog.
   - Total ERROR count went UP, or a new critical rule (Rule 1 dup IDs,
     Rule 9 OSCAL missing fields, Rule 15 NCName violations) appeared
     that wasn't there before.
     → Revert the edit and try a smaller, more targeted change.
   - validate.py or generate.py now raises a Python exception.
     → Revert or fix the syntax; never leave broken code for the next
       iteration.
   - The failure signature is byte-identical to the input (nothing
     changed). → Your edit didn't take effect. Check that the edit
     actually landed in the right file, and that you re-ran the right
     script.

6. Print "DONE" on its own line and stop.

## Absolute prohibitions for this iteration

- **NEVER edit `validate.py` itself.** It is a ~1,700-line rule body
  maintained by the skill template and placed on disk by the
  orchestrator. Every past attempt by a subagent to rewrite it (via
  write_to_file / apply_diff / patch on validate.py) has produced a
  truncated / broken file at the LLM's output-token limit, wasting
  the entire iteration and often several after it. If a genuine
  bug in a rule function seems to be the cause of a failure, say so
  in your DONE message so the orchestrator can escalate. Your CONFIG
  file (`validate_config.py`) is the correct knob for every rule
  behaviour you need to influence.
- **NEVER edit `catalog.json` by hand.** It is regenerated from
  `generate.py`; hand-edits are lost on the next `generate.py` run and
  are a form of hallucination.
- **NEVER "fix" a rule by disabling it** (adding a `skip_rule_*` flag
  to validate_config.py) unless the flag is explicitly documented in
  `validate_config_template.py` as skippable AND there is genuine
  evidence from `merged.txt` that the rule's expectation doesn't
  apply to this PDF. Silencing a rule to make the run go green is
  the second-worst outcome; the worst is hallucinated content.
- **NEVER rewrite `parse_structure()` wholesale.** The template's
  2-level structure (Chapter/Part/Schedule → Article/Section/Rule) is
  correct for essentially every compliance PDF. If a rule seems to
  require inverting the hierarchy, you have mis-diagnosed — re-read
  the rule-to-file mapping above.
- **NEVER hand a regression to the next iteration.** Iteration N+1
  can only refine; it cannot recover from an empty catalog or a
  syntax error N introduced.
"""


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def _extract_context_keywords(validate_output: str) -> list[str]:
    """Pull likely control/group IDs and names out of validate.py's
    error text so we can slice merged.txt around them."""
    keywords: list[str] = []
    for m in re.findall(r"['\"`]([^'\"`\n]{2,80})['\"`]", validate_output):
        keywords.append(m.strip())
    for m in re.findall(r"\b([a-z][a-z0-9]*(?:-[a-z0-9]+){1,6})\b", validate_output):
        keywords.append(m)
    for m in re.findall(
        r"\b((?:Part|Schedule|Chapter|Article|Annex|Division)\s+[0-9IVXLCDMA-Za-z]+)\b",
        validate_output,
    ):
        keywords.append(m)
    seen: set[str] = set()
    out: list[str] = []
    for k in keywords:
        if k not in seen and len(k) >= 2:
            seen.add(k)
            out.append(k)
    return out[:20]


def _slice_merged(
    merged_path: Path,
    keywords: list[str],
    context_lines: int,
    max_slices: int = 8,
    max_total_lines: int = 400,
) -> str:
    if not merged_path.is_file():
        return "(merged.txt not found)"
    lines = merged_path.read_text(encoding="utf-8", errors="replace").splitlines()
    hits: list[tuple[int, str]] = []
    used_kw: set[str] = set()
    for kw in keywords:
        if kw in used_kw:
            continue
        for i, ln in enumerate(lines):
            if kw in ln:
                hits.append((i, kw))
                used_kw.add(kw)
                break
        if len(hits) >= max_slices:
            break

    if not hits:
        return (
            "\n".join(lines[:200])
            + "\n\n(no keyword matches; showing head of merged.txt)"
        )

    half = max(1, context_lines // 2)
    slices: list[tuple[int, int, str]] = []
    for idx, kw in hits:
        start = max(0, idx - half)
        end = min(len(lines), idx + half + 1)
        slices.append((start, end, kw))
    slices.sort()
    merged: list[tuple[int, int, list[str]]] = []
    for start, end, kw in slices:
        if merged and start <= merged[-1][1] + 2:
            prev_start, prev_end, prev_kws = merged[-1]
            merged[-1] = (prev_start, max(prev_end, end), prev_kws + [kw])
        else:
            merged.append((start, end, [kw]))

    out_lines: list[str] = []
    total = 0
    for start, end, kws in merged:
        if total >= max_total_lines:
            out_lines.append("... (truncated to keep prompt size manageable)")
            break
        header = (
            f"--- merged.txt lines {start + 1}-{end} "
            f"(matched: {', '.join(kws)}) ---"
        )
        out_lines.append(header)
        chunk = lines[start:end]
        take = min(len(chunk), max_total_lines - total)
        out_lines.extend(chunk[:take])
        total += take
        out_lines.append("...")
    return "\n".join(out_lines)


def _extract_missing_group_names(validate_output: str) -> list[str]:
    """Pull out group headers Rule 12 / Rule 6a reported as missing.

    Rule 12's output shape is:
        [Rule 12]   - 'Part 5' exists in merged.txt but not in catalog

    Rule 6a is similar but reports whole categories:
        [Rule 6a]   - Missing required group: 'Chapter III'

    We return the raw header strings (e.g. "Part 5", "Chapter III"),
    deduplicated but order-preserving, so the caller can grep for each
    one in merged.txt to show the fix subagent what the source actually
    contains around that header. The evidence turns "your regex missed
    Part 5" from an assertion into a proof.
    """
    names: list[str] = []
    seen: set[str] = set()
    patterns = [
        # Rule 12: "'X' exists in merged.txt but not in catalog"
        re.compile(
            r"\[Rule\s+12\][^\n]*?['\"`]([^'\"`\n]{2,80})['\"`]"
            r"[^\n]*?exists in merged\.txt",
            re.IGNORECASE,
        ),
        # Rule 6a: "Missing required group: 'X'"
        re.compile(
            r"\[Rule\s+6a\][^\n]*?['\"`]([^'\"`\n]{2,80})['\"`]",
            re.IGNORECASE,
        ),
    ]
    for pat in patterns:
        for m in pat.finditer(validate_output):
            name = m.group(1).strip()
            if name and name not in seen:
                seen.add(name)
                names.append(name)
    return names


def _grep_missing_group_evidence(
    merged_path: Path,
    group_names: list[str],
    context_lines: int = 3,
    max_headers: int = 20,
) -> str:
    """For each missing group header, show where (or whether) it
    actually appears in merged.txt.

    The fix subagent's job on Rule 12 / Rule 6a failures is to fix
    `PATTERNS["chapter"]` in generate.py. It cannot do that well if it
    has to trust the validator's word that "Part 5" is there — showing
    the concrete line lets it match its regex against the actual bytes.

    Output is a bounded, self-labelled block. If a header is NOT found
    in merged.txt at all, that too is signal (Rule 12 is now wrong, or
    the header string has drifted — either way the subagent needs to
    know).
    """
    if not group_names:
        return (
            "(No Rule 12 / Rule 6a errors in the current output — "
            "skip this section.)"
        )
    if not merged_path.is_file():
        return f"(merged.txt not found at {merged_path})"

    lines = merged_path.read_text(encoding="utf-8", errors="replace").splitlines()
    out: list[str] = []
    for name in group_names[:max_headers]:
        # Case-insensitive substring match; anchored to start of line to
        # avoid false positives from in-prose cross-references like
        # "under Chapter III of this Act".
        pat = re.compile(rf"^\s*{re.escape(name)}\b", re.IGNORECASE)
        hits: list[int] = [i for i, ln in enumerate(lines) if pat.search(ln)]
        if not hits:
            out.append(f"### {name}")
            out.append(
                f"NOT FOUND in merged.txt via `^\\s*{name}\\b` — either "
                f"the header is spelled differently in the PDF text, or "
                f"Rule 12 is stale."
            )
            out.append("")
            continue
        # Show the FIRST occurrence with a few lines of context; that's
        # the group header, and it's almost always what PATTERNS["chapter"]
        # needs to match.
        idx = hits[0]
        start = max(0, idx - context_lines)
        end = min(len(lines), idx + context_lines + 1)
        out.append(f"### {name}")
        out.append(f"merged.txt line {idx + 1} (first of {len(hits)} match(es)):")
        out.append("```text")
        for i in range(start, end):
            marker = ">> " if i == idx else "   "
            out.append(f"{marker}{i + 1:5d}: {lines[i]}")
        out.append("```")
        out.append("")
    return "\n".join(out) if out else "(no evidence collected)"


def _extract_error_stats(validate_output: str) -> dict[str, object]:
    """Pull the ERROR count and per-rule breakdown from a validate.py
    report. Returns {} if the shape doesn't match."""
    stats: dict[str, object] = {}
    m = re.search(r"ERRORS \((\d+)\):", validate_output)
    if m:
        stats["error_count"] = int(m.group(1))
    per_rule: dict[str, int] = {}
    for m in re.finditer(r"\[Rule (\d+[a-z]?)\]", validate_output):
        rule = m.group(1)
        per_rule[rule] = per_rule.get(rule, 0) + 1
    if per_rule:
        stats["per_rule"] = per_rule
    for m in re.finditer(r"^\s*(control_count|group_count|groups_in_catalog|missing_required_groups|trestle_compliance_issues|prose_contamination):\s*(\d+)\s*$", validate_output, re.MULTILINE):
        stats[m.group(1)] = int(m.group(2))
    return stats


def _format_prev_diff(prev_path: Path | None, cur_output: str, iter_n: int) -> str:
    """Format a compact 'what changed since last iteration' block."""
    if iter_n <= 1:
        return "(This is iteration 1. There is no previous iteration to compare against.)"
    if prev_path is None:
        return (
            "(No previous validate output provided. Orchestrator should pass "
            "--prev-validate-output pointing at iter N-1's validate output "
            "so you can see what your previous iteration changed.)"
        )
    if not prev_path.is_file():
        return f"(Previous validate output not found on disk: {prev_path})"
    prev_output = _read_text(prev_path)
    if not prev_output.strip():
        return "(Previous validate output is empty.)"

    prev_stats = _extract_error_stats(prev_output)
    cur_stats = _extract_error_stats(cur_output)

    if not prev_stats and not cur_stats:
        return "(Could not parse either validate output — both look malformed.)"

    lines: list[str] = []
    lines.append(f"Previous iteration ({iter_n - 1}) vs current ({iter_n}):")
    lines.append("")

    def _fmt(key: str, label: str) -> None:
        p = prev_stats.get(key)
        c = cur_stats.get(key)
        if p is None and c is None:
            return
        arrow = "→"
        note = ""
        if isinstance(p, int) and isinstance(c, int):
            if c < p:
                note = "  (improved ✓)"
            elif c > p:
                note = "  (regressed ✗)"
            else:
                note = "  (unchanged)"
        lines.append(f"  {label:38s}: {p} {arrow} {c}{note}")

    _fmt("error_count", "Total ERROR count")
    _fmt("control_count", "control_count")
    _fmt("group_count", "group_count")
    _fmt("groups_in_catalog", "groups_in_catalog")
    _fmt("missing_required_groups", "missing_required_groups")
    _fmt("prose_contamination", "prose_contamination")
    _fmt("trestle_compliance_issues", "trestle_compliance_issues")

    prev_rules = prev_stats.get("per_rule", {}) or {}
    cur_rules = cur_stats.get("per_rule", {}) or {}
    if isinstance(prev_rules, dict) and isinstance(cur_rules, dict):
        all_rules = sorted(set(prev_rules) | set(cur_rules), key=lambda r: (int(re.match(r"\d+", r).group()), r))
        if all_rules:
            lines.append("")
            lines.append("  Per-rule error counts:")
            for r in all_rules:
                p = prev_rules.get(r, 0)
                c = cur_rules.get(r, 0)
                mark = ""
                if c < p: mark = "  (improved ✓)"
                elif c > p: mark = "  (regressed ✗)"
                elif c == p and c > 0: mark = "  (unchanged)"
                lines.append(f"    Rule {r:4s}: {p} → {c}{mark}")

    lines.append("")
    lines.append("If the error count went UP or a new critical rule appeared, the")
    lines.append("previous iteration's edit was a regression. Consider reverting it")
    lines.append("as the first move of THIS iteration before layering another change.")
    lines.append("If the failure signature is BYTE-IDENTICAL to the previous iteration")
    lines.append("(same error count, same rules, same counts), the previous edit")
    lines.append("didn't take effect (was the wrong file re-run? was catalog.json not")
    lines.append("regenerated?). Investigate that first.")
    return "\n".join(lines)


def build_prompt(
    output_dir: Path,
    iter_n: int,
    validate_output_path: Path,
    merged_context_lines: int,
    input_pdf_path: Path,
    prev_validate_output_path: Path | None,
) -> str:
    validate_output = _read_text(validate_output_path)
    if not validate_output.strip():
        validate_output = (
            "(validate output is empty — cannot proceed without knowing "
            "which rules failed)"
        )

    keywords = _extract_context_keywords(validate_output)
    merged_context = _slice_merged(
        output_dir / "merged.txt", keywords, merged_context_lines
    )
    prev_diff_block = _format_prev_diff(prev_validate_output_path, validate_output, iter_n)
    missing_group_names = _extract_missing_group_names(validate_output)
    missing_group_evidence = _grep_missing_group_evidence(
        output_dir / "merged.txt", missing_group_names
    )

    subs = {
        "{iter_n}": str(iter_n),
        "{output_dir}": str(output_dir),
        "{input_pdf_path}": str(input_pdf_path),
        "{generate_py_path}": str(output_dir / "generate.py"),
        "{validate_py_path}": str(output_dir / "validate.py"),
        "{validate_config_py_path}": str(output_dir / "validate_config.py"),
        "{validate_output_path}": str(validate_output_path),
        "{merged_txt_path}": str(output_dir / "merged.txt"),
        "{validate_output}": validate_output,
        "{merged_context}": merged_context,
        "{prev_diff_block}": prev_diff_block,
        "{missing_group_evidence}": missing_group_evidence,
    }
    out = PROMPT_HEADER
    for key, value in subs.items():
        out = out.replace(key, value)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path, help="Output directory")
    parser.add_argument("iter_n", type=int, help="Iteration number (1-based)")
    parser.add_argument(
        "--validate-output",
        required=True,
        type=Path,
        help="Path to a text file containing the last validate.py output",
    )
    parser.add_argument(
        "--input-pdf",
        required=True,
        type=Path,
        help="Path to the source PDF (needed so the fix subagent can re-run generate.py)",
    )
    parser.add_argument(
        "--merged-context-lines",
        type=int,
        default=40,
        help="Lines of merged.txt to include around each keyword hit (default: 40)",
    )
    parser.add_argument(
        "--prev-validate-output",
        type=Path,
        default=None,
        help="Path to the previous iteration's validate output (enables the "
             "'progress since last iteration' block). Optional but strongly "
             "recommended for iterations >= 2.",
    )
    args = parser.parse_args()

    if not args.output_dir.is_dir():
        print(f"ERROR: output_dir does not exist: {args.output_dir}", file=sys.stderr)
        return 1
    if not args.validate_output.is_file():
        print(
            f"ERROR: validate-output file not found: {args.validate_output}",
            file=sys.stderr,
        )
        return 1
    if not args.input_pdf.is_file():
        print(
            f"ERROR: input-pdf not found: {args.input_pdf}",
            file=sys.stderr,
        )
        return 1

    prompt = build_prompt(
        args.output_dir,
        args.iter_n,
        args.validate_output,
        args.merged_context_lines,
        args.input_pdf,
        args.prev_validate_output,
    )
    out_path = args.output_dir / f"_fix_prompt_{args.iter_n}.txt"
    out_path.write_text(prompt, encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
