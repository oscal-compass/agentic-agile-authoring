#!/usr/bin/env python3
"""Build a Phase 2 authoring prompt: write `generate.py` only.

Design principle: the prompt is a set of INSTRUCTIONS + file paths, NOT
an embedded copy of every source file. The subagent uses the Read tool
to pull in the template and merged.txt slices when it needs them. This
keeps the prompt itself small (a few KB) so the subagent's input tokens
stay reasonable across the authoring turn.

The prompt embeds only:
  - PDF analyzer output (short, human-readable)
  - A small merged.txt head sample so the subagent can decide right away
    whether pdfplumber is needed and roughly what regex to plan

Everything else is a path reference:
  - `<script_dir>/generate_template.py` — read then customize + write
  - `<input_pdf>` — read on demand for spot-checks

This prompt covers Phase 2 (author `generate.py`) only. Phase 3 (author
`validate.py`) is a separate subagent run driven by `build_validate_prompt.py`;
by that point the orchestrator will have executed `generate.py` and the
validate subagent gets to see the real `merged.txt` / `catalog.json` when
choosing `required_groups`.

Written to `<output_dir>/_author_prompt.txt`. Path is echoed to stdout.

Usage:
    python build_author_prompt.py <output_dir> <input_pdf> \
        [--merged-head-lines 200] [--reference-catalog <path>]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


PROMPT_HEADER = """You are the Phase 2 authoring subagent for the compliance-catalog skill.
Your deliverables are two files on disk, produced across TWO runs of
`generate.py` (see Steps below — this is not optional, the second run
is what makes your exclusions take effect):

  - <output_dir>/generate.py         →  parseable as Python AND runs
                                        end-to-end AND produces a
                                        non-empty catalog.json that
                                        contains NEITHER any control id
                                        listed in excluded_units.json
                                        NOR any group id listed under
                                        its `_groups` section
  - <output_dir>/excluded_units.json →  valid JSON (may be `{}`) — see
                                        "Non-requirement content" below.
                                        Supports both control-level
                                        exclusion and whole-group
                                        exclusion (`_groups`).

If the first condition is not met when you finish, you have NOT
completed your task — you must fix it yourself in this same session
before printing "DONE". Do NOT hand off a broken generate.py to Phase 3
or the fix loop; those phases assume a working extraction script.
`excluded_units.json` being empty (`{}`) is a perfectly valid outcome,
but the file must still exist and be valid JSON before you stop, and
if it is non-empty, the SECOND `generate.py` run (Step 4.6) confirming
none of its ids leaked into catalog.json is mandatory, not optional.

`generate.py` starts life as a copy of `generate_template.py` under the
skill's `scripts/` directory (path given below). You customize the copy
for THIS specific PDF before writing. When the file is on disk, is valid
Python, executes cleanly against the input PDF, and the resulting
`catalog.json` contains ≥ 1 group and ≥ 1 control, print "DONE" on its
own line and stop.

Do NOT also write validate.py — that is a separate subagent's job in
Phase 3, launched by the orchestrator after your generate.py has been
executed once. Writing validate.py here is out of scope and interferes
with the pipeline.

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

Prefer whichever "read whole file" / "targeted edit" combo minimises
token spend. Never dump the full template body back into your reply —
read the template file, mutate it via targeted edits, and write the
final version to disk directly.

