#!/usr/bin/env python3
"""Build a Phase 6 authoring prompt: write ``report.md`` describing the run.

The report is the generation-summary artifact defined in SPEC §12.5. It is a
narrative document for the human reviewer who will commit the outputs; it is
NOT a validation log and NOT a defect list — the machine-checkable defects
have already been resolved by Phases 4 and 5.

This script gathers the deterministic facts about the completed run (control
count, group breakdown, rule categories in ``validate_config.py``, whether
this was a re-run, and any ``generate.py`` patches applied during a repair
sub-loop), then hands the report subagent a concrete brief. The subagent
composes the Markdown itself — it decides tone, phrasing, and which judgment
calls to surface — but the facts and section structure are pinned by the
prompt so the report cannot drift out of spec.

Design principle (same as ``build_author_prompt.py``): the prompt embeds only
small, human-readable facts. Bulk files (``catalog.json``, ``validate.py``,
``merged.txt``) are referenced by path — the subagent uses its Read tool on
demand when it needs to quote a specific control's ID or check a rule
category name.

Written to ``<output_dir>/_report_prompt.txt``. Path is echoed to stdout.

Usage::

    python build_report_prompt.py <output_dir> <input_pdf> \
        [--rerun] [--patched generate.py:<reason>] [--iterations N]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent


PROMPT_HEADER = """You are the Phase 6 authoring subagent for the compliance-catalog skill.
Your single deliverable is one working file on disk:

  - <output_dir>/report.md  →  a Markdown generation summary for a human
                               reviewer, structured per SPEC §12.5.

You are called AFTER Phases 1–5 have all passed. The catalog is valid, the
validator exits 0, trestle validate is green, and the spot check has been
performed. Do NOT re-litigate any of that. Your job is to describe the
finished result in a way the reviewer can skim in under three minutes and
decide whether to commit.

**WHO YOUR READER IS.** The reader of ``report.md`` is a compliance /
GRC practitioner who is looking at the finished output directory. They
know **NOTHING** about:

  - how the compliance-catalog skill works internally,
  - what ``validate.py`` contains,
  - what ``validate_config.py`` contains,
  - what "Phase N" means,
  - what CONFIG keys like ``header_lines`` or ``toc_pages`` mean.

Everything the reader needs to trust the output must be **stated in
plain language in the report itself**. Do not reference internal file
names as if they were self-explanatory; if you mention
``validate_config.py``, explain what it is in the same sentence.

**A CRITICAL PIT TO AVOID — "no validation" false negatives.**
``validate.py`` carries a fixed set of BUILT-IN validation rules
(typically ~15 checks: duplicate-ID detection, sequential-order checks,
TOC-contamination checks, prose hygiene, OSCAL schema compliance,
trestle validate, etc.). These rules ALWAYS RUN regardless of what
``validate_config.py`` contains. ``validate_config.py`` only provides
*parameters* (e.g. which groups are required, what control count is
expected). It is the **shape check config**, not the rule set.

Never write "no validation rules applied", "validate_config.py has 0
custom rules", "schema-only validation", or anything else that could
lead the reader to conclude the catalog was not properly validated.
The Facts block below tells you exactly which built-in rules ran and
which (if any) were intentionally skipped for this document. Base the
"Validation approach" section on those facts, not on a rule count from
``validate_config.py``.

**A CRITICAL PIT TO AVOID — "config off" false alarms.**
Many CONFIG keys default to a disabled or empty state and are only
enabled when the document actually needs them (e.g. ``header_lines=0``
means "this PDF has no repeating page header to strip", not "header
stripping is broken"; empty ``required_sections`` means "this document
does not organise itself into named sections"; ``use_ocr=False`` means
"the PDF is text-native, no OCR needed"). Do NOT list disabled CONFIG
flags as if they were review concerns. Describe only what the extractor
**actively did** — the reader trusts that the choices were correct
unless the agent has a specific reason to flag one.

Structure of the file — five sections, in this order, using level-2
Markdown headings. All five are required; a section may say "None." but
must not be omitted:

  ## Summary
  ## What was built
  ## Validation approach
  ## Points for human review
  ## Known limitations

The rules below are hard constraints. Read them before you write.

RULE 1 — Not a defect list.
    Do NOT enumerate individual validation warnings or rule-level failures
    that were seen during Phase 4 and fixed. The final run passes cleanly
    by construction; a reviewer looking at ``report.md`` is not debugging.
    If you find yourself typing "the validator initially reported N
    errors...", delete that sentence.

