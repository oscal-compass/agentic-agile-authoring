---
name: compliance-catalog
description: Convert a compliance-document PDF (law, regulation, industry standard) into a validated OSCAL Catalog JSON. Use when the user wants to turn a compliance PDF into an OSCAL Catalog, ingest a new framework into the OSCAL ecosystem, or regenerate a catalog from a revised PDF while keeping control IDs stable.
argument-hint: Path to the source PDF (e.g., "examples/EU-GDPR.pdf") plus an output directory
license: Complete terms in LICENSE.txt
---

# Compliance Catalog

Convert a compliance document PDF into a validated OSCAL Catalog JSON through an iterative loop between a deterministic extraction script (`generate.py`) and a comprehensive validator (`validate.py`).

```
┌─ Catalog Agent (loop control, CONFIG edits, gap judgments) ────────────┐
│  ┌─ Deterministic Extraction Pipeline (scripts/) ────────────────────┐ │
│  │ PDF → text extract → structure parse → OSCAL emit                 │ │
│  │       → postprocess → validate (17 rules + trestle)               │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────┘

  generate.py ──▶ catalog.json ──▶ validate.py
      ▲                                │
      └── FIX_GUIDANCE tells you which ─┘
          function of generate.py to edit
```

## What is an OSCAL Catalog, and what counts as a control

An OSCAL Catalog is NIST's machine-readable representation of a compliance document. OSCAL defines a **control** as *"a requirement or guideline, which when implemented will reduce an aspect of risk related to an information system and its information"* — not simply "a numbered thing in the document." A catalog groups controls under `group` (the document's own Parts / Chapters / Schedules), and each control's textual content lives in a `part` named `statement`.

This matters because compliance PDFs almost always contain numbered units that are **not** controls under this definition: definitions sections, purely administrative articles (commencement dates, amending formulas, short titles), and similar non-normative text. **The final `catalog.json` you deliver must not contain these units** — only genuine requirements. See "Extraction is requirement-agnostic; exclusion is a separate, reviewable step" below for the two-pass mechanism (`excluded_units.json`) that achieves this without weakening the extraction itself.

**What Phase 2's FIRST `generate.py` run does, unaffected by the paragraph above**: extract every numbered unit in the PDF as a control, exactly as this document already instructs — extraction stays mechanical and complete. The removal of non-requirement units happens in a later, separate step (Phase 2's second `generate.py` run, after `excluded_units.json` is written). The OSCAL definition above explains *why* the catalog is organized as controls-under-groups and *why* `statement` is the right place for extracted prose — it does not change what the first pass extracts.

## Trigger

Use this skill when asked to convert a compliance document PDF (law, regulation, industry standard) into an OSCAL Catalog JSON — or to update the catalog for a revised version of the same PDF.

## Inputs

- `input_pdf` (required): Path to the source PDF file.
- `output_dir` (required): Directory to write `generate.py`, `validate.py`, `catalog.json`, `merged.txt`, and `pages/`.
- `reference_catalog` (optional): Path to an existing OSCAL Catalog to merge metadata from (parties, props, published date, remarks, title, version). Useful when maintaining multiple versions of the same document.

## Setup

Required Python packages and system tools:

```bash
pip install -r scripts/requirements.txt
# or explicitly:
pip install pypdf pdfplumber pillow pytesseract pdf2image compliance-trestle
```

System dependencies (needed by `pdf2image` and OCR fallback):

```bash
# macOS
brew install poppler tesseract
# Ubuntu / Debian
apt-get install poppler-utils tesseract-ocr
```

The scripts do not call any external LLM API. All semantic judgment (structure interpretation, CONFIG tuning, gap classification) happens in your reasoning as the Agent executing this skill.

## CRITICAL: No Hardcoding of Catalog Content

**The whole point of using an extraction script is to avoid AI hallucination.** If you hardcode catalog content in `generate.py`, you defeat this purpose entirely.

### FORBIDDEN in generate.py

```python
# Static title lookup tables — hallucinate content that doesn't match the PDF
PART_TITLES = {"1": "Preliminary", "2": "Administration", ...}
SCHEDULE_TITLES = {"1": "Data Protection Principles", ...}
SECTION_TO_PART = {"1": "1", "2": "1", ...}

# Direct assignment bypassing the PDF
control["title"] = "Hardcoded title"
group["title"] = f"Part {num} {PART_TITLES[num]}"
```

### ALLOWED in generate.py

```python
# Extraction control parameters
CONFIG = {"toc_pages": [...], "id_prefix": "hk-pdpo", ...}
PATTERNS = {"chapter": r"...", "section": r"...", ...}

# Regex-captured title from the PDF text itself
chapter_title = chapter_match.group(3)
section_title = section_match.group(2)

# Document-level metadata NOT extractable from the PDF
CONFIG["metadata"] = {"jurisdiction": "Hong Kong", "source": "Cap. 486"}
```

### Why this matters

If you write `PART_TITLES = {"6": "Enforcement Powers"}` but the actual PDF says "Part 6: Matching Procedures", the catalog will contain "Enforcement Powers" — hallucinated content that doesn't match the source. All titles and prose MUST come from the PDF via regex capture. CONFIG may only hold parameters and document-level metadata that isn't extractable.

## CRITICAL: Do not give up mid-loop

The most common failure mode is not a technical bug — it is the Agent calling `attempt_completion` (or otherwise ending the run) with a partial result and a rationalisation like "the template cannot handle this document" or "a custom parser is required beyond the template's capabilities". **This is forbidden.** Every rationalisation below is wrong and must not be used as an exit condition:

- ❌ "This document has an unusual structure the template doesn't support."
- ❌ "A custom parser is needed — that goes beyond this skill."
- ❌ "Force-fitting would violate the anti-hallucination principle."
- ❌ "The extraction reached its limit; further tuning would be guesswork."
- ❌ "Partially complete — recommend the user extend the template."

**These are not valid outcomes for this skill.** The skill is complete only when ALL of the following hold simultaneously:

- `<output_dir>/catalog.json` contains **at least one group** and **at least one control**
- `python3 <output_dir>/validate.py <output_dir>/catalog.json --merged <output_dir>/merged.txt` returns **exit code 0**
- `python3 skills/compliance-catalog/scripts/validate_oscal_catalog.py --catalog <output_dir>/catalog.json` returns **exit code 0**
- Spot-check of 3–5 controls confirms the titles and prose match the PDF

Until all four are true, you are still in Phase 4 and must continue the fix loop.

### What "anti-hallucination" actually means (narrow definition)

The anti-hallucination principle prohibits **one thing only**: putting strings into `catalog.json` that do not appear in the PDF. Concretely, that means no static lookup tables like `PART_TITLES = {...}` and no hand-writing titles into the JSON.

It does **NOT** prohibit any of the following — all of which are the intended work of this skill:

- **Rewriting `PATTERNS["chapter"]`, `PATTERNS["section"]`, or `PATTERNS["nested_control"]` for this specific document.** These regexes are supposed to be document-specific. If a document lacks explicit "Article N" markers and instead uses "Chapter heading → paragraph number" structure, the correct move is to write a regex that captures that structure.
- **Rewriting `parse_structure()` in `generate.py` to handle the document's structure.** The template's `parse_structure()` is a starting point, not a fixed algorithm. If it does not fit the document, edit it.
- **Adding document-specific stop conditions, title-continuation rules, or zone handling.** These are all local extraction tuning — they capture what is actually in the PDF, they don't invent content.
- **Iterating many times.** If you have iterated 5+ times on the same rule, that is normal for exotic documents. Re-read FIX_GUIDANCE, look at `merged.txt` around the failing control, make a bigger change (`use_pdfplumber`, new regex, `DOCUMENT_ZONES` block), and continue.

If a document's structure is unusual, the answer is **always** "write a regex or `parse_structure()` change that captures its actual structure" — never "abandon the loop and report the template's limits to the user".

### Explicit forbidden termination patterns

You must not call `attempt_completion` (or otherwise end the task) if any of these are true:

- The `catalog.json` has zero groups or zero controls
- `validate.py` last exited non-zero and you have not made a subsequent change and re-run
- You are about to tell the user "custom parser needed", "template limits reached", or "manual pre-processing required"

If you find yourself writing any of those phrases, stop, re-read the PDF around a specific failing control, and change the regex or `parse_structure()` to match what is actually on the page. The extraction will work — the question is only whether you have iterated enough.

## Execution environment notes (read this FIRST)

Before you start running commands, internalise these rules:

1. **You are the orchestrator, not the implementer.** Phases 2, 3, each iteration of Phase 4, and Phase 6 are executed by **subagents** you spawn via your harness's native subagent tool (`spawn_subagent` on bob v2, `Task` on claude, `task` on opencode). Your own tool calls should be limited to:
   - Running the deterministic scripts (`analyze_pdf.py`, `build_author_prompt.py`, `build_fix_prompt.py`, `generate.py`, `validate.py`, `validate_oscal_catalog.py`).
   - Spawning subagents.
   - Reading small status signals (whether a file exists, `validate.py`'s exit code).

   You should NOT open `generate.py`, `validate.py`, or `merged.txt` yourself with Read/Edit/grep/sed/cat — that reading and editing is the subagent's job. Doing it yourself will burn your context budget and destabilise your judgment in later iterations. Design rationale: SPEC §3.6.

2. **The subagent tool is synchronous — no polling needed.** All three supported harnesses' subagent tools return only once the child has finished. Do NOT wrap them in `while ps -p …` / `sleep`-based polling loops; there is nothing to poll. The subagent will hand back a short summary; you read the on-disk artefacts (`generate.py`, `validate.py`, `catalog.json`, etc.) yourself to verify what it produced.

3. **Every subagent inherits the parent's credentials.** No `.env` handling, no `AGENT_HARNESS` branching in this file — pick one harness at startup and stick with it. All three (bob v2 / claude / opencode) provide the same abstraction (spawn a fresh subagent inside the parent's process), so the phases below describe **one** subagent-launch pattern that works everywhere.

4. **Never write `sleep N && something` in a Bash tool call.** Some agent harnesses block that pattern. Almost every place where earlier revisions of this document called for polling has been replaced by "spawn subagent → subagent returns → you check the on-disk artefact." If you find yourself wanting to poll, re-read the phase description — the answer is almost always "the subagent already returned; just Read/Bash the artefact."

## Pipeline