**Critical write-method rule:** do NOT use shell heredocs (`cat <<EOF`,
`python3 <<'PY'`, multi-line `bash -c` blobs, or similar) to create or
rewrite `generate.py`, `excluded_units.json`, or helper temp files. In
this harness those patterns have repeatedly produced `bash: -c: line N:
syntax error: unexpected end of file` and stalled Phase 2. Use native
file tools instead (Read + Edit/apply_diff/write_to_file, or the
harness's equivalent). Use the shell only for short commands like `cp`,
`python3 path/to/generate.py ...`, and syntax/shape checks.

**Critical editing rule:** do NOT try to mutate `generate.py` via shell
one-liners, `sed`, inline Python launched through `bash -c`, or other
command-string editing tricks. Read the template with your file-read
tool, then write/edit files with native file-edit tools only. When the
first regex guess fails, inspect the actual extracted text using your
file-read tool on `merged.txt` or page text files and then make a
targeted file edit. Do not keep iterating through shell-generated edit
attempts.

**Critical workflow rule — copy first, then edit; NEVER rewrite the
whole file.** `generate_template.py` is ~40 KB of working Python code.
Whole-file writes at that size have repeatedly produced *truncated*
output that leaves a `SyntaxError: unterminated string literal` or
`unexpected EOF while parsing` in the tail of the file, and Phase 2
then stalls attempting to "fix" the artefact. To eliminate that
failure mode entirely, your ONLY sanctioned sequence is:

  1. **Copy the template verbatim** with your shell tool — one command,
     no heredoc, no inline Python:

         cp {gen_template_path} {output_dir}/generate.py

     After this call, `{output_dir}/generate.py` MUST be byte-identical
     to the shipped template (verify via `wc -c` or a diff if you're
     unsure). Also copy the sibling `generate_lib.py`:

         cp {gen_lib_path} {output_dir}/generate_lib.py

  2. **Make targeted edits with your Edit/apply_diff tool** to the
     handful of PDF-specific regions in the copy — typically:

     - the `CONFIG` dict (title, version, id_prefix, page ranges,
       header/footer patterns, garbage patterns)
     - the `PATTERNS` dict (`chapter`, `section`, optionally
       `nested_control`)
     - occasionally a small addition inside `parse_structure()` for
       document-specific stop conditions

     Each edit should be a small, targeted diff — a 5-50 line
     replacement, never a wholesale rewrite. If a single edit would
     touch more than a quarter of the file, split it into smaller
     edits.

  3. **NEVER** rewrite `generate.py` from scratch with a single
     `write_to_file` / `Write` call, and NEVER regenerate it via
     `python3 -c "shutil.copy(...)"` or a heredoc after your first
     `cp`. Both routes hit the truncation ceiling. If your targeted
     edits somehow produce a broken file, delete it (`rm generate.py`),
     re-`cp` the template, and re-apply the edits — do NOT reach for a
     whole-file write.

  4. **If you catch a `SyntaxError` at Step 3 (parse check),** the
     immediate remedy is the same three lines: `rm generate.py`,
     `cp template`, then apply just the diffs you actually needed. Do
     NOT try to Edit around the syntax error in-place — the whole tail
     of the file after a truncation point is unreliable.

The point of the discipline: `apply_diff` on a valid file cannot
produce a truncated file. `write_to_file` on 40 KB of content
sometimes can. Given a known-good starting point (the shipped
template) and small edits, the surface area for truncation is
eliminated.

## Paths for this run

- Output directory:            {output_dir}
- Input PDF:                   {input_pdf}
- Reference catalog (optional, metadata merge): {reference_catalog}
- generate_template.py:        {gen_template_path}
- generate_lib.py (READ-ONLY): {gen_lib_path}
- merged.txt (may not exist yet — see below): {merged_txt_path}

If `merged.txt` already exists (a previous Phase 2 attempt), it is your
primary source for structure discovery. If it does not, base your
initial CONFIG on the analyzer output and merged.txt head sample
embedded below. You (this subagent) will run `generate.py` yourself in
Step 4 to produce it and the first-cut catalog.

{seed_catalog_block}

## Anti-hallucination principle (must-obey)

The catalog's titles and prose come from PDF text via regex capture only.
FORBIDDEN patterns in `generate.py`:

    PART_TITLES = {"1": "Preliminary", ...}
    SCHEDULE_TITLES = {"1": "Data Protection Principles", ...}
    SECTION_TO_PART = {"1": "1", "2": "1", ...}
    control["title"] = "Hardcoded title"

ALLOWED in CONFIG: extraction parameters (`toc_pages`, `id_prefix`,
`use_pdfplumber`, `garbage_line_patterns`) and document-level metadata
that is NOT in the PDF body (`jurisdiction`, `publisher`, `source`).

Rewriting `PATTERNS["chapter"]`, `PATTERNS["section"]`,
`PATTERNS["nested_control"]`, and `parse_structure()` for this document
IS the intended work of Phase 2. Do not skip it out of caution — that
is not hallucination, that is what makes the extraction fit this PDF.

## Anti-patterns you must NOT add to CONFIG (they will destroy the extraction)

Past runs have failed because subagents added seemingly-innocent filter
patterns that ended up deleting the very lines the extraction depends on.
Do not do any of the following:

- **DO NOT add `r"\\s+\\d{1,3}\\s*$"` (or any equivalent "trailing number
  on a line") to `CONFIG["toc_line_patterns"]`.** This looks like a
  reasonable TOC dot-leader alternative — page numbers do appear on the
  right side of TOC entries — but it also matches legitimate section
  headings like `Article 1`, `Article 12`, `Section 42`, `Rule 5`. On
  documents that use `Article N` / `Section N` / `Rule N` as their
  numbered-control markers (i.e. the majority of law and regulation
  PDFs, including the sample GDPR), enabling this pattern removes
  EVERY control heading from merged.txt during postprocessing. The
  extraction then produces `groups >= 1` but `controls == 0` — a
  seemingly-fine catalog file that is actually completely empty of
  controls. Rule 10 (sequential gaps) cannot warn about this because
  there are no IDs at all. **Restrict `toc_line_patterns` to explicit
  dot-leader / ellipsis markers only** (`r"\\.{3,}"`, `r"…{2,}"`,
  `r"……"`). Most documents don't need any TOC pattern beyond those,
  because pages without TOC content don't have dot-leader lines.

- **DO NOT add `r"^\\d+$"` alone to `garbage_line_patterns`.** It's
  meant to remove standalone page numbers but it also catches bare
  numeric section IDs that appear in some frameworks.

- **DO NOT add wildcard "merge adjacent whitespace" regexes to
  `postprocess_text`** such as `re.sub(r"\\b([a-z]+)\\s+([a-z]+)\\b",
  r"\\1\\2", text)` to "fix" kerning. It will collapse every legitimate
  space between two lowercase-starting words and destroy the extraction.
  The correct kerning fix is `CONFIG["use_pdfplumber"] = True`; if
  kerning survives that, leave the artefacts in prose — they don't
  block validation.

- **DO NOT add whitespace-flattening regexes** to `postprocess_text`.
  The following are FORBIDDEN because `\\s` matches `\\n` and the
  substitution removes line boundaries that `parse_structure()` needs
  to detect `^Article N$` and `^CHAPTER N$` headings:

      re.sub(r"\\s+", " ", text)       # kills newlines → controls=0
      re.sub(r"\\s+", "", text)        # obviously kills them too
      re.sub(r"[\\s\\n]+", " ", text)   # same
      text.replace("\\n", " ")         # also destroys structure

  Instead, if you really need to tidy whitespace, restrict the regex
  to spaces and tabs only:

      re.sub(r" +", " ", text)          # runs of spaces
      re.sub(r"[ \\t]+", " ", text)     # spaces + tabs
      re.sub(r"\\n{3,}", "\\n\\n", text)  # triple+ blank lines only

  Every past run that dropped to `control_count=0` mid-fix-loop was
  caused by a subagent introducing one of the forbidden forms above.

- **DO NOT add a chapter/section regex that captures the title on the
  same line via `.*$`**, e.g. `r"^CHAPTER\\s+([IVX]+)\\s+(.*)$"`.
  In-prose cross-references like "Chapter VII, a body as..." will then
  match and create phantom groups. Require a **bare line** with
  `r"^CHAPTER\\s+([IVXLCDM]+)\\s*$"` (empty title capture, or no title
  capture) and let the multi-line title extractor grab the title from
  the next line.

- **DO NOT hand-roll title/prose boundary logic inside `parse_structure()`.**
  Many law/regulation PDFs put the article number and the FIRST SENTENCE
  of the article on the same line, like:

      Article 1 This Law is enacted for the purpose of regulating data
      processing, ensuring data security, promoting development and use.

      Article 2 This Law shall apply to data processing activities within
      the territory of ...

  A regex `^Article\\s+(\\d+)\\s+(.*)$` will happily capture group(2) as
  the entire first body sentence. If your `parse_structure()` then
  keeps eating lowercase-continuation lines "because it looks like the
  title is wrapped", the title fills up with 200-400 chars of body prose
  and the control's `statement` prose ends up empty — the classic Rule 7
  ("empty or too short prose") + Rule 14 ("prose contamination") stall
  that Phase 4 cannot recover from.

  The shipped `generate_lib.py` exports a helper for exactly this:

      from generate_lib import (
          assemble_catalog,
          split_title_and_prose_on_section_line,
          looks_like_prose_remainder,
      )

  Call `split_title_and_prose_on_section_line(remainder)` on whatever
  your section regex captures after the article number. It returns
  `(title, prose_seed)` — when `remainder` looks like body prose (long,
  ends with a preposition/comma, starts with a sentence-opener,
  contains internal sentence terminators), it returns `("", remainder)`
  and you seed the control's prose with that string instead of using it
  as title. When it looks like a real title ("Definitions", "Scope and
  application"), it returns `(remainder, "")` and you proceed as normal.

  The helper is version-locked to `generate_lib.py`, so every
  document's `generate.py` gets the same behaviour. Do NOT re-implement
  this heuristic in your `generate.py`; call the helper. It is
  deliberately conservative — when in doubt it prefers "title empty,
  prose seeded" because a Rule 15 missing-title warning is much cheaper
  than a Rule 7 stall.

  In the multi-line title extractor that runs AFTER the same-line
  capture, call `looks_like_prose_remainder(next_line)` before consuming
  a lowercase-starting continuation line. That's what stops the
  extractor from vacuuming body text into a still-empty title on
  PDFs where each article's first sentence is on its own line under
  the "Article N" heading.

If ANY of these patterns is in your generated `CONFIG` / `PATTERNS` when
you finish, Phase 2 Step 4 will report `groups=0 controls=0` and Main
will re-run this authoring — with the same prompt. Save yourself the
loop: don't add them in the first place.

## Control ID naming — read this BEFORE writing generate.py

Control IDs and group IDs generated by `generate.py` MUST follow the
pattern `<prefix>-<article-number>`:

    ✓  eu-gdpr-1, eu-gdpr-2, ..., eu-gdpr-99         (Article 1 .. Article 99)
    ✓  hk-pdpo-1, hk-pdpo-30, ..., hk-pdpo-71        (Section 1 .. Section 71)
    ✓  nist-800-53-ac-1, nist-800-53-au-2            (family + control number)
    ✓  asset-1-a, threat-2-b                          (C2M2-style)

The following are FORBIDDEN — do not produce them under any circumstance:

    ✗  gdpr-chapter-i-conditions-for-consent
    ✗  gdpr-chapter-i-def-initions
    ✗  gdpr-chapter-vi-acti-vity-repor-ts
    ✗  gdpr-chapter-vii-mutual-assist-ance

These slug-based IDs are wrong regardless of how tempting they look. They
break Rule 10 (numeric continuity check), they change across re-extractions
because kerning artifacts leak in ("Def initions" → "-def-initions" one
run, "-definitions" another), and they make the catalog unusable for
downstream OSCAL tooling.

The IMPLICATION for `PATTERNS["section"]`: it must match numbered
headings (`Article N`, `Section N`, `Rule N`, `Practice N`, `Principle N`,
etc.), NOT article titles. If Articles are hard to find in this PDF, work
harder on the regex — do not fall back to slugifying titles.

If a document truly has no numbered controls (e.g. a policy that names
each control by title alone), pick a scheme that still gives short stable
IDs: number them 1..N by document order (`myframework-1`, `myframework-2`,
…) using enumerate() in parse_structure. Never slugify titles into IDs.

## Non-requirement content — parse_structure() extracts it anyway; a later step removes it from the final catalog

OSCAL defines a control as "a requirement or guideline, which when
implemented will reduce an aspect of risk." Many compliance PDFs number
units that don't fit this — definitions articles, commencement clauses,
short-title / citation articles, purely administrative provisions. As
you read the PDF in Step 1, you will likely notice some of these. The
FINAL `catalog.json` (after Step 4.6) must NOT contain these units —
only genuine requirements belong in the deliverable.

**Do NOT let that judgment change what `parse_structure()` extracts,
and do NOT hand-remove anything from `catalog.json` yourself.** In
Step 4, `parse_structure()` extracts every numbered unit in the PDF
unconditionally, including the ones you believe are non-requirement —
extraction stays mechanical and complete, so a missing control is
always attributable to a regex bug, never to a judgment call baked
into the regex. If `parse_structure()` skipped units it judged
non-requirement, a missing control would be ambiguous — bug or
intentional? — and Rule 10 (numeric continuity) would lose the ability
to tell those apart.

Instead, the removal happens in a SEPARATE, later step (4.5–4.6): you
write your requirement/non-requirement judgment into
`excluded_units.json` as data, then re-run `generate.py`, which reads
that file and mechanically omits the listed ids while building
`catalog.json` — see `load_excluded_units()` and `assemble_catalog()`
in `generate_lib.py` (a sibling library, not part of the template you
edit; you inherited it when you copied the template). Your only job is
to get `excluded_units.json`'s content right.

**Two granularities of exclusion exist and both matter.**
`excluded_units.json` supports (a) individual control exclusions
(top-level keys) for the common case of a single non-requirement
control scattered inside a normative group, and (b) whole-group
exclusions (`_groups` section) for the case where an entire chapter is
introductory or administrative (e.g. Chapter I of a typical regulation
= Subject-matter + Scope + Definitions). Choosing the right granularity
matters: listing every control of Chapter I individually would leave
the group with `controls: []`, which the assembly library deliberately
does NOT silently drop (it violates Rule 2) — the only way to remove
Chapter I entirely and keep Rule 12 happy is to list it under
`_groups`. Step 4.5 below has the exact schema and decision procedure.

## Steps

1. Read the analyzer output (below) and the merged.txt head sample
   (below) to decide:
   - What is the top-level group marker for this document?
     (PART / SCHEDULE / CHAPTER / ARTICLE / ANNEX / … case sensitivity?)
   - What is the numbered-control marker? (`Article N`, `Section N`,
     `Rule N`, etc.) You will encode this in `PATTERNS["section"]`.
   - (Do NOT deliberate about `use_pdfplumber` — always set it to `True`.
     See Step 2 below for the reason.)
   - What TOC page range should be skipped?
   - What is a good `id_prefix` (short, lowercase, letters + hyphens)?

2. Prepare the `generate.py` and `generate_lib.py` in `{output_dir}` via
   **`cp` first, then targeted edits** — never a whole-file write. This
   is the discipline described in the "Critical workflow rule" above;
   the concrete commands for this run are:

       cp {gen_template_path} {output_dir}/generate.py
       cp {gen_lib_path}      {output_dir}/generate_lib.py

   After the two `cp`s, `{output_dir}/generate.py` is a byte-identical
   copy of the shipped template — a known-good starting point. From
   here you customize with **Edit / apply_diff / str_replace_editor**
   (whichever your harness exposes) against small regions only. Do
   NOT read the whole template into your context and then re-emit it
   through `write_to_file` — that route has been the top source of
   syntax-error-in-tail failures in Phase 2.

   `generate_lib.py` is READ-ONLY: after `cp`, do NOT edit it, do NOT
   paste its body back into the conversation, do NOT duplicate any of
   its contents into `generate.py`. The orchestrator's Step 4
   verification sha256-compares this sibling copy against the source
   and will fail Phase 2 if the bytes differ.

   The generate.py edits you SHOULD make are all local — CONFIG dict,
   PATTERNS dict, occasionally a small addition to `parse_structure()`.
   None of them need touch more than 10-50 contiguous lines. If you
   find yourself preparing an edit that would replace hundreds of
   lines at once, stop and split it — a large replacement written
   back through Edit / apply_diff is safer than a `write_to_file`,
   but still not as safe as several small diffs.

   Key edits:
   - `CONFIG["name"]`: short identifier (e.g. "eu-gdpr").
   - `CONFIG["title"]`: full document title from the PDF masthead.
   - `CONFIG["toc_pages"]`: page range to skip (Python `range(...)` OK).
   - `CONFIG["id_prefix"]`: short lowercase prefix. Combines with the
     article number to form control IDs (`<prefix>-<N>`).
   - `CONFIG["use_pdfplumber"]`: **always `True`**. pdfplumber produces
     cleaner text than pypdf on essentially every compliance PDF we
     have tested (EU regulations, Hong Kong PDPO, NIST, etc.) and never
     produces worse text. Do not spend time judging whether the sample
     shows kerning issues — set it to `True` unconditionally.
   - `CONFIG["metadata"]`: jurisdiction, source, publisher.
   - `PATTERNS["chapter"]`: regex for top-level groups (bare lines).
   - `PATTERNS["section"]`: regex for **numbered** controls — MUST
     capture the article/section number as a group. E.g.
     `r'^(?:Article|ARTICLE)\\s+(\\d+)()\\s*$'` for GDPR-like PDFs.
   - `PATTERNS["nested_control"]`: only if the document is hierarchical
     (e.g. Principle N inside Schedule N).

   The `generate_control_id()` helper in the template builds IDs from
   `<id_prefix>-<captured_number>`; do NOT replace this with a title-based
   ID generator.

   **Also review `CONFIG["page_number_patterns"]` for this PDF.** The
   template ships with safe cross-document defaults (bare page numbers,
   "Page N of M", and EU Official Journal boilerplate). If the merged.txt
   head sample below shows any RUNNING HEADER OR FOOTER that repeats on
   every page and would leak into control prose (a common source of
   Rule 14 "prose contamination" errors), add a regex for it here now.
   Typical examples to look for and add:
   - Corporate publisher / logo lines: `r"^Verified\\s+Copy$"`,
     `r"^Cap\\.\\s+\\d+$"`, `r"^NIST\\s+SP\\s+\\d+-\\d+"`.
   - Date-stamped page headers: e.g. `r"^\\d{4}-\\d{2}-\\d{2}\\s+Confidential"`.
   - Legislation citation footers: e.g. `r"^Section\\s+\\d+\\s+Cap\\.\\s+\\d+$"`.

   Each pattern should match ONLY page furniture, never body prose.
   Adding these here means Phase 4 doesn't have to discover them via
   Rule 14 errors — which is worth doing because Rule 14 tends to fire
   many times per unfixed header (one per contaminated control), and
   the resulting error volume can overwhelm the fix loop's judgement.

3. **Verify the file parses as Python.** Run from your shell tool:

       python3 -c "import ast; ast.parse(open('{output_dir}/generate.py').read())"

   Exit code MUST be 0. If it fails with a SyntaxError, your write got
   truncated or a regex has an unescaped character. **Fix it now, in
   THIS session, before proceeding.** Do NOT hand off a
   syntactically-broken generate.py — Phase 3 depends on being able to
   run it.

   **Recovery discipline for SyntaxError:** do NOT try to Edit / patch
   the broken file in place. When Python reports a syntax error like
   "unterminated string literal at line N" the actual defect is almost
   always AT OR AFTER a truncation point, and the rest of the file
   is unreliable. The clean-room fix is three shell commands:

       rm {output_dir}/generate.py
       cp {gen_template_path} {output_dir}/generate.py
       # then re-apply your CONFIG / PATTERNS edits with Edit / apply_diff

   Trying to write a "corrected" whole file with `write_to_file` after
   a SyntaxError typically produces a fresh truncation in a different
   place. The template + small diffs path is the one that reliably
   produces a parseable file.

4. **Execute generate.py yourself and verify the result.** Run:

       python3 {output_dir}/generate.py {input_pdf} {output_dir}

   This must:
   - Exit with code 0 (no Python exception).
   - Produce `{output_dir}/merged.txt` (non-empty, >1 KB is typical).
   - Produce `{output_dir}/catalog.json` (non-empty, valid JSON, with
     at least one group AND at least one control).

   After it finishes, verify with:

       python3 -c "import json,sys; c=json.load(open('{output_dir}/catalog.json'))['catalog']; g=c.get('groups',[]) or []; ctrls=sum(len(x.get('controls') or []) for x in g)+len(c.get('controls') or []); print(f'groups={{len(g)}} controls={{ctrls}}'); sys.exit(0 if (len(g)>=1 and ctrls>=1) else 2)"

   Exit code MUST be 0. If it prints `groups=0` or `controls=0`, your
   regex / parse_structure() did not match this PDF's structure.

   **This is where most bad generate.py's are caught.** Common causes:
   - `PATTERNS["section"]` doesn't match the actual heading format —
     look at merged.txt around the first article and adjust the regex.
   - `toc_pages` range excluded body pages by mistake — narrow it.
   - You added a forbidden anti-pattern (see the section above) — remove it.

   Iterate on the regex / CONFIG in THIS session until the verification
   passes. Do NOT print "DONE" while `groups=0` or `controls=0`. Do NOT
   defer to Phase 3 or Phase 4 for this — they cannot recover from a
   generate.py that produces an empty catalog because they operate on
   an already-extracted catalog.

4.5. **Write `{output_dir}/excluded_units.json`.** Now that `catalog.json`
   exists and `CONFIG["id_prefix"]` is final, go through the controls it
   contains and identify any whose content is non-requirement (see
   "Non-requirement content" above — definitions, commencement clauses,
   purely administrative text). The file has TWO sections that address
   different sizes of exclusion:

   **Section 1 — top-level keys: individual control exclusions.** For a
   single non-requirement control inside an otherwise-normative group
   (e.g. a repeal clause at the end of Chapter XI), add an entry keyed
   by its EXACT control id as it appears in `catalog.json`:

       {
         "eu-gdpr-94": {"reason": "Repeal of Directive 95/46/EC — administrative provision retiring the predecessor directive; no compliance obligation."},
         "eu-gdpr-99": {"reason": "Entry into force and application — commencement clause specifying effective dates; not a substantive requirement."}
       }

   **Section 2 — `_groups`: whole-group exclusions.** When EVERY
   numbered unit in a group is non-requirement (e.g. Chapter I of a
   typical regulation contains only Subject-matter, Scope, and
   Definitions — the entire chapter is introductory and imposes no
   obligations of its own), do NOT list each of its controls
   individually in Section 1. Instead, list the GROUP id under
   `_groups`:

       {
         "_groups": {
           "eu-gdpr-chapter-i": {
             "reason": "General provisions — Subject-matter, Scope, and Definitions; entire chapter is introductory and imposes no obligations of its own."
           }
         }
       }

   **`merged_txt_header` is optional.** For any group id shaped like
   `<prefix>-<kind>-<num>` where `<kind>` is one of
   `chapter`/`part`/`schedule`/`annex` and `<num>` is a Roman numeral
   or decimal (e.g. `eu-gdpr-chapter-i`, `hk-pdpo-part-1`), validate.py
   auto-derives the merged.txt header from the group id itself. Only
   set `merged_txt_header` explicitly when the group id follows an
   exotic convention that this rule can't reverse.

   The two sections combine freely in a single file:

       {
         "eu-gdpr-94": {"reason": "..."},
         "eu-gdpr-99": {"reason": "..."},
         "_groups": {
           "eu-gdpr-chapter-i": {"reason": "..."}
         }
       }

   **When to use control-level vs group-level exclusion:**

   - If a group has AT LEAST ONE control that IS a requirement, use
     control-level exclusion for the non-requirement ones inside it.
     The group stays in `catalog.json` with the requirements it does
     have.
   - If a group would be left with ZERO controls after control-level
     exclusion, DO NOT list its controls individually — instead, put
     the group id in `_groups` with its merged.txt header. Reason:
     `generate.py`'s assembly library DOES NOT silently drop empty
     groups (a group with `controls: []` violates Rule 2, which Phase 4
     will then flag); the only clean way to remove the group entirely
     is via `_groups`. This is also the only mechanism that keeps
     Rule 12 (merged.txt group comparison) happy, because Rule 12
     checks `merged_txt_header` from `_groups` to know a missing group
     was intentional.
   - Individual control exclusion inside a "normally-most-controls-
     are-requirements" group is fine and expected (e.g. Article 94
     inside Chapter XI in GDPR).

   Rules that apply to BOTH sections:

   - Every control-id key (Section 1) MUST be a real control id that
     appears in the just-produced `catalog.json` — check, don't guess.
   - Every group-id key (Section 2) MUST be a real group id that
     appears in the just-produced `catalog.json`. `merged_txt_header`
     is optional (validate.py auto-derives it from the group id for
     the standard `<prefix>-<chapter|part|schedule|annex>-<num>`
     shape) — only add it explicitly if the group id follows an
     exotic naming convention.
   - Every reason must be specific (one sentence, naming what the
     content actually is), not a generic placeholder.
   - If you find no non-requirement units at either level, write an
     empty JSON object (`{}`) — this is a common and completely normal
     outcome, not a gap in your work.
   - When genuinely unsure about a borderline unit, leave it OUT.
     Under-listing is safe (Phase 4 gives a second, more focused pass
     at anything you miss); over-listing silently removes real
     requirements from the final catalog with no downstream check
     left to catch it.
   - Write this file once. You are not required to re-read the whole
     PDF a second time for this step — use the understanding you
     already built while writing `generate.py` and `PATTERNS`.

4.6. **Re-run `generate.py` so the final `catalog.json` reflects your
   exclusions.** `generate.py` reads `excluded_units.json` at write time
   and OMITS every listed control id AND every group id under `_groups`
   from `catalog.json` — this did not happen in Step 4 because the file
   did not exist yet. Run the exact same command as Step 4:

       python3 {output_dir}/generate.py {input_pdf} {output_dir}

   Then verify BOTH kinds of omission actually happened:

       python3 -c "
       import json
       c = json.load(open('{output_dir}/catalog.json'))['catalog']
       ex = json.load(open('{output_dir}/excluded_units.json'))
       control_ids = {{ctrl['id'] for g in c.get('groups', []) for ctrl in g.get('controls', [])}}
       group_ids = {{g['id'] for g in c.get('groups', [])}}
       excluded_controls = {{k for k in ex if k != '_groups'}}
       excluded_groups = set(ex.get('_groups', {{}}).keys()) if isinstance(ex.get('_groups'), dict) else set()
       leaked_controls = control_ids & excluded_controls
       leaked_groups = group_ids & excluded_groups
       print(f'excluded_controls={{len(excluded_controls)}} leaked_controls_into_catalog={{len(leaked_controls)}}')
       print(f'excluded_groups={{len(excluded_groups)}} leaked_groups_into_catalog={{len(leaked_groups)}}')
       if leaked_controls: print('LEAKED CONTROLS:', sorted(leaked_controls))
       if leaked_groups: print('LEAKED GROUPS:', sorted(leaked_groups))
       "

   Both leak counts MUST be 0. If a control id leaked, the id you wrote
   in `excluded_units.json` does not exactly match the id `generate.py`
   assigns (typo or case/prefix mismatch — fix the entry in
   `excluded_units.json`, not `generate.py`, and re-run this step). If
   a group id leaked, similar: fix the group id in the `_groups` entry.
   Do NOT print "DONE" while either kind of leak is nonzero.

   Also re-confirm the shape check from Step 4 still holds
   (`groups >= 1 and controls >= 1`) — excluding a handful of
   non-requirement articles or one introductory chapter should never
   zero out the catalog. If it does, you excluded too aggressively;
   trim `excluded_units.json` back down and re-run.

5. Print "DONE" and stop.

## Failure discipline

Your job is not "produce a file called generate.py" — it is "produce a
working generate.py that yields a non-empty catalog.json for THIS PDF".

- **Never** print "DONE" while generate.py fails Step 3 (syntax) or
  Step 4 (execution / non-empty output).
- **Never** hand off the problem with excuses like "template can't
  handle this document" or "the fix loop can iterate". Both statements
  are wrong at this stage — the fix loop can only refine a working
  extraction, not repair a fundamentally broken one.
- If after multiple attempts (say, 5 regex iterations in Step 4) you
  still cannot get a non-empty catalog, look at merged.txt yourself,
  find one specific line that should have matched, and single-step
  through `parse_structure()` in your head. The regex is almost always
  the culprit, and it's always fixable by reading the source.
- Never leave a Python file with a syntax error on disk. If your write
  got truncated, write it again in full.
- **`excluded_units.json` is not a way to make a stubborn regex problem
  disappear.** If `PATTERNS["section"]` is failing to match a real
  article, the fix is the regex — never list that article's expected
  id in `excluded_units.json` to sidestep the extraction problem. That
  file is for content you have read and judged non-requirement, not
  for content your extraction happens to be struggling with. This
  matters MORE than it used to: an id in `excluded_units.json` is now
  REMOVED from the final `catalog.json` entirely (Step 4.6), so a
  wrongly-excluded requirement doesn't just get mislabeled — it
  silently disappears from the deliverable with no trace except a
  reason string in a file the reader may never open.

## Assembly boundary — invariant

The final catalog-assembly step (metadata construction, the exclusion
filter that consults `excluded_units.json`, the group-drop-when-empty
rule, and the file write) lives in the READ-ONLY sibling module
`generate_lib.py`. Your `generate.py` reaches it via one call:

```python
from generate_lib import assemble_catalog
# EXCLUSION-POINT: assemble_catalog handles excluded_units.json via generate_lib.
# DO NOT reimplement or replace this call — see SKILL.md Phase 2 verification.
assemble_catalog(
    groups,
    catalog_path,
    catalog_config={
        "title": CONFIG["title"],
        "version": CONFIG["version"],
        "metadata": CONFIG.get("metadata", {}),
    },
)
```

Four hard rules — the orchestrator's Step 4 verification enforces
each of them and will reject your work exactly like a Step 3 syntax
error if any of them breaks:

1. `generate.py` MUST contain exactly one call to `assemble_catalog(`
   — the one shown above, at the end of `main()`. Do not add more, do
   not remove it.
2. `generate.py` MUST NOT open-code an exclusion loop (e.g.
   `for ctrl in group["controls"]: if ctrl["id"] in excluded_units: continue`).
   Do not iterate `groups` in `generate.py` after `parse_structure()`
   returns them, for any reason other than passing them straight into
   `assemble_catalog`. **Real precedent:** a past subagent inlined this
   filter, then had to set `skip_rule_10_sequential_gaps=True` in
   `validate_config.py` to silence the gap errors that resulted —
   solving one problem by breaking another. Do not repeat this.
3. `generate.py` MUST NOT define its own `assemble_catalog` (that
   would shadow the shared function locally), and MUST NOT edit
   `generate_lib.py` or copy any of its code into `generate.py`.
   **Real precedent:** a past subagent authored `excluded_units.json`
   but wrote a `generate.py` that never called `load_excluded_units`
   / `assemble_catalog` at all — the exclusions had zero effect, but
   the pipeline still passed validation.
4. Preserve the `# EXCLUSION-POINT:` marker comment exactly at the
   call site. The orchestrator greps for it.

The one CONFIG piece you author that DOES matter for assembly is
`CONFIG["title"]`, `CONFIG["version"]`, and (optionally)
`CONFIG["metadata"]`. `assemble_catalog` reads these via the
`catalog_config` dict you pass; missing `title` or `version` raises a
`KeyError` at the first `generate.py` run in Step 4 with the exact
missing-key name, so a typo fails fast rather than shipping a broken
catalog.

## PDF analyzer output

```
{analyzer_output}
```

## merged.txt — first {merged_head_lines} lines

```text
{merged_head}
```
"""


def _read_text(path: Path, max_lines: int | None = None) -> str:
    with path.open("r", encoding="utf-8", errors="replace") as f:
        if max_lines is None:
            return f.read()
        lines = []
        for i, line in enumerate(f):
            if i >= max_lines:
                break
            lines.append(line)
        return "".join(lines)


def _render_seed_catalog_block(seed_path: str, max_controls_to_dump: int = 60) -> str:
    """Render a Markdown block summarising an existing (previous-generation)
    catalog whose structure the author subagent should inherit as closely as
    possible.

    Passed to Phase 2 as an authoring hint — NOT metadata merge (that's
    `--reference-catalog`).  Purpose: preserve control IDs, group IDs, group
    titles, and rough prose scaling across regenerations of the same PDF so
    downstream mappings and human bookmarks don't break.
    """
    if not seed_path:
        return ""
    p = Path(seed_path)
    if not p.is_file():
        return (
            "## Seed catalog (structure to inherit)\n\n"
            f"(seed catalog path was `{seed_path}` but the file was not\n"
            "found — proceed without it. Inheritance target: none.)\n"
        )
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return (
            "## Seed catalog (structure to inherit)\n\n"
            f"(seed catalog `{seed_path}` failed to parse: {e} — proceed\n"
            "without it. Inheritance target: none.)\n"
        )

    cat = data.get("catalog", data)
    groups = cat.get("groups", []) or []
    all_controls: list[dict] = []
    for g in groups:
        for c in (g.get("controls") or []):
            all_controls.append({
                "group_id": g.get("id"),
                "group_title": g.get("title"),
                "control_id": c.get("id"),
                "control_title": c.get("title"),
                "prose_len": sum(
                    len(part.get("prose") or "")
                    for part in (c.get("parts") or [])
                ),
            })

    lines: list[str] = []
    lines.append("## Seed catalog (structure to inherit)")
    lines.append("")
    lines.append(
        "An earlier generation of this framework's OSCAL Catalog is available "
        "as a seed at:"
    )
    lines.append("")
    lines.append(f"  `{seed_path}`")
    lines.append("")
    lines.append(
        "**Your generate.py MUST produce a catalog whose structure closely "
        "mirrors the seed.** This means:"
    )
    lines.append("")
    lines.append(
        "- **Group IDs and group titles**: reuse the seed's exact `id` and "
        "`title` strings for each group.  Do not invent alternative naming "
        "(e.g. `arg-ppl-chapter-ii` instead of `chapter-ii`)."
    )
    lines.append(
        "- **Control IDs**: reuse the seed's exact `id` strings.  If the "
        "PDF text obviously demands a new control the seed does not have, "
        "you may add it, but never rename an existing seed ID.  Renaming "
        "silently breaks downstream Mappings and reviewer bookmarks."
    )
    lines.append(
        "- **Number of controls**: aim to reproduce the seed count.  If your "
        "extraction produces materially fewer controls than the seed, either "
        "your `PATTERNS` are too narrow or you are excluding units the seed "
        "chose to keep.  Prefer inclusion — the seed represents the "
        "already-reviewed shape of this catalog."
    )
    lines.append(
        "- **Prose freshness**: prose text itself MUST come from the new "
        "PDF via your extraction (per Anti-hallucination §).  Do not copy "
        "prose from the seed.  The seed only fixes IDs and structure; the "
        "wording is recomputed from the input PDF each run."
    )
    lines.append(
        "- **Group ordering**: keep the seed's group order unless the PDF "
        "obviously reordered them."
    )
    lines.append("")
    lines.append(
        "If the PDF's structure has changed enough that some seed IDs no "
        "longer have counterpart text (the section was removed from the "
        "PDF), drop those controls but leave the surrounding IDs "
        "unchanged.  Report any drops in your final message so the "
        "reviewer can confirm they were intended."
    )
    lines.append("")
    lines.append(
        f"### Seed summary: {len(groups)} group(s), "
        f"{len(all_controls)} control(s)"
    )
    lines.append("")

    if groups:
        lines.append("**Groups (id → title)**:")
        for g in groups:
            gid = g.get("id", "?")
            gtitle = (g.get("title") or "").replace("\n", " ").strip()
            ccount = len(g.get("controls") or [])
            lines.append(f"- `{gid}` — {gtitle}  ({ccount} controls)")
        lines.append("")

    if all_controls:
        lines.append(
            f"**Controls (first {min(max_controls_to_dump, len(all_controls))} "
            f"of {len(all_controls)}, id → prose length)**:"
        )
        for c in all_controls[:max_controls_to_dump]:
            ctitle = (c["control_title"] or "").replace("\n", " ").strip()
            ctitle_short = (ctitle[:80] + "…") if len(ctitle) > 80 else ctitle
            lines.append(
                f"- `{c['control_id']}` (group `{c['group_id']}`, "
                f"prose_len={c['prose_len']}) — {ctitle_short}"
            )
        if len(all_controls) > max_controls_to_dump:
            lines.append(
                f"- … {len(all_controls) - max_controls_to_dump} more "
                "controls in the seed — read the seed file directly if "
                "you need the full list."
            )
        lines.append("")

    lines.append(
        "You may read the full seed at any time with your file-read tool "
        "if the summary above is insufficient (e.g. to inspect a specific "
        "control's `parts` layout)."
    )
    lines.append("")
    lines.append("### Turn-budget discipline (mandatory when a seed is present)")
    lines.append("")
    lines.append(
        "The seed above already tells you the shape.  Your job is to write a "
        "`generate.py` that reproduces that shape from the new PDF — NOT to "
        "re-discover the structure from scratch.  Batch runs on 200+ "
        "frameworks target ~20 minutes end-to-end per framework, so you MUST "
        "keep Phase 2 tight:"
    )
    lines.append("")
    lines.append(
        "- **One `cp` + at most TWO `Edit` calls.**  Copy `generate_template.py` "
        "once; make your CONFIG changes as a SINGLE Edit and your PATTERNS "
        "changes as a SINGLE Edit.  Do NOT split CONFIG edits across three "
        "separate calls just because three fields need to change — combine "
        "the diff.  Same for PATTERNS."
    )
    lines.append(
        "- **NO exploratory `pdfplumber` spot-checks beyond the analyzer "
        "output and merged.txt head embedded below.**  If the seed says the "
        "document has 8 groups named `part-1..8`, trust it — do not spend "
        "three turns opening pages to \"confirm\".  Save those turns for "
        "genuine ambiguity flagged by the analyzer."
    )
    lines.append(
        "- **NO iterative `python3 generate.py && jq` cycles** to fine-tune "
        "regexes turn by turn.  Run `generate.py` once at Step 4 to check "
        "it produces ≥1 group + ≥1 control (that is the completion "
        "condition).  Anything beyond that — validation issues, per-control "
        "problems — is Phase 4's job, not yours."
    )
    lines.append(
        "- **Print `DONE` as soon as Step 4 shows ≥1 group + ≥1 control.**  "
        "You do NOT need `catalog.json` to match the seed's control count "
        "here; Phase 4 fills that gap.  Your bar for stopping is "
        "\"generate.py runs, catalog.json non-empty\"."
    )
    lines.append("")
    lines.append(
        "Rule of thumb: with a good seed you should finish Phase 2 in **20-25 "
        "turns**.  Past 35 turns means you are re-discovering something the "
        "seed already told you.  **BUT** the hard-stop conditions are:"
    )
    lines.append("")
    lines.append(
        "  (a) `catalog.json` on disk after Step 4 must contain at least "
        "**30 % of the seed's control count** — anything less means "
        "`generate.py` did not actually run end-to-end and Phase 2 is not "
        "done."
    )
    lines.append(
        "  (b) `catalog.json` must contain the seed's group ids (at least "
        "the majority) — a fresh extraction that produces different group "
        "boundaries is Phase 2 not converged."
    )
    lines.append("")
    lines.append(
        "Never print `DONE` if either (a) or (b) fails.  It is far better "
        "to spend 30 turns and hand the wrapper a seed-shape catalog than "
        "to stop at 12 turns with a stub."
    )
    lines.append("")
    return "\n".join(lines)


def _run_analyzer(analyzer_script: Path, pdf: Path) -> str:
    try:
        proc = subprocess.run(
            ["python3", str(analyzer_script), str(pdf)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        out = proc.stdout.strip()
        if proc.stderr and not out:
            out = f"(analyzer stderr)\n{proc.stderr[-2000:]}"
        return out or "(analyzer produced no output)"
    except Exception as e:
        return f"(analyzer failed: {e})"


def build_prompt(
    output_dir: Path,
    input_pdf: Path,
    reference_catalog: str,
    seed_catalog: str,
    merged_head_lines: int,
) -> str:
    analyzer_output = _run_analyzer(SCRIPT_DIR / "analyze_pdf.py", input_pdf)

    merged_txt_path = output_dir / "merged.txt"
    if merged_txt_path.is_file():
        merged_head = _read_text(merged_txt_path, max_lines=merged_head_lines)
    else:
        merged_head = (
            "(merged.txt has not been produced yet — the orchestrator\n"
            " will regenerate it once you write generate.py. Base your\n"
            " initial CONFIG on the analyzer output above.)"
        )

    subs = {
        "{output_dir}": str(output_dir),
        "{input_pdf}": str(input_pdf),
        "{reference_catalog}": reference_catalog or "(none)",
        "{seed_catalog_block}": _render_seed_catalog_block(seed_catalog),
        "{gen_template_path}": str(SCRIPT_DIR / "generate_template.py"),
        "{gen_lib_path}": str(SCRIPT_DIR / "generate_lib.py"),
        "{merged_txt_path}": str(merged_txt_path),
        "{merged_head_lines}": str(merged_head_lines),
        "{merged_head}": merged_head,
        "{analyzer_output}": analyzer_output,
    }
    out = PROMPT_HEADER
    for key, value in subs.items():
        out = out.replace(key, value)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path, help="Output directory (must exist)")
    parser.add_argument("input_pdf", type=Path, help="Source PDF")
    parser.add_argument(
        "--merged-head-lines",
        type=int,
        default=200,
        help="Number of lines from merged.txt to embed (default: 200)",
    )
    parser.add_argument(
        "--reference-catalog",
        default="",
        help="Optional path to an existing catalog for metadata merge",
    )
    parser.add_argument(
        "--seed-catalog",
        default="",
        help=(
            "Optional path to a previous-generation catalog whose group/control "
            "IDs and structure the author subagent should inherit.  Prose comes "
            "from the new PDF; only IDs and shape are copied.  Different from "
            "--reference-catalog, which merges document-level metadata only."
        ),
    )
    args = parser.parse_args()

    if not args.output_dir.is_dir():
        print(f"ERROR: output_dir does not exist: {args.output_dir}", file=sys.stderr)
        return 1
    if not args.input_pdf.is_file():
        print(f"ERROR: input_pdf not found: {args.input_pdf}", file=sys.stderr)
        return 1

    prompt = build_prompt(
        args.output_dir,
        args.input_pdf,
        args.reference_catalog,
        args.seed_catalog,
        args.merged_head_lines,
    )
    out_path = args.output_dir / "_author_prompt.txt"
    out_path.write_text(prompt, encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