RULE 2 — Not a schema dump.
    Do NOT paste the OSCAL schema, the full list of controls, or the full
    text of ``validate.py``. A shape summary (control count, group
    breakdown, rule categories in play) is exactly what is wanted.

RULE 3 — Not a process narrative.
    Do NOT describe the pipeline itself, the fix loop, or the number of
    times a subagent was retried. Only the state of the finished artefact
    matters. Iteration count belongs as a single number in "What was
    built"; it is not a story.

RULE 4 — Surface judgment calls, not warnings.
    "Points for human review" (section 4) is for **decisions the agent
    made** that a domain expert should sanity-check — not for warnings the
    validator raised. Example of what belongs:
      - "The PDF has both a French and an English column; the English
         column was chosen as the authoritative source."
    Example of what does NOT belong:
      - "Rule 12 was applied 47 times." (facts about validation, not
         judgment)
      - "Some controls have short prose." (this is what the validator is
         for)
    Typically this section has 3–7 bullets. If nothing rose to that level,
    write "No judgment calls of note; the document mapped cleanly." and
    move on.

RULE 4a — Removed non-requirement controls AND groups are NOT OPTIONAL to report.
    If the Facts block reports ANY excluded controls or excluded whole
    groups, "Points for human review" MUST list every one together with
    its recorded reason, AND must state plainly that they were REMOVED
    from the final catalog. Report the two categories with slightly
    different framing so the reader knows which is which:

      - Individual control removals — e.g. "Article 94 (Repeal clause)
        and Article 99 (Entry into force) were extracted, judged
        administrative/non-normative rather than enforceable
        obligations, and removed from the catalog — they do not appear
        in catalog.json."
      - Whole-group removals — e.g. "Chapter I (General provisions)
        was extracted in full but judged introductory / non-normative
        (its four articles cover Subject-matter, Scope, Definitions)
        and REMOVED FROM THE CATALOG AS A WHOLE — Chapter I does not
        appear in catalog.json at all, neither as a group nor via its
        articles."

    Both are required even when the rest of the run is otherwise clean
    and even if together they are the only bullets in this section. Do
    not fold either kind into "Known limitations" — a specific,
    individually-justified removal (with a reason attached to each ID)
    is a judgment call the reader should sanity-check, not a generic
    limitation of the run.

RULE 5 — Length and tone.
    Target 60–200 lines of Markdown. Skimmable — short paragraphs,
    bulleted lists, no walls of text. Write it as if writing to the SME
    who will commit the outputs, not as if writing to a machine.

RULE 6 — Do not invent facts.
    Everything factual (control count, page count, extractor family, rule
    count) is provided below or can be read from the on-disk artefacts.
    If you are unsure of a number, read the file — do not estimate.
