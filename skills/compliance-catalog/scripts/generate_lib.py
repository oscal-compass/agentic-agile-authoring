#!/usr/bin/env python3
"""Invariant catalog-assembly library for the compliance-catalog skill.

This module owns the parts of `generate.py` that MUST NOT vary between
documents:

  - `load_excluded_units()` — reads `<output_dir>/excluded_units.json`
  - `assemble_catalog()`     — builds the OSCAL catalog dict and writes
                               it, applying the exclusion filter and
                               dropping empty groups (Rule 2).

The Phase 2 authoring subagent copies this file verbatim next to its
customized `generate.py` (see SKILL.md Phase 2). It is READ-ONLY —
editing it would break the invariants SPEC §7.5 depends on, and the
orchestrator's Phase 2 verification enforces this by sha256-comparing
the sibling copy against this source file.

Why this lives outside `generate_template.py`: two failure modes have
been seen in real Phase 2 runs — (Run A) the subagent's `generate.py`
never called `load_excluded_units()` at all, and (Run B) the subagent
inlined its own exclusion loop in `generate.py` and, needing to
silence the resulting Rule 10 gap errors, flipped
`skip_rule_10_sequential_gaps=True` in `validate_config.py`. Both were
possible because the assembly logic used to live inside the same file
the subagent freely edited. Splitting it out closes that surface.

See SPEC §7.5 for the two-pass design.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone


def load_excluded_units(output_dir: str) -> tuple[dict, dict]:
    """Load <output_dir>/excluded_units.json if present (SPEC §7.5).

    Returns a `(controls, groups)` tuple:
      - `controls`: {control_id: {"reason": str}} — controls to omit from
        the final catalog.json; SPEC §7.5 case A.
      - `groups`:   {group_id: {"reason": str, "merged_txt_header": str}}
        — groups whose entire contents are non-requirement content; SPEC
        §7.5 case B. `merged_txt_header` is the exact heading string that
        appears in merged.txt for this group (e.g. "Chapter I"), used by
        Rule 12 to downgrade its "group in merged.txt but not in catalog"
        finding for this group from ERROR to INFO.

    Schema (backwards-compatible with the flat pre-groups format):

        {
          "eu-gdpr-94": {"reason": "..."},
          "eu-gdpr-99": {"reason": "..."},
          "_groups": {
            "eu-gdpr-chapter-i": {
              "reason": "...",
              "merged_txt_header": "Chapter I"
            }
          }
        }

    - Any top-level key OTHER than `_groups` is treated as a control ID.
    - `_groups`, if present, must be a dict of group IDs to entries.
    - Files without `_groups` behave exactly as they did in the pre-
      groups format (control-only exclusion), so old outputs keep
      working with the new code.

    Absence of the file (the case on generate.py's FIRST run, before
    excluded_units.json exists yet, and the case for most documents on
    every run) means no controls or groups are excluded; this is not an
    error — see "Two-pass extraction" in SKILL.md Phase 2 for why
    generate.py is expected to run once without this file and once with
    it.

    This function does NOT judge requirement-ness itself; it only reads
    a judgment that has already been made and recorded as data.
    assemble_catalog() below acts on the `controls` dict mechanically;
    the `groups` dict is used by BOTH assemble_catalog() (to skip
    emitting the group at all) AND validate.py's Rule 12 (to accept the
    matching merged.txt header as an intentional absence).
    """
    path = os.path.join(output_dir, "excluded_units.json")
    if not os.path.isfile(path):
        return {}, {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}, {}
    if not isinstance(data, dict):
        return {}, {}

    groups_raw = data.get("_groups", {}) if isinstance(data.get("_groups"), dict) else {}
    controls = {k: v for k, v in data.items() if k != "_groups"}
    return controls, groups_raw


def _require(catalog_config: dict, key: str):
    if key not in catalog_config:
        raise KeyError(f"assemble_catalog: catalog_config missing required key {key!r}")
    return catalog_config[key]


def assemble_catalog(groups: list[dict], output_path: str, *, catalog_config: dict) -> None:
    """Build the OSCAL catalog dict and write it to `output_path`.

    Non-requirement exclusion (SPEC §7.5): if
    `<output_dir>/excluded_units.json` exists (where `<output_dir>` is
    `os.path.dirname(output_path)`), it declares two independent
    exclusions:

      - Every control ID listed at the top level (i.e. anywhere except
        under `_groups`) is OMITTED from the catalog this function writes.
      - Every group ID listed under `_groups` is OMITTED whole — the
        group and all its controls are dropped, regardless of how many
        of its controls would otherwise have been kept.

    The final catalog.json therefore contains only controls judged to
    be requirements, structured under groups the subagent judged as
    normatively meaningful. This is NOT a judgment made here: the
    judgments were already made by the Phase 2 author subagent and
    recorded as data in `excluded_units.json`; this function only acts
    on them mechanically.

    Empty groups (a group that had controls in the input `groups` list
    but ends up with zero after control-level exclusion) are NOT
    silently dropped here — they emit a warning and the group is
    written to catalog.json with `controls: []`. Rule 2 will then flag
    this as an error and the fix-loop subagent will decide whether the
    group should be moved into `_groups` (whole-group exclusion, which
    ALSO gets Rule 12 to accept the resulting merged.txt gap) or
    whether the exclusion is wrong. Silently dropping empty groups
    hides this decision from Rule 12 and was the failure mode observed
    on the GDPR sample when Chapter I's Articles 1-4 were all excluded.

    `catalog_config` is a small dict pulled out of the subagent's
    module-global `CONFIG`:

        {
            "title":    <str>,                 # required
            "version":  <str>,                 # required
            "metadata": <dict, may be empty>,  # optional; keys: parties, props, published, remarks
        }

    Passing this dict explicitly (rather than importing `CONFIG` from
    the caller's module) decouples the library from the caller's
    naming and prevents the library from silently picking up an
    unrelated global.
    """
    title = _require(catalog_config, "title")
    version = _require(catalog_config, "version")
    cfg_meta = catalog_config.get("metadata", {}) or {}

    output_dir = os.path.dirname(output_path) or "."
    excluded_controls, excluded_groups = load_excluded_units(output_dir)

    metadata = {
        "title": title,
        "last-modified": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "version": version,
        "oscal-version": "1.2.1",
    }

    if cfg_meta.get("parties"):
        parties = []
        for party in cfg_meta["parties"]:
            if party.get("name") and party["name"] != "CHANGE_ME":
                parties.append({
                    "uuid": str(uuid.uuid4()),
                    "type": party.get("type", "organization"),
                    "name": party["name"],
                    "remarks": party.get("remarks", ""),
                })
        if parties:
            metadata["parties"] = parties

    if cfg_meta.get("props"):
        props = []
        for prop in cfg_meta["props"]:
            if prop.get("value") and prop["value"] != "CHANGE_ME":
                props.append({
                    "name": prop["name"],
                    "value": prop["value"],
                    "ns": prop.get("ns", "https://ibm.com/concert/ns/oscal"),
                })
        if props:
            metadata["props"] = props

    if cfg_meta.get("published") and cfg_meta["published"] != "CHANGE_ME":
        metadata["published"] = cfg_meta["published"]

    if cfg_meta.get("remarks") and cfg_meta["remarks"] != "CHANGE_ME":
        metadata["remarks"] = cfg_meta["remarks"]

    catalog = {
        "catalog": {
            "uuid": str(uuid.uuid4()),
            "metadata": metadata,
            "groups": [],
        }
    }

    excluded_control_count = 0
    excluded_group_count = 0
    emitted_empty_groups: list[str] = []
    for group in groups:
        # Whole-group exclusion (SPEC §7.5): the entire group is skipped
        # BEFORE any control-level processing. This is a stronger and
        # more specific decision than "all controls of this group ended
        # up in `controls`" — it explicitly declares the group itself
        # as non-normative (e.g. "General provisions") and gives Rule 12
        # the merged_txt_header it needs to accept the resulting gap.
        if group["id"] in excluded_groups:
            excluded_group_count += 1
            continue

        oscal_group = {
            "id": group["id"],
            "title": group["title"],
            "controls": [],
        }

        for control in group["controls"]:
            if control["id"] in excluded_controls:
                excluded_control_count += 1
                continue

            props = [
                {
                    "name": "label",
                    "value": control["label"],
                }
            ]

            oscal_control = {
                "id": control["id"],
                "title": control["title"],
                "parts": [
                    {
                        "id": f"{control['id']}_stmt",
                        "name": "statement",
                        "prose": control["prose"],
                    }
                ],
                "props": props,
            }
            oscal_group["controls"].append(oscal_control)

        # Deliberately DO NOT silently drop empty groups here — Rule 2
        # will flag them and the fix subagent decides whether to move
        # them into `_groups` (whole-group exclusion) or whether one of
        # the control-level exclusions was wrong. Silent drops made
        # Rule 12 blind to whole-chapter exclusions (see GDPR Chapter I
        # failure mode) and are prohibited by SPEC §7.5.
        catalog["catalog"]["groups"].append(oscal_group)
        if not oscal_group["controls"]:
            emitted_empty_groups.append(oscal_group["id"])

    if excluded_controls:
        matched = min(excluded_control_count, len(excluded_controls))
        print(f"Excluded {excluded_control_count} non-requirement control(s) per excluded_units.json ({matched}/{len(excluded_controls)} listed IDs matched)")
        if excluded_control_count < len(excluded_controls):
            unmatched = set(excluded_controls) - {c["id"] for g in groups for c in g["controls"] if c["id"] in excluded_controls}
            print(f"  WARNING: {len(excluded_controls) - excluded_control_count} excluded_units.json control entries did not match any extracted control ID: {sorted(unmatched)}")

    if excluded_groups:
        matched_groups = min(excluded_group_count, len(excluded_groups))
        print(f"Excluded {excluded_group_count} non-requirement group(s) per excluded_units.json _groups ({matched_groups}/{len(excluded_groups)} listed IDs matched)")
        if excluded_group_count < len(excluded_groups):
            unmatched_groups = set(excluded_groups) - {g["id"] for g in groups}
            print(f"  WARNING: {len(excluded_groups) - excluded_group_count} excluded_units.json _groups entries did not match any extracted group ID: {sorted(unmatched_groups)}")

    if emitted_empty_groups:
        print(
            f"  NOTE: {len(emitted_empty_groups)} group(s) have no controls after exclusion "
            f"({sorted(emitted_empty_groups)}). Rule 2 will flag these; the fix subagent should "
            f"either move them into _groups (whole-group exclusion) or reconsider the control-level exclusions."
        )

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    print(f"Created: {output_path}")


# ---------------------------------------------------------------------------
# Title / prose boundary helper
# ---------------------------------------------------------------------------
#
# This is the second invariant the shared library owns (besides
# assemble_catalog). Every generate.py MUST route section-line title
# extraction through here — hand-rolled logic in generate.py has proved
# unreliable across document families and produced the single largest
# class of validation failures we track (Rule 7 "empty or too short
# prose" + Rule 14 "prose contamination", both driven by the same root
# cause: `parse_structure` treated substantive body text as title).
#
# The observed failure mode, in the language of what actually shows up
# in `merged.txt`:
#
#   Article 1 This Law is enacted for the purpose of regulating
#   data processing, ensuring data security, promoting development
#   and utilization of data, protecting the lawful rights and
#   interests of individuals and organizations, ...
#
#   Article 2 This Law shall apply to data processing activities
#   ...
#
# A regex like `^Article\s+(\d+)\s*(.*)$` captures group(2) as the
# entire "This Law is enacted..." — that's already a full sentence of
# BODY TEXT, not a title. Worse, the naive "next line starts lowercase
# → title continuation" heuristic in `generate_template.py`'s section
# extractor then keeps eating body lines into the title until the next
# Article header. End result: title is 200-400 chars of body text and
# `statement` prose is empty (Rule 7), triggering the fix loop.
#
# What law/regulation PDFs actually do:
#
# 1. Some documents have real short titles for each article:
#      "Article 1 Definitions"
#      "Article 2 Scope and application"
#    Here group(2) is the title as intended.
#
# 2. Some documents jump straight into body prose:
#      "Article 1 This Law is enacted for the purpose of ..."
#    Here the "title" is effectively empty (or unnamed), and everything
#    after the article number is body prose.
#
# The heuristic below distinguishes (1) from (2). It's intentionally
# conservative: when in doubt, we return `(title="", prose=full_remainder)`,
# because a missing title is a Rule 15 warning we can live with (and
# Phase 4 can polish), while body-text-as-title is a Rule 7 failure
# that STALLS the fix loop.

# Tokens that indicate the "remainder" text starts a sentence, i.e. is
# body prose, not a title. Lowercased-compared. Titles rarely begin
# with these words in legal writing; sentences frequently do.
#
# Keeping this list short and English-first is deliberate — a wider
# net (e.g. every possible sentence starter) would over-fire on real
# short titles like "This Order applies to..." if it exists. If a
# specific document needs more starters, `looks_like_prose_remainder`
# takes an optional `extra_prose_starters` argument.
_DEFAULT_PROSE_STARTERS = frozenset({
    "this", "these", "those", "the", "a", "an",
    "for", "where", "when", "if", "unless", "notwithstanding",
    "subject", "without", "any", "every", "each", "no",
    "in", "on", "at", "by", "with", "under",
    "we", "he", "she", "it", "they",
    "such", "all",
    # Modal-ish sentence openers common in legal text
    "must", "shall", "may", "should",
})


def looks_like_prose_remainder(remainder: str,
                               *,
                               title_char_limit: int = 90,
                               extra_prose_starters: frozenset | set | None = None) -> bool:
    """Heuristic: given the text that follows a section number on the
    same line (e.g. group(2) from a regex like `^Article\\s+(\\d+)\\s+(.*)$`),
    return True if it looks like BODY PROSE rather than a section title.

    True results tell the caller to treat `remainder` as prose (not
    title). False results say "this looks like a normal title; keep
    the existing multi-line title extraction".

    Signals of prose (any one is enough):

      - Length > `title_char_limit` (default 90 chars). Real section
        titles in law texts are almost never that long; body sentences
        routinely are.
      - Ends with a sentence-terminating punctuation (`.`, `?`, `!`,
        `;`), OR contains any sentence terminator NOT at the end (real
        titles rarely contain a middle-of-string period, but body prose
        with multiple sentences on the same line does).
      - Ends with a comma (`,`) — a good tell of a wrapped body line.
      - Starts with a well-known sentence-opener word (see
        `_DEFAULT_PROSE_STARTERS`).
      - Contains a colon followed by a lowercase word — indicating an
        inline list intro, characteristic of body text.

    This is deliberately conservative. If a document truly has titles
    like "The Board's responsibilities include—" the "the" starter will
    misclassify it as prose and the title will end up empty; that's a
    cheap Rule 15 warning to live with, whereas the alternative (400
    chars of body text as title) reliably STALLS Phase 4.
    """
    if not remainder:
        return False
    text = remainder.strip()
    if not text:
        return False

    # Short remainders are almost always titles ("The Board",
    # "Interpretation", "Purpose and scope"). Body sentences that
    # happen to be truncated to <= 30 chars are rare, and misclassifying
    # a title as prose is much less harmful than misclassifying prose as
    # title (the latter is the STALL failure this helper exists to
    # prevent). Below this threshold, only fire on the strongest
    # signal — a trailing sentence terminator.
    is_short = len(text) <= 30

    if len(text) > title_char_limit:
        return True

    # Trailing punctuation — strongest signal, applies at every length
    if text.endswith((".", "!", "?", ";")) and not text.endswith("etc."):
        return True

    # For SHORT titles, only trailing punctuation counts as body-prose.
    # Everything below (mid-sentence tail, comma-then-lowercase, sentence
    # starter, past-tense first word) would over-fire on real short
    # titles like "The Commissioner", "Short title, commencement and
    # application", "Reporting requirements".
    if is_short:
        return False

    if text.endswith(","):
        return True

    # Ends with a word that only makes sense mid-sentence — a strong
    # tell that the PDF wrapped a body line at this point. Titles
    # almost never end with a preposition or conjunction.
    _MID_SENTENCE_TAIL = (
        " for", " of", " in", " on", " to", " by", " with", " from", " at",
        " and", " or", " but", " nor", " so", " if", " as", " that",
        " the", " a", " an", " into", " onto", " over", " under", " between",
        " through", " during", " without", " within", " upon",
    )
    lowered_tail = text.lower()
    if any(lowered_tail.endswith(t) for t in _MID_SENTENCE_TAIL):
        return True

    # Sentence terminator not at the very end → likely 2+ sentences
    if any(mark in text[:-1] for mark in (". ", "? ", "! ")):
        return True

    # An internal comma followed by a lowercase word is a very
    # characteristic body-text pattern ("... shall be adopted, sound
    # data security..."). Titles use commas rarely and, when they do,
    # the following word is typically capitalised
    # ("Rights, remedies and enforcement" — Capitalised follow-up) or
    # is a short list-glue word like "and"/"or". A short list-title
    # style like "Short title, commencement and application" is also
    # allowed via the is_short early-return above.
    for i, ch in enumerate(text):
        if ch == "," and i + 2 < len(text) and text[i + 1] == " " and text[i + 2].islower():
            # Allow "and/or" continuations in short lists
            after = text[i + 2:].split(None, 1)[0]
            if after not in {"and", "or"}:
                return True

    # Opening word signals
    first_word = text.split(None, 1)[0].lower().strip('"\'“”‘’(){}[]')
    starters = _DEFAULT_PROSE_STARTERS
    if extra_prose_starters:
        starters = starters | frozenset(extra_prose_starters)
    if first_word in starters:
        return True

    # First word looks like a past-tense/participle verb ("elaborated",
    # "established", "recognized", ...) — legal boilerplate frequently
    # opens body sentences this way, and titles almost never do.
    # We look for the -ed / -ing suffix as a cheap approximation.
    if len(first_word) > 4 and first_word.endswith(("ed", "ing")):
        # But allow well-known noun-form titles like "meeting",
        # "reporting" — those tend to be single-word titles. Only fire
        # when there's a second word, i.e. it's a phrase not a bare
        # gerund/participle title.
        if len(text.split()) >= 3:
            return True

    # Inline list intro: "colon followed by lowercase" is very
    # characteristic of body text ("...must include: name, address,").
    for i, ch in enumerate(text):
        if ch == ":" and i + 2 < len(text) and text[i + 1] == " " and text[i + 2].islower():
            return True

    return False


def split_title_and_prose_on_section_line(remainder: str,
                                          *,
                                          title_char_limit: int = 90,
                                          extra_prose_starters: frozenset | set | None = None,
                                          ) -> tuple[str, str]:
    """Given the text captured after a section number on the section
    header line (e.g. `group(2)` from `re.match(r"^Article\\s+(\\d+)\\s+(.*)$", line)`),
    return `(title, prose_seed)`:

      - If `remainder` looks like body prose (see
        `looks_like_prose_remainder`), return `("", remainder.strip())`.
        The caller should then use the empty title, seed the control's
        prose with `remainder`, and continue reading body lines as
        prose — NOT as title continuation.
      - Otherwise return `(remainder.strip(), "")` — treat it as a
        title and let the caller do its normal multi-line title
        extraction on the FOLLOWING lines.

    The point of a dedicated helper is that generate.py's
    section-detection loop calls one function and no longer has to
    reason about "is this a title or body". The heuristic is centralised,
    unit-testable, and can be improved in one place without editing
    every per-document generate.py.

    Callers should treat the returned `title` as "the title so far":
    if it's non-empty and doesn't already end with a stop token, the
    caller may still merge in short lookahead lines. But when the
    helper says `title=""`, that decision has already been made — do
    NOT then peek at lookahead lines looking for a title, because the
    following lines are prose too.
    """
    text = (remainder or "").strip()
    if not text:
        return "", ""
    if looks_like_prose_remainder(text,
                                  title_char_limit=title_char_limit,
                                  extra_prose_starters=extra_prose_starters):
        return "", text
    return text, ""
