#!/usr/bin/env python3
"""
Comprehensive OSCAL Catalog Validation Script Template.

This script validates a catalog.json against all quality rules.
Copy and customize for each PDF document.

Usage:
    python validate_<name>.py <catalog.json> [--merged <merged.txt>] [--reference <ref_catalog.json>] [--excluded <excluded_units.json>]

Exit codes:
    0 - All checks passed (may have warnings)
    1 - Errors found (validation failed)

Validation Rules (all mandatory):
    Rule 1:  No duplicate IDs (group, control, part, param)
    Rule 2:  No empty lists (controls: [], groups: [])
    Rule 3:  Sequential control order within groups
    Rule 4:  No duplicate group IDs
    Rule 5:  No title contamination (TOC artifacts, page numbers, reference markers, Division names)
    Rule 6:  Complete section extraction (all expected sections present)
    Rule 6a: All required groups present (Schedules, Parts, Chapters)
    Rule 6b: All required controls within specific groups
    Rule 7:  Valid control content (no empty/garbage prose or titles)
    Rule 8:  Balanced structure (parentheses, no truncation)
    Rule 9:  OSCAL format compliance (required fields present)
    Rule 10: Sequential gaps (WARNING only; IDs listed in excluded_units.json
             are downgraded individually with their recorded reason, see
             SPEC compliance-catalog §7.5)
    Rule 11: Control count comparison (WARNING only, if reference provided)
    Rule 12: Merged.txt group comparison (auto-detects missing groups;
             groups listed under `_groups` in excluded_units.json are
             downgraded individually with their recorded reason, see
             SPEC compliance-catalog §7.5)
    Rule 13: CONFIG completeness (required_groups must not be empty)
    Rule 14: No prose contamination (page numbers, headers, footers in prose)

ITERATIVE FIX LOOP:
    This script is designed to be run repeatedly until all errors are fixed.
    Each error includes fix guidance pointing to what to change in generate.py.

IMPORTANT - CONFIG SETUP:
    Before running validation, you MUST populate CONFIG with:
    1. required_groups: List ALL groups from the PDF (Parts, Schedules, Chapters, etc.)
       Run: grep -E "^(Part|Schedule|Chapter|PART|SCHEDULE|CHAPTER)" merged.txt
    2. required_controls_in_groups: For hierarchical documents, list controls within groups

    Failing to set required_groups will result in Rule 13 error.
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

# ===== Patterns for auto-detecting TOP-LEVEL GROUPS in merged.txt =====
#
# These patterns are used by Rule 12 to auto-detect group headers in
# merged.txt and cross-check them against the catalog. Only ONE level of
# nesting is expected: top-level group (Part / Schedule / Chapter / Annex)
# contains controls (Article / Section / Rule / Principle / …).
#
# CRITICAL: this list must contain ONLY patterns that identify **top-level
# groups**, never control-level headings like "Article N" or "Section N".
# In the OSCAL Catalog produced by this pipeline, Articles and Sections are
# controls, not groups. If you list "Article N" here, Rule 12 will emit
# one false-positive error per Article ("Article N exists in merged.txt
# but not in catalog") on every regulation whose Articles are correctly
# extracted as controls. Past runs on the GDPR sample generated 99 false
# Rule 12 errors this way — do not reintroduce that behaviour.
#
# For documents where Article-level items ARE top-level groups (a rare
# structure), don't edit this default. Instead, override it per-document
# by setting CONFIG["merged_text_group_patterns"] in the customised
# validate.py. See MERGED_TEXT_GROUP_PATTERNS_DEFAULT vs the accessor
# `_active_merged_text_group_patterns()` below.
MERGED_TEXT_GROUP_PATTERNS_DEFAULT = [
    r"^(Part)\s+(\d+[A-Za-z]?)\s*$",  # "Part 1", "Part 6A"
    r"^(Schedule)\s+(\d+)\s*$",  # "Schedule 1", "Schedule 2"
    r"^(Chapter)\s+([IVXLCDM]+|\d+)\s*$",  # "Chapter I", "Chapter 1"
    r"^(PART)\s+(\d+[A-Za-z]?)\s*$",  # "PART 1"
    r"^(SCHEDULE)\s+(\d+)\s*$",  # "SCHEDULE 1"
    r"^(CHAPTER)\s+([IVXLCDM]+|\d+)\s*$",  # "CHAPTER I"
    r"^(Annex)\s+([A-Z]|\d+)\s*$",  # "Annex A", "Annex 1"
    r"^(ANNEX)\s+([A-Z]|\d+)\s*$",  # "ANNEX A"
]
# Alias for backwards compatibility with earlier drafts of this template
# that referenced MERGED_TEXT_GROUP_PATTERNS directly. New code should
# call `_active_merged_text_group_patterns()` so CONFIG can override.
MERGED_TEXT_GROUP_PATTERNS = MERGED_TEXT_GROUP_PATTERNS_DEFAULT


def _active_merged_text_group_patterns() -> list[str]:
    """Return the pattern list Rule 12 should use.

    CONFIG["merged_text_group_patterns"] takes precedence if set to a
    non-empty list. Otherwise falls back to MERGED_TEXT_GROUP_PATTERNS_DEFAULT.
    This lets Phase 3 subagents override per PDF (e.g., a regulation
    where "Article N" really is a top-level group) without editing the
    template's module-level default.
    """
    override = CONFIG.get("merged_text_group_patterns") if "CONFIG" in globals() else None
    if isinstance(override, list) and override:
        return override
    return MERGED_TEXT_GROUP_PATTERNS_DEFAULT


def _candidate_group_headers_from_id(group_id: str) -> list[str]:
    """Derive plausible merged.txt header strings from an OSCAL group ID.

    Used by Rule 12 to make `excluded_units.json`'s `_groups` entries
    self-describing: the subagent only lists the group ID, and this
    function reverses OSCAL naming conventions to guess the header form
    Rule 12 sees in merged.txt (after its own `.capitalize()`
    normalisation — see check_rule_12_merged_text_comparison).

    Examples:
      "eu-gdpr-chapter-i"     → ["Chapter I", "Chapter i"]
      "hk-pdpo-part-1"        → ["Part 1"]
      "nist-800-53-schedule-2" → ["Schedule 2"]

    The heuristic: split the ID on hyphens from the right, look for
    a trailing (kind, num_or_roman) pair whose kind matches one of the
    Rule 12 group patterns (Chapter/Part/Schedule/Annex). If no such
    pair is found, return []. The caller (Rule 12) falls back to the
    subagent-supplied `merged_txt_header` in that case.
    """
    parts = group_id.strip().lower().split("-")
    if len(parts) < 2:
        return []
    # walk backwards for the last (kind, tail) pair where kind is a
    # known group-type token
    KNOWN_KINDS = {"chapter", "part", "schedule", "annex"}
    for i in range(len(parts) - 2, -1, -1):
        kind = parts[i]
        tail = "-".join(parts[i + 1:])
        if kind in KNOWN_KINDS and tail:
            # Roman numerals are uppercased; digits stay as-is; single letters uppercased.
            if re.fullmatch(r"[ivxlcdm]+", tail):
                normalised_tail = tail.upper()
            elif re.fullmatch(r"[a-z]", tail):
                normalised_tail = tail.upper()
            else:
                normalised_tail = tail
            return [f"{kind.capitalize()} {normalised_tail}"]
    return []


# ===== PDF-specific configuration (loaded from validate_config.py) =====
#
# CONFIG is now maintained in a SEPARATE, small companion file so that
# authoring subagents (Phase 3) and fix-loop subagents (Phase 4) never
# need to rewrite the ~1,700-line rule body of validate.py. They edit
# a ~60-line CONFIG file next to validate.py instead. This is the fix
# for reproducible "validate.py has a SyntaxError" failures caused by
# subagents' `write_to_file` truncating the full validate.py at the
# LLM's output-token limit.
#
# Search order at import time:
#   1. `validate_config.py` in the SAME directory as this validate.py
#      (this is what the orchestrator copies into <output_dir>/)
#   2. Fallback to `validate_config_template.py` (bundled with the
#      skill) — useful when someone runs `validate_template.py` in
#      isolation for a smoke test.
_CONFIG_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_CONFIG_DIR))
try:
    from validate_config import CONFIG  # type: ignore[import-not-found]  # customised per-document copy
except ImportError:
    # Fallback: skill's default template values, only for standalone tests
    from validate_config_template import CONFIG  # type: ignore[assignment,import-not-found]
finally:
    # Do not leave the injected sys.path entry around; other imports
    # in this module should use normal resolution.
    try:
        sys.path.remove(str(_CONFIG_DIR))
    except ValueError:
        pass


# ===== Fix guidance for each rule =====
# These are printed when errors are found to guide generate.py modifications
FIX_GUIDANCE = {
    "Rule 1": """
    FIX in generate.py → generate_control_id() or generate_group_id()
    - Add parent context to IDs: "{group_id}-{control_num}" not just "{control_num}"
    - Ensure different document sections use different prefixes
    - Check if parse_structure() creates duplicate entries from repeated patterns
    - IDs must be OSCAL NCName compliant (see Rule 15)
    """,
    "Rule 2": """
    FIX in generate.py → generate_catalog()
    - Add filter to remove groups with 0 controls before JSON output:
      groups = [g for g in groups if g.get("controls")]
    - Check parse_structure() isn't creating groups without matching controls
    """,
    "Rule 3": """
    FIX in generate.py → parse_structure()
    - Sort controls by numeric label before adding to group
    - Check regex patterns aren't matching sections in wrong order
    - Add: group["controls"].sort(key=lambda c: extract_number(c["id"]))
    """,
    "Rule 4": """
    FIX in generate.py → generate_group_id()
    - Add unique prefix per document section
    - Example: "schedule-1-part-1" instead of just "part-1"
    - Check if document has multiple "Part 1" in different contexts
    """,
    "Rule 5": """
    FIX in generate.py → CONFIG["toc_pages"] or postprocess_text() or parse_structure()
    - Expand toc_pages range to exclude all TOC pages
    - Add filter: if "..." in line or "……" in line: continue
    - Add regex to strip trailing page numbers from titles
    - For reference marker contamination (e.g., "[ss. 30(1)(d) & 71]" or "& 74]" in title):
      In parse_structure(), skip lines starting with "[" when collecting titles
    - For Division contamination (e.g., "Part 5 ... Division 6—Doxxing" in title):
      In parse_structure(), stop title collection when encountering "Division N" pattern
      Example: if re.match(r"^Division\\s+\\d+", next_line, re.IGNORECASE): break
    """,
    "Rule 6": """
    FIX in generate.py → PATTERNS or parse_structure()
    - Check regex patterns match ALL section formats in the PDF
    - Look for sections with -bis, -ter, -quater suffixes
    - Check for sections with non-standard numbering (roman numerals, letters)
    - Verify expected_controls_min in validate.py CONFIG matches PDF
    - For hierarchical documents: ensure nested patterns (e.g., Principles within Schedules) are captured
    - Check if DOCUMENT_ZONES are needed for different document sections
    """,
    "Rule 6a": """
    FIX: Missing required groups (Schedules, Parts, Chapters)
    - Check PATTERNS["chapter"] or PATTERNS["group"] regex captures all group formats
    - Look at merged.txt to find how missing groups appear in the text
    - Some documents have "SCHEDULE" vs "Schedule" - use case-insensitive patterns
    - Check if missing groups are in toc_pages range and being skipped
    """,
    "Rule 6b": """
    FIX: Missing controls within specific groups (e.g., Principles in Schedule)
    - The group exists but is missing expected controls
    - Check PATTERNS["section"] or nested control patterns
    - Look at merged.txt to see how missing controls appear
    - May need DOCUMENT_ZONES for different extraction patterns per group
    - Check if parent context is needed in parse_structure()
    """,
    "Rule 7": """
    FIX in generate.py → postprocess_text() or CONFIG["garbage_title_patterns"]
    - Add patterns to filter garbage titles (dates, page headers)
    - Fix header/footer removal: increase header_lines or footer_lines
    - Check extract_text_from_page() for encoding issues
    """,
    "Rule 8": """
    FIX in generate.py → handle_page_break() or merge_pages()
    - Fix hyphenation handling: rejoin split words across page breaks
    - Check for truncated sections at page boundaries
    - Verify page range includes all content pages
    """,
    "Rule 9": """
    FIX in generate.py → generate_catalog() or CONFIG
    - Ensure all metadata fields are set in CONFIG["metadata"]
    - Check every control gets id, title, and parts in generate_catalog()
    - Verify oscal-version is exactly "1.2.1"
    """,
    "Rule 10": """
    Sequential gaps detected in control IDs.

    FIRST CHECK - ID NAMING CONVENTION:
    This rule only works if IDs follow the standard naming convention:
    - Allowed characters: lowercase letters, digits, hyphens only
    - Format: prefix-N-letter (asset-1-a) or prefix-N (pdpa-1)
    - NOT allowed: underscores, periods, uppercase, metadata in ID

    WRONG: "asset-1-mil1-a" (MIL in ID breaks detection)
    RIGHT: "asset-1-a" (clean ID, MIL goes in props)

    If IDs don't follow convention, fix generate.py first. See SKILL.md
    "Control ID Naming Convention" section.

    This rule indicates either:
    1. EXTRACTION BUG: Controls were not extracted from the PDF
       - For num_letter patterns (asset-1-a, asset-1-b): Check generate.py parsing
       - Common cause: MIL headers like "MIL1 a." not being parsed correctly
       - Fix: Update practice detection regex in parse_structure()
       - Store MIL level in control props, not in the ID

    2. INTENTIONAL GAPS: The source PDF has non-consecutive numbering
       - Law articles may skip numbers (repealed sections, reserved numbers)
       - NIST profiles contain only selected controls from full catalog
       - Some documents use chapter-based numbering (e.g., 105, 1701-1707)

    TO DETERMINE WHICH:
    - Check the source PDF manually for the reported missing controls
    - If PDF has them → fix generate.py extraction
    - If PDF doesn't have them → set skip_rule_10_sequential_gaps=True in CONFIG

    COMMON FIXES for extraction bugs:
    - C2M2-style "MIL1 a." format: Update regex to handle MIL prefix on same line
    - Multi-line practice text: Ensure prose continuation logic works correctly
    - Page breaks: Check if controls span pages and are being missed
    - MIL in ID: Remove MIL from ID, store as prop instead
    """,
    "Rule 12": """
    FIX: Groups found in merged.txt but missing from catalog
    - Check PATTERNS["chapter"] regex matches the group format in merged.txt
    - Some groups may have different case: "SCHEDULE" vs "Schedule"
    - Groups in Schedules section may need separate extraction logic
    - Check if groups are being filtered out by toc_pages or postprocess_text()
    """,
    "Rule 13": """
    CONFIG INCOMPLETE: required_groups is empty
    - You MUST populate required_groups with ALL groups from the PDF
    - Run: grep -E "^(Part|Schedule|Chapter|PART|SCHEDULE|CHAPTER)" merged.txt
    - Add every group found to required_groups in validate.py CONFIG
    - This ensures no groups are silently dropped
    """,
    "Rule 14": """
    FIX in generate.py → postprocess_text() or CONFIG["page_number_patterns"]
    - Page artifacts (headers, footers, page numbers) are leaking into prose
    - Add patterns to CONFIG["page_number_patterns"] to filter these lines
    - Add patterns to CONFIG["garbage_line_patterns"] for document-specific artifacts
    - Check header_lines/footer_lines settings in CONFIG
    - Example patterns: "Verified Copy", "Cap. 486", "Page X of Y", date headers
    """,
    "Rule 15": """
    FIX in generate.py → generate_control_id(), generate_group_id(), or title extraction

    OSCAL NCName ID requirements (enforced by trestle validate):
    - IDs must START with letter (a-z, A-Z) or underscore (_)
    - IDs can CONTAIN letters, digits, hyphens, dots, underscores
    - IDs must NOT contain parentheses (), brackets [], or other special chars

    Common fixes:
    - "03.01.01" → "ctrl-03-01-01" (prefix with letter)
    - "1.S.A" → "ctrl-1-S-A" (prefix with letter)
    - "tx-dir-ca-7(4)" → "tx-dir-ca-7-4" (remove parentheses)

    Title requirements:
    - Titles must NOT contain newline characters (\\n or \\r)
    - Multi-line titles must be joined with spaces in generate.py
    - Check parse_structure() title extraction logic
    """,
    "Rule 16": """
    trestle validate command failed.

    This is the final check using the actual trestle tool. Common causes:
    - ID format violations (see Rule 15)
    - Invalid group structure (controls in wrong nesting level)
    - Missing required OSCAL fields

    To debug:
    1. cd to trestle workspace (directory with .trestle/)
    2. Run: trestle validate -f <path-to-catalog.json>
    3. Review the detailed error output
    """,
    "Rule 17": """
    Props missing namespace (ns) field.

    OSCAL requires that all non-standard props have a namespace (ns) field.
    Standard props that do NOT require ns: label

    All other props MUST have ns, e.g.:
    - mil-level, source, jurisdiction, effective-date, etc.

    FIX in generate.py → where props are added to controls/groups:

    WRONG:
        control["props"].append({"name": "mil-level", "value": "MIL1"})

    RIGHT:
        control["props"].append({
            "name": "mil-level",
            "value": "MIL1",
            "ns": "https://ibm.com/concert/ns/oscal"
        })

    Check all places where props are added:
    - generate_catalog() for metadata props
    - parse_structure() for control/group props
    - Any custom prop additions
    """,
}


class ValidationResult:
    """Holds validation results with fix guidance."""

    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.infos: list[str] = []  # For skipped-as-error rules
        self.stats: dict[str, Any] = {}
        self.rules_failed: set[str] = set()
        self.rules_skipped: set[str] = set()  # Rules that were checked but skipped as error

    def add_error(self, rule: str, message: str):
        self.errors.append(f"[{rule}] {message}")
        self.rules_failed.add(rule)

    def add_warning(self, rule: str, message: str):
        self.warnings.append(f"[{rule}] {message}")

    def add_info(self, rule: str, message: str):
        """Add info message for rules that are checked but skipped as error."""
        self.infos.append(f"[{rule}] {message}")
        self.rules_skipped.add(rule)

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0


def collect_all_ids(catalog_data: dict) -> dict[str, list[dict]]:
    """Collect all IDs from the catalog with their locations and types."""
    all_ids: dict[str, list[dict]] = defaultdict(list)

    def register_id(id_value: str, id_type: str, location: str):
        if id_value:
            all_ids[id_value].append({"type": id_type, "location": location})

    def process_part(part: dict, path: str):
        part_id = part.get("id")
        register_id(part_id, "part", f"{path}/part[{part_id}]")
        for nested in part.get("parts", []):
            process_part(nested, f"{path}/part[{part_id}]")

    def process_control(control: dict, path: str):
        ctrl_id = control.get("id")
        register_id(ctrl_id, "control", f"{path}/control[{ctrl_id}]")
        for part in control.get("parts", []):
            process_part(part, f"{path}/control[{ctrl_id}]")
        for param in control.get("params", []):
            param_id = param.get("id")
            register_id(param_id, "param", f"{path}/control[{ctrl_id}]/param[{param_id}]")
        for enhancement in control.get("controls", []):
            process_control(enhancement, f"{path}/control[{ctrl_id}]")

    def process_group(group: dict, path: str):
        group_id = group.get("id")
        register_id(group_id, "group", f"{path}/group[{group_id}]")
        for control in group.get("controls", []):
            process_control(control, f"{path}/group[{group_id}]")
        for subgroup in group.get("groups", []):
            process_group(subgroup, f"{path}/group[{group_id}]")

    catalog = catalog_data.get("catalog", {})
    catalog_uuid = catalog.get("uuid")
    register_id(catalog_uuid, "catalog_uuid", "catalog")

    for party in catalog.get("metadata", {}).get("parties", []):
        party_uuid = party.get("uuid")
        register_id(party_uuid, "party_uuid", f"metadata/party[{party_uuid}]")

    for group in catalog.get("groups", []):
        process_group(group, "catalog")

    for control in catalog.get("controls", []):
        process_control(control, "catalog")

    return all_ids


def check_rule_1_duplicate_ids(catalog: dict, result: ValidationResult):
    """Rule 1: All IDs must be unique across the entire catalog."""
    all_ids = collect_all_ids(catalog)
    duplicates = {id_val: occs for id_val, occs in all_ids.items() if len(occs) > 1}

    result.stats["total_unique_ids"] = len(all_ids)
    result.stats["duplicate_ids"] = len(duplicates)

    if duplicates:
        result.add_error("Rule 1", f"DUPLICATE IDS: {len(duplicates)} IDs appear multiple times")
        for id_val, occs in sorted(duplicates.items())[:10]:
            types = ", ".join(set(o["type"] for o in occs))
            result.add_error("Rule 1", f"  - '{id_val}' appears {len(occs)} times (types: {types})")
        if len(duplicates) > 10:
            result.add_error("Rule 1", f"  ... and {len(duplicates) - 10} more duplicate IDs")


def check_rule_2_empty_lists(catalog: dict, result: ValidationResult):
    """Rule 2: Groups must not have empty controls or groups lists."""
    issues = []

    def check_group(group: dict, path: str):
        group_id = group.get("id", "unknown")
        group_title = group.get("title", "unknown")
        current_path = f"{path}/group[{group_id}]"

        if "controls" in group and isinstance(group["controls"], list) and len(group["controls"]) == 0:
            issues.append(f"Group '{group_title}' ({group_id}) has empty controls list")

        if "groups" in group and isinstance(group["groups"], list) and len(group["groups"]) == 0:
            issues.append(f"Group '{group_title}' ({group_id}) has empty groups list")

        for subgroup in group.get("groups", []):
            check_group(subgroup, current_path)

    for group in catalog.get("catalog", {}).get("groups", []):
        check_group(group, "catalog")

    result.stats["empty_list_issues"] = len(issues)

    for issue in issues:
        result.add_error("Rule 2", issue)


def check_rule_3_sequential_order(catalog: dict, result: ValidationResult):
    """Rule 3: Controls must be in sequential order within each group.

    If CONFIG["skip_rule_3_sequential_order"] is True, this rule is still executed
    but issues are reported as INFO instead of ERROR. This is for documents where
    non-sequential control IDs are intentional (e.g., Australia-ISM: ISM-0009, ISM-0027, ISM-0714).
    """
    errors = []
    warnings = []
    skip_as_error = CONFIG.get("skip_rule_3_sequential_order", False)

    def parse_label(label: str) -> tuple[str | None, int | None]:
        if not label:
            return None, None
        match = re.match(r"^([A-Za-z.\-]+?)(\d+)$", label.strip())
        if match:
            prefix = match.group(1).rstrip(".-")
            number = int(match.group(2))
            return prefix, number
        return None, None

    def collect_labels(group: dict, labels: list):
        for control in group.get("controls", []):
            label = None
            for prop in control.get("props", []):
                if prop.get("name") == "label":
                    label = prop.get("value")
                    break
            if not label:
                label = control.get("id", "")
            if label:
                labels.append({"label": label, "control_id": control.get("id")})
        for subgroup in group.get("groups", []):
            collect_labels(subgroup, labels)

    all_labels = []
    for group in catalog.get("catalog", {}).get("groups", []):
        collect_labels(group, all_labels)

    by_prefix = defaultdict(list)
    for item in all_labels:
        prefix, number = parse_label(item["label"])
        if prefix is not None and number is not None:
            by_prefix[prefix].append({"number": number, "label": item["label"]})

    for prefix, items in sorted(by_prefix.items()):
        if len(items) < 2:
            continue
        numbers = [item["number"] for item in items]
        if numbers != sorted(numbers):
            errors.append(f"Controls in '{prefix}' group are OUT OF ORDER")

        sorted_nums = sorted(set(numbers))
        expected = list(range(sorted_nums[0], sorted_nums[-1] + 1))
        missing = [x for x in expected if x not in numbers]
        if missing:
            sep = "-" if prefix else ""
            missing_labels = [f"{prefix}{sep}{m}" for m in missing[:5]]
            more = f" ... and {len(missing) - 5} more" if len(missing) > 5 else ""
            warnings.append(f"Sequential gap in '{prefix}': missing {', '.join(missing_labels)}{more}")

    result.stats["order_errors"] = len(errors)
    result.stats["sequential_gaps"] = len(warnings)

    # Report errors/info based on skip flag
    if skip_as_error and errors:
        result.add_info("Rule 3", f"[SKIPPED AS ERROR] {len(errors)} order issues found (non-sequential IDs expected for this document)")
        for err in errors:
            result.add_info("Rule 3", f"  {err}")
    else:
        for err in errors:
            result.add_error("Rule 3", err)

    # Note: Sequential gaps are now handled by check_rule_10_sequential_gaps()


def check_rule_10_sequential_gaps(catalog: dict, result: ValidationResult, excluded_units: dict | None = None):
    """Rule 10: Check for sequential gaps in control IDs.

    This rule detects missing controls by checking ID continuity.
    Handles two patterns:
    - num_letter: prefix-N-letter (e.g., asset-1-a, asset-1-b, cpg-1-a)
    - num_only: prefix-N (e.g., pdpa-1, pdpa-2, art-10)

    IMPORTANT - ID NAMING CONVENTION:
    IDs must follow the standard format for this rule to work correctly:
    - Allowed: lowercase letters, digits, hyphens only
    - Format: prefix-N-letter or prefix-N
    - NOT allowed: underscores, periods, uppercase, metadata (like MIL) in ID

    If IDs don't follow the convention (e.g., "asset-1-mil1-a" instead of
    "asset-1-a"), this rule will fail to detect gaps. See SKILL.md for the
    full Control ID Naming Convention.

    If CONFIG["skip_rule_10_sequential_gaps"] is True, ALL gaps in the
    document are reported as INFO instead of ERROR. Use this for documents
    where the source numbering itself has gaps (repealed articles, cherry-
    picked profiles, non-standard numbering schemes).

    `excluded_units` (loaded from <output_dir>/excluded_units.json, see
    SPEC §7.5) is a DIFFERENT and narrower mechanism: it downgrades only
    the specific missing IDs it lists — each with its own recorded reason
    — leaving every other gap as ERROR. This is for the case where a
    missing ID was judged non-requirement content (definitions, purely
    administrative text) rather than "the source document skips this
    number." The two mechanisms are independent and may both apply.

    CONFIG["respect_excluded_units_for_rule_10"] (default True) is a
    DIAGNOSTIC-ONLY escape hatch. When set to False, this function
    ignores `excluded_units` entirely — every gap becomes ERROR, exactly
    as if the file were empty. The only reason to set this to False is
    to audit whether `excluded_units.json` is masking a real extraction
    bug; a normal production `validate_config.py` leaves it at True (or
    omits the key, which defaults to True). This flag is orthogonal to
    `skip_rule_10_sequential_gaps` — if the skip flag is True, every
    gap is INFO regardless of this flag's value.

    To verify if gaps are intentional, check the source PDF manually.
    """
    skip_as_error = CONFIG.get("skip_rule_10_sequential_gaps", False)
    respect_excluded = CONFIG.get("respect_excluded_units_for_rule_10", True)
    excluded_units = excluded_units or {}
    if not respect_excluded:
        excluded_units = {}

    def parse_control_id(control_id: str) -> dict:
        """Parse control ID into components."""
        cid = control_id.lower().strip()

        # Pattern 1a: prefix-NUMletter (e.g., asset-1a, threat-2b)
        match = re.match(r'^([a-z][a-z0-9]*(?:[-][a-z]+)*)-(\d+)([a-z]+)$', cid)
        if match:
            return {
                'prefix': match.group(1),
                'obj_num': int(match.group(2)),
                'letter': match.group(3),
                'pattern': 'num_letter',
            }

        # Pattern 1b: prefix-NUM-letter (e.g., cpg-1-a, cpg-2-b)
        match = re.match(r'^([a-z][a-z0-9]*(?:[-][a-z]+)*)-(\d+)-([a-z]+)$', cid)
        if match:
            return {
                'prefix': match.group(1),
                'obj_num': int(match.group(2)),
                'letter': match.group(3),
                'pattern': 'num_letter',
            }

        # Pattern 2: prefix-NUM (e.g., pdpa-1, art-10)
        match = re.match(r'^([a-z][a-z0-9]*(?:[-][a-z]+)*)-(\d+)$', cid)
        if match:
            return {
                'prefix': match.group(1),
                'obj_num': int(match.group(2)),
                'letter': None,
                'pattern': 'num_only',
            }

        return {'prefix': cid, 'obj_num': None, 'letter': None, 'pattern': 'unknown'}

    def letter_to_num(letter: str) -> int:
        """Convert letter(s) to number: a=1, b=2, ..., z=26, aa=27."""
        if not letter:
            return 0
        result = 0
        for c in letter:
            result = result * 26 + (ord(c) - ord('a') + 1)
        return result

    def num_to_letter(n: int) -> str:
        """Convert number to letter(s): 1=a, 2=b, ..., 26=z, 27=aa."""
        if n <= 0:
            return ''
        result = []
        while n > 0:
            n -= 1
            result.append(chr(ord('a') + (n % 26)))
            n //= 26
        return ''.join(reversed(result))

    # Collect all controls
    controls = []

    def collect_controls(obj: dict):
        if 'id' in obj and 'parts' in obj:
            controls.append(obj['id'])
        for group in obj.get('groups', []):
            collect_controls(group)
        for ctrl in obj.get('controls', []):
            collect_controls(ctrl)

    for group in catalog.get('catalog', {}).get('groups', []):
        collect_controls(group)

    # Analyze num_letter pattern (e.g., asset-1a, asset-1b)
    by_objective = defaultdict(list)
    for ctrl_id in controls:
        parsed = parse_control_id(ctrl_id)
        if parsed['pattern'] == 'num_letter':
            key = (parsed['prefix'], parsed['obj_num'])
            by_objective[key].append({
                'id': ctrl_id,
                'letter': parsed['letter'],
                'letter_num': letter_to_num(parsed['letter']),
            })

    num_letter_gaps = []
    for (prefix, obj_num), items in sorted(by_objective.items()):
        sorted_items = sorted(items, key=lambda x: x['letter_num'])
        letter_nums = [item['letter_num'] for item in sorted_items]

        if len(letter_nums) >= 2:
            # Check if missing letters at start (e.g., starts at 'c' instead of 'a')
            first_letter = letter_nums[0]
            if first_letter > 1:
                missing = [num_to_letter(i) for i in range(1, first_letter)]
                missing_ids = [f"{prefix}-{obj_num}{l}" for l in missing]
                num_letter_gaps.append({
                    'obj': f"{prefix}-{obj_num}",
                    'type': 'missing_start',
                    'first': sorted_items[0]['id'],
                    'missing': missing_ids,
                })

            # Check for gaps between letters
            for i in range(len(letter_nums) - 1):
                curr = letter_nums[i]
                next_val = letter_nums[i + 1]
                if next_val > curr + 1:
                    missing = [num_to_letter(j) for j in range(curr + 1, next_val)]
                    missing_ids = [f"{prefix}-{obj_num}{l}" for l in missing]
                    num_letter_gaps.append({
                        'obj': f"{prefix}-{obj_num}",
                        'type': 'gap',
                        'after': sorted_items[i]['id'],
                        'before': sorted_items[i + 1]['id'],
                        'missing': missing_ids,
                    })

    # Analyze num_only pattern (e.g., pdpa-1, pdpa-2)
    by_prefix = defaultdict(list)
    for ctrl_id in controls:
        parsed = parse_control_id(ctrl_id)
        if parsed['pattern'] == 'num_only':
            by_prefix[parsed['prefix']].append({
                'id': ctrl_id,
                'num': parsed['obj_num'],
            })

    num_only_gaps = []
    for prefix, items in sorted(by_prefix.items()):
        sorted_items = sorted(items, key=lambda x: x['num'])
        nums = [item['num'] for item in sorted_items]

        if len(nums) >= 2:
            for i in range(len(nums) - 1):
                curr = nums[i]
                next_val = nums[i + 1]
                if next_val > curr + 1:
                    missing_nums = list(range(curr + 1, next_val))
                    missing_ids = [f"{prefix}-{n}" for n in missing_nums]
                    num_only_gaps.append({
                        'prefix': prefix,
                        'type': 'gap',
                        'after': sorted_items[i]['id'],
                        'before': sorted_items[i + 1]['id'],
                        'missing': missing_ids,
                    })

    # Record stats
    total_gaps = len(num_letter_gaps) + len(num_only_gaps)
    total_missing = sum(len(g['missing']) for g in num_letter_gaps) + sum(len(g['missing']) for g in num_only_gaps)
    result.stats["sequential_gaps"] = total_gaps
    result.stats["missing_controls"] = total_missing

    # Report issues
    if total_gaps == 0:
        return

    # Split each gap's `missing` IDs into ones covered by excluded_units.json
    # (non-requirement content, downgraded to INFO with the recorded reason
    # regardless of skip_rule_10_sequential_gaps) and everything else (follows
    # skip_as_error as before). A gap can be partially excluded.
    def split_missing(missing_ids: list) -> tuple[list, list]:
        excluded = [m for m in missing_ids if m in excluded_units]
        real = [m for m in missing_ids if m not in excluded_units]
        return real, excluded

    total_excluded = sum(
        len(split_missing(g['missing'])[1]) for g in num_letter_gaps + num_only_gaps
    )
    if total_excluded:
        result.stats["excluded_gaps"] = total_excluded

    # Improvement (2026-07-23): if every missing ID is accounted for by
    # excluded_units.json, treat this exactly like `skip_as_error` — the
    # gaps are fully explained and shouldn't be an ERROR. Previously the
    # summary line unconditionally errored on any gap count > 0, forcing
    # the fix subagent to add `skip_rule_10_sequential_gaps=True` to
    # validate_config even when the residual gap was already covered
    # per-ID. That is the exact iter-3 waste we're removing.
    fully_excluded = respect_excluded and total_missing > 0 and total_excluded == total_missing
    if fully_excluded:
        skip_as_error = True

    report_func = result.add_info if skip_as_error else result.add_error

    if skip_as_error:
        result.add_info("Rule 10", f"[SKIPPED AS ERROR] {total_gaps} sequential gaps found ({total_missing} missing controls)")
        if fully_excluded:
            result.add_info("Rule 10", f"  All {total_missing} missing IDs are recorded in excluded_units.json — see per-ID reasons below")
        else:
            result.add_info("Rule 10", "  Gaps are expected for this document (skip_rule_10_sequential_gaps=True)")
    else:
        result.add_error("Rule 10", f"Found {total_gaps} sequential gaps ({total_missing} missing controls)")
        if total_excluded:
            result.add_info("Rule 10", f"  ({total_excluded} of the missing controls above are recorded in excluded_units.json as non-requirement content — see per-ID reasons below)")

    # Report num_letter gaps (these usually indicate extraction bugs)
    for gap in num_letter_gaps[:10]:  # Limit output
        real, excluded = split_missing(gap['missing'])
        if real:
            missing_str = ', '.join(real[:5])
            if len(real) > 5:
                missing_str += f" ... (+{len(real) - 5} more)"
            if gap['type'] == 'missing_start':
                report_func("Rule 10", f"  [{gap['obj']}] Missing at start, first found: '{gap['first']}' - Missing: {missing_str}")
            else:
                report_func("Rule 10", f"  [{gap['obj']}] Gap after '{gap['after']}' before '{gap['before']}' - Missing: {missing_str}")
        for m in excluded:
            reason = excluded_units.get(m, {}).get("reason", "(no reason recorded)")
            result.add_info("Rule 10", f"  [excluded_units.json] '{m}' — {reason}")

    # Report num_only gaps
    for gap in num_only_gaps[:10]:  # Limit output
        real, excluded = split_missing(gap['missing'])
        if real:
            missing_str = ', '.join(real[:5])
            if len(real) > 5:
                missing_str += f" ... (+{len(real) - 5} more)"
            report_func("Rule 10", f"  [{gap['prefix']}] Gap after '{gap['after']}' before '{gap['before']}' - Missing: {missing_str}")
        for m in excluded:
            reason = excluded_units.get(m, {}).get("reason", "(no reason recorded)")
            result.add_info("Rule 10", f"  [excluded_units.json] '{m}' — {reason}")

    if total_gaps > 20:
        report_func("Rule 10", f"  ... and {total_gaps - 20} more gaps")


def check_rule_4_duplicate_group_ids(catalog: dict, result: ValidationResult):
    """Rule 4: No duplicate group IDs."""
    group_ids = []

    def collect_group_ids(group: dict):
        group_ids.append(group.get("id"))
        for subgroup in group.get("groups", []):
            collect_group_ids(subgroup)

    for group in catalog.get("catalog", {}).get("groups", []):
        collect_group_ids(group)

    id_counts = Counter(group_ids)
    duplicates = {gid: count for gid, count in id_counts.items() if count > 1}

    result.stats["duplicate_group_ids"] = len(duplicates)

    for gid, count in duplicates.items():
        result.add_error("Rule 4", f"Group ID '{gid}' appears {count} times")


def check_rule_5_toc_contamination(catalog: dict, result: ValidationResult):
    """Rule 5: No TOC/title contamination (dot leaders, page numbers, reference markers, Division names)."""
    issues = []

    def check_obj(obj: dict, path: str):
        title = obj.get("title", "")
        obj_id = obj.get("id", "unknown")
        # Check for dot leaders (TOC artifacts)
        if "..." in title or "…" in title or "……" in title:
            issues.append(f"{path}/{obj_id}: TOC dot leader in title: '{title[:60]}'")
        # Check for trailing page numbers like "Section 44 24" where 24 is page number
        # But exclude valid titles that naturally end with numbers (e.g., "Part 5", "Schedule 6", "Chapter 10")
        if re.search(r"\s+\d{1,3}$", title):
            # Allow titles that reference parts/schedules/chapters (e.g., "Interpretation of Part 5")
            if not re.search(r"(Part|Schedule|Chapter|Section|Article|Division|Annex)\s+\d+[A-Za-z]?$", title, re.IGNORECASE):
                issues.append(f"{path}/{obj_id}: Possible page number in title: '{title[:60]}'")
        # Check for reference markers like "[ss. 30(1)(d) & 71]" or "& 74]" leaked into title
        if re.search(r"\[.*\]|\[\s*ss?\.", title) or re.search(r"&\s*\d+\]", title):
            issues.append(f"{path}/{obj_id}: Reference marker in title: '{title[:60]}'")
        # Check for Division names mixed into Part/Schedule titles
        # e.g., "Part 5 Personal Data Division 6—Doxxing" should NOT have "Division 6" in the title
        if re.search(r"^(Part|Schedule|Chapter)\s+\d+[A-Za-z]?\s+.+\bDivision\s+\d+", title, re.IGNORECASE):
            issues.append(f"{path}/{obj_id}: Division contamination in title: '{title[:60]}'")

        for g in obj.get("groups", []):
            check_obj(g, f"{path}/{obj_id}")
        for c in obj.get("controls", []):
            check_obj(c, f"{path}/{obj_id}")

    check_obj(catalog.get("catalog", {}), "catalog")

    result.stats["toc_contamination"] = len(issues)

    for issue in issues:
        result.add_error("Rule 5", issue)


def check_rule_6_complete_extraction(catalog: dict, result: ValidationResult, excluded_groups: dict | None = None):
    """Rule 6: All expected sections must be present.

    `excluded_groups` (the `_groups` section of excluded_units.json,
    SPEC §7.5) lets the caller tell Rule 6a that certain top-level
    groups are intentionally missing from `catalog.json` because
    excluded_units.json declared them whole-group exclusions. Without
    this, Rule 6a fires on required_groups entries that Rule 12
    already reports as INFO — a double-report that forces a redundant
    fix-loop iteration whose only job is deleting the entry from
    `required_groups`. Added 2026-07-23 as a symmetry fix to the
    Rule 12 excluded_groups handling.
    """
    excluded_groups = excluded_groups or {}
    # Collect all group titles and IDs
    all_group_titles = []
    all_group_ids = []
    groups_with_controls: dict[str, list[str]] = {}  # group_title -> [control_titles]

    def collect_groups(group: dict, parent_title: str = ""):
        group_title = group.get("title", "").lower()
        group_id = group.get("id", "").lower()
        all_group_titles.append(group_title)
        all_group_ids.append(group_id)

        # Collect control titles within this group
        control_titles = []
        for control in group.get("controls", []):
            control_titles.append(control.get("title", "").lower())
        groups_with_controls[group_title] = control_titles

        for subgroup in group.get("groups", []):
            collect_groups(subgroup, group_title)

    for group in catalog.get("catalog", {}).get("groups", []):
        collect_groups(group)

    # Collect all control titles and IDs (flat list)
    all_control_titles = []
    all_control_ids = []

    def collect_controls(group: dict):
        for control in group.get("controls", []):
            all_control_titles.append(control.get("title", "").lower())
            all_control_ids.append(control.get("id", "").lower())
        for subgroup in group.get("groups", []):
            collect_controls(subgroup)

    for group in catalog.get("catalog", {}).get("groups", []):
        collect_controls(group)

    # Check required sections (controls anywhere in catalog)
    if CONFIG.get("required_sections"):
        missing_sections = []
        for required in CONFIG["required_sections"]:
            req_lower = required.lower()
            found = False
            for title in all_control_titles:
                if req_lower in title:
                    found = True
                    break
            if not found:
                for ctrl_id in all_control_ids:
                    if req_lower.replace(" ", "-") in ctrl_id or req_lower.replace(" ", "_") in ctrl_id:
                        found = True
                        break
            if not found:
                missing_sections.append(required)

        result.stats["missing_required_sections"] = len(missing_sections)
        for section in missing_sections:
            result.add_error("Rule 6", f"Required section not found: '{section}'")

    # Check required groups (Schedules, Parts, Chapters).
    #
    # Any required_groups entry that matches an excluded whole-group
    # (via excluded_units.json's `_groups`) is downgraded to INFO —
    # Rule 12 already reports these with the exclusion reason, and
    # firing an ERROR here as well only forces the fix subagent to
    # delete the entry from `required_groups`, which is wasted work.
    excluded_group_header_forms: set[str] = set()
    for gid in excluded_groups.keys():
        for cand in _candidate_group_headers_from_id(gid):
            excluded_group_header_forms.add(cand.lower())

    if CONFIG.get("required_groups"):
        missing_groups = []
        excluded_missing_groups = []
        for required in CONFIG["required_groups"]:
            req_lower = required.lower()
            found = False
            for title in all_group_titles:
                if req_lower in title or title in req_lower:
                    found = True
                    break
            if not found:
                for gid in all_group_ids:
                    if req_lower.replace(" ", "-") in gid or req_lower.replace(" ", "_") in gid:
                        found = True
                        break
            if not found:
                if req_lower in excluded_group_header_forms:
                    excluded_missing_groups.append(required)
                else:
                    missing_groups.append(required)

        result.stats["missing_required_groups"] = len(missing_groups)
        for group in missing_groups:
            result.add_error("Rule 6a", f"Required group not found: '{group}'")
        for group in excluded_missing_groups:
            result.add_info(
                "Rule 6a",
                f"  [excluded_units.json _groups] '{group}' — required_groups entry matches a whole-group exclusion; see Rule 12 for the recorded reason"
            )

    # Check required controls within specific groups
    if CONFIG.get("required_controls_in_groups"):
        for group_name, required_controls in CONFIG["required_controls_in_groups"].items():
            group_lower = group_name.lower()
            # Find the group
            group_controls = None
            for gtitle, controls in groups_with_controls.items():
                if group_lower in gtitle or gtitle in group_lower:
                    group_controls = controls
                    break

            if group_controls is None:
                # Group itself is missing - already reported by required_groups check
                continue

            # Check each required control within this group
            missing_in_group = []
            for required in required_controls:
                req_lower = required.lower()
                found = False
                for ctrl_title in group_controls:
                    if req_lower in ctrl_title:
                        found = True
                        break
                if not found:
                    missing_in_group.append(required)

            if missing_in_group:
                result.stats[f"missing_in_{group_name}"] = len(missing_in_group)
                for ctrl in missing_in_group:
                    result.add_error("Rule 6b", f"'{group_name}' is missing required control: '{ctrl}'")


def check_rule_7_valid_content(catalog: dict, result: ValidationResult):
    """Rule 7: Control content must be valid (no empty/garbage prose or titles)."""
    issues = []

    def check_control(control: dict, path: str):
        ctrl_id = control.get("id", "unknown")
        title = control.get("title", "")

        # Check for garbage titles.
        # `or []` guards against a subagent setting the key to None
        # explicitly (dict.get returns the stored value, not the default,
        # when the key IS present with a None value — that would crash
        # the `for` below with `TypeError: 'NoneType' is not iterable`).
        for pattern in (CONFIG.get("garbage_title_patterns") or []):
            if re.match(pattern, title, re.IGNORECASE):
                issues.append(f"{path}/{ctrl_id}: Garbage title detected: '{title[:60]}'")
                break

        # Check for empty or too short prose
        for part in control.get("parts", []):
            prose = part.get("prose", "")
            if not prose or len(prose.strip()) < 10:
                issues.append(f"{path}/{ctrl_id}: Empty or too short prose in part '{part.get('id', 'unknown')}'")

            # Check for garbled characters
            if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", prose):
                issues.append(f"{path}/{ctrl_id}: Garbled characters in prose")

    def process_group(group: dict, path: str):
        group_id = group.get("id", "unknown")
        for control in group.get("controls", []):
            check_control(control, f"{path}/group[{group_id}]")
        for subgroup in group.get("groups", []):
            process_group(subgroup, f"{path}/group[{group_id}]")

    for group in catalog.get("catalog", {}).get("groups", []):
        process_group(group, "catalog")

    result.stats["content_issues"] = len(issues)

    for issue in issues:
        result.add_error("Rule 7", issue)


def check_rule_8_balanced_structure(catalog: dict, result: ValidationResult):
    """Rule 8: Balanced parentheses, no truncated content."""
    issues = []

    def check_control(control: dict, path: str):
        ctrl_id = control.get("id", "unknown")
        for part in control.get("parts", []):
            prose = part.get("prose", "")

            # Check parentheses balance
            open_p = prose.count("(")
            close_p = prose.count(")")
            if abs(open_p - close_p) > 2:
                issues.append(
                    f"{path}/{ctrl_id}: Unbalanced parentheses (open: {open_p}, close: {close_p})"
                )

            # Check for truncation (ends with hyphen)
            if prose.rstrip().endswith("-") or prose.rstrip().endswith("–"):
                issues.append(f"{path}/{ctrl_id}: Prose ends with hyphen (possible truncation)")

    def process_group(group: dict, path: str):
        group_id = group.get("id", "unknown")
        for control in group.get("controls", []):
            check_control(control, f"{path}/group[{group_id}]")
        for subgroup in group.get("groups", []):
            process_group(subgroup, f"{path}/group[{group_id}]")

    for group in catalog.get("catalog", {}).get("groups", []):
        process_group(group, "catalog")

    result.stats["structure_issues"] = len(issues)

    for issue in issues:
        result.add_error("Rule 8", issue)


def check_rule_9_oscal_compliance(catalog: dict, result: ValidationResult):
    """Rule 9: OSCAL format compliance (required fields present)."""
    issues = []

    if "catalog" not in catalog:
        result.add_error("Rule 9", "Missing 'catalog' root element")
        return

    cat = catalog["catalog"]

    # Check catalog-level required fields
    if "uuid" not in cat:
        issues.append("Missing catalog.uuid")

    # Check metadata
    metadata = cat.get("metadata", {})
    if not metadata:
        issues.append("Missing catalog.metadata")
    else:
        required_meta = ["title", "last-modified", "version", "oscal-version"]
        for field in required_meta:
            if field not in metadata:
                issues.append(f"Missing metadata.{field}")

        # Check oscal-version value
        oscal_version = metadata.get("oscal-version", "")
        if oscal_version and oscal_version != "1.2.1":
            issues.append(f"Invalid oscal-version '{oscal_version}' (must be '1.2.1')")

    # Check groups/controls exist
    groups = cat.get("groups", [])
    controls = cat.get("controls", [])
    if not groups and not controls:
        issues.append("Catalog has no groups or controls")

    # Check each control has required fields
    def check_control(ctrl: dict, path: str):
        ctrl_id = ctrl.get("id")
        if not ctrl_id:
            issues.append(f"{path}: Control missing 'id'")
        if "title" not in ctrl:
            issues.append(f"{path}/{ctrl_id}: Control missing 'title'")
        if "parts" not in ctrl or not ctrl["parts"]:
            issues.append(f"{path}/{ctrl_id}: Control missing 'parts'")

    def process_group(group: dict, path: str):
        group_id = group.get("id", "unknown")
        if "id" not in group:
            issues.append(f"{path}: Group missing 'id'")
        if "title" not in group:
            issues.append(f"{path}/{group_id}: Group missing 'title'")

        for ctrl in group.get("controls", []):
            check_control(ctrl, f"{path}/group[{group_id}]")
        for subgroup in group.get("groups", []):
            process_group(subgroup, f"{path}/group[{group_id}]")

    for group in groups:
        process_group(group, "catalog")

    result.stats["oscal_issues"] = len(issues)

    for issue in issues:
        result.add_error("Rule 9", issue)


def check_rule_11_control_count(catalog: dict, ref_catalog: dict | None, result: ValidationResult, excluded_groups: dict | None = None):
    """Rule 11: Control count comparison (WARNING if reference provided)."""
    excluded_groups = excluded_groups or {}
    def count_controls(cat: dict) -> int:
        count = 0
        def process_group(group: dict):
            nonlocal count
            count += len(group.get("controls", []))
            for ctrl in group.get("controls", []):
                count += len(ctrl.get("controls", []))  # Nested controls
            for subgroup in group.get("groups", []):
                process_group(subgroup)

        for group in cat.get("catalog", {}).get("groups", []):
            process_group(group)
        count += len(cat.get("catalog", {}).get("controls", []))
        return count

    control_count = count_controls(catalog)
    result.stats["control_count"] = control_count

    # Check against expected range
    if CONFIG.get("expected_controls_min") is not None:
        if control_count < CONFIG["expected_controls_min"]:
            result.add_error(
                "Rule 6",
                f"Too few controls: {control_count} (expected at least {CONFIG['expected_controls_min']})"
            )

    if CONFIG.get("expected_controls_max") is not None:
        if control_count > CONFIG["expected_controls_max"]:
            result.add_warning(
                "Rule 11",
                f"Too many controls: {control_count} (expected at most {CONFIG['expected_controls_max']})"
            )

    # Check against reference
    if ref_catalog:
        ref_count = count_controls(ref_catalog)
        result.stats["ref_control_count"] = ref_count
        diff = control_count - ref_count
        result.stats["control_diff"] = diff

        if abs(diff) > ref_count * 0.1 and abs(diff) > 5:
            result.add_warning(
                "Rule 11",
                f"Significant control count difference: {control_count} vs reference {ref_count} ({diff:+d})"
            )
        elif diff != 0:
            result.add_warning(
                "Rule 11",
                f"Minor control count difference: {control_count} vs reference {ref_count} ({diff:+d})"
            )

    # Check against expected groups
    group_count = len(catalog.get("catalog", {}).get("groups", []))
    result.stats["group_count"] = group_count

    # Improvement (2026-07-23): `expected_groups` is now auto-derived
    # from CONFIG["required_groups"] minus any whole-group exclusions
    # recorded in excluded_units.json's `_groups` section. Subagents no
    # longer need to compute this manually — an out-of-date value was
    # the #1 cause of Fix Loop iter 2 in the sample GDPR run.
    #
    # Precedence (in order): explicit CONFIG["expected_groups"] > derived.
    # If neither is set (rare — a validate_config with no required_groups
    # at all), the check is skipped.
    expected_groups_effective = CONFIG.get("expected_groups")
    if expected_groups_effective is None and CONFIG.get("required_groups"):
        expected_groups_effective = max(
            0, len(CONFIG["required_groups"]) - len(excluded_groups)
        )
    if expected_groups_effective is not None:
        if group_count != expected_groups_effective:
            result.add_warning(
                "Rule 11",
                f"Group count mismatch: {group_count} (expected {expected_groups_effective})"
            )


def check_rule_12_merged_text_comparison(
    catalog: dict,
    merged_path: Path | None,
    result: ValidationResult,
    excluded_groups: dict | None = None,
):
    """Rule 12: Compare catalog groups against groups found in merged.txt.

    `excluded_groups` is the `_groups` section of excluded_units.json
    (SPEC §7.5): a dict of group_id → {"reason": str, "merged_txt_header": str}.
    When a group appears in merged.txt but is absent from catalog.json AND
    its merged.txt header matches one of the recorded `merged_txt_header`
    values, that group is reported as INFO (with the recorded reason)
    instead of ERROR — the absence is intentional, `generate.py` was told
    to omit the group whole because its content is non-normative.
    """
    excluded_groups = excluded_groups or {}
    if not merged_path or not merged_path.exists():
        return  # Skip if no merged.txt provided

    # Read merged.txt
    try:
        with open(merged_path, "r", encoding="utf-8") as f:
            merged_text = f.read()
    except Exception as e:
        result.add_warning("Rule 12", f"Could not read merged.txt: {e}")
        return

    # Find all groups in merged.txt. Use the active pattern list so
    # per-document overrides via CONFIG["merged_text_group_patterns"]
    # take effect. See _active_merged_text_group_patterns() docstring
    # for the rationale (avoids false-positive Rule 12 errors when
    # Article/Section-level headings are misclassified as groups).
    active_patterns = _active_merged_text_group_patterns()
    groups_in_merged = set()
    for line in merged_text.split("\n"):
        line = line.strip()
        for pattern in active_patterns:
            match = re.match(pattern, line)
            if match:
                group_type = match.group(1)
                group_num = match.group(2)
                # Normalize to "Type N" format
                normalized = f"{group_type.capitalize()} {group_num}"
                groups_in_merged.add(normalized)
                break

    if not groups_in_merged:
        return  # No groups found in merged.txt

    # Collect groups from catalog
    groups_in_catalog = set()

    def collect_groups(group: dict):
        title = group.get("title", "")
        # Extract "Part 1", "Schedule 2", etc. from title
        for pattern in active_patterns:
            # Adjust pattern to match within title
            title_pattern = pattern.replace("^", "").replace("$", "")
            match = re.search(title_pattern, title, re.IGNORECASE)
            if match:
                group_type = match.group(1)
                group_num = match.group(2)
                normalized = f"{group_type.capitalize()} {group_num}"
                groups_in_catalog.add(normalized)
                break
        for subgroup in group.get("groups", []):
            collect_groups(subgroup)

    for group in catalog.get("catalog", {}).get("groups", []):
        collect_groups(group)

    # Find groups in merged.txt but not in catalog
    missing_from_catalog = groups_in_merged - groups_in_catalog

    result.stats["groups_in_merged_txt"] = len(groups_in_merged)
    result.stats["groups_in_catalog"] = len(groups_in_catalog)
    result.stats["groups_missing_from_catalog"] = len(missing_from_catalog)

    # Partition the missing set into (a) intentional whole-group
    # exclusions declared by excluded_units.json's `_groups`, matched by
    # merged.txt header string, and (b) genuinely-unexpected absences.
    # Only (b) is an ERROR; (a) is reported as INFO with the recorded
    # reason so the exclusion never disappears from validation output.
    #
    # Header resolution (improved 2026-07-23): the subagent no longer
    # needs to provide `merged_txt_header` — if it's absent, validate.py
    # derives candidate headers from the group ID itself by stripping the
    # `<prefix>-` and re-formatting the tail against Rule 12's own group
    # regexes. `eu-gdpr-chapter-i` → try `Chapter I`; `hk-pdpo-part-1` →
    # try `Part 1`. This is possible because we know exactly what shapes
    # Rule 12 accepts (MERGED_TEXT_GROUP_PATTERNS_DEFAULT) and can walk
    # them backwards.
    #
    # If the auto-derived header matches a value in `groups_in_merged`,
    # use it. If it doesn't match anything (unusual group naming), fall
    # back to the explicit `merged_txt_header` the subagent wrote — that
    # remains the escape hatch for exotic documents.
    excluded_headers_to_reason: dict[str, tuple[str, str]] = {}
    for gid, entry in excluded_groups.items():
        if not isinstance(entry, dict):
            continue
        reason = entry.get("reason", "(no reason recorded)")
        header_candidates = _candidate_group_headers_from_id(gid)
        matched = next((h for h in header_candidates if h in groups_in_merged), None)
        if matched is None:
            # Fall back to explicit header if the subagent provided one
            explicit = entry.get("merged_txt_header")
            if isinstance(explicit, str) and explicit:
                matched = explicit
        if matched:
            excluded_headers_to_reason[matched] = (gid, reason)

    real_missing = sorted(m for m in missing_from_catalog if m not in excluded_headers_to_reason)
    excluded_missing = sorted(m for m in missing_from_catalog if m in excluded_headers_to_reason)

    result.stats["excluded_group_absences"] = len(excluded_missing)

    if real_missing:
        result.add_error(
            "Rule 12",
            f"Groups found in merged.txt but MISSING from catalog: {real_missing}"
        )
        for group in real_missing:
            result.add_error("Rule 12", f"  - '{group}' exists in merged.txt but not in catalog")

    for group in excluded_missing:
        gid, reason = excluded_headers_to_reason[group]
        result.add_info(
            "Rule 12",
            f"  [excluded_units.json _groups] '{group}' (group id '{gid}') — {reason}"
        )


def check_rule_13_config_completeness(result: ValidationResult):
    """Rule 13: Ensure CONFIG has required_groups populated."""
    issues = []

    # Check if required_groups is empty
    if not CONFIG.get("required_groups"):
        issues.append(
            "CONFIG['required_groups'] is EMPTY - you must list ALL expected groups"
        )

    # Check if name is still CHANGE_ME
    if CONFIG.get("name") == "CHANGE_ME":
        issues.append("CONFIG['name'] is still 'CHANGE_ME' - set document identifier")

    result.stats["config_issues"] = len(issues)

    for issue in issues:
        result.add_error("Rule 13", issue)


def check_rule_14_prose_contamination(catalog: dict, result: ValidationResult):
    """Rule 14: Check for page artifacts (headers, footers, page numbers) in prose."""
    issues = []
    # `or []` guards against a subagent setting the key to None — see
    # the matching comment in check_rule_7_valid_content(). Observed
    # crash on 2026-07-23 when a fix subagent replaced
    # `prose_contamination_patterns_anywhere: [...]` with `None` to
    # "disable" the check, blowing up validate.py itself and confusing
    # the outer main agent into looping.
    line_patterns = CONFIG.get("prose_contamination_patterns") or []
    anywhere_patterns = CONFIG.get("prose_contamination_patterns_anywhere") or []

    if not line_patterns and not anywhere_patterns:
        # No patterns configured, skip check
        return

    def check_control(control: dict, path: str):
        ctrl_id = control.get("id", "unknown")
        for part in control.get("parts", []):
            prose = part.get("prose", "")
            if not prose:
                continue

            # Check patterns that should match anywhere in prose (embedded headers)
            for pattern in anywhere_patterns:
                matches = re.findall(pattern, prose, re.IGNORECASE)
                for match in matches:
                    display = match if len(match) <= 50 else match[:50] + "..."
                    issues.append(f"{path}/{ctrl_id}: Embedded header in prose: '{display}'")

            # Check each line of prose for line-based contamination patterns
            for line in prose.split("\n"):
                line_stripped = line.strip()
                for pattern in line_patterns:
                    if re.search(pattern, line_stripped, re.IGNORECASE):
                        # Truncate the line for display
                        display_line = line_stripped[:50] + "..." if len(line_stripped) > 50 else line_stripped
                        issues.append(f"{path}/{ctrl_id}: Prose contamination: '{display_line}'")
                        break  # One match per line is enough

    def check_group(group: dict, path: str):
        group_id = group.get("id", "unknown")
        current_path = f"{path}/{group_id}"
        for control in group.get("controls", []):
            check_control(control, current_path)
        for subgroup in group.get("groups", []):
            check_group(subgroup, current_path)

    for group in catalog.get("catalog", {}).get("groups", []):
        check_group(group, "catalog")

    result.stats["prose_contamination"] = len(issues)

    # Limit output to first 20 issues to avoid spam
    for issue in issues[:20]:
        result.add_error("Rule 14", issue)
    if len(issues) > 20:
        result.add_error("Rule 14", f"... and {len(issues) - 20} more prose contamination issues")


def print_results(result: ValidationResult, catalog_path: Path):
    """Print validation results with fix guidance."""
    print("=" * 70)
    print("OSCAL Catalog Validation Report")
    print("=" * 70)
    print(f"Catalog: {catalog_path}")
    print()

    # Print statistics
    print("Statistics:")
    for key, value in sorted(result.stats.items()):
        print(f"  {key}: {value}")
    print()

    # Print errors
    if result.errors:
        print(f"ERRORS ({len(result.errors)}):")
        print("-" * 70)
        for error in result.errors:
            print(f"  ❌ {error}")
        print()

    # Print warnings
    if result.warnings:
        print(f"WARNINGS ({len(result.warnings)}):")
        print("-" * 70)
        for warning in result.warnings:
            print(f"  ⚠️  {warning}")
        print()

    # Print info (skipped-as-error rules)
    if result.infos:
        print(f"INFO - RULES CHECKED BUT SKIPPED AS ERROR ({len(result.infos)}):")
        print("-" * 70)
        for info in result.infos:
            print(f"  ℹ️  {info}")
        print()

    # Print summary and fix guidance
    print("=" * 70)
    if result.passed:
        if result.warnings:
            print("✅ VALIDATION PASSED (with warnings)")
        else:
            print("✅ VALIDATION PASSED")
    else:
        print("❌ VALIDATION FAILED")
        print(f"   {len(result.errors)} errors must be fixed")
        print()
        # Print fix guidance for failed rules
        print("FIX GUIDANCE - Modify generate.py as follows:")
        print("-" * 70)
        for rule in sorted(result.rules_failed):
            if rule in FIX_GUIDANCE:
                print(f"\n{rule}:{FIX_GUIDANCE[rule]}")
    print("=" * 70)


def check_rule_15_trestle_compliance(catalog: dict, result: ValidationResult):
    """Rule 15: OSCAL/Trestle compliance for IDs, titles, and required fields.

    Checks that all elements comply with trestle validate requirements:
    - IDs must match OSCAL NCName pattern (no dots except after first char, no parentheses)
    - Titles must not contain newlines and must not be empty
    - Parts must have 'name' field
    - Props must have 'value' field
    - UUIDs must be valid format
    - last-modified must be valid datetime

    NCName pattern: ^[_A-Za-z][_A-Za-z0-9.-]*$
    (Simplified: must start with letter/underscore, can contain letters, digits, hyphens, dots, underscores)
    """
    issues = []

    # OSCAL NCName pattern - IDs must start with letter or underscore
    # and can only contain letters, digits, hyphens, dots (after first char), underscores
    # Note: The actual OSCAL pattern is more permissive for Unicode, but practically:
    # - Must NOT start with a digit or dot
    # - Must NOT contain parentheses, brackets, or other special chars
    ncname_pattern = re.compile(r'^[_A-Za-z][_A-Za-z0-9.\-]*$')

    # UUID pattern (v4 or v5)
    uuid_pattern = re.compile(r'^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[45][0-9A-Fa-f]{3}-[89ABab][0-9A-Fa-f]{3}-[0-9A-Fa-f]{12}$')

    # ISO datetime pattern (simplified)
    datetime_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}')

    def check_id(id_value: str, location: str, id_type: str):
        if not id_value:
            issues.append(f"{location}: {id_type} ID is empty")
            return

        # Check NCName pattern
        if not ncname_pattern.match(id_value):
            # Provide specific guidance based on the violation
            if id_value[0].isdigit():
                issues.append(f"{location}: {id_type} ID '{id_value}' starts with digit (must start with letter or underscore)")
            elif id_value[0] == '.':
                issues.append(f"{location}: {id_type} ID '{id_value}' starts with dot (must start with letter or underscore)")
            elif '(' in id_value or ')' in id_value:
                issues.append(f"{location}: {id_type} ID '{id_value}' contains parentheses (not allowed in OSCAL IDs)")
            elif '[' in id_value or ']' in id_value:
                issues.append(f"{location}: {id_type} ID '{id_value}' contains brackets (not allowed in OSCAL IDs)")
            else:
                issues.append(f"{location}: {id_type} ID '{id_value}' doesn't match OSCAL NCName pattern")

    def check_title(title: str, location: str, obj_type: str, required: bool = True):
        # Empty titles violate ^[^\n]+$ pattern (must have at least one non-newline char)
        if not title and required:
            issues.append(f"{location}: {obj_type} title is empty (must have at least one character)")
            return

        if not title:
            return

        # Check for newlines in title
        if '\n' in title or '\r' in title:
            # Show truncated version for display
            display_title = title.replace('\n', '\\n').replace('\r', '\\r')[:60]
            issues.append(f"{location}: {obj_type} title contains newline: '{display_title}...'")

    def check_part(part: dict, path: str):
        part_id = part.get("id", "")
        check_id(part_id, path, "Part")

        # Check required 'name' field for parts
        if "name" not in part:
            issues.append(f"{path}/part[{part_id}]: Part missing required 'name' field")

        for nested in part.get("parts", []):
            check_part(nested, f"{path}/part[{part_id}]")

    def check_props(props: list, path: str):
        for i, prop in enumerate(props):
            # Check required 'value' field for props
            if "value" not in prop:
                prop_name = prop.get("name", "unknown")
                issues.append(f"{path}/props[{i}]: Prop '{prop_name}' missing required 'value' field")

    def check_control(control: dict, path: str):
        ctrl_id = control.get("id", "")
        check_id(ctrl_id, path, "Control")
        check_title(control.get("title", ""), path, "Control")

        for part in control.get("parts", []):
            check_part(part, f"{path}/control[{ctrl_id}]")

        # Check props
        check_props(control.get("props", []), f"{path}/control[{ctrl_id}]")

        for param in control.get("params", []):
            param_id = param.get("id", "")
            check_id(param_id, f"{path}/control[{ctrl_id}]", "Param")

        # Check nested controls (enhancements)
        for enhancement in control.get("controls", []):
            check_control(enhancement, f"{path}/control[{ctrl_id}]")

    def check_group(group: dict, path: str):
        group_id = group.get("id", "")
        check_id(group_id, path, "Group")
        check_title(group.get("title", ""), path, "Group")

        for control in group.get("controls", []):
            check_control(control, f"{path}/group[{group_id}]")

        for subgroup in group.get("groups", []):
            check_group(subgroup, f"{path}/group[{group_id}]")

    catalog_data = catalog.get("catalog", {})

    # Check catalog UUID format (v4 or v5)
    catalog_uuid = catalog_data.get("uuid", "")
    if catalog_uuid:
        if not uuid_pattern.match(catalog_uuid):
            issues.append(f"catalog: Invalid UUID format '{catalog_uuid}' (must be valid UUID v4 or v5)")
    else:
        issues.append("catalog: Missing required 'uuid' field")

    # Check metadata
    metadata = catalog_data.get("metadata", {})
    if metadata:
        # Check last-modified datetime format
        last_modified = metadata.get("last-modified", "")
        if last_modified and not datetime_pattern.match(last_modified):
            issues.append(f"metadata: Invalid last-modified datetime format '{last_modified}' (must be ISO 8601)")
        elif not last_modified:
            issues.append("metadata: Missing required 'last-modified' field")

    # Check all groups
    for group in catalog_data.get("groups", []):
        check_group(group, "catalog")

    # Check top-level controls (if any)
    for control in catalog_data.get("controls", []):
        check_control(control, "catalog")

    result.stats["trestle_compliance_issues"] = len(issues)

    # Limit output to first 30 issues
    for issue in issues[:30]:
        result.add_error("Rule 15", issue)
    if len(issues) > 30:
        result.add_error("Rule 15", f"... and {len(issues) - 30} more trestle compliance issues")


def check_rule_17_props_namespace(catalog: dict, result: ValidationResult):
    """Rule 17: All non-standard props must have namespace (ns) field.

    OSCAL requires that props not defined in the core OSCAL schema must have
    a namespace (ns) field to identify their source/meaning.

    Standard OSCAL props that do NOT require ns:
    - label

    All other props (e.g., mil-level, source, jurisdiction) MUST have ns.
    Recommended ns: "https://ibm.com/concert/ns/oscal"
    """
    # Standard OSCAL props that do NOT require namespace
    standard_props = {"label"}
    issues = []

    def check_props_list(props: list, location: str):
        for prop in props:
            name = prop.get("name", "")
            if name not in standard_props and "ns" not in prop:
                issues.append({
                    "location": location,
                    "prop_name": name,
                    "prop_value": prop.get("value", "")[:50],
                })

    def check_part(part: dict, path: str):
        part_id = part.get("id", "unknown")
        current_path = f"{path}/part[{part_id}]"
        if "props" in part:
            check_props_list(part["props"], current_path)
        for nested in part.get("parts", []):
            check_part(nested, current_path)

    def check_control(control: dict, path: str):
        ctrl_id = control.get("id", "unknown")
        current_path = f"{path}/control[{ctrl_id}]"
        if "props" in control:
            check_props_list(control["props"], current_path)
        for part in control.get("parts", []):
            check_part(part, current_path)
        for nested in control.get("controls", []):
            check_control(nested, current_path)

    def check_group(group: dict, path: str):
        group_id = group.get("id", "unknown")
        current_path = f"{path}/group[{group_id}]"
        if "props" in group:
            check_props_list(group["props"], current_path)
        for control in group.get("controls", []):
            check_control(control, current_path)
        for subgroup in group.get("groups", []):
            check_group(subgroup, current_path)

    # Check catalog-level metadata props
    catalog_data = catalog.get("catalog", {})
    metadata = catalog_data.get("metadata", {})
    if "props" in metadata:
        check_props_list(metadata["props"], "catalog/metadata")

    # Check groups
    for group in catalog_data.get("groups", []):
        check_group(group, "catalog")

    # Check top-level controls
    for control in catalog_data.get("controls", []):
        check_control(control, "catalog")

    result.stats["props_missing_ns"] = len(issues)

    if not issues:
        return

    # Group by prop name for summary
    by_name: dict[str, int] = {}
    for issue in issues:
        name = issue["prop_name"]
        by_name[name] = by_name.get(name, 0) + 1

    result.add_error("Rule 17", f"Found {len(issues)} props missing namespace (ns)")
    for name, count in sorted(by_name.items(), key=lambda x: -x[1]):
        result.add_error("Rule 17", f"  - {name}: {count} occurrences")

    # Show first few details
    for issue in issues[:5]:
        result.add_error("Rule 17", f"  Example: {issue['location']} → {issue['prop_name']}=\"{issue['prop_value']}\"")
    if len(issues) > 5:
        result.add_error("Rule 17", f"  ... and {len(issues) - 5} more")


def run_trestle_validate(catalog_path: Path, result: ValidationResult):
    """Rule 16: Run actual trestle validate command as final check.

    This runs `trestle validate -f <catalog>` to catch any issues that
    our custom rules might miss. Requires trestle to be installed and
    the catalog to be in a trestle workspace.
    """
    import subprocess
    import shutil

    # Check if trestle is available
    trestle_path = shutil.which("trestle")
    if not trestle_path:
        result.add_warning("Rule 16", "trestle command not found - skipping trestle validate")
        return

    # Find trestle workspace root (look for .trestle directory)
    catalog_dir = catalog_path.parent
    trestle_root = None

    # Search up to 5 levels up for trestle workspace
    current = catalog_dir
    for _ in range(5):
        if (current / ".trestle").exists():
            trestle_root = current
            break
        parent = current.parent
        if parent == current:  # Reached filesystem root
            break
        current = parent

    if not trestle_root:
        result.add_warning("Rule 16", "Not in a trestle workspace - skipping trestle validate")
        return

    # Run trestle validate
    try:
        proc = subprocess.run(
            ["trestle", "validate", "-f", str(catalog_path)],
            cwd=str(trestle_root),
            capture_output=True,
            text=True,
            timeout=60,
        )

        if proc.returncode == 0:
            result.stats["trestle_validate"] = "PASSED"
        else:
            result.stats["trestle_validate"] = "FAILED"
            # Parse error output
            error_output = proc.stderr or proc.stdout
            if error_output:
                # Extract first few error lines
                error_lines = error_output.strip().split('\n')
                for line in error_lines[:10]:
                    if line.strip():
                        result.add_error("Rule 16", f"trestle: {line.strip()}")
                if len(error_lines) > 10:
                    result.add_error("Rule 16", f"... and {len(error_lines) - 10} more trestle errors")
            else:
                result.add_error("Rule 16", "trestle validate failed (no error details)")

    except subprocess.TimeoutExpired:
        result.add_warning("Rule 16", "trestle validate timed out after 60 seconds")
    except Exception as e:
        result.add_warning("Rule 16", f"Could not run trestle validate: {e}")


def validate_catalog(
    catalog_path: Path,
    merged_path: Path | None = None,
    ref_path: Path | None = None,
    excluded_path: Path | None = None,
    skip_trestle: bool = False,
) -> ValidationResult:
    """Run all validation checks on a catalog."""
    result = ValidationResult()

    # Check CONFIG completeness first (Rule 13)
    check_rule_13_config_completeness(result)

    # Load catalog
    try:
        with open(catalog_path, "r", encoding="utf-8") as f:
            catalog = json.load(f)
    except json.JSONDecodeError as e:
        result.add_error("JSON", f"Invalid JSON: {e}")
        return result
    except FileNotFoundError:
        result.add_error("File", f"Catalog file not found: {catalog_path}")
        return result

    # Load reference catalog if provided
    ref_catalog = None
    if ref_path and ref_path.exists():
        try:
            with open(ref_path, "r", encoding="utf-8") as f:
                ref_catalog = json.load(f)
        except Exception as e:
            result.add_warning("File", f"Could not load reference catalog: {e}")

    # Load excluded_units.json if provided (SPEC §7.5). The file has two
    # sections:
    #   - top-level keys (any key other than `_groups`) = control IDs to
    #     be treated as intentionally missing by Rule 10
    #   - `_groups` = group IDs (with their merged.txt header string)
    #     for whole-group exclusions, used by Rule 12 to accept the
    #     group as intentionally absent from catalog.json
    # Absence of the file, or a file with neither section, is the normal
    # case, not an error: most documents have none.
    excluded_controls: dict = {}
    excluded_groups: dict = {}
    if excluded_path and excluded_path.exists():
        try:
            with open(excluded_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                _groups_section = loaded.get("_groups", {})
                if isinstance(_groups_section, dict):
                    excluded_groups = _groups_section
                excluded_controls = {k: v for k, v in loaded.items() if k != "_groups"}
            else:
                result.add_warning("File", f"excluded_units.json is not a JSON object, ignoring: {excluded_path}")
        except Exception as e:
            result.add_warning("File", f"Could not load excluded_units.json: {e}")

    # Run all checks
    check_rule_1_duplicate_ids(catalog, result)
    check_rule_2_empty_lists(catalog, result)
    check_rule_3_sequential_order(catalog, result)
    check_rule_4_duplicate_group_ids(catalog, result)
    check_rule_5_toc_contamination(catalog, result)
    check_rule_6_complete_extraction(catalog, result, excluded_groups)
    check_rule_7_valid_content(catalog, result)
    check_rule_8_balanced_structure(catalog, result)
    check_rule_9_oscal_compliance(catalog, result)
    check_rule_10_sequential_gaps(catalog, result, excluded_controls)
    check_rule_11_control_count(catalog, ref_catalog, result, excluded_groups)

    # Rule 12: Compare against merged.txt if provided
    check_rule_12_merged_text_comparison(catalog, merged_path, result, excluded_groups)

    # Rule 14: Check for page artifacts in prose
    check_rule_14_prose_contamination(catalog, result)

    # Rule 15: Check trestle/OSCAL ID and title compliance
    check_rule_15_trestle_compliance(catalog, result)

    # Rule 16: Run actual trestle validate command
    if not skip_trestle:
        run_trestle_validate(catalog_path, result)
    else:
        result.add_warning("Rule 16", "trestle validate skipped via --skip-trestle")

    # Rule 17: Check props namespace
    check_rule_17_props_namespace(catalog, result)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Comprehensive OSCAL catalog validation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Validation Rules:
  Rule 1:  No duplicate IDs (ERROR)
  Rule 2:  No empty lists (ERROR)
  Rule 3:  Sequential control order (ERROR)
  Rule 4:  No duplicate group IDs (ERROR)
  Rule 5:  No TOC contamination (ERROR)
  Rule 6:  Complete section extraction (ERROR)
  Rule 6a: Required groups present (ERROR)
  Rule 6b: Required controls in groups (ERROR)
  Rule 7:  Valid control content (ERROR)
  Rule 8:  Balanced structure (ERROR)
  Rule 9:  OSCAL format compliance (ERROR)
  Rule 10: Sequential gaps (WARNING; per-ID downgrade via excluded_units.json)
  Rule 11: Control count comparison (WARNING)
  Rule 12: Merged.txt group comparison (ERROR; per-group downgrade via
           excluded_units.json _groups)
  Rule 13: CONFIG completeness (ERROR)
  Rule 14: Prose contamination (ERROR)
  Rule 15: Trestle ID/title compliance (ERROR)
  Rule 16: Trestle validate command (ERROR)
        """
    )
    parser.add_argument("catalog", type=Path, help="Path to catalog.json file")
    parser.add_argument("--merged", type=Path, help="Path to merged.txt (for group comparison)")
    parser.add_argument("--reference", type=Path, help="Path to reference catalog.json")
    parser.add_argument("--excluded", type=Path, help="Path to excluded_units.json (non-requirement control IDs, see SPEC §7.5)")
    parser.add_argument("--skip-trestle", action="store_true", help="Skip trestle validate command")

    args = parser.parse_args()

    if not args.catalog.exists():
        print(f"Error: Catalog file not found: {args.catalog}", file=sys.stderr)
        sys.exit(1)

    # Auto-detect merged.txt if not provided
    merged_path = args.merged
    if not merged_path:
        # Try to find merged.txt in same directory as catalog
        catalog_dir = args.catalog.parent
        possible_merged = list(catalog_dir.glob("*-merged.txt"))
        if len(possible_merged) == 1:
            merged_path = possible_merged[0]
            print(f"Auto-detected merged.txt: {merged_path}")

    # Auto-detect excluded_units.json if not provided (same directory as
    # catalog.json — this is where the Phase 2 author subagent writes it).
    # Absence is normal (most documents have none); this is a convenience
    # default, not a required file.
    excluded_path = args.excluded
    if not excluded_path:
        candidate = args.catalog.parent / "excluded_units.json"
        if candidate.is_file():
            excluded_path = candidate
            print(f"Auto-detected excluded_units.json: {excluded_path}")

    result = validate_catalog(
        args.catalog, merged_path, args.reference, excluded_path,
        skip_trestle=args.skip_trestle,
    )
    print_results(result, args.catalog)

    sys.exit(0 if result.passed else 1)


if __name__ == "__main__":
    main()