"""


PROMPT_STRUCTURE_HINTS = """
Guidance per section:

  ## Summary
    One to three sentences. Follow the template:
    "From `<source PDF>` the agent produced an OSCAL Catalog of <N>
     controls across <G> groups, validated with <R> rules in <K>
     iterations."
    Substitute real numbers from the "Facts" block below. In re-run mode,
    add a second sentence noting the re-run and whether scripts were
    patched.

    If the Facts block reports ANY excluded controls or excluded whole
    groups, BOTH <N> (controls) and <G> (groups) in the template above
    are already the POST-removal counts — do not silently let the reader
    assume they match the PDF's full section / chapter counts. Add a
    clause naming what was removed and why the counts are smaller than
    the source, e.g.:

      "...an OSCAL Catalog of 87 controls across 10 groups (2 further
       numbered articles were extracted and removed as administrative
       non-requirement content, and Chapter I — 4 introductory
       articles — was extracted and removed whole as
       non-normative — see Points for human review)..."

    This is the single most important number in the report to get
    right — it is the one a reader pastes into a status
    update without reading further.

  ## What was built
    An inventory. Bullet list is fine. Cover:
      - source PDF: filename + page count (from Facts block).
      - catalog: total controls, groups with counts, rough prose length
         range (short/typical/long, not exact quantiles). Do not mention
         "catalog.json" as a filename to the reader — say "the catalog".
      - extraction: describe what the extractor ACTIVELY DID in plain
         language — "used pdfplumber to pull text from a text-native
         PDF", "skipped the table of contents", "joined words hyphenated
         across page breaks". Do NOT list CONFIG keys or their values;
         do NOT list disabled options (e.g. header stripping wasn't
         needed because this PDF has no repeating page header — that
         is not review-worthy, it is a normal outcome).
    If this was a re-run, note that here in one bullet: which scripts
    were reused verbatim, which were patched (one-line rationale per
    patch, no diff, no file names beyond "the extractor" / "the
    validator").

  ## Validation approach
    THIS SECTION IS CRITICAL. The reader does not know that validation
    happens at all unless you tell them. Read the "Validation actually
    applied" block in the Facts below — those built-in rules ALL ran
    and ALL passed for this catalog, plus trestle validate.

    Structure this section as:

    1. One sentence stating the size of the safety net, e.g.:
       "The catalog passed <N> built-in structural and content checks
        plus the OSCAL trestle validator."
       Use the number from the Facts block ``builtin_rule_count``. Do
       NOT say "0 rules" — even in the rare case where every built-in
       rule is intentionally skipped, that fact belongs under
       "intentional skips" below, not as a top-line number.

    2. A short grouped summary of what those checks cover, translated
       into reader-friendly categories. Do not paste the raw rule names;
       cluster them. Suggested clusters (adapt to what actually ran):
         - Identifier hygiene    — no duplicate IDs, valid NCName format,
                                    no leaked TOC labels.
         - Structural integrity  — sequential control ordering, no
                                    empty groups, correct nesting.
         - Content completeness  — extraction covers every article in
                                    the merged text; prose is non-empty
                                    where required.
         - Schema compliance     — the OSCAL trestle validator accepts
                                    the file.
       Two or three lines is enough — this is a summary, not a spec.

    3. INTENTIONALLY ALLOWED behaviours (only if any exist for this
       document). This is what the SME needs to sanity-check. Examples:
         - "Controls in Chapter X have no prose because the source
            marks them as reserved."
         - "Hyphenated tokens across page breaks are re-joined, so
            'per-\\nsonal data' appears as 'personal data' in output."
         - "Multi-part hierarchy in the source is compressed to a
            two-level Chapter → Article model."
       Do NOT include CONFIG keys or file names in this list.

    4. INTENTIONAL SKIPS (only if any exist). If any built-in rules were
       explicitly skipped for this document (see ``intentional_skips`` in
       the Facts block), name each in plain language along with the
       reason. Example: "Sequential-numbering enforcement was disabled
       because the source uses non-numeric article labels."

    Never write "no validation rules applied" or "schema-only
    validation" — those phrasings misrepresent what happened.

  ## Points for human review
    See RULE 4 and RULE 4a above. This is the most important section.
    If the Facts block lists any excluded controls, name each control
    ID and its reason here. If it lists any excluded whole groups
    (Facts block's "Whole groups removed" subsection), name each group
    with its merged.txt header, its reason, and the fact that ALL its
    controls were removed together with it. In BOTH cases, say plainly
    that the content is not present in catalog.json. This is a hard
    requirement, not a suggestion, even if these are the only bullets
    you write.

  ## Known limitations
    Anything the run INTENTIONALLY did not do. Examples:
      - figures and tables were skipped (only the normative text was
         extracted);
      - non-normative appendices were excluded;
      - only the English-language version of a bilingual document was
         extracted.
    "None." is a valid section body. Do not manufacture limitations to
    fill the section.
"""


def _load_catalog(catalog_path: Path) -> dict[str, Any]:
    try:
        return json.loads(catalog_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _catalog_stats(catalog: dict[str, Any]) -> dict[str, Any]:
    """Extract a small set of shape statistics from catalog.json.

    Kept intentionally deterministic and low-effort — the subagent can read
    the file directly if it needs anything more precise.
    """
    root = catalog.get("catalog") or catalog
    groups = root.get("groups") or []

    group_summaries: list[str] = []
    total_controls = 0
    prose_lengths: list[int] = []

    def walk_controls(controls: list[dict[str, Any]]) -> int:
        n = 0
        for c in controls or []:
            n += 1
            for part in c.get("parts") or []:
                prose = (part.get("prose") or "").strip()
                if prose:
                    prose_lengths.append(len(prose))
            n += walk_controls(c.get("controls") or [])
        return n

    for g in groups:
        gid = g.get("id") or "?"
        n = walk_controls(g.get("controls") or [])
        total_controls += n
        group_summaries.append(f"{gid} ({n} controls)")

    if prose_lengths:
        prose_lengths.sort()
        median = prose_lengths[len(prose_lengths) // 2]
        prose_range = f"{prose_lengths[0]}–{prose_lengths[-1]} chars (median {median})"
    else:
        prose_range = "no prose captured"

    return {
        "num_groups": len(groups),
        "num_controls": total_controls,
        "group_summaries": group_summaries,
        "prose_range": prose_range,
    }


def _list_builtin_rules(validate_py: Path) -> list[str]:
    """Return the list of built-in rule names defined in ``validate.py``.

    ``validate.py`` carries a fixed rule set (typically ~15 checks) written
    at Phase 3 template-copy time. It is what actually gates the run —
    ``validate_config.py`` only supplies *parameters* (required groups,
    expected control counts, skip flags) for those built-in rules. The
    subagent must never confuse "``validate_config.py`` has 0 custom rules"
    with "no validation was performed" — those are entirely different
    statements.

    The names look like ``check_rule_5_toc_contamination`` in the source.
    We return them in the form ``5:toc_contamination`` for compactness.
    """
    if not validate_py.exists():
        return []
    pattern = re.compile(r"^def\s+check_rule_(\d+)_([A-Za-z0-9_]+)\s*\(", re.MULTILINE)
    try:
        matches = pattern.findall(validate_py.read_text(encoding="utf-8"))
    except Exception:
        return []
    # Sort numerically so the reader sees "1, 2, 3, ..." not lexical order.
    matches.sort(key=lambda m: int(m[0]))
    return [f"{n}:{name}" for n, name in matches]


def _summarise_config(validate_config: Path) -> dict[str, Any]:
    """Extract the CONFIG dict from validate_config.py as a best-effort dict.

    We AST-parse rather than import to avoid side effects. Missing fields
    are returned as None. Only the keys that a reader might reasonably want
    surfaced in the report are pulled — anything else the subagent can Read
    on demand.
    """
    result: dict[str, Any] = {
        "required_groups_count": None,
        "expected_controls_min": None,
        "expected_controls_max": None,
        "skip_flags": [],
    }
    if not validate_config.exists():
        return result
    try:
        import ast

        tree = ast.parse(validate_config.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
                if "CONFIG" in targets and isinstance(node.value, ast.Dict):
                    for k, v in zip(node.value.keys, node.value.values):
                        if not isinstance(k, ast.Constant):
                            continue
                        key = k.value
                        if key == "required_groups" and isinstance(v, ast.List):
                            result["required_groups_count"] = len(v.elts)
                        elif key == "expected_controls_min" and isinstance(v, ast.Constant):
                            result["expected_controls_min"] = v.value
                        elif key == "expected_controls_max" and isinstance(v, ast.Constant):
                            result["expected_controls_max"] = v.value
                        elif isinstance(key, str) and key.startswith("skip_rule_"):
                            if isinstance(v, ast.Constant) and v.value is True:
                                result["skip_flags"].append(key)
                    break
    except Exception:
        pass
    return result


def _load_excluded_units(output_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load excluded_units.json (SPEC §7.5) as a `(controls, groups)` tuple.

    Splits the file into its two sections (see `generate_lib.load_excluded_units`):
      - `controls`: top-level entries (all keys except `_groups`) — individual
        control IDs that were removed from catalog.json.
      - `groups`:   the `_groups` section — group IDs that were removed whole,
        each entry carries a `merged_txt_header` for Rule 12 downgrade.

    Absence, or a malformed file, is treated as "no exclusions" — the same
    convention validate.py uses. This is informational for the report
    subagent, not a gate, so we never raise here.
    """
    path = output_dir / "excluded_units.json"
    if not path.exists():
        return {}, {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}, {}
    if not isinstance(data, dict):
        return {}, {}
    groups = data.get("_groups", {}) if isinstance(data.get("_groups"), dict) else {}
    controls = {k: v for k, v in data.items() if k != "_groups"}
    return controls, groups


def _load_validate_final(output_dir: Path) -> tuple[int | None, str]:
    """Return (best-effort exit code, tail text) for the last run of
    validate.py. Used to surface concrete failing-rule facts to the
    Phase 6 subagent when it was launched in --allow-failed-validation
    mode. Returns (None, "") if no final validation output is on disk.
    """
    final = output_dir / "_validate_final.txt"
    if not final.is_file():
        return None, ""
    text = final.read_text(encoding="utf-8", errors="replace")
    # The file is validate.py's raw stdout+stderr, so the exit code
    # isn't recorded there. We infer failure from a "❌ VALIDATION
    # FAILED" line and success from "✅ VALIDATION PASSED". Absent
    # either, treat as unknown.
    exit_hint: int | None
    if "❌ VALIDATION FAILED" in text:
        exit_hint = 1
    elif "✅ VALIDATION PASSED" in text:
        exit_hint = 0
    else:
        exit_hint = None
    return exit_hint, text


def _summarise_validation_failure(final_text: str, max_rules: int = 12) -> str:
    """Compress the tail of _validate_final.txt into a per-rule ERROR
    count digest the Phase 6 subagent can quote directly. Keeps only
    top-level assertions (skips "- '<id>' appears N times" continuation
    lines and the "... and N more" trailer)."""
    if not final_text:
        return ""
    import re as _re
    body_match = _re.search(r"ERRORS \(\d+\):(.*?)(?:WARNINGS|\Z)", final_text, _re.S)
    if not body_match:
        return ""
    body = body_match.group(1)
    rule_re = _re.compile(r"\[Rule (\d+[a-z]?)\]")
    counts: dict[str, int] = {}
    for line in body.splitlines():
        if not line.startswith("  ❌ "):
            continue
        stripped = line.strip()
        after_tag = stripped.split("] ", 1)[-1] if "] " in stripped else stripped
        if after_tag.startswith("- '") or after_tag.startswith("... and "):
            continue
        m = rule_re.search(line)
        if not m:
            continue
        counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    if not counts:
        return ""
    sorted_rules = sorted(
        counts.items(),
        key=lambda kv: (int(_re.match(r"\d+", kv[0]).group()), kv[0]),
    )
    parts = [f"Rule {r} × {n}" for r, n in sorted_rules[:max_rules]]
    if len(sorted_rules) > max_rules:
        parts.append(f"...+{len(sorted_rules) - max_rules} more")
    return ", ".join(parts)


def _facts_block(
    output_dir: Path,
    input_pdf: Path,
    rerun: bool,
    patched: list[str],
    iterations: int | None,
    allow_failed_validation: bool = False,
) -> str:
    catalog = _load_catalog(output_dir / "catalog.json")
    stats = _catalog_stats(catalog)
    builtin_rules = _list_builtin_rules(output_dir / "validate.py")
    config_summary = _summarise_config(output_dir / "validate_config.py")
    excluded_controls, excluded_groups = _load_excluded_units(output_dir)
    _, val_final_text = _load_validate_final(output_dir)
    failing_rules_digest = _summarise_validation_failure(val_final_text) if allow_failed_validation else ""

    lines: list[str] = ["Facts about this run (use these numbers verbatim in the report):", ""]
    lines.append(f"  source_pdf:         {input_pdf.name}")
    lines.append(f"  output_dir:         {output_dir}")
    lines.append(f"  num_groups:         {stats['num_groups']}")
    lines.append(f"  num_controls:       {stats['num_controls']}")
    lines.append(f"  groups:             {', '.join(stats['group_summaries']) or '—'}")
    lines.append(f"  prose_length_range: {stats['prose_range']}")
    if iterations is not None:
        lines.append(f"  phase4_iterations:  {iterations}")
    lines.append(f"  rerun_mode:         {'yes' if rerun else 'no'}")
    if patched:
        lines.append("  scripts_patched:")
        for entry in patched:
            lines.append(f"    - {entry}")
    else:
        lines.append("  scripts_patched:    (none)")

    # Validation facts — the reader of report.md knows NOTHING about
    # validate.py's internals, so we surface them explicitly here and the
    # prompt above instructs the subagent how to phrase them.
    lines.append("")
    if allow_failed_validation:
        lines.append("Validation actually applied (READ THIS CAREFULLY — validation did NOT pass):")
    else:
        lines.append("Validation actually applied (READ THIS CAREFULLY):")
    lines.append(f"  builtin_rule_count: {len(builtin_rules)} rules always run inside validate.py")
    if allow_failed_validation:
        lines.append("  builtin_rules:      the following built-in checks ran for this run:")
    else:
        lines.append("  builtin_rules:      the following built-in checks all passed for this run:")
    if builtin_rules:
        for rule in builtin_rules:
            lines.append(f"    - check_rule_{rule}")
    else:
        lines.append("    (validate.py could not be parsed — Read it directly)")
    if allow_failed_validation:
        # Best-effort completion path: validate.py exited non-zero. The
        # subagent MUST make this visible to the reviewer — hiding it
        # would defeat the purpose of a best-effort report.
        lines.append("  validation_status:  ❌ FAILED — validate.py did NOT return 0 on the final run.")
        if failing_rules_digest:
            lines.append(f"  failing_rules:      {failing_rules_digest}")
        else:
            lines.append("  failing_rules:      (unable to parse _validate_final.txt — Read it directly)")
        lines.append(
            "  external_gates:     trestle OSCAL schema check status is UNKNOWN in this run"
        )
        lines.append(
            "                      (validate.py exited before that check could report cleanly)"
        )
    else:
        lines.append("  external_gates:     the trestle OSCAL schema check ALSO passed")
        lines.append("                      (run as a subprocess by validate_oscal_catalog.py,")
        lines.append("                      separate from validate.py's in-process rules)")
    lines.append(
        f"  config_shape:       validate_config.py declares "
        f"{config_summary['required_groups_count']} required_groups, "
        f"expected_controls={config_summary['expected_controls_min']}"
        + (
            f"–{config_summary['expected_controls_max']}"
            if config_summary["expected_controls_max"] not in (None, config_summary["expected_controls_min"])
            else ""
        )
    )
    if config_summary["skip_flags"]:
        lines.append(
            "  intentional_skips:  the following built-in rules were INTENTIONALLY skipped"
        )
        lines.append(
            "                      (this is a design choice for this document, not a defect):"
        )
        for flag in config_summary["skip_flags"]:
            lines.append(f"    - {flag}")
    else:
        lines.append("  intentional_skips:  none — the full built-in rule set was enforced")

    # excluded_units.json (SPEC §7.5) — controls AND whole groups that
    # were extracted internally on generate.py's first pass, judged
    # non-requirement content by the Phase 2 author subagent, and then
    # REMOVED from the final catalog.json on the second pass. num_groups
    # and num_controls above already reflect the catalog AFTER removal;
    # neither excluded group ids nor their controls are counted in the
    # catalog totals. RULE 4a above makes surfacing this in "Points for
    # human review" a hard requirement, not optional — spell it out
    # here so the subagent cannot miss it.
    lines.append("")
    if excluded_controls or excluded_groups:
        # Counterfactual "pre-control-removal" count: what the catalog
        # would have held if the individual controls hadn't been
        # removed, ignoring whole-group removals (which are surfaced
        # separately below because their pre-removal control counts
        # aren't recoverable from the post-removal catalog.json alone).
        total_control_ids_after = stats["num_controls"]
        total_control_ids_before_control_removal = total_control_ids_after + len(excluded_controls)

        lines.append(
            f"excluded_units ({len(excluded_controls)} control(s), "
            f"{len(excluded_groups)} whole group(s) — MUST appear in "
            f"'Points for human review', see RULE 4a):"
        )
        lines.append(
            f"  catalog.json currently has {stats['num_groups']} groups and "
            f"{total_control_ids_after} controls after removal."
        )

        if excluded_controls:
            lines.append("")
            lines.append(
                f"  Individual controls removed ({len(excluded_controls)}) — "
                f"pre-removal, the catalog held "
                f"{total_control_ids_before_control_removal} controls "
                f"in the surviving groups:"
            )
            for control_id, entry in excluded_controls.items():
                reason = entry.get("reason", "(no reason recorded)") if isinstance(entry, dict) else str(entry)
                lines.append(f"    - {control_id}: {reason}")

        if excluded_groups:
            lines.append("")
            lines.append(
                f"  Whole groups removed ({len(excluded_groups)}) — these groups "
                f"appear in merged.txt but were omitted entirely from catalog.json "
                f"as introductory / administrative / non-normative content:"
            )
            for group_id, entry in excluded_groups.items():
                if isinstance(entry, dict):
                    reason = entry.get("reason", "(no reason recorded)")
                    header = entry.get("merged_txt_header", "(no header recorded)")
                else:
                    reason = str(entry)
                    header = "(no header recorded)"
                lines.append(f"    - {group_id} (merged.txt header '{header}'): {reason}")

        lines.append(
            "  (none of these ids or group ids appear anywhere in catalog.json — say so"
        )
        lines.append(
            "   explicitly in the report, both for controls and for whole groups)"
        )
    else:
        lines.append("excluded_units: (none — every extracted control and group was judged a requirement)")

    lines.extend(
        [
            "",
            "On-disk artefacts you may Read as needed:",
            f"  {output_dir}/catalog.json",
            f"  {output_dir}/generate.py",
            f"  {output_dir}/validate.py            (built-in rules live here)",
            f"  {output_dir}/validate_config.py     (parameters for the built-in rules)",
            f"  {output_dir}/merged.txt             (only if you need to check prose verbatim)",
            "",
        ]
    )
    return "\n".join(lines)


_BEST_EFFORT_HEADER_OVERRIDE = """
BEST-EFFORT MODE — READ THIS BEFORE YOU START.

This Phase 6 was launched by tools/cli/catalog.py in best-effort mode:
validate.py did NOT return 0 on the final run. The catalog on disk is
imperfect, but it is what the pipeline was able to produce. Your job is
to describe the finished result HONESTLY — including the failing
validation — so the human reviewer can decide whether to accept,
retry, or hand-edit.

Overrides to the "you are called after Phases 1–5 have all passed"
line in the general prompt below:

  - Validation did NOT pass. The catalog is a best-effort artefact.
    The "Validation approach" section MUST make that visible, using
    the per-rule digest in the Facts block.
  - The "Points for human review" section MUST include a bullet
    naming the failing rules (from the Facts block's `failing_rules`)
    and telling the reviewer that a green validation was not obtained
    on this run.
  - You may still write the other sections normally — the catalog
    itself is real, and the extraction facts (control count, group
    breakdown, excluded_units) all hold.
  - Do NOT tell the reader "validation passed" or "the catalog is
    valid". Do NOT omit the failing_rules digest.
  - Do NOT re-run validate.py yourself, do NOT try to fix
    generate.py, do NOT loop. Your job is to REPORT the state on
    disk, not to change it.

Everything below still applies with those overrides in mind.
"""


def build(
    output_dir: Path,
    input_pdf: Path,
    rerun: bool,
    patched: list[str],
    iterations: int | None,
    allow_failed_validation: bool = False,
) -> str:
    parts = []
    if allow_failed_validation:
        parts.extend([_BEST_EFFORT_HEADER_OVERRIDE, ""])
    parts.extend([
        PROMPT_HEADER,
        "",
        PROMPT_STRUCTURE_HINTS,
        "",
        _facts_block(
            output_dir, input_pdf, rerun, patched, iterations,
            allow_failed_validation=allow_failed_validation,
        ),
        "",
        "When you are done, write the report to:",
        f"  {output_dir}/report.md",
        "",
        "Then print DONE on its own line and stop.",
        "",
    ])
    return "\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("output_dir", type=Path)
    ap.add_argument("input_pdf", type=Path)
    ap.add_argument(
        "--rerun",
        action="store_true",
        help="This run reused an existing generate.py / validate.py from a prior run",
    )
    ap.add_argument(
        "--patched",
        action="append",
        default=[],
        metavar="script:reason",
        help=(
            "Record a Phase 4 repair-loop patch, e.g. "
            "'generate.py:added Article 21bis to CHAPTER_HEADS'. "
            "May be specified multiple times."
        ),
    )
    ap.add_argument(
        "--iterations",
        type=int,
        default=None,
        help="Number of Phase 4 iterations that ran (0 in a clean re-run)",
    )
    ap.add_argument(
        "--allow-failed-validation",
        action="store_true",
        help=(
            "Best-effort mode: build a report even though validate.py did NOT return 0. "
            "Reads _validate_final.txt from output_dir, summarises the failing rules, "
            "and instructs the report subagent to surface the failure honestly instead "
            "of assuming a green run."
        ),
    )
    args = ap.parse_args()

    output_dir: Path = args.output_dir
    input_pdf: Path = args.input_pdf

    if not output_dir.exists():
        print(f"error: output_dir does not exist: {output_dir}", file=sys.stderr)
        return 1
    if not input_pdf.exists():
        print(f"error: input_pdf does not exist: {input_pdf}", file=sys.stderr)
        return 1

    prompt = build(
        output_dir, input_pdf, args.rerun, args.patched, args.iterations,
        allow_failed_validation=args.allow_failed_validation,
    )
    out = output_dir / "_report_prompt.txt"
    out.write_text(prompt, encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
