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

"""Per-document CONFIG for validate.py — the ONLY file Phase 3 and
Phase 4 subagents edit for validation tuning.

Design rationale (READ THIS BEFORE EDITING):
    validate.py's body (rule functions, main(), reporting) is
    template-managed and never edited by subagents. All PDF-specific
    tuning goes into the CONFIG dict below. Splitting the config out
    into its own small file guarantees a subagent's `write` cannot
    accidentally truncate the 1700-line rule body (which caused
    reproducible "validate.py has a SyntaxError" failures in earlier
    runs when the whole file was rewritten from scratch and hit the
    LLM's output-token limit).

What Phase 3 fills in from scratch:
    - name, expected_controls_min/max
    - required_groups (top-level Part/Schedule/Chapter/Annex only —
      NEVER Article/Section/Rule/Principle). List EVERY group header
      found in merged.txt, including any that will be excluded via
      excluded_units.json's `_groups` — the exclusion is applied
      automatically at count time.
    - required_controls_in_groups (only for hierarchical PDFs)
    - garbage_title_patterns / prose_contamination_patterns /
      prose_contamination_patterns_anywhere for this document's page
      furniture (headers, footers, running titles)

    NOTE (2026-07-23): `expected_groups` is now auto-derived from
    `len(required_groups) - len(excluded_units _groups)` unless you
    explicitly override it. Do NOT hand-set expected_groups on new
    documents — leave it None. Setting it to the wrong number was the
    #1 cause of an unnecessary Fix Loop iteration on the sample GDPR
    run and is easy to get wrong when the exclusion list changes.

What Phase 4 fix subagents may adjust:
    - Add more entries to required_groups / required_controls_in_groups
      when Rule 6 / 6a / 6b fires on a missing entry
    - Add more prose_contamination patterns when Rule 14 fires on a
      new header/footer form
    - Flip skip_rule_10_sequential_gaps to True when Rule 10 fires on
      an INTENTIONAL numbering gap that has been verified in
      merged.txt (rare)
    - Set merged_text_group_patterns only in the extremely rare case
      where an Article-level unit really is the top-level group

What subagents may NOT touch:
    - Any file other than this one (validate_config.py in the output
      directory)
    - The rule functions inside validate.py's body
    - The MERGED_TEXT_GROUP_PATTERNS_DEFAULT module-level default in
      validate_template.py — use merged_text_group_patterns override
      here instead
"""

CONFIG = {
    # ---------------- Identity + expected shape --------------------------
    "name": "CHANGE_ME",  # Document identifier (short slug, e.g. "eu-gdpr")
    # Leave `expected_groups` as None on new documents. When None,
    # validate.py auto-derives it as
    #   len(required_groups) - len(excluded_units.json._groups)
    # which is always correct as long as required_groups lists EVERY
    # top-level group in the source (including whole-group exclusions).
    "expected_groups": None,
    "expected_controls_min": None,  # Minimum expected controls, or None
    "expected_controls_max": None,  # Maximum expected controls, or None

    # ---------------- Required-group / required-control checks -----------
    # Enumerated from merged.txt. Every top-level group header in the PDF
    # goes into required_groups. Never list Article/Section/Rule here.
    "required_sections": [],
    "required_groups": [],
    # For hierarchical PDFs only (e.g. HK PDPO Schedule 1 → Principle 1..6).
    "required_controls_in_groups": {},

    # ---------------- Rule 12 group-pattern override ---------------------
    # Leave as None on almost every PDF. Only set this on documents where
    # a control-level unit (Article / Section / Rule) IS the top-level
    # group with no enclosing Part/Chapter/Schedule (extremely rare).
    # Adding r"^(Article)\s+(\d+)\s*$" here on a normal 2-level document
    # like the GDPR causes a 99-error Rule 12 explosion.
    "merged_text_group_patterns": None,

    # ---------------- Rule-specific skip flags ---------------------------
    # When True, the rule still runs but issues become INFO instead of
    # ERROR — the check is preserved for audit, only the failure gate is
    # relaxed. Set True only with evidence from merged.txt or the PDF
    # itself; never as a "make it green" shortcut.
    "skip_rule_3_sequential_order": False,
    "skip_rule_10_sequential_gaps": False,

    # DIAGNOSTIC ONLY — leave this True in every production run.
    # When True (default), Rule 10 downgrades each gap whose ID appears
    # in excluded_units.json to INFO with its recorded reason (SPEC
    # §7.5). Setting it False makes Rule 10 ignore excluded_units.json
    # entirely, so every gap reports as ERROR — the ONLY reason to do
    # this is to audit whether excluded_units.json is masking a real
    # extraction bug. Orthogonal to skip_rule_10_sequential_gaps: if
    # that flag is True, everything is INFO regardless of this one.
    "respect_excluded_units_for_rule_10": True,

    # ---------------- Content-hygiene patterns ---------------------------
    # Fine-grained filters applied per line during validation.
    "garbage_title_patterns": [
        r"^November\s+\d{4}",
        r"^\d{4}$",
        r"^Page\s+\d+",
        r"^Version\s+as\s+at",
    ],
    # Line-anchored prose contamination (each pattern matches a whole line
    # inside a control's prose). Add patterns for THIS document's page
    # furniture (running headers, dated footers, publisher tags).
    "prose_contamination_patterns": [
        r"Verified Copy",
        r"^\d+-\d+$",
        r"^S\d+-\d+$",
        r"^Page\s+\d+\s+of\s+\d+",
        r"^\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}",
    ],
    # Substring prose contamination (each pattern is searched anywhere in
    # a control's prose). Reserve for embedded headers that appear
    # mid-sentence.
    "prose_contamination_patterns_anywhere": [
        r"Part\s+\d+[A-Za-z]?—Division\s+\d+\s+\d+-\d+",
        r"Schedule\s+\d+\s+\d+-\d+",
    ],
}