Run all commands from the repository root. Assume `SKILL_DIR=skills/compliance-catalog` and `OUT=<output_dir>`.

Terminology used below:

- **Main agent**: you. You orchestrate the phases by running scripts and launching subagents. You do not open template files or `merged.txt` directly.
- **Subagent**: a fresh agent session spawned via your harness's native subagent tool (`spawn_subagent` on bob v2, `Task` on claude, `task` on opencode). Each subagent receives a self-contained prompt file that includes exactly the context it needs, does one focused edit (write `generate.py` and `validate.py`, or write an edited `generate.py`), and exits.

### Phase 0 — Detect prior artifacts (main agent, deterministic)

Before running any other phase, inspect `$OUT` and decide whether this is a **fresh run** or a **re-run against updated inputs** (SPEC §13). This determines which phases you skip.

```bash
mkdir -p $OUT
ls "$OUT/generate.py" "$OUT/validate.py" "$OUT/catalog.json" 2>/dev/null
```

Branch on the result:

- **All three files present** → this is a **re-run**. Skip Phases 1, 2, and 3 entirely; jump straight to Phase 4 using the existing scripts. The scripts are the previous run's deliverable; treat them as a trusted starting point. Note in your working notes that Phase 6's `report.md` must record "re-run against existing outputs".
- **None of the three present** (empty or missing directory) → this is a **fresh run**. Execute Phases 1 → 6 as written below.
- **Some but not all** (partial state — e.g. `generate.py` present but `validate.py` missing) → this is a broken prior run per SPEC §12.2. Do **not** enter re-run mode. Instead, treat any present file as a starting point and resume from the first missing artefact (e.g. run Phase 3 to create the missing `validate.py`, then continue into Phase 4). Do not delete anything; the human can clean up if they want a truly fresh start.

Do not try to detect subtler drift (e.g. "was `generate.py` written for a different regulation?"). The presence of the three artefacts is the entire criterion. If the previous scripts don't fit the new PDF, Phase 4 will fail and the repair sub-loop (see Phase 4) will handle it — same mechanism the fresh run uses.

### Phase 1 — PDF Analysis (deterministic)

You do this yourself; there is no subagent for Phase 1.

```bash
mkdir -p $OUT
python3 $SKILL_DIR/scripts/analyze_pdf.py <input_pdf>
```

Read only enough of its output to notice the page count, whether the PDF is text-native or scanned, and roughly how many pages the TOC occupies. Do NOT try to guess the full CONFIG here — the subagent in Phase 2 will see the analyzer output too.

You do not need to produce `merged.txt` at this phase — Phase 2's `generate.py` will produce one when it runs. If for some reason you want an early `merged.txt` before Phase 2 (e.g., the subagent in Phase 2 fails to find any structure in the analyzer summary), you can run `generate.py` from the template once with pass-through defaults, but this is not the normal path.

### Phase 2 — Author `generate.py` (subagent)

**Skip this phase entirely if `$OUT/generate.py` already exists.** In re-run mode (Phase 0), the previous run's script is trusted as-is. Do not launch the author subagent, do not touch the file. Proceed directly to Phase 3 (which will also be skipped if `$OUT/validate.py` exists), or to Phase 4 if both scripts are already there.

Phase 2 covers ONLY writing `generate.py`. The orchestrator then runs
it — that produces `merged.txt` and a first-cut `catalog.json` — and
Phase 3 authors `validate.py` against those concrete artefacts. This
ordering means the Phase 3 subagent gets to see real extracted content
when populating `required_groups`, and any syntax error the Phase 2
subagent might have left in `generate.py` fails loudly at execution
rather than being deferred to Phase 4.

Phase 2 also drops a sibling `generate_lib.py` next to `generate.py`
in `$OUT`. It is a READ-ONLY copy of the shipped
`scripts/generate_lib.py`, and it owns the invariant catalog-assembly
step (`assemble_catalog`) — `generate.py` imports and calls it exactly
once at the end of `main()`. This split is what prevents a Phase 2
subagent from re-implementing the exclusion filter inline (see Phase 2
Step 4 verification below and the "Failure modes seen in the wild"
callout further down).

```bash
# Step 1: Build the authoring prompt (small, path-referenced, ~10 KB).
python3 $SKILL_DIR/scripts/build_author_prompt.py $OUT <input_pdf>
# → writes $OUT/_author_prompt.txt

# Step 2: Spawn the author subagent via your harness's native subagent
# tool. Its prompt should be exactly this (interpolate $OUT to its real
# absolute path first):
#
#   Read the prompt file at $OUT/_author_prompt.txt and follow its
#   instructions verbatim. It tells you how to author generate.py,
#   copy generate_lib.py next to it, and run generate.py once to
#   produce merged.txt and catalog.json. Do everything the prompt
#   asks. When done, reply with a one-line summary: "phase-2: wrote
#   generate.py, catalog has G groups / C controls".
#
# The subagent tool is synchronous — it returns once the subagent has
# finished. No polling, no wait_for. When it returns, proceed to Step 3.

# Step 3: Verify generate.py is present, non-empty, and syntactically valid.
if [ ! -s $OUT/generate.py ]; then
  echo "Phase 2: MISSING generate.py"
  # → retry per "Phase 2 authoring failure" below (re-spawn the subagent).
elif ! python3 -c "import ast; ast.parse(open('$OUT/generate.py').read())" 2>&1; then
  echo "Phase 2: generate.py has a syntax error (subagent Write was truncated)"
  rm -f $OUT/generate.py    # remove the broken file so retry writes fresh
  # → retry per "Phase 2 authoring failure" below
else
  echo "Phase 2: generate.py OK"
fi

# Step 4: Run generate.py once and INSPECT what it extracted. Simply
# producing a non-empty merged.txt / catalog.json is NOT enough — a
# catalog with `groups: []` and no controls is a valid JSON file but a
# broken extraction, and advancing to Phase 3 in that state produces a
# `validate.py` written against an empty catalog (garbage `required_groups`,
# no way for Rule 6a/6b to help). You MUST re-do Phase 2 authoring
# until the initial extraction has non-zero groups AND non-zero controls.
python3 $OUT/generate.py <input_pdf> $OUT
python3 - "$OUT" <<'PY'
import json, sys
out = sys.argv[1]
try:
    c = json.load(open(f"{out}/catalog.json"))["catalog"]
except Exception as e:
    print(f"Phase 2: catalog.json is unreadable: {e}")
    sys.exit(2)
groups = c.get("groups") or []
top_controls = c.get("controls") or []
total_controls = sum(len(g.get("controls") or []) for g in groups) + len(top_controls)
print(f"Phase 2: extraction shape → groups={len(groups)} total_controls={total_controls}")
if len(groups) == 0 or total_controls == 0:
    print("Phase 2: BROKEN — catalog has 0 groups or 0 controls; do NOT proceed to Phase 3")
    sys.exit(1)
print("Phase 2: initial extraction OK — advancing to Phase 3")
sys.exit(0)
PY
RC=$?
```

**Phase 2 authoring failure — required behaviour**:

If Step 3 rejected `generate.py`, OR Step 4's `python3 generate.py` blew up before producing `merged.txt`, OR Step 4's shape check reported groups=0 or total_controls=0, do the following in order:

1. Delete `$OUT/generate.py` if it exists (broken or absent, we don't want to inherit it into the next attempt).
2. Re-run Steps 1–4 once. A fresh subagent from a fresh prompt usually recovers from transient harness issues AND writes a smarter regex on the next attempt because it can look at the failing extraction as evidence.
3. If it fails a second time (Step 4 still reports groups=0 or controls=0), re-run once more. Between attempts, `tail -c 4000 $OUT/_author_agent.jsonl` — this is the one place where you may glance at subagent output, and only when authoring has visibly stalled.
4. If the third attempt still fails, STOP. Do NOT proceed to Phase 3 with an empty catalog. Do NOT synthesise generate.py yourself. End your turn by clearly stating to the user: (a) that `generate.py` could not extract a non-empty catalog even after three tries, (b) `groups` / `total_controls` from the last attempt (both should be zero if you reach this point), (c) the last 40 lines of `$OUT/_author_agent.jsonl` (or "log file empty"), and (d) suggest checking whether the PDF's structure needs a hand-tuned `PATTERNS` block. The wrapping CLI will surface the empty catalog as a non-zero exit automatically.

**Why the shape check is stricter than "file exists"**: `generate.py` can legitimately write a `catalog.json` shaped like `{"catalog": {"metadata": {...}, "groups": []}}` when its `PATTERNS["section"]` regex doesn't match anything in the PDF. That file is 1–2 KB and passes `[ -s catalog.json ]`, but it is not a usable extraction — it is a signal that Phase 2 authoring got the regex wrong. The Phase 3 subagent, given such a catalog.json summary, has no basis for populating `required_groups` and will guess badly. Fix Phase 2 before advancing.

#### Extraction is requirement-agnostic; exclusion happens in a second `generate.py` run

The Phase 2 author subagent read the whole PDF to write `generate.py`, so by the time it finishes it already has a document-wide view of which numbered units (and which whole chapters) are genuine requirements and which are not (definitions articles, commencement clauses, purely administrative text — see "What is an OSCAL Catalog" above). **The final `catalog.json` must not contain those units.** This is achieved in two passes within the same Phase 2 subagent session, not by ever writing requirement-vs-non-requirement logic into `parse_structure()`:

1. **First `generate.py` run (Step 4, above).** `parse_structure()` extracts every numbered unit in the PDF as a control, full stop, exactly as before — this pass has no concept of "excluded" and never will. This is what makes a missing control at this stage unambiguous: it's always a regex bug, never a judgment call.
2. **The subagent writes `$OUT/excluded_units.json`** (Step 4.5): a JSON object with two sections — top-level control IDs to omit individually, and (optionally) a `_groups` section listing whole groups to omit along with their merged.txt header string. Both are keyed off the catalog.json the first run just produced, with a one-line reason each. Empty object `{}` if the subagent found nothing to exclude — that is a normal, common outcome, not a failure.
3. **Second `generate.py` run (Step 4.6).** The SAME command as Step 4, run again. `assemble_catalog()` in the shared library `generate_lib.py` reads `excluded_units.json` at this point and: (a) OMITS every top-level control ID from `catalog.json`, (b) OMITS every group ID under `_groups` from `catalog.json` entirely (the whole group is skipped, not just its controls). A group whose control-level exclusions leave it with zero controls is NOT silently dropped — it is emitted with `controls: []` and Rule 2 will flag it, prompting the fix subagent to either move the group into `_groups` or reconsider its control-level exclusions. This is the run whose output is the actual deliverable.

```json
{
  "eu-gdpr-94": {"reason": "Repeal of Directive 95/46/EC — administrative provision; no obligation."},
  "eu-gdpr-99": {"reason": "Entry into force clause — commencement provision; not a substantive requirement."},
  "_groups": {
    "eu-gdpr-chapter-i": {
      "reason": "General provisions — Subject-matter, Scope, Definitions; entire chapter is introductory and imposes no obligations of its own.",
      "merged_txt_header": "Chapter I"
    }
  }
}
```

**Failure modes seen in the wild — do not repeat.** Four specific mistakes have been observed in real Phase 2 runs and are called out here so the subagent (and the orchestrator's verification) can catch them by name:

1. **Author `excluded_units.json` but skip the second `generate.py` run.** The file on disk does nothing on its own; without Step 4.6 the excluded IDs remain in the delivered `catalog.json` and the pipeline still reports PASSED. The Step 4.6 leak-check below is the guard against this — do not print "DONE" until it passes.
2. **Inline the exclusion filter inside your own `generate.py` (e.g. `for ctrl in group["controls"]: if ctrl["id"] in excluded_units: continue`) instead of routing catalog assembly through the invariant callable `assemble_catalog()` in the shared library `generate_lib.py`.** Assembly is a single call; do not re-implement it. See "Invariant assembly boundary" in the Phase 2 authoring prompt.
3. **Set `skip_rule_10_sequential_gaps=True` in `validate_config.py` to silence gap errors caused by exclusions.** That flag is for source-numbering gaps only; it silences the whole document. `excluded_units.json` already downgrades each listed ID's gap to INFO with its reason (see Rule 10 handling in Phase 4 below). Reaching for the skip flag when the gap is already covered per-ID is solving the wrong problem — the fix is to let `validate.py` see `excluded_units.json`, not to disable the check.
4. **List every control of an introductory chapter (Chapter I: Subject-matter, Scope, Definitions) individually at the top level, expecting the group to disappear.** It doesn't — `assemble_catalog()` deliberately keeps the group in `catalog.json` as `controls: []` when all its controls are removed, so Rule 2 (no empty groups) will fire and, because there is no `_groups` entry, Rule 12 will ALSO fire ("Chapter I in merged.txt but missing from catalog"). The two errors combined create a modification loop the fix subagent cannot escape without human help. The correct handling for whole-chapter exclusion is a single entry under `_groups` (with `merged_txt_header`) — see the schema example above. This is the exact failure mode observed on the GDPR sample on 2026-07-22.

Requirements on this file:

- **Top-level keys must be real control IDs, `_groups` keys must be real group IDs, both as they appeared in the FIRST `generate.py` run's `catalog.json`.** The subagent cross-checks every key against that first-pass output — an ID that never existed is a bug in this file, not a valid entry.
- **`_groups` entries must include `merged_txt_header`**, the exact heading string that `merged.txt` contains for that group (typical forms: "Chapter I", "Part 1", "Schedule 2"). Rule 12 uses this to accept the resulting group-level gap; a wrong or missing header string leaves Rule 12 firing.
- **Every value needs a specific, one-line reason**, not a placeholder. "Not a requirement" alone is not acceptable; "Defines terms used elsewhere; states no obligation" is.
- **When genuinely unsure whether a unit is a requirement, leave it OUT of this file.** An ID left out simply stays in the final catalog as a normal control — that is the safe default. Over-including silently deletes a real requirement from the deliverable with no trace beyond a reason string in a file nobody may open (see the Phase 5/6 review requirements below, which exist specifically to counter this).
- This file is authored **once**, in Phase 2. Phase 4 fix subagents do not add to it — see Phase 4's Rule 10 handling below for why.
- **The second `generate.py` run (Step 4.6) is mandatory whenever `excluded_units.json` is non-empty.** Writing the file alone does nothing — `catalog.json` on disk after Step 4 already exists and will NOT update itself. If Step 4.6 is skipped, the excluded units remain in `catalog.json` silently, which is a Phase 2 failure per the check below.

`build_author_prompt.py` already instructs the subagent to produce this file and re-run `generate.py` afterward as part of its Phase 2 deliverable. You (the orchestrator) still don't construct `excluded_units.json` yourself, but your Step 4 verification now has one more thing to check: after Phase 2 reports "DONE", confirm neither excluded control IDs nor excluded group IDs remain in the final `catalog.json`:

```bash
python3 - "$OUT" <<'PY'
import json, sys
out = sys.argv[1]
try:
    ex = json.load(open(f"{out}/excluded_units.json"))
except FileNotFoundError:
    ex = {}
excluded_controls = {k for k in ex if k != "_groups"}
excluded_groups = set(ex.get("_groups", {}).keys()) if isinstance(ex.get("_groups"), dict) else set()
c = json.load(open(f"{out}/catalog.json"))["catalog"]
control_ids = {ctrl["id"] for g in c.get("groups", []) for ctrl in g.get("controls", [])}
group_ids = {g["id"] for g in c.get("groups", [])}
leaked_controls = control_ids & excluded_controls
leaked_groups = group_ids & excluded_groups
if leaked_controls or leaked_groups:
    if leaked_controls:
        print(f"Phase 2: BROKEN — {len(leaked_controls)} excluded control id(s) leaked into catalog.json: {sorted(leaked_controls)}")
    if leaked_groups:
        print(f"Phase 2: BROKEN — {len(leaked_groups)} excluded group id(s) leaked into catalog.json: {sorted(leaked_groups)}")
    sys.exit(1)
print(f"Phase 2: exclusion OK — {len(excluded_controls)} controls excluded, {len(excluded_groups)} groups excluded, 0 leaked")
PY
```

If this reports a leak, the subagent skipped or mis-ran Step 4.6 — treat it as a Phase 2 authoring failure per the retry discipline below (do not hand-fix `catalog.json` yourself; re-launch Phase 2 so the subagent re-runs `generate.py` correctly). A missing `excluded_units.json` is not an error — treat it as `{}` and move on.

Second Step 4 verification: **the assembly boundary is intact.** The subagent's `generate.py` must route catalog assembly through the shared `generate_lib.assemble_catalog()` — not open-code its own exclusion loop, and not edit or duplicate `generate_lib.py`. This block enforces that; failures follow the SAME retry discipline as the leak-check above (delete `$OUT/generate.py` and `$OUT/generate_lib.py`, re-launch Phase 2, up to 3 attempts before escalating):

```bash
python3 - "$OUT" "$SKILL_DIR/scripts/generate_lib.py" <<'PY'
import hashlib, pathlib, re, sys
out = pathlib.Path(sys.argv[1])
lib_source = pathlib.Path(sys.argv[2])
gen = out / "generate.py"
gen_lib = out / "generate_lib.py"

def fail(msg):
    print(f"Phase 2: BROKEN — {msg}")
    sys.exit(1)

if not gen.is_file():
    fail("generate.py missing")
text = gen.read_text(encoding="utf-8")
if "assemble_catalog(" not in text:
    fail("no assemble_catalog(...) call site in generate.py — assembly boundary breached")
if "EXCLUSION-POINT:" not in text:
    fail("EXCLUSION-POINT marker comment missing from generate.py — required at the assemble_catalog call site")
if re.search(r"^def\s+assemble_catalog\s*\(", text, re.M):
    fail("generate.py defines its own assemble_catalog — shadowing the shared function is forbidden")
if not gen_lib.is_file():
    fail("generate_lib.py sibling copy missing — Phase 2 subagent must copy it verbatim next to generate.py")
if hashlib.sha256(gen_lib.read_bytes()).hexdigest() != hashlib.sha256(lib_source.read_bytes()).hexdigest():
    fail("generate_lib.py bytes differ from the shipped source — the sibling copy must be verbatim (READ-ONLY)")
print("Phase 2: assembly boundary OK")
PY
```

If this fails, delete `$OUT/generate.py` AND `$OUT/generate_lib.py` and re-launch Phase 2 exactly as before — do not hand-patch the subagent's files. The subagent needs to re-author `generate.py` from the template and re-copy `generate_lib.py`; hand-editing here would mask the underlying failure mode from the retry cycle.

### Phase 3 — Author `validate_config.py` (subagent authors CONFIG only)

**Skip this phase entirely if `$OUT/validate.py` already exists.** In re-run mode the existing validator is trusted as-is; do not overwrite `validate.py`, do not rewrite `validate_config.py`, do not launch the Phase 3 subagent. Proceed directly to Phase 4.

Phase 3 has TWO deliverables on disk when it completes:

  - `$OUT/validate.py`         — copied verbatim from the skill's template by YOU (the orchestrator). Subagents never touch this file.
  - `$OUT/validate_config.py`  — small CONFIG dict written by the Phase 3 subagent, imported at runtime by validate.py.

Splitting the config out into its own tiny file (~60–90 lines) is a
deliberate design choice: it makes it structurally impossible for the
subagent's `write_to_file` to truncate the 1,700-line rule body of
validate.py (a reproducible failure mode we saw with the old design
where subagents rewrote the whole validate.py from scratch and hit the
LLM's output-token limit).

```bash
# Step 1: Orchestrator copies validate.py from the template. This is
# a deterministic file-copy — no subagent involvement, no chance of
# truncation. The template is version-controlled inside the skill.
cp $SKILL_DIR/scripts/validate_template.py $OUT/validate.py

# Sanity-check that validate.py is on disk and parses. This should
# always pass because it's a straight cp — a failure here means the
# skill install is broken, not a subagent problem.
python3 -c "import ast; ast.parse(open('$OUT/validate.py').read())" \
    || { echo "SKILL BUG: template validate_template.py has a syntax error" ; exit 2 ; }

# Step 2: Build the validate-config authoring prompt. It embeds a
# catalog.json summary and the group-header lines it can find in
# merged.txt, so the subagent doesn't have to grep either itself.
python3 $SKILL_DIR/scripts/build_validate_prompt.py $OUT
# → writes $OUT/_validate_prompt.txt

# Step 3: Spawn the validate-config authoring subagent via your
# harness's native subagent tool. Its prompt should be exactly this
# (interpolate $OUT first):
#
#   Read the prompt file at $OUT/_validate_prompt.txt and follow its
#   instructions verbatim. Author $OUT/validate_config.py with a CONFIG
#   dict that matches the catalog.json summary the prompt embeds. Do
#   not invent rules; only populate the fields the prompt asks for.
#   When done, reply with a one-line summary: "phase-3: wrote
#   validate_config.py with R rules".
#
# The subagent tool returns synchronously; proceed to Step 4 once it
# does.

# Step 4: Verify validate_config.py is on disk, parses as Python,
# and defines a CONFIG dict. If any check fails, retry per
# "Phase 3 authoring failure" below — do NOT inherit a broken
# validate_config.py into Phase 4.
if [ ! -s $OUT/validate_config.py ]; then
  echo "Phase 3: MISSING validate_config.py — re-spawn the subagent"
elif ! python3 -c "import ast; ast.parse(open('$OUT/validate_config.py').read())" 2>&1; then
  echo "Phase 3: validate_config.py has a syntax error"
  rm -f $OUT/validate_config.py
elif ! python3 -c "import sys; sys.path.insert(0, '$OUT'); from validate_config import CONFIG; assert isinstance(CONFIG, dict) and 'name' in CONFIG" 2>&1; then
  echo "Phase 3: validate_config.py does not define a valid CONFIG dict"
  rm -f $OUT/validate_config.py
else
  echo "Phase 3: validate_config.py OK"
fi

# Step 5: Meta-check that the orchestrator's copy of validate.py still
# has all 17 rule functions (this is a check on the template, not on
# the subagent's work). Should always pass.
if ! python3 $SKILL_DIR/scripts/validate_validate_py.py $OUT/validate.py; then
  echo "SKILL BUG: template validate_template.py is missing rule functions"
  exit 2
fi

# Step 6: Smoke-run validate.py + subagent's validate_config.py against
# the current catalog. This is where CONFIG type errors surface as
# Python exceptions. If it raises, treat as Phase 3 authoring failure.
python3 $OUT/validate.py $OUT/catalog.json --merged $OUT/merged.txt \
    > $OUT/_validate_smoke.txt 2>&1
if grep -qE "Traceback|SyntaxError|IndentationError" $OUT/_validate_smoke.txt; then
  echo "Phase 3: validate.py raised an exception on first run (bad CONFIG?)"
  tail -c 3000 $OUT/_validate_smoke.txt
  rm -f $OUT/validate_config.py
  # → retry per "Phase 3 authoring failure" below
else
  echo "Phase 3: validate.py runs cleanly (may still report validation errors — that is Phase 4's job)"
fi
```

**Phase 3 authoring failure — required behaviour**:

Same discipline as Phase 2. If Step 4 or Step 6 rejects the produced `validate_config.py`, delete the broken file, re-run Steps 2–6 up to two more times. On the third failure, STOP with a clear user-facing message and let the CLI surface a non-zero exit.

Never proceed to Phase 4 with a `validate_config.py` that fails `import ast; ast.parse(...)`, fails the CONFIG-dict check, or causes `validate.py` to raise an exception on the smoke run. Note that `validate.py` itself (the file placed by `cp` in Step 1) is not something Phase 3 can break — if it fails those checks the skill install is corrupt, not a subagent problem.

### Phase 4 — Iterative Fix Loop (subagent per iteration)

This is the core work of the skill. You loop the following pattern until `validate.py` exits 0 OR you hit the iteration cap (default 15).

**Division of labour**:

- The **fix subagent** (per iteration) is responsible for the entire fix cycle within its own session: edit a file, re-run `generate.py`, re-run `validate.py`, verify progress vs the prior iteration, and revert its own change if it introduced a regression. It prints "DONE" only after it has produced a strictly-better `catalog.json` on disk.
- **You (main agent)** are responsible for orchestration only: capture the current validate output, build the fix prompt, launch the fix subagent, wait for it to finish, then read the fresh validate output to decide whether to loop again.

Because the fix subagent runs `generate.py` and `validate.py` itself, the main-agent iteration is now a straightforward launch-and-wait:

```bash
# --- One iteration ---
ITER=1                     # bump by 1 each round; you track this in your head or via a temp file

# (A) Capture the current validate output. On iteration 1 this is
#     Phase 3's smoke run; on later iterations it is whatever the
#     previous iteration's fix subagent left behind.
python3 $OUT/validate.py $OUT/catalog.json --merged $OUT/merged.txt \
    > $OUT/_validate_${ITER}.txt 2>&1
RC=$?
echo "iteration $ITER exit code: $RC"

# CRITICAL COMPLETION RULE:
# If RC == 0, YOU ARE DONE with Phase 4. Do NOT launch another fix
# subagent, do NOT re-run validate for "confidence", do NOT bump ITER
# "just in case". A passing validate means the catalog satisfies every
# non-informational rule and the only work left is Phase 5 final
# verification.
#
# In past runs the main agent, on seeing RC=0, launched an ITER+1 fix
# subagent "to be safe" — that subagent then wrecked a green catalog
# (adding a whitespace regex to postprocess_text, or slugifying IDs)
# and the run turned red again. The following tool call in Phase 4 on
# RC=0 must be the transition to Phase 5, nothing else.
if [ "$RC" -eq 0 ]; then
  echo "iteration $ITER PASSED — advancing to Phase 5, no further fix subagents"
  # break the fix loop here; skip straight to Phase 5.
fi

# BUILD-ERROR CHECK (non-zero RC that is NOT a rule failure):
# `validate.py` itself can crash — Python Traceback, SyntaxError,
# NameError from a fix subagent that broke validate.py or
# validate_config.py. This looks identical to a validation FAILED at
# the RC level (both are non-zero exit codes), but the treatment is
# opposite: on a real FAILED, fix generate.py / validate_config.py;
# on a Traceback, the *previous* fix subagent broke the config and
# must be REVERTED, not iterated on.
#
# Observed 2026-07-23: a fix subagent replaced
# `prose_contamination_patterns_anywhere: [...]` with `None`. Next
# iteration's validate.py exited with a Python TypeError. The main
# agent saw RC != 0 and launched fix iter N+1, which ran a NEW fix
# subagent against a *crashed* validate output — the subagent had
# nothing to fix, so it made cosmetic changes, and the loop repeated
# to iter 6+.
if [ "$RC" -ne 0 ] && grep -qE "^Traceback|SyntaxError|IndentationError|NameError|TypeError" $OUT/_validate_${ITER}.txt; then
  echo "iteration $ITER: validate.py CRASHED (not a rule failure). Reverting the last fix subagent's edit rather than iterating."
  # Do NOT launch a fix subagent for this iteration. Recovery paths:
  #   1. If the previous iteration's fix subagent touched validate_config.py,
  #      the change is at $OUT/validate_config.py. Restore from git if the
  #      file is tracked, or from the values reported in the smoke run's
  #      preceding _validate_$((ITER-1)).txt if it isn't.
  #   2. If the previous iteration touched generate.py, revert that file
  #      (git checkout, or restore from a prior _fix_agent_$((ITER-1)).jsonl
  #      inspection) and re-run pass 1/2.
  #   3. If it's not obvious which file was corrupted, STOP the loop and
  #      report the Traceback path to the user. Do NOT launch iter+1.
  # A fix subagent CANNOT fix a Traceback by editing generate.py — the
  # bug is in validate.py or validate_config.py, and continuing the loop
  # will only make things worse.
  exit 1
fi

# Otherwise, launch a fix subagent for this iteration:
if [ "$RC" -ne 0 ]; then
  # Snapshot generate.py mtime BEFORE launching — the fix subagent is
  # required to update generate.py OR validate.py by end of its
  # session, so we watch for a fresh mtime as a completion signal.
  BEFORE=$(python3 -c "import os,sys; print(os.path.getmtime('$OUT/generate.py'))")

  # Point the prompt builder at the PREVIOUS iteration's validate
  # output too (if this is iter >= 2) so the fix subagent can see what
  # its predecessor changed and whether progress was made. This is what
  # gives the subagent the ability to detect its own iteration having
  # made things WORSE and revert it as the first move.
  PREV_ARG=""
  if [ "$ITER" -ge 2 ]; then
    PREV_ITER=$((ITER - 1))
    if [ -s "$OUT/_validate_${PREV_ITER}.txt" ]; then
      PREV_ARG="--prev-validate-output $OUT/_validate_${PREV_ITER}.txt"
    fi
  fi

  python3 $SKILL_DIR/scripts/build_fix_prompt.py $OUT $ITER \
      --input-pdf <input_pdf> \
      --validate-output $OUT/_validate_${ITER}.txt \
      $PREV_ARG

  # Spawn the fix subagent via your harness's native subagent tool.
  # Its prompt should be exactly this (interpolate $OUT and $ITER first):
  #
  #   Read the prompt file at $OUT/_fix_prompt_${ITER}.txt and follow
  #   its instructions verbatim. It contains the current validate
  #   output, the prior iteration's validate output (if any), and the
  #   Rule → Fix decision table. Edit $OUT/generate.py and/or
  #   $OUT/validate_config.py in place, then re-run generate.py and
  #   validate.py once so the artefacts on disk reflect your fix.
  #   When done, reply with a one-line summary: "phase-4 iter ${ITER}:
  #   <what changed>, validate now K errors".
  #
  # The subagent tool is synchronous — it returns once the fix subagent
  # has finished editing and re-running. This prevents overlapping fix
  # subagents from clobbering each other's edits (which caused catalog=0
  # disasters in past runs) AND prevents the orchestrator from moving on
  # while the subagent is still mid-decision.

  # STALL GUARD (mandatory for iter >= 2):
  # After the fix subagent finishes and we have a fresh
  # _validate_${NEXT}.txt (i.e. next loop turn's capture), compare
  # against _validate_${ITER}.txt. If total error count AND per-rule
  # breakdown are BYTE-IDENTICAL, the fix subagent printed DONE without
  # producing progress. In-prompt warnings ("if the failure signature is
  # byte-identical, the previous edit didn't take effect") have been
  # observed to be ineffective on their own (ADGM-DPR-2021-Guidance,
  # 2026-07-27: 3 iterations back-to-back with 27 errors and identical
  # Rule 1/6a/11/12/16 counts, subagent shipped DONE each time).
  #
  # The check runs at the TOP of the next iteration, after step (A) has
  # captured _validate_${NEXT}.txt but before we build the next fix
  # prompt:
  #
  #   python3 $SKILL_DIR/scripts/detect_fix_loop_stall.py \
  #       $OUT/_validate_${ITER}.txt \
  #       $OUT/_validate_${NEXT}.txt
  #   STALL_RC=$?
  #
  #   Exit codes:
  #     0 — progress detected; continue normally
  #     2 — STALL detected; retry THIS iteration ONCE (keep ITER the
  #         same, rerun build_fix_prompt.py and spawn a fresh fix
  #         subagent). A fresh subagent is non-deterministic — one
  #         retry catches transient "subagent found nothing to change"
  #         outcomes.
  #     1 — cannot compare (missing/malformed file); treat as "unknown,
  #         continue looping" — do NOT abort on exit 1.
  #
  # If the retry ALSO produces exit 2, break the fix loop and exit
  # Phase 4 with failure. Do NOT keep iterating on a stall — the
  # catalog.py wrapper's phase-4-fix-loop recovery pass will pick up
  # the fresh on-disk state in a clean context, which is more
  # productive than another ineffectual iteration in the current
  # session.
fi
```

Then bump `$ITER` and repeat.

**Why the wait target changed from `generate.py` to the subagent log.**
Earlier versions of this skill waited on `generate.py`'s mtime being
newer than `$BEFORE`. That was correct for detecting "the subagent
made an edit" but wrong for detecting "the subagent finished making
edits". In production we saw four fix subagents live simultaneously
because each mtime bump was interpreted as completion. Watching the
subagent's own log for size stability closes that race: the log is
exclusive to one subagent and grows monotonically until end of
session, so a size-stable window is a reliable
"this subagent is done" signal.

**Important**: You do NOT run `generate.py` in the main-agent shell between iterations. The fix subagent runs it itself inside its own session as part of verifying its edit, so `catalog.json` is already up-to-date on disk when the subagent prints "DONE". Running `generate.py` again in the main-agent shell after the subagent finished would (a) waste tokens, (b) be redundant, and (c) risk racing with a subagent that might still be tail-writing. Trust the subagent's self-verification.

**Rules for the loop:**

- **PASSED is the terminal state. No re-check, no extra iter.** The instant `python3 validate.py catalog.json --merged merged.txt` exits 0, Phase 4 is over. Do NOT run a second validate for confirmation, do NOT launch another fix subagent "just to tidy up", do NOT bump `ITER` "in case something regressed". Transition to Phase 5 as the very next tool call. Past runs have wrecked a green catalog by launching an extra fix subagent on RC=0 — the subagent then found something to "improve" (added a whitespace regex to postprocess_text, slugified IDs) and turned the run red again.
- **Do NOT read `_validate_${ITER}.txt`, `generate.py`, `validate.py`, or `merged.txt` yourself.** `build_fix_prompt.py` slices the relevant part into the fix prompt for the subagent, and the subagent will Read the scripts on its own. Reading these yourself in a Bash `cat` or a Read tool call is the failure mode this whole design is trying to prevent.
- **One subagent per iteration, ONE AT A TIME.** Iterations are sequential (each iteration depends on the previous `generate.py`), not parallel. Do not try to launch multiple fix subagents in parallel. The subagent tool returns synchronously, so as long as you wait for one spawn call to return before issuing the next, this is enforced naturally — do NOT bypass that by pipelining subagents.
- **Iteration cap.** If you reach iteration 15 and validate.py still fails, stop and report the last `_validate_${ITER}.txt` path to the user. Do not keep looping past this cap silently. This is a safety valve for degenerate PDFs — most real documents complete in 3–8 iterations.
- **Stall guard.** From iteration 2 onward, before launching the next fix subagent, invoke `scripts/detect_fix_loop_stall.py $OUT/_validate_${ITER-1}.txt $OUT/_validate_${ITER}.txt`. Exit 2 = stall (error count AND per-rule breakdown identical to the previous iteration). On stall, retry the SAME iteration once (a fresh subagent may not repeat the no-op). If the retry also returns exit 2, break the fix loop and exit Phase 4 with failure — the catalog.py wrapper's `phase-4-fix-loop` recovery pass will pick up the on-disk state in a fresh context. Do NOT ignore exit 2 and keep looping; the observed cost of a bob fix subagent is 5–10 minutes and a stalled loop can burn an hour before hitting the iteration cap. Exit 1 (missing/malformed file) is "cannot compare" — treat as inconclusive and continue.
- **Idempotency.** The scripts are idempotent: re-running the same command with the same `$ITER` produces the same fix prompt. If a subagent fails to write, launch it again.
- **What runs in `generate.py`.** The `generate.py` script re-writes `merged.txt` and `catalog.json` from scratch each invocation. There is no incremental state — each iteration is a full re-extraction.
- **Degradation guard.** After each iteration, before launching the next fix subagent, check whether the catalog **regressed** (fewer groups or controls than the previous iteration, or the same validate output twice in a row):

  ```bash
  # Groups / controls in current catalog
  CUR_G=$(python3 -c "import json; c=json.load(open('$OUT/catalog.json'))['catalog']; print(len(c.get('groups',[])))" 2>/dev/null || echo 0)
  CUR_C=$(python3 -c "import json,sys; c=json.load(open('$OUT/catalog.json'))['catalog']; print(sum(len(g.get('controls',[])) for g in c.get('groups',[])) + len(c.get('controls',[])))" 2>/dev/null || echo 0)
  echo "iter $ITER: groups=$CUR_G controls=$CUR_C"
  ```

  If iteration N drops `groups=0` or `controls=0` when iteration N-1 had non-zero values, the fix subagent produced a regression — do NOT continue naively. Re-run the SAME iteration once (build_fix_prompt.py is deterministic, but the subagent is not; a fresh subagent may not regress). If the regression persists on the second attempt, STOP the loop and report to the user with the diff between `_validate_${N-1}.txt` and `_validate_${N}.txt`. The final saved `generate.py` should be the last version that had non-zero groups/controls — use `git` or file backups if you need to recover.

**Fix-loop failure — required behaviour**:

Same discipline as Phase 2/3 authoring. If you exit Phase 4 without exit-code-0 validation AND the failure isn't the "hit iteration cap" case, you MUST tell the user explicitly (last iteration number, path to `_validate_${LAST}.txt`, one-line summary of the failing rule). Do not report the run as complete when `catalog.json` still has failing validation rules. The wrapping CLI checks Completion Criteria at the end and surfaces missing artefacts as a non-zero exit; a `catalog.json` that fails validation is treated by the CLI as `missing` for completion-check purposes.

**Rule 10 (sequential gaps) judgment**: When Rule 10 reports missing controls, the fix subagent will look at merged.txt around the failing IDs and decide whether to fix `generate.py`'s regex or to treat the gap as intentional. There are two distinct "intentional" outcomes and the fix subagent must not conflate them:

- **The ID never existed in the source at all** (e.g. Austria-DSG jumps from Article 1 to 4 in the original law). This is a numbering gap, not a content gap — set `skip_rule_10_sequential_gaps: True` in `validate.py`'s CONFIG.
- **The ID exists in the PDF and has real text, but the fix subagent judges its content is non-requirement** (definitions, administrative text) and it has ALREADY been removed from `catalog.json` (by Phase 2's `excluded_units.json` + second `generate.py` run — see "Extraction is requirement-agnostic" above). By design, a removed control shows up in Rule 10's gap output exactly like a real extraction bug would — the removal is real, `catalog.json` genuinely no longer has this ID. Do NOT touch `skip_rule_10_sequential_gaps` for this case: check `excluded_units.json` first. If the ID is already listed there, Rule 10 downgrades it to INFO automatically (the validator cross-references the file — see Rule 10 in `validate_template.py`) and the fix subagent should move on. If the ID is judged non-requirement but is NOT yet in `excluded_units.json`, that is a Phase 2 omission the fix subagent may correct by adding an entry (same schema as Phase 2) — this adds the ID to the exclusion record, but note that `catalog.json` on disk right now was NOT built with this new entry in scope, so the fix subagent must also re-run `generate.py` in this same iteration for the removal to actually take effect (same two-pass requirement as Phase 2 Step 4.6).

You (main agent) do not need to intervene in this decision — it is the subagent's job, driven by what it sees in the merged.txt slice inside its prompt. What you do need to know: `skip_rule_10_sequential_gaps` and `excluded_units.json` solve different problems (numbering gaps that exist in the source vs. controls the pipeline itself removed as non-requirement) and are not interchangeable. A fix subagent that reaches for the skip flag to silence a gap actually caused by an exclusion is solving the wrong problem — re-running `generate.py` after updating `excluded_units.json` is what actually keeps Rule 10 honest for that ID going forward.

Both mechanisms downgrade the affected rule output from ERROR to INFO — the rule still runs and still reports, it just doesn't block completion.

### Phase 5 — Final Verification

After validation passes (exit 0):

0. **Late-write drift check.** Immediately after Phase 4 declares PASSED,
   snapshot the hash of `catalog.json`, `generate.py`, `validate.py`,
   and `validate_config.py`. Then run any Phase 5 checks. Before
   reporting the run complete, re-hash and confirm nothing changed
   between the snapshot and now.

   Rationale: some harnesses can flush buffered tool writes after a
   subagent's synchronous return. The subagent tool itself waits for
   the child's session end, which in practice covers most cases —
   but a very slow flush could still land during Phase 5. If a hash
   changes here, a lingering subagent write has clobbered the PASSED
   state and the run must restart Phase 4 from the current disk
   state (do NOT report success on a drifted catalog).

   ```bash
   python3 - "$OUT" <<'PY' > $OUT/_phase5_hashes.txt
   import hashlib, sys, pathlib
   out = pathlib.Path(sys.argv[1])
   for name in ("catalog.json", "generate.py", "validate.py", "validate_config.py"):
       p = out / name
       if not p.is_file():
           print(f"{name}: MISSING")
           continue
       h = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
       print(f"{name}: {h}  ({p.stat().st_size} bytes)")
   PY
   cat $OUT/_phase5_hashes.txt
   ```

1. Confirm `trestle validate` explicitly (validate.py's Rule 16 already runs it, but a standalone re-check is cheap):

   ```bash
   python3 $SKILL_DIR/scripts/validate_oscal_catalog.py --catalog $OUT/catalog.json
   ```

2. **Spot-check 3–5 controls against the PDF.** Pick controls from different groups. Open the PDF, find the corresponding section, and confirm the title and prose in `catalog.json` match. This catches subtle extraction bugs that no rule can detect.

3. Confirm the control count roughly matches the PDF's own count MINUS any exclusions. `$OUT/excluded_units.json` removes controls two ways: (a) individually via top-level control IDs, and (b) whole groups via the `_groups` section (which drops the group AND all its controls). So the expected count is `PDF sections − (individually-excluded controls + controls in excluded whole groups)`. E.g. if the TOC lists 99 articles and `excluded_units.json` has 2 top-level control entries plus one `_groups` entry for a chapter that contains 4 articles, the catalog should have ~93 controls in ~one-fewer-than-original groups. If the arithmetic doesn't add up, something is wrong: either an exclusion didn't take effect (re-run `generate.py`) or a real extraction gap is being masked.

4. **Re-hash and diff.** Before reporting the task complete, re-run
   the hash snapshot above and compare against `_phase5_hashes.txt`.
   If any hash differs, a lingering subagent write landed during
   Phase 5 — do NOT report success. Instead: re-run
   `python3 $OUT/validate.py $OUT/catalog.json --merged $OUT/merged.txt`
   on the current on-disk catalog. If it still PASSES, snapshot again
   and continue. If it FAILS, resume Phase 4 with the current state
   as iteration N+1.

   ```bash
   python3 - "$OUT" <<'PY' > $OUT/_phase5_hashes_final.txt
   import hashlib, sys, pathlib
   out = pathlib.Path(sys.argv[1])
   for name in ("catalog.json", "generate.py", "validate.py", "validate_config.py"):
       p = out / name
       if not p.is_file():
           print(f"{name}: MISSING")
           continue
       h = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
       print(f"{name}: {h}  ({p.stat().st_size} bytes)")
   PY
   if diff -q $OUT/_phase5_hashes.txt $OUT/_phase5_hashes_final.txt >/dev/null; then
     echo "Phase 5: no drift, artefacts stable"
   else
     echo "Phase 5: DRIFT DETECTED — late subagent write clobbered PASSED state"
     diff $OUT/_phase5_hashes.txt $OUT/_phase5_hashes_final.txt
     # → treat as Phase 4 failure and resume the fix loop from the CURRENT
     #   on-disk state
   fi
   ```

If any of the above fails, treat it as a Phase 4 failure: fix `generate.py`, re-run, re-validate.

### Phase 6 — Author `report.md` (subagent)

**Run this phase whenever `catalog.json` and `validate.py` are both on disk, regardless of whether validation is green.** This is a policy change from the earlier "only after Phases 1–5 pass" rule. Rationale: a catalog with a known-red validation is still more useful to the reviewer than *no* catalog at all — the report.md is where we communicate "here is what we extracted, here are the rules that stayed red, here is what the reviewer should look at." A run that stops before Phase 6 hands the reviewer nothing to work from.

The catalog.py wrapper drives the two branches:

- **Validation green** → Phase 6 as originally documented below. The report has no failure caveat to raise.
- **Validation red (best-effort completion)** → Phase 6 runs via a recovery pass with `--allow-failed-validation` passed to `build_report_prompt.py`. The report subagent is told upfront that validation did NOT return 0, is handed a per-rule digest of the failing rules from `_validate_final.txt`, and is required to surface both facts in `## Validation approach` and `## Points for human review`. The CLI then returns the best-effort exit code (see `tools/cli/catalog.py :: BEST_EFFORT_EXIT_CODE`) so downstream tooling can classify the run as `completed_best_effort` rather than `failed`.

The main agent almost never has to make this call itself — the catalog.py wrapper's `_verify_generate_outputs` decides whether to launch Phase 6 in normal or best-effort mode based on the final `validate.py` exit code. What the main agent needs to know is that Phase 6 is NOT gated on validation succeeding; a stuck fix loop should still hand off to Phase 6 rather than terminating the run early.

Phase 6 produces `$OUT/report.md`, the human-facing generation summary specified in SPEC §12.5. Its purpose is to let a reviewer decide whether to commit the outputs. Read SPEC §12.5 before authoring the prompt — the report has a fixed structure (Summary / What was built / Validation approach / Points for human review / Known limitations) and strict anti-goals (no rule-by-rule warning lists, no iteration transcripts).

```bash
# Step 1: Build the report prompt. This gathers the artefact statistics
# (control count, group breakdown, rule categories in validate_config.py,
# whether re-run mode was used) and hands the subagent a concrete brief.
python3 $SKILL_DIR/scripts/build_report_prompt.py $OUT <input_pdf>
# → writes $OUT/_report_prompt.txt

# Step 2: Spawn the report subagent via your harness's native subagent
# tool. It is a light-weight subagent: reads numbers from the prompt
# file, opens catalog.json / validate.py / merged.txt as needed, writes
# report.md in one shot. Budget 2–4 min. Its prompt should be exactly
# this (interpolate $OUT first):
#
#   Read the prompt file at $OUT/_report_prompt.txt and follow its
#   instructions verbatim. Write $OUT/report.md in one shot, following
#   the SPEC §12.5 structure the prompt embeds. When done, reply with
#   a one-line summary: "phase-6: wrote report.md, N sections".
#
# The subagent tool is synchronous — proceed to Step 3 once it returns.
```

The Main Agent's role in Phase 6 is minimal — just launch the subagent, wait for the file, and confirm it is non-empty and starts with a level-1 heading. **Do not edit `report.md` yourself.** If the subagent produces something that clearly fails the SPEC §12.5 structure (missing a required section, or the "Points for human review" section is packed with individual rule warnings instead of judgment calls), rebuild the prompt once and retry. Two failed attempts → escalate; do not hand-write a substitute.

When you are in re-run mode (Phase 0), pass this information through to the report prompt via `build_report_prompt.py`'s `--rerun` flag and, if `generate.py` was patched during the Phase 4 repair sub-loop, `--patched generate.py:<one-line-reason>`. The subagent will fold this into the report's "What was built" section per SPEC §13.5.

**Do not**:

- enumerate the specific validation errors that were fixed during Phase 4 — the reader trusts the pipeline has already resolved them,
- include the full JSON schema of `catalog.json` — a shape summary (control count, group breakdown) is enough,
- describe the pipeline itself — this is a report about the artefact, not about the tool that built it.

**Reader model — the report is self-contained.** The reader of
`report.md` is a compliance / GRC practitioner who is looking at the
finished output directory. They know **nothing** about the internals of
this skill — they do not know what `validate.py` contains, do not know
what `validate_config.py` is for, do not know what "Phase N" means, and
do not know what CONFIG keys like `header_lines` or `toc_pages` do.
Anything they need in order to trust the output has to be **stated in
plain language in the report itself**. When you inspect the subagent's
draft, watch for two classes of mistake in particular:

1. **"No validation rules applied" / "schema-only validation" /
   "0 rules"** — these all misrepresent the run. `validate.py` carries a
   fixed set of ~15 built-in rules that ALWAYS run; `validate_config.py`
   only supplies parameters (required groups, expected counts) for those
   rules. If the draft's "Validation approach" section could lead the
   reader to conclude the catalog was not properly validated, rebuild
   the prompt and re-launch Phase 6. This is exactly the failure that
   SPEC §12.5.3 forbids.
2. **CONFIG defaults surfaced as review concerns** — bullets like
   "Header/footer stripping disabled" or "use_ocr=False" list a normal
   outcome (this PDF did not need those facilities) as if it were a
   review item. Empty `required_sections`, `header_lines=0`, and
   `use_ocr=False` are not defects. They belong in the report only if
   the extractor made a non-obvious choice the SME should verify —
   otherwise they should not appear at all.
3. **A non-empty `excluded_units.json` not reflected in "Points for
   human review"** — per SPEC §12.5.2, if `$OUT/excluded_units.json`
   contains any entries (either top-level control IDs OR entries under
   `_groups`), the report MUST list every entry with its reason, AND
   must say plainly that the content was REMOVED from the catalog:
   - For control-level exclusions: "Article 4 (Definitions) was
     extracted, judged non-requirement, and removed from the final
     catalog; it does not appear in catalog.json."
   - For whole-group exclusions: "Chapter I (General provisions) was
     extracted in full but judged introductory / non-normative and
     removed from the catalog as a whole; neither the chapter nor any
     of its articles appear in catalog.json."
   This is not optional even when the rest of the run was clean. Check
   this explicitly: `cat $OUT/excluded_units.json` and confirm each
   top-level control ID and each `_groups` entry appears by name in the
   report before treating Phase 6 as done. Omitting either kind is the
   same class of error as under-reporting validation coverage — the
   reviewer loses the one piece of information that tells them the
   catalog's control and group counts are smaller than the source
   document's, and why.

`build_report_prompt.py` embeds all three of these guard rails into
the subagent prompt, but the Main Agent is the last line of defence —
if you spot any of these mistakes in `report.md`, do not commit it;
rebuild the prompt and retry.

## Completion criteria

Two levels of completion are recognised — full and best-effort. The main agent aims for **full**; the catalog.py wrapper falls back to **best-effort** when Phase 4 has genuinely stalled AFTER the recovery pass has also been used up. Do not aim for best-effort intentionally — but do NOT terminate the run early to avoid Phase 6 either; a best-effort report is strictly better than no report.

### Full completion (goal)

ALL of these are true:

- `<output_dir>/generate.py` exists and is executable
- `<output_dir>/validate.py` exists and is executable
- `<output_dir>/catalog.json` exists **and contains at least one group and at least one control** (files with only metadata do NOT satisfy this criterion)
- If `<output_dir>/excluded_units.json` is non-empty, **neither its top-level control IDs nor its `_groups` group IDs appear in `<output_dir>/catalog.json`** (see the leak check in Phase 2) — an excluded ID still present in the final catalog means Phase 2's second `generate.py` run did not happen or did not take effect
- `python3 <output_dir>/validate.py <output_dir>/catalog.json --merged <output_dir>/merged.txt` exits with code 0
- Rule 16 (`trestle validate`) is green
- Spot-check confirms no obvious divergence from the PDF
- `<output_dir>/report.md` exists, is non-empty, starts with a top-level Markdown heading, and contains all five sections mandated by SPEC §12.5.2 (Summary / What was built / Validation approach / Points for human review / Known limitations)

If your Bash tool call returned but the catalog is not validated, the skill is **NOT** fully done — re-run the loop within the iteration cap. A `catalog.json` with `groups: []` and `controls: []` is NOT a valid completion state; it is a mid-loop artefact and Phase 4 must continue.

### Best-effort completion (fallback the CLI applies when full completion is unreachable)

The catalog.py wrapper accepts these as "deliverables shipped" (any downstream orchestrator classifies this state as `completed_best_effort`, exit code = `BEST_EFFORT_EXIT_CODE`):

- `catalog.json` exists and contains at least one group and at least one control
- `generate.py`, `validate.py` exist
- `report.md` exists AND was authored in `--allow-failed-validation` mode so it names the failing rules and marks validation as red

Best-effort is **not** something the main agent should aim for — always try to converge Phase 4. But if the fix loop's cap-and-stall guards trigger AND the phase-4-fix-loop recovery pass also gives up, the CLI will drive one more Phase 6 recovery in best-effort mode so the reviewer receives a report describing what stayed broken and why, rather than a bare non-zero exit.

**Do not report the task as complete, and do not call `attempt_completion`, until you have reached at least the best-effort criterion.** See "CRITICAL: Do not give up mid-loop" earlier in this document for the specific rationalisations that are forbidden — those still apply. What the best-effort mechanism enables is *the CLI* completing the pipeline for you when the fix loop hits a wall; it does NOT license terminating the main-agent session early with a "template limits reached" narrative.

## Control ID Naming Convention

Control IDs and group IDs generated by `generate.py` must follow the rules below. Fix subagents that modify `parse_structure()` or the sanitizers must preserve these rules; if they don't, the catalog looks superficially valid but is unusable downstream (Rule 10 breaks, cross-references drift, `trestle validate` rejects some IDs even when Rule 15 is silent, and re-runs produce non-reproducible IDs because titles carry kerning artifacts).

### Allowed characters

- Lowercase letters (a–z)
- Digits (0–9)
- Hyphens (`-`) as segment separators

**NOT allowed**: underscores, uppercase, periods, parentheses, brackets, spaces, any Unicode.

### Preferred pattern for control IDs: `<prefix>-<article-number>`

This skill targets law / regulation / standard PDFs, and the near-universal case is that each Article (or Section, Rule, Principle, Practice) is a control. The generated control ID should be the article number, prefixed:

| PDF structure | Correct control IDs |
|---|---|
| EU GDPR: Article 1 … Article 99 | `eu-gdpr-1`, `eu-gdpr-2`, …, `eu-gdpr-99` |
| HK PDPO: Section 1 … Section 71 | `hk-pdpo-1`, `hk-pdpo-2`, …, `hk-pdpo-71` |
| NIST SP 800-53: AC-1, AC-2, AU-1 … | `nist-800-53-ac-1`, `nist-800-53-ac-2`, `nist-800-53-au-1` |
| C2M2: ASSET-1a, ASSET-1b, THREAT-2a | `asset-1-a`, `asset-1-b`, `threat-2-a` |

Group IDs follow the same convention (e.g. `eu-gdpr-chapter-i`, `hk-pdpo-part-1`, `nist-800-53-ac`).

### ANTI-PATTERN — slug-based control IDs (FORBIDDEN)

Do NOT build control IDs by slugifying the extracted title. These IDs are invalid for this skill and any fix subagent that produces them must be re-run:

```
✗  gdpr-chapter-i-conditions-for-consent
✗  gdpr-chapter-i-def-initions             ← "definitions" broken by kerning
✗  gdpr-chapter-vi-acti-vity-repor-ts      ← "activity reports" broken by kerning
✗  gdpr-chapter-vii-mutual-assist-ance     ← "mutual assistance" broken by kerning
✗  gdpr-chapter-i-the-controller-shall-communicate-any-rectifi-cation-or-erasure-of-personal-data-or-restr-iction-of-processing-...
```

Why forbidden:

1. **Rule 10 (sequential gaps) is neutered.** Rule 10 inspects the numeric part of each ID to detect missing articles. Slug IDs have no numeric part, so an entire class of extraction bugs (missing Article 63, missing Article 89, …) becomes silent.
2. **kerning artifacts leak into IDs and destabilise them across re-extractions.** `pdfplumber` may render "Definitions" cleanly one run and as "Def initions" another; the slug switches between `-definitions` and `-def-initions`; downstream references break.
3. **Titles are not stable keys.** OSCAL identifies controls across profile inheritance, mapping collections, and audit reports by ID. If two catalogs of the same regulation use different slug IDs (because subagents generated titles differently), cross-catalog operations break.
4. **Long slugs make the catalog unreadable.** A 120-character ID like `gdpr-chapter-i-the-controller-shall-communicate-any-...-processing-car-ried-out-in` is a symptom, not just an aesthetic issue.

If `PATTERNS["section"]` in your `generate.py` cannot find `Article N` (or `Section N`, `Rule N`, etc.) as bare lines and you're tempted to make each in-article heading into a control, the correct fix is to **fix the section regex**, not to redefine the extraction unit. Consult SPEC §5 and the merged.txt slice around the failing IDs to see how article headers are actually formatted in this PDF.

### Sanitizers

`generate.py` template provides two helpers:

- `sanitize_oscal_id()` — enforces the character rules above (lowercases, replaces disallowed chars with `-`, prefixes `ctrl-` if the raw ID starts with a digit)
- `sanitize_title()` — replaces newlines with spaces in titles (Rule 15 compliance)

These MUST be used for every ID and title `generate.py` emits. Fix subagents must not bypass them.

## ABSOLUTE PROHIBITION — read this carefully

These apply to both the main agent and any subagent it launches:

- **NEVER edit `catalog.json` by hand to make validation pass.** If validate.py fails, the fix goes in `generate.py` (or, for completeness rules like 6/6a/6b/13, in `validate.py` CONFIG). Hand-editing `catalog.json`:
  - Violates the anti-hallucination principle
  - Is lost the next time `generate.py` runs
  - Leaves the underlying regex bug in place, so the same problem recurs for other controls
- **NEVER modify `scripts/generate_template.py` or `scripts/validate_template.py`.** These are the pristine template originals shipped with the skill. The subagent authoring phase writes customized copies to `<output_dir>/generate.py` and `<output_dir>/validate.py`; the templates themselves are inputs to `build_author_prompt.py` and must remain unchanged.
- **NEVER add title lookup dictionaries (`PART_TITLES`, `SCHEDULE_TITLES`, `SECTION_TO_PART`, etc.) to `generate.py`.** All titles must be captured from the PDF via regex.
- **NEVER skip populating `required_groups`.** An empty `required_groups` causes Rule 13 to fail explicitly; if that were somehow bypassed, Schedule 2-6 could be silently dropped and validation would still "pass" — the opposite of what you want.
- **NEVER end the run with an empty or partial catalog by reporting "template limits" or "custom parser required".** Editing `PATTERNS` and `parse_structure()` in `<output_dir>/generate.py` for the specific document is the intended work of Phase 4 — it is NOT a violation of the anti-hallucination principle and it is NOT out of scope. If the document has an unusual structure, write regex/parse logic that captures its actual structure; do not abandon the loop. See "CRITICAL: Do not give up mid-loop" for the full list of forbidden exit rationalisations.
- **NEVER generate control IDs by slugifying the title.** Control IDs must be `<prefix>-<article-number>` (e.g. `eu-gdpr-5`), never `gdpr-chapter-i-conditions-for-consent` or `gdpr-chapter-i-def-initions`. See "Control ID Naming Convention" above for why. If your `parse_structure()` can't extract Article numbers, fix the section regex — do NOT fall back to title-based IDs as a workaround.

Additional prohibitions specifically for the **main agent** (as orchestrator):

- **NEVER open `merged.txt`, `_validate_${ITER}.txt`, `generate.py`, or `validate.py` with Read / Edit / apply_diff / grep / sed / cat.** Those files are the subagent's input material. The main agent's job is to run scripts and launch subagents, not to read or edit source-of-truth files. Doing so bloats your context and destabilises later iterations.
- **NEVER inline the fix-loop reasoning yourself.** If a fix subagent's output doesn't produce progress, the fix is (a) re-run the same iteration once (it may have been a transient subagent hiccup), or (b) if it fails twice on the same rule, stop at the iteration cap and escalate to the user with the last `_validate_${ITER}.txt` path. Do not take over the editing yourself.

## Troubleshooting (main-agent view)

The main agent almost never diagnoses individual regex or CONFIG problems — that's the fix subagent's job. But there are a few skill-level failure modes the main agent needs to recognise and respond to:

### Phase 2 authoring fails (subagent produces no `generate.py`, or a broken one)

**Symptom**: after Phase 2's launch, `$OUT/generate.py` is missing, empty, or fails `python3 -c "import ast; ast.parse(...)"`. Also: `python3 generate.py` blows up before producing `merged.txt` / `catalog.json`.

**Diagnosis**: tail `_author_agent.jsonl` (a rare exception where reading the subagent log is warranted). Common causes:
- Subagent timed out (extend `-t` in the launch, e.g., 900 → 1500)
- Subagent's harness rejected the prompt due to a size limit (reduce `--merged-head-lines` in `build_author_prompt.py`)
- Subagent Write got truncated mid-file (the syntax check catches this)

**Action**: delete the broken `generate.py` and re-run Phase 2 (`build_author_prompt.py` → spawn author subagent). Subagent runs are independent; a fresh session usually recovers.

### Phase 3 authoring fails (validate_config.py broken or missing)

**Symptom**: `$OUT/validate_config.py` is missing, has a syntax error, does not define a valid `CONFIG` dict, or causes `validate.py` to raise a Python exception on the smoke run in Phase 3 Step 6.

**Note**: `$OUT/validate.py` itself is produced by an orchestrator `cp` from the template and is not something the subagent can break. If the smoke run fails, the fault is in `validate_config.py`, not `validate.py`.

**Cause**: the validate-config subagent's write was malformed (unterminated string literal in a regex, a CONFIG value of the wrong type, or extraneous code around the `CONFIG = {…}` literal).

**Action**: delete the broken `validate_config.py` (or let Phase 3's Step 4 do it for you) and re-run Phase 3 Steps 2–6 (`build_validate_prompt.py` → spawn validate-config subagent). A fresh subagent starts from the template with the corrected shape reference. Do NOT re-copy `validate.py`; it was correct the first time.

### Fix loop makes no progress across iterations

**Symptom**: iterations 5, 6, 7 all fail with the same rule number.

**Diagnosis**: subagent may be stuck on an edge case. Look at the tail of `_fix_agent_${ITER}.jsonl` for that iteration — either the subagent is doing nothing (regressed to a no-op), or it's making cosmetic edits that don't move the needle.

**Action**:
1. Re-run the same iteration once — subagents are non-deterministic, one bad run doesn't mean the design is stuck.
2. If two consecutive re-runs of the same iteration still stall, escalate to the user: cite the last `_validate_${ITER}.txt` and the failing rule. Do not silently keep iterating past the cap of 15.

### `validate.py` reports Rule 13 (empty `required_groups`)

**Cause**: the authoring subagent produced a `validate.py` with a placeholder `required_groups = []`.

**Action**: this should be fixable by one fix iteration (the fix subagent will scan `merged.txt` for group headers and populate the list). If it persists across 2 iterations, delete `$OUT/validate.py` and re-run Phase 3 to get a fresh one — the initial state was too broken to recover from incrementally.

### Everything below is subagent-facing reference

The following symptoms and fixes are the material the **fix subagent** navigates using its embedded slice of `merged.txt`. The main agent does not act on these directly, but keeps them here as a shared reference so both parties understand the target behaviour.

### Broken word spacing (pypdf kerning issue)

**Symptom**: extracted text has spurious spaces inside words:
- `"Gener al provisions"` instead of `"General provisions"`
- `"f or"`, `"la w"`, `"t o"` scattered through prose

**Detection**:

```bash
grep -E '\b[a-z]\s[a-z]\b' $OUT/merged.txt | head
```

If you see patterns like `f or` or `la w`, this is the kerning issue.

**Fix**: In `$OUT/generate.py` CONFIG:

```python
CONFIG = {
    ...,
    "use_pdfplumber": True,
}
```

Regenerate. pdfplumber is slower but handles kerning better.

### Empty or short titles

**Symptom**: some controls have `title: ""` or 1-2 character titles.

**Common causes**:

1. `garbage_line_patterns` filters short but legitimate titles (`"Tasks"`, `"Chair"`). Loosen the pattern:

   ```python
   # WRONG — filters legitimate short titles
   r"^.{0,5}$"
   # RIGHT — only filter 1-2 char lines
   r"^.{0,2}$"
   ```

2. Multi-line title not merged. Check `parse_structure()`'s title-continuation logic. The template already handles common cases (prepositions/articles at end of line, lowercase continuation, structural marker to stop), but very specific PDFs may need custom stop conditions.

**Detection**:

```bash
python3 -c "
import json
with open('$OUT/catalog.json') as f:
    c = json.load(f)
for g in c['catalog']['groups']:
    for ctrl in g.get('controls', []):
        if not ctrl['title'] or len(ctrl['title']) < 3:
            print(f'{ctrl[\"id\"]}: \"{ctrl[\"title\"]}\"')
"
```

### Number-only headings (Section 1.1 followed immediately by prose)

**Symptom**: `trestle validate` fails with "string does not match regex" on `title`. The title contains newlines because the parser absorbed prose into the title.

**Cause**: The PDF has section headers like `1.1 These controls must be implemented...` where the section number and the prose are on the same line, and the prose continues on subsequent lines.

**Fix**: In this document, use the section number as the title:

```python
# In parse_structure(), for number-only sections:
section_title = f"Section {section_num}"
# Do NOT extract continuation lines as title
```

### Title contamination (Division names, reference markers)

**Symptom**: A Part or Schedule title includes `Division 6—Doxxing` or `[ss. 30(1)(d) & 71]`.

**Fix**: In `parse_structure()`, when collecting multi-line titles, add stop/skip conditions:

```python
# Stop at Division headers
if re.match(r"^Division\s+\d+", next_line, re.IGNORECASE):
    break
# Skip lines starting with reference brackets
if next_line.startswith("["):
    continue
```

### Rule 10 gap: intentional or bug?

Decision procedure:

1. Note the "missing" IDs from validate.py's output (e.g., `pdpa-3, pdpa-4` missing between `pdpa-2` and `pdpa-5`)
2. Open the PDF, search for `Section 3` or `Section 4`
3. **Absent from the PDF** → intentional numbering gap in the source itself. In validate.py CONFIG:

   ```python
   "skip_rule_10_sequential_gaps": True,
   # Reason: Austria-DSG articles skip due to original law structure
   ```

4. **Present in the PDF, missing from `catalog.json`, and NOT in `excluded_units.json`** → extraction bug, fix `parse_structure()` or `PATTERNS["section"]`, then re-run `generate.py`. Do not reach for `excluded_units.json` here as a shortcut — that file drives which controls get REMOVED from the final catalog (see "Extraction is requirement-agnostic" in Phase 2); it is never a way to explain away a control your regex failed to capture. Listing it there would not fix the regex, it would just make the omission look intentional.
5. **Present in the PDF, missing from `catalog.json`, and IS in `excluded_units.json`** → this is the expected, working case: the control was extracted, judged non-requirement, and removed by design. Rule 10 should already report this as INFO (it cross-references `excluded_units.json` automatically). If you're reading this because Rule 10 is still reporting it as ERROR, check that the ID in `excluded_units.json` is spelled EXACTLY as `generate.py` produces it (prefix, hyphens, case) — a mismatch means the validator can't match the two and the entry is silently ineffective.
6. **Present in the PDF, missing from `catalog.json`, judged non-requirement, but NOT yet in `excluded_units.json`** → this is a legitimate Phase 2 omission (the author subagent didn't add it) or a Phase 4 discovery. Add an entry to `$OUT/excluded_units.json` with a one-line reason, then **re-run `generate.py`** — writing the entry alone does nothing to a `catalog.json` that's already on disk; see "Extraction is requirement-agnostic" in Phase 2 for why the removal is a re-run, not an edit. Do NOT use `skip_rule_10_sequential_gaps` for this case — that flag silences the whole document's numbering checks, not one control's classification.

Do NOT set either mechanism before confirming with the PDF — you might mask a real bug.

### Rule 12 missing-group: extraction bug, empty-group side effect, or whole-group exclusion?

Rule 12 fires when a group header appears in `merged.txt` but no matching group appears in `catalog.json`. Decision procedure:

1. Note the group name(s) Rule 12 reports as missing (e.g. "Chapter I").
2. Open the PDF and locate that chapter. Does it contain any articles that ARE genuine requirements (i.e. articles that this run should keep in the catalog)?
3. **Yes, it contains requirements** → this is either an extraction bug (`PATTERNS["chapter"]` isn't matching this chapter header — fix the regex and re-run `generate.py`) OR an empty-group side effect (every one of its controls was listed at the top level of `excluded_units.json`, so the group ends up with `controls: []`; Rule 2 also fires and the correct fix is to REPLACE the individual entries with a single `_groups` entry — see the "empty group after control-level exclusion" failure mode in Phase 2).
4. **No, the whole chapter is introductory or administrative** (Subject-matter, Scope, Definitions; or purely a repeal / commencement block) → the group is legitimately non-requirement in its entirety. Add it to `excluded_units.json` under `_groups` with the exact `merged_txt_header` string Rule 12 reported. Rule 12 will then downgrade this specific group's absence to INFO with the recorded reason. If any of its articles were already listed at the top level, REMOVE those individual entries — the `_groups` entry replaces them, and leaving both in place is confusing (though not incorrect, since a whole-group exclusion overrides).
5. **Rule 12 still reports ERROR after adding the `_groups` entry** → the `merged_txt_header` string doesn't match what Rule 12 normalized from merged.txt. Rule 12 normalizes the header via `"{Type} {Num}".capitalize()` — so "CHAPTER I" in merged.txt becomes "Chapter I" for matching purposes. Set `merged_txt_header` to that normalized form (case-sensitive first-letter-upper). If the mismatch persists, run `grep -E "^(Chapter|Part|Schedule|Annex)" $OUT/merged.txt` to see the raw form and check `MERGED_TEXT_GROUP_PATTERNS_DEFAULT` in `validate_template.py` for the exact normalization pattern.

Do NOT reach for `expected_missing_groups` or similar `validate_config.py` config to silence Rule 12 — that route lets a real extraction bug hide behind an ambiguously-named "expected" flag. `_groups` in `excluded_units.json` is the ONLY sanctioned mechanism for whole-group exclusion, and its `reason` field forces the subagent to state WHY.

### Validation keeps failing after many iterations

If you've iterated 5+ times without progress on the same rule, step back:

- Re-read the FIX_GUIDANCE carefully. It names a specific function or CONFIG key
- Read that function's current code in `$OUT/generate.py`
- Check `$OUT/merged.txt` around the failing control to see the actual PDF text
- Consider whether a bigger change is needed (e.g., switching to `use_pdfplumber`, adding a `DOCUMENT_ZONES` block for a specific page range)

The template already handles the common cases. If you're stuck on an uncommon case, adding one specific fix is fine — but stay within the anti-hallucination principle.

## Notes

- `generate.py` and `validate.py` are treated as artifacts, not throwaway scripts. Keep them alongside `catalog.json` — the next revision of the same document can start from these.
- The skill produces `merged.txt` and `pages/` as debug outputs. `merged.txt` is also the input to Rule 12 (auto-detect missing groups), so always pass `--merged` to validate.py.
- The `_author_prompt.txt`, `_author_agent.jsonl`, `_validate_${ITER}.txt`, `_fix_prompt_${ITER}.txt`, and `_fix_agent_${ITER}.jsonl` files under `<output_dir>` are the audit trail of subagent runs. They are useful for post-mortem debugging if a run fails, and can be deleted after a successful completion.
- All PDF text extraction and OSCAL structuring is done by deterministic Python (`generate.py` + `postprocess_catalog.py`). All semantic judgment (structure interpretation, CONFIG tuning, regex authoring, gap classification) is done by subagents, one per phase or iteration. The main agent orchestrates but does not judge.
- Iterations are sequential (not parallel). Each iteration's subagent depends on the previous iteration's `generate.py`. Attempting to parallelise the fix loop breaks its causal order.
