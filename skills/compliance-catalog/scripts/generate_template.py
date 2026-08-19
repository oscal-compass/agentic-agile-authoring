#!/usr/bin/env python3
"""
PDF-specific extraction script template.

Copy this file and rename it for the target PDF, then customize
CONFIG and PATTERNS to match the PDF's format.

==============================================================================
CRITICAL: NO HARDCODING OF CATALOG CONTENT
==============================================================================
DO NOT hardcode any catalog content (titles, prose, section names) in this
script. All content MUST be extracted directly from the PDF.

FORBIDDEN (causes hallucination in catalog):
    PART_TITLES = {"1": "Preliminary", "2": "Administration", ...}
    SCHEDULE_TITLES = {"1": "Data Protection Principles", ...}
    SECTION_TO_PART = {"1": "1", "2": "1", ...}  # Mapping sections to parts
    control["title"] = "Some hardcoded title"

ALLOWED (extraction logic only):
    CONFIG settings (toc_pages, patterns, id_prefix, metadata)
    PATTERNS for regex matching
    Structural logic in parse_structure()

WHY: The purpose of using a script is to AVOID AI hallucination. If you
hardcode content, the catalog will contain whatever you typed, NOT what's
actually in the PDF. This causes:
    - Wrong Part/Schedule/Chapter titles
    - Incorrect section assignments
    - Content that doesn't match the source document

The ONLY exception is CONFIG["metadata"] which contains document-level info
that may not be extractable from the PDF (publisher, jurisdiction, etc.).
==============================================================================

Usage:
    1. Copy: cp generate_template.py generate_<name>.py
    2. Edit CONFIG with PDF-specific settings
    3. Edit PATTERNS to define article structure patterns
    4. Run: python generate_<name>.py <input.pdf> <output_dir>
    5. Validate: python validate_<name>.py <output_dir>/catalog.json
    6. If errors, fix this script based on validation guidance
    7. Repeat steps 4-6 until validation passes

ITERATIVE FIX LOOP:
    This script is designed to be modified based on validate.py feedback.
    Each validation error points to a specific function/config to fix.

    Common fix locations (marked with # FIX POINT comments):
    - CONFIG["toc_pages"]      → Rule 5 (TOC contamination)
    - CONFIG["id_prefix"]      → Rule 1, 4 (duplicate IDs)
    - postprocess_text()       → Rule 5, 7 (garbage content)
    - parse_structure()        → Rule 1, 2, 3, 6 (structure issues)
    - generate_control_id()    → Rule 1 (duplicate control IDs)
    - generate_group_id()      → Rule 4 (duplicate group IDs)
    - handle_page_break()      → Rule 8 (truncation)

    Catalog assembly (excluded_units.json handling, group-drop-when-empty,
    OSCAL metadata construction) is NOT a fix point — it lives in
    `generate_lib.assemble_catalog()`, a shipped READ-ONLY sibling module.
    Rule 2 / Rule 9 issues that would previously have been fixed inside
    `generate_catalog()` are now impossible to introduce here because the
    logic is not in this file. If Rule 2 fires, fix `parse_structure()`
    so it does not emit empty groups; if Rule 9 fires, the OSCAL shape
    is wrong at the library level — report it, do not patch it here.
"""

import argparse
import os
import re
import sys

from pdf2image import convert_from_path
from pypdf import PdfReader, PdfWriter

# The invariant catalog-assembly lives in a sibling READ-ONLY module,
# `generate_lib.py`, which the Phase 2 authoring subagent copies verbatim
# next to this script. Prepend the script's own directory to sys.path so
# `from generate_lib import assemble_catalog` resolves regardless of the
# caller's CWD. See SPEC §7.5 and SKILL.md Phase 2 for why assembly is
# not part of this customizable template.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate_lib import (  # noqa: E402
    assemble_catalog,
    looks_like_prose_remainder,
    split_title_and_prose_on_section_line,
)

# pdfplumber provides better text extraction for some PDFs (handles kerning/spacing issues)
# Uncomment if pypdf produces broken spacing like "Gener al" instead of "General"
# import pdfplumber

# Uncomment if using OCR
# import pytesseract
# from PIL import Image


# ===== PDF-specific settings (MUST EDIT) =====
CONFIG = {
    "name": "CHANGE_ME",  # Output file prefix
    "id_prefix": "CHANGE_ME",  # Control ID prefix (e.g., "hk-pdpo", "eu-gdpr")
    # FIX POINT for Rule 1, 4: Use unique prefix to prevent ID collisions
    "title": "CHANGE_ME",  # Catalog title (formal document title)
    "version": "1.0",  # Document version (e.g., "2.0", "2018", "Law No. 13,709/2018")
    "language": "eng",  # OCR language (eng, jpn, deu, fra, etc.)
    "dpi": 200,  # Image conversion DPI (300 recommended for OCR)
    "use_ocr": False,  # Whether to use OCR
    # pdfplumber vs pypdf: pdfplumber handles font-kerning quirks (present in
    # essentially every EU / IBM-published PDF) much better and never worse
    # in our tests. Default to True; do NOT flip this off for a document
    # unless you have concrete evidence pypdf produces cleaner output for it.
    "use_pdfplumber": True,
    # FIX POINT for Rule 5: Expand this range if TOC content leaks into catalog
    "toc_pages": [],  # Page numbers to skip (0-indexed), e.g., list(range(0, 10))
    "header_lines": 0,  # Number of header lines to remove per page
    "footer_lines": 0,  # Number of footer lines to remove per page
    # FIX POINT for Rule 7 / Rule 14: page-header and page-footer patterns.
    # Every line matching one of these regexes is dropped during
    # postprocess_text(). Add document-specific header/footer patterns
    # here to prevent them from ending up as prose contamination inside
    # controls (validate.py Rule 14).
    #
    # Patterns kept here should be structurally safe on any compliance
    # PDF — they match forms that occur on virtually every PDF page as
    # running headers/footers and never as legitimate body text:
    #   * bare page-number lines
    #   * "Page N of M" boilerplate
    #   * EU Official Journal masthead ("L 119/34 EN Official Journal…")
    #   * EU date-stamp lines that appear on every page ("4.5.2016 EN …")
    # These EU patterns are safe defaults because their shape is very
    # specific (date + " EN " + "Official Journal"); no valid regulation
    # text ever matches them.
    "page_number_patterns": [
        r"^\s*\d+\s*$",  # bare page-number
        r"^Page\s+\d+",
        # --- EU Official Journal boilerplate (safe cross-document defaults) ---
        r"^L\s+\d+/\d+\s+EN\s+Official\s+Journal",  # "L 119/34 EN Official Journal…"
        r"^\d+\.\d+\.\d{4}\s+EN\s+Official\s+Journal",  # "4.5.2016 EN Official Journal…"
        r"^EN\s+Official\s+Journal\s+of\s+the\s+European\s+Union",  # standalone masthead
    ],
    # FIX POINT for Rule 5, 7, 14: Add patterns for garbage titles/content
    # These patterns filter out page headers, footers, and artifacts
    "garbage_line_patterns": [
        # CAUTION: Don't filter lines too aggressively!
        # Short titles like "Tasks", "Chair", "Scope" (5 chars) are valid.
        # Use 0-2 chars max, or customize per document.
        r"^.{0,2}$",  # Very short lines (1-2 chars, likely artifacts)
        r"^\s*[-–—]\s*$",  # Just dashes
        r"^\s*[•·]\s*$",  # Just bullets
        # Page headers/footers that embed in prose (Rule 14)
        # Customize these patterns per document:
        r"^Part\s+\d+[A-Za-z]?—Division\s+\d+\s+\d+-\d+$",  # "Part 5—Division 1 5-12"
        r"^Schedule\s+\d+—Part\s+\d+\s+S\d+-\d+$",  # "Schedule 6—Part 1 S6-2"
        r"^Part\s+\d+\s+\d+-\d+$",  # "Part 1 1-2"
        r"^Schedule\s+\d+\s+S\d+-\d+$",  # "Schedule 1 S1-2"
        # Add more document-specific patterns as needed, e.g.:
        # r"^Verified Copy$",
        # r"^Last updated",
        # r"^Cap\.\s+\d+",
    ],
    # FIX POINT for Rule 5: TOC line patterns to filter
    # These lines indicate Table of Contents contamination.
    #
    # CRITICAL: keep this list restricted to dot-leader / ellipsis markers.
    # Do NOT add a "trailing number" pattern like r"\s+\d{1,3}\s*$" — it
    # looks like a reasonable "TOC entries end with a page number" filter
    # but it also matches legitimate section headings such as
    # `Article 1`, `Article 12`, `Section 42`, `Rule 5`. Enabling that
    # pattern on any law/regulation PDF will delete every control heading
    # from merged.txt, producing groups >= 1 but controls == 0 — a
    # catalog that looks structurally valid but is empty of controls.
    "toc_line_patterns": [
        r"\.{3,}",  # Three or more dots (dot leaders)
        r"…{2,}",  # Multiple ellipsis
        r"……",  # Chinese dot leaders
    ],
    # ===== Metadata fields (MUST EDIT for complete catalog) =====
    "metadata": {
        # Publishing organization - who issued this document
        "parties": [
            {
                "name": "CHANGE_ME",  # e.g., "European Parliament and Council of the European Union"
                "type": "organization",
                "remarks": "CHANGE_ME",  # e.g., "Original author of GDPR regulation"
            }
        ],
        # Document properties - key metadata about the document
        "props": [
            {
                "name": "source",
                "value": "CHANGE_ME",  # e.g., "CELEX:32016R0679", document reference number
                "ns": "https://ibm.com/concert/ns/oscal",
            },
            {
                "name": "jurisdiction",
                "value": "CHANGE_ME",  # e.g., "European Union", "Brazil", "United States"
                "ns": "https://ibm.com/concert/ns/oscal",
            },
            # Optional: Add more props as appropriate for the document
            # {
            #     "name": "regulation-type",
            #     "value": "...",  # e.g., "EU Regulation", "Federal Law", "Industry Standard"
            #     "ns": "https://ibm.com/concert/ns/oscal",
            # },
            # {
            #     "name": "effective-date",
            #     "value": "...",  # e.g., "2018-05-25"
            #     "ns": "https://ibm.com/concert/ns/oscal",
            # },
        ],
        # Publication date - when the document was officially published
        "published": "CHANGE_ME",  # e.g., "2016-04-27T00:00:00Z" (ISO 8601 format)
        # Description of the catalog
        "remarks": "CHANGE_ME",  # e.g., "OSCAL catalog representation of GDPR controls..."
    },
}


# ===== Article structure regex patterns (customize per PDF) =====
# CRITICAL: Customize these patterns based on PDF analysis
# Run analyze_pdf.py first to understand the document structure
PATTERNS = {
    # Chapter level (becomes groups)
    # FIX POINT for Rule 6a: Ensure this matches ALL group formats
    # Examples: "CHAPTER I", "Chapter 1", "PART I", "Part 1", "SCHEDULE 1", "Schedule 1"
    # Use case-insensitive: r"(?i)^(CHAPTER|PART|SCHEDULE)\s+(\w+)[:\.]?\s*(.*)$"
    "chapter": r"^(CHAPTER|Chapter|PART|Part)\s+(\w+)[:\.]?\s*(.*)$",

    # Section level (becomes controls)
    # FIX POINT for Rule 6, 6b: Ensure this matches ALL control formats
    # Examples: "1. Title", "Section 1", "Article 1", "Principle 1"
    "section": r"^(\d+)\.\s+(.+)$",

    # Subsection level (included in prose)
    "subsection": r"^\((\d+)\)\s+",

    # Item level
    "item": r"^\(([a-z])\)\s+",

    # NESTED CONTROLS: For hierarchical documents where controls exist within groups
    # FIX POINT for Rule 6b: Add patterns for nested structures
    # Example for HK PDPO: Schedule 1 contains "Principle 1", "Principle 2", etc.
    # "nested_control": r"^(Principle|Article|Section)\s+(\d+)[:\.]?\s*(.*)$",
}


# ===== Multi-pattern support for documents with structure changes =====
# Some documents change structure mid-way (e.g., General Provisions vs Chapters).
# Define document zones with different extraction patterns here.
#
# Each zone has:
#   - detector: function(text, page_num) -> bool that returns True if this zone applies
#   - patterns: override patterns for this zone
#   - id_prefix: prefix for control IDs to ensure uniqueness
#
# Zones are checked in order; first matching zone wins.
# If no zone matches, default PATTERNS are used.
#
# Example for Thailand-PDPA style documents:
# DOCUMENT_ZONES = [
#     {
#         "name": "general_provisions",
#         "detector": lambda text, page_num: "GENERAL PROVISIONS" in text or page_num < 10,
#         "patterns": {
#             "section": r"^Section\s+(\d+)\.\s*(.*)$",
#         },
#         "id_prefix": "general",
#     },
#     {
#         "name": "chapters",
#         "detector": lambda text, page_num: re.search(r"CHAPTER\s+[IVX]+", text) is not None,
#         "patterns": {
#             "chapter": r"^CHAPTER\s+([IVX]+)\s*[:\.]?\s*(.*)$",
#             "section": r"^Section\s+(\d+)\.\s*(.*)$",
#         },
#         "id_prefix": None,  # Use chapter ID as prefix
#     },
# ]
DOCUMENT_ZONES = []  # Empty = single-pattern mode (use PATTERNS everywhere)


def get_active_zone(text: str, page_num: int) -> dict | None:
    """
    Determine which document zone applies to the given text/page.
    Returns the zone dict if found, None if default PATTERNS should be used.
    """
    for zone in DOCUMENT_ZONES:
        detector = zone.get("detector")
        if detector and detector(text, page_num):
            return zone
    return None


def get_patterns_for_context(text: str, page_num: int) -> dict:
    """
    Get the appropriate patterns for the current context.
    Merges zone-specific patterns with defaults.
    """
    zone = get_active_zone(text, page_num)
    if zone and zone.get("patterns"):
        merged = PATTERNS.copy()
        merged.update(zone["patterns"])
        return merged
    return PATTERNS


def get_id_prefix_for_context(text: str, page_num: int, group_id: str = None) -> str:
    """
    Get the ID prefix for controls in the current context.
    Ensures unique IDs across document zones.
    """
    zone = get_active_zone(text, page_num)
    if zone:
        if zone.get("id_prefix"):
            return zone["id_prefix"]
        elif group_id:
            return group_id
    return CONFIG["name"].lower().replace("-", "_")


def split_pdf(input_pdf: str, output_dir: str) -> list[str]:
    """Split PDF into individual pages."""
    reader = PdfReader(input_pdf)
    pdf_files = []

    for i, page in enumerate(reader.pages, 1):
        writer = PdfWriter()
        writer.add_page(page)

        output_path = os.path.join(output_dir, f"{CONFIG['name']}-page-{i:03d}.pdf")
        with open(output_path, "wb") as f:
            writer.write(f)
        pdf_files.append(output_path)
        print(f"Created: {output_path}")

    return pdf_files


def convert_to_images(pdf_files: list[str]) -> list[str]:
    """Convert PDF pages to images."""
    image_files = []

    for pdf_file in pdf_files:
        images = convert_from_path(pdf_file, dpi=CONFIG["dpi"])
        for img in images:
            png_path = pdf_file.replace(".pdf", ".png")
            img.save(png_path)
            image_files.append(png_path)
            print(f"Created: {png_path}")

    return image_files


def extract_text_from_page(pdf_path: str, png_path: str) -> str:
    """
    Extract text from a page.

    Customize this function if PDF-specific processing is needed.
    Examples: multi-column handling, special header/footer removal, etc.

    TEXT EXTRACTION METHODS:
    1. pypdf (default): Fast, works for most PDFs
    2. pdfplumber: Better handling of kerning/spacing issues
       - Use when pypdf produces broken words like "Gener al" or "prote ction"
       - Set CONFIG["use_pdfplumber"] = True
    3. OCR: For scanned PDFs or image-based PDFs
       - Set CONFIG["use_ocr"] = True
    """
    if CONFIG["use_ocr"]:
        # Use OCR for scanned/image PDFs
        import pytesseract
        from PIL import Image

        img = Image.open(png_path)
        text = pytesseract.image_to_string(img, lang=CONFIG["language"])
    elif CONFIG.get("use_pdfplumber", False):
        # Use pdfplumber for PDFs with spacing/kerning issues
        import pdfplumber

        with pdfplumber.open(pdf_path) as pdf:
            text = pdf.pages[0].extract_text() or ""
    else:
        # Default: Direct extraction from PDF using pypdf
        reader = PdfReader(pdf_path)
        text = reader.pages[0].extract_text() or ""

    # Post-processing
    text = postprocess_text(text)

    return text


def postprocess_text(text: str) -> str:
    """
    Post-process extracted text.

    FIX POINT for Rule 5, 7:
    - Add patterns to garbage_line_patterns in CONFIG to filter unwanted lines
    - Increase header_lines/footer_lines to remove page headers/footers
    - Add TOC detection: if "..." in line, skip it

    ANTI-CATASTROPHE GUARD (do not remove):
    A common fix-loop failure mode is a subagent inserting a
    whitespace-flattening regex like `re.sub(r"\\s+", " ", text)` into
    this function. `\\s` matches `\\n`, so the substitution collapses
    the whole document into a single line, `parse_structure()` then
    fails to match `^Article N$` / `^CHAPTER N$` and produces zero
    controls. The guard at the tail of this function detects that
    outcome (drastic length shrink or complete newline loss) and
    reverts to the original input so the run can proceed on
    unprocessed text rather than an empty catalog.
    """
    _original_text = text  # snapshot for the anti-catastrophe guard below
    _original_lines = text.count("\n")
    _original_len = len(text)
    lines = text.split("\n")

    # Remove header/footer lines
    if CONFIG["header_lines"] > 0:
        lines = lines[CONFIG["header_lines"]:]
    if CONFIG["footer_lines"] > 0 and len(lines) > CONFIG["footer_lines"]:
        lines = lines[:-CONFIG["footer_lines"]]

    # Remove page numbers and garbage lines
    filtered_lines = []
    for line in lines:
        stripped = line.strip()

        # Skip page numbers
        is_page_number = False
        for pattern in CONFIG["page_number_patterns"]:
            if re.match(pattern, stripped):
                is_page_number = True
                break
        if is_page_number:
            continue

        # FIX POINT for Rule 5: Skip TOC lines (dot leaders, page numbers)
        is_toc_line = False
        for pattern in CONFIG.get("toc_line_patterns", []):
            if re.search(pattern, stripped):
                is_toc_line = True
                break
        if is_toc_line:
            continue
        # Fallback check for common TOC patterns
        if "..." in stripped or "……" in stripped or "…" in stripped:
            continue

        # FIX POINT for Rule 7: Skip garbage lines
        is_garbage = False
        for pattern in CONFIG.get("garbage_line_patterns", []):
            if re.match(pattern, stripped):
                is_garbage = True
                break
        if is_garbage:
            continue

        filtered_lines.append(line)
    lines = filtered_lines

    # Normalize blank lines
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)

    result = text.strip()

    # Anti-catastrophe guard. If postprocess_text somehow shrank the
    # text by > 30 % or destroyed nearly all newlines (both signatures
    # of the `\s+` bug described in the docstring), fall back to the
    # unprocessed original so downstream parsing at least has line
    # structure to work with. This is a soft fail: log to stderr and
    # keep going, don't raise — a hard crash here would waste the
    # entire iteration.
    result_len = len(result)
    result_lines = result.count("\n")
    shrink_ratio = result_len / max(1, _original_len)
    lines_ratio = result_lines / max(1, _original_lines)
    if _original_len > 1000 and (shrink_ratio < 0.7 or lines_ratio < 0.5):
        import sys as _sys
        _sys.stderr.write(
            "\n[postprocess_text GUARD] catastrophic shrink detected — "
            f"input={_original_len} chars / {_original_lines} lines, "
            f"output={result_len} chars / {result_lines} lines "
            f"(shrink={shrink_ratio:.0%}, lines_kept={lines_ratio:.0%}).\n"
            "[postprocess_text GUARD] This is usually caused by a "
            "regex like `re.sub(r\"\\\\s+\", \" \", text)` that collapses "
            "newlines. Reverting to unprocessed input for this run so "
            "extraction can proceed. Fix postprocess_text in generate.py "
            "to preserve line boundaries (see prompt Anti-patterns).\n\n"
        )
        _sys.stderr.flush()
        return _original_text.strip()

    return result


def merge_pages(text_files: list[str], output_path: str) -> str:
    """Merge page texts with page break handling."""
    merged = []

    for txt_file in sorted(text_files):
        with open(txt_file, "r", encoding="utf-8") as f:
            page_text = f.read()

        if merged:
            # Handle page breaks
            merged_text = handle_page_break(merged[-1], page_text)
            merged[-1] = merged_text[0]
            merged.append(merged_text[1])
        else:
            merged.append(page_text)

    full_text = "\n\n".join(merged)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_text)

    print(f"Created: {output_path}")
    return full_text


def handle_page_break(prev_text: str, next_text: str) -> tuple[str, str]:
    """
    Handle page breaks.

    FIX POINT for Rule 8:
    - Fix hyphenation handling to rejoin split words
    - Handle mid-sentence page breaks
    """
    prev_lines = prev_text.rstrip().split("\n")
    next_lines = next_text.lstrip().split("\n")

    if not prev_lines or not next_lines:
        return (prev_text, next_text)

    last_line = prev_lines[-1]
    first_line = next_lines[0]

    # Handle hyphenation (mid-word line breaks)
    if last_line.rstrip().endswith("-"):
        # Remove hyphen and concatenate
        prev_lines[-1] = last_line.rstrip()[:-1] + first_line.lstrip()
        next_lines = next_lines[1:]
        return ("\n".join(prev_lines), "\n".join(next_lines))

    # Handle mid-sentence page breaks
    if last_line.strip() and not last_line.rstrip().endswith((".", ":", ";", ")", "]", '"', "'")):
        # If next page starts with lowercase, concatenate
        if first_line.strip() and first_line.strip()[0].islower():
            prev_lines[-1] = last_line.rstrip() + " " + first_line.lstrip()
            next_lines = next_lines[1:]
            return ("\n".join(prev_lines), "\n".join(next_lines))

    return (prev_text, next_text)


def sanitize_oscal_id(raw_id: str) -> str:
    """
    Sanitize an ID to be OSCAL NCName compliant AND follow the standard naming convention.

    ==============================================================================
    CONTROL ID NAMING CONVENTION
    ==============================================================================
    IDs must follow this format for proper validation and sequence checking:

    ALLOWED CHARACTERS:
    - Lowercase letters (a-z)
    - Digits (0-9)
    - Hyphens (-) as segment separators

    NOT ALLOWED:
    - Underscores, parentheses, brackets, periods, uppercase letters
    - Metadata in ID (like MIL levels) - put these in control props instead

    VALID PATTERNS:
    - prefix-N-letter: "asset-1-a", "threat-2-b" (C2M2-style)
    - prefix-N: "pdpa-1", "art-10" (law articles)
    - prefix-N-N: "section-1-2" (nested sections)

    INVALID PATTERNS:
    - "asset-1-mil1-a" → MIL in ID (use "asset-1-a", put MIL in props)
    - "asset_1_a" → underscores (use "asset-1-a")
    - "ASSET-1-A" → uppercase (use "asset-1-a")

    WHY THIS MATTERS:
    - validate.py Rule 10 checks ID sequence continuity
    - Non-standard formats cause false negatives in gap detection
    ==============================================================================

    OSCAL NCName requirements (enforced by trestle validate):
    - Must START with letter (a-z, A-Z) or underscore (_)
    - Can CONTAIN letters, digits, hyphens (-), dots (.), underscores (_)
    - Must NOT contain parentheses (), brackets [], spaces, or other special chars

    Examples:
    - "03.01.01" → "ctrl-03-01-01" (prefix with letter, dots to hyphens)
    - "1.S.A" → "ctrl-1-s-a" (prefix with letter, lowercase)
    - "tx-dir-ca-7(4)" → "tx-dir-ca-7-4" (remove parentheses)
    - "Part 1" → "part-1" (replace space with hyphen)
    """
    if not raw_id:
        return "unknown"

    # Replace common problematic characters
    sanitized = raw_id.strip()

    # Convert to lowercase first
    sanitized = sanitized.lower()

    # Replace spaces with hyphens
    sanitized = sanitized.replace(" ", "-")

    # Replace periods with hyphens (for standard format)
    sanitized = sanitized.replace(".", "-")

    # Replace underscores with hyphens (for standard format)
    sanitized = sanitized.replace("_", "-")

    # Replace parentheses with hyphens
    sanitized = re.sub(r'\(([^)]*)\)', r'-\1', sanitized)  # "(4)" → "-4"
    sanitized = sanitized.replace("(", "-").replace(")", "")

    # Replace brackets with hyphens
    sanitized = sanitized.replace("[", "-").replace("]", "")

    # Replace other special characters with hyphens
    sanitized = re.sub(r'[^a-z0-9\-]', '-', sanitized)

    # Remove consecutive hyphens
    sanitized = re.sub(r'-+', '-', sanitized)

    # Remove leading/trailing hyphens
    sanitized = sanitized.strip('-')

    # Ensure ID starts with letter (OSCAL NCName requirement)
    if sanitized and sanitized[0].isdigit():
        sanitized = f"ctrl-{sanitized}"

    return sanitized if sanitized else "unknown"


def sanitize_title(raw_title: str) -> str:
    """
    Sanitize a title to be OSCAL compliant.

    OSCAL title requirements (enforced by trestle validate):
    - Must NOT contain newline characters (\\n or \\r)
    - Should be a single line of text

    This function:
    - Replaces newlines with spaces
    - Collapses multiple spaces
    - Strips leading/trailing whitespace
    """
    if not raw_title:
        return ""

    # Replace newlines and carriage returns with spaces
    sanitized = raw_title.replace('\n', ' ').replace('\r', ' ')

    # Collapse multiple spaces
    sanitized = re.sub(r'\s+', ' ', sanitized)

    # Strip leading/trailing whitespace
    return sanitized.strip()


def generate_control_id(group_id: str, section_num: str) -> str:
    """
    Generate a unique control ID that is OSCAL NCName compliant.

    FIX POINT for Rule 1, Rule 15:
    - Include group context to prevent duplicates across different sections
    - Use CONFIG["id_prefix"] for document-specific prefix
    - Ensure ID is OSCAL NCName compliant (starts with letter, no special chars)
    - Format: {id_prefix}-{section_num}
    """
    prefix = CONFIG.get("id_prefix", CONFIG["name"]).lower()

    # Sanitize section_num to ensure OSCAL compliance
    safe_section = sanitize_oscal_id(section_num)

    # Remove the "ctrl-" prefix if sanitize_oscal_id added it (we have our own prefix)
    if safe_section.startswith("ctrl-"):
        safe_section = safe_section[5:]

    # Include group context to ensure uniqueness
    return f"{prefix}-{safe_section}"


def generate_group_id(group_type: str, group_num: str, parent_context: str = "") -> str:
    """
    Generate a unique group ID that is OSCAL NCName compliant.

    FIX POINT for Rule 4, Rule 15:
    - Include parent context to prevent duplicates
    - Example: "schedule-1-part-1" instead of just "part-1"
    - Ensure ID is OSCAL NCName compliant
    """
    prefix = CONFIG.get("id_prefix", CONFIG["name"]).lower()

    # Sanitize group_type and group_num
    safe_type = sanitize_oscal_id(group_type)
    safe_num = sanitize_oscal_id(group_num)

    # Remove "ctrl-" prefix if added by sanitize
    if safe_type.startswith("ctrl-"):
        safe_type = safe_type[5:]
    if safe_num.startswith("ctrl-"):
        safe_num = safe_num[5:]

    if parent_context:
        group_id = f"{parent_context}-{safe_type}-{safe_num}"
    else:
        group_id = f"{prefix}-{safe_type}-{safe_num}"

    return group_id


def parse_structure(text: str, page_num: int = 1) -> list[dict]:
    """
    Parse article structure from text.

    ============================================================================
    CRITICAL: ALL TITLES MUST COME FROM THE PDF TEXT
    ============================================================================
    DO NOT create dictionaries like PART_TITLES or SCHEDULE_TITLES to map
    numbers to titles. This causes hallucination in the catalog.

    WRONG:
        PART_TITLES = {"1": "Preliminary", "2": "Administration"}
        title = PART_TITLES.get(chapter_num, "")

    RIGHT:
        # Extract title from the line following the chapter header
        title = chapter_match.group(3)  # Captured from regex
        # Or read the next non-empty line as the title
    ============================================================================

    FIX POINT for Rule 1, 2, 3, 6, 6a, 6b:
    - Rule 1: Ensure generate_control_id() produces unique IDs
    - Rule 2: Filter out empty groups at the end
    - Rule 3: Sort controls by numeric value after parsing
    - Rule 6: Check regex patterns match all section formats
    - Rule 6a: Ensure PATTERNS["chapter"] matches ALL groups (Schedules, Parts, etc.)
    - Rule 6b: For nested structures, check PATTERNS["nested_control"] or custom logic

    Args:
        text: The text to parse
        page_num: Current page number (used for zone detection)

    CUSTOMIZATION FOR HIERARCHICAL DOCUMENTS:
    If your document has nested structures (e.g., Principles within Schedules),
    you may need to:
    1. Add "nested_control" to PATTERNS
    2. Add detection logic below the chapter/section detection
    3. Use DOCUMENT_ZONES for different extraction per section

    Example for HK PDPO (Schedule 1 contains Principles):
    ```python
    # After chapter detection, check for nested controls
    if current_group and "schedule" in current_group["id"].lower():
        nested_match = re.match(r"^(Principle)\s+(\d+)[:\.]?\s*(.*)$", line, re.IGNORECASE)
        if nested_match:
            # Handle as a control within the schedule
            ...
    ```
    """
    groups = []
    current_group = None
    current_control = None
    control_counter = {}  # Track control numbers per group for unique IDs

    # Defense-in-depth against duplicate extraction. Some PDFs put the
    # same Article header string in more than one place — a table of
    # contents at the front, the body itself, an appendix listing at the
    # back, in-prose cross-references ("... under Section 6A ..."), or a
    # per-Schedule mini-TOC. Once a control ID has been emitted, seeing
    # its section marker again means we are re-encountering the same
    # unit, not a new one, and we must NOT create a second control for
    # it. The observed failure mode on the Australia Privacy Act 1988
    # PDF was 88173 control slots with only 826 distinct IDs (average
    # ~107 copies of each real control), producing a 155 MB catalog.json
    # that no validator could reasonably digest.
    #
    # `seen_control_ids` is populated only when a section is ACCEPTED
    # into `current_group`; a re-match on an already-emitted ID
    # short-circuits by parking the section body as prose on the
    # already-existing control instead of spawning a new one, and skips
    # the section header line itself. `seen_group_ids` does the same
    # thing for chapter/group markers so a TOC's "Part 1" and the body's
    # "Part 1" collapse into one group whose `controls` list is the union
    # of the two occurrences (which, after per-control dedupe, means the
    # body's control set with the TOC entries filtered out).
    seen_control_ids: dict[str, dict] = {}   # control_id -> the control dict
    seen_group_ids: dict[str, dict] = {}     # group_id -> the group dict

    lines = text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        i += 1

        if not line:
            continue

        # Get context-appropriate patterns
        patterns = get_patterns_for_context(line, page_num)

        # Detect chapter/group (Part, Chapter, Schedule, etc.)
        chapter_match = re.match(patterns["chapter"], line, re.IGNORECASE)
        if chapter_match:
            # Save previous group — same double-append guard as the
            # section branch. If `current_control` was reused by the
            # duplicate-ID guardrail, it's already in the group's
            # controls list. Same for `current_group`: it may have been
            # re-pointed at an already-appended instance.
            if current_control and current_group and current_control not in current_group["controls"]:
                current_group["controls"].append(current_control)
            if current_group and current_group not in groups:
                groups.append(current_group)

            chapter_type = chapter_match.group(1)
            chapter_num = chapter_match.group(2)
            chapter_title = chapter_match.group(3).strip() if chapter_match.group(3) else ""

            # FIX POINT for Rule 5: Multi-line title extraction
            # Read subsequent lines if title is empty or ends with preposition/article
            title_lines = [chapter_title] if chapter_title else []
            max_title_lines = 4  # Limit to prevent runaway
            while i < len(lines) and len(title_lines) < max_title_lines:
                next_line = lines[i].strip()
                if not next_line:
                    i += 1
                    continue
                # Stop conditions - next structural element
                if re.match(r"^Division\s+\d+", next_line, re.IGNORECASE):
                    break  # Stop at Division headers
                if next_line.startswith("["):
                    i += 1
                    continue  # Skip reference markers like [ss. 30(1)(d)]
                if re.match(patterns["section"], next_line):
                    break  # Stop at next section
                if re.match(patterns["chapter"], next_line, re.IGNORECASE):
                    break  # Stop at next chapter/part/schedule
                if re.match(r"^Subpart\s+\d+", next_line, re.IGNORECASE):
                    break  # Stop at subpart
                # If we have no title yet, take this line
                if not title_lines:
                    title_lines.append(next_line)
                    i += 1
                    continue
                # Check if current title looks complete (doesn't end with preposition/article)
                current_title = " ".join(title_lines)
                if not current_title.endswith((" in", " of", " to", " for", " by", " the", " a", " an", " or", " and", " with", " from", " without")):
                    break  # Title looks complete
                # Add next line to continue the title
                title_lines.append(next_line)
                i += 1
            chapter_title = " ".join(title_lines)

            # FIX POINT for Rule 4, Rule 15: Use generate_group_id for unique IDs
            group_id = generate_group_id(chapter_type, chapter_num)

            # Sanitize title to ensure OSCAL compliance (no newlines)
            full_title = sanitize_title(f"{chapter_type} {chapter_num} {chapter_title}")

            # Defense-in-depth against duplicate group extraction. Same
            # reasoning as `seen_control_ids`: a TOC and the body will
            # both surface "Part 1" as a chapter marker, and without
            # this guard we would create TWO `smk-part-1` groups with
            # overlapping controls. Re-encountering a known group ID
            # means "we are re-entering that group", not "there is a
            # second group with the same name" — so re-point
            # `current_group` at the existing instance.
            existing_group = seen_group_ids.get(group_id)
            if existing_group is not None:
                # Prefer the longer/more descriptive title if the first
                # occurrence was a TOC entry.
                if full_title and len(full_title) > len(existing_group.get("title") or ""):
                    existing_group["title"] = full_title
                current_group = existing_group
                current_control = None
                continue

            current_group = {
                "id": group_id,
                "title": full_title,
                "controls": [],
            }
            seen_group_ids[group_id] = current_group
            current_control = None
            control_counter[group_id] = 0
            continue

        # FIX POINT for Rule 6b: Detect nested controls (e.g., Principles within Schedules)
        # Uncomment and customize if your document has nested structures:
        # if current_group and patterns.get("nested_control"):
        #     nested_match = re.match(patterns["nested_control"], line, re.IGNORECASE)
        #     if nested_match:
        #         if current_control:
        #             current_group["controls"].append(current_control)
        #         nested_type = nested_match.group(1)
        #         nested_num = nested_match.group(2)
        #         nested_title = nested_match.group(3).strip() if len(nested_match.groups()) > 2 else ""
        #         group_id = current_group["id"]
        #         control_id = generate_control_id(group_id, f"{nested_type.lower()}-{nested_num}")
        #         current_control = {
        #             "id": control_id,
        #             "title": f"{nested_type} {nested_num} {nested_title}".strip(),
        #             "prose": "",
        #             "label": f"{nested_type} {nested_num}",
        #         }
        #         continue

        # Detect section
        section_match = re.match(patterns["section"], line)
        if section_match:
            # Save previous control — but only if it's a NEW one. If
            # `current_control` was re-pointed at an existing control by
            # the duplicate-ID guardrail below, it's already in the
            # group's controls list; appending again would double-insert.
            if current_control and current_group and current_control not in current_group["controls"]:
                current_group["controls"].append(current_control)

            section_num = section_match.group(1)
            section_title = section_match.group(2) if len(section_match.groups()) > 1 else ""

            # =================================================================
            # TITLE / PROSE BOUNDARY — call the shared helper
            # =================================================================
            # Many law-and-regulation PDFs put the ARTICLE NUMBER and the FIRST
            # SENTENCE OF THE ARTICLE on the same line, e.g.:
            #
            #     Article 1 This Law is enacted for the purpose of regulating
            #     data processing, ensuring data security, promoting
            #     ...
            #
            # A regex like ^Article\s+(\d+)\s+(.*)$ then captures the *whole
            # first body sentence* as `section_title`, and if we naively let
            # the multi-line title extractor below keep consuming lowercase-
            # continuation lines, the "title" fills up with several hundred
            # characters of body text and the control's prose ends up empty.
            # That is the Rule 7 ("empty or too short prose") + Rule 14
            # ("prose contamination") stall we see repeatedly.
            #
            # `split_title_and_prose_on_section_line()` in generate_lib.py
            # makes the call heuristically. If the captured remainder looks
            # like body prose (long, sentence-terminated, starts with a
            # sentence-opener, ends with a preposition/conjunction, or has
            # an internal comma-then-lowercase pattern), the helper returns
            # `("", <remainder-as-prose-seed>)`; otherwise it returns
            # `(<remainder-as-title>, "")`. Do NOT re-implement this in
            # per-document generate.py — the helper is version-locked to
            # generate_lib.py so all documents share the same behaviour.
            title_from_line, prose_seed = split_title_and_prose_on_section_line(section_title)
            section_title = title_from_line

            # Skip the multi-line title-extraction pass entirely when the
            # helper decided the captured remainder was body prose. If we
            # didn't skip, the extractor would happily keep vacuuming
            # body-text lines into a still-empty title and re-create the
            # exact failure the helper just prevented.
            if not prose_seed:
                # FIX POINT: Multi-line title extraction for sections
                # Some documents have section titles spanning multiple lines
                # (e.g., "Transparent information, communication and modalities for\nthe exercise of the rights")
                title_lines = [section_title] if section_title else []
                max_title_lines = 5
                while i < len(lines) and len(title_lines) < max_title_lines:
                    next_line = lines[i].strip()
                    if not next_line:
                        i += 1
                        continue
                    # Stop conditions
                    if re.match(r"^\d+\.\s+", next_line):  # Numbered paragraph
                        break
                    if re.match(r"^\([a-z]\)\s+", next_line):  # Lettered item
                        break
                    if re.match(patterns["section"], next_line):  # Another section
                        break
                    if re.match(patterns["chapter"], next_line, re.IGNORECASE):  # Chapter
                        break
                    # If no title yet, take this line — but if IT looks
                    # like body prose, bail out immediately (the helper's
                    # heuristic applies just as well to the next line as
                    # to the same-line remainder).
                    if not title_lines:
                        if looks_like_prose_remainder(next_line):
                            break
                        title_lines.append(next_line)
                        i += 1
                        continue
                    # Check if current title looks complete
                    current_title = " ".join(title_lines)
                    if current_title.endswith((" in", " of", " to", " for", " by", " the", " a", " an", " or", " and", " with", " from")):
                        # Incomplete - continue reading
                        title_lines.append(next_line)
                        i += 1
                        continue
                    # Check if next line is a continuation (starts with lowercase)
                    if next_line and next_line[0].islower() and not re.match(r"^\([a-z]\)", next_line):
                        title_lines.append(next_line)
                        i += 1
                        continue
                    break  # Title is complete
                section_title = " ".join(title_lines)

            # Create default group if none exists
            if not current_group:
                # Use zone-specific ID prefix if available
                id_prefix = get_id_prefix_for_context(line, page_num)
                # Reuse the default group across chunks so a document
                # that never emits a chapter header stays as a single
                # "General Provisions" group instead of accidentally
                # cloning it.
                existing_default = seen_group_ids.get(id_prefix)
                if existing_default is not None:
                    current_group = existing_default
                else:
                    current_group = {
                        "id": id_prefix,
                        "title": "General Provisions",
                        "controls": [],
                    }
                    seen_group_ids[id_prefix] = current_group
                    control_counter[id_prefix] = 0

            # FIX POINT for Rule 1, Rule 15: Generate unique control ID
            group_id = current_group["id"]
            control_id = generate_control_id(group_id, section_num)

            # Sanitize title to ensure OSCAL compliance (no newlines)
            safe_title = sanitize_title(section_title)

            # Defense-in-depth: is this a re-encounter of a control we
            # already extracted? See the `seen_control_ids` comment near
            # the top of this function for the rationale (TOC, per-
            # Schedule mini-TOCs, back-of-book indexes, in-prose
            # cross-references, and PDF quirks all cause the same
            # Article header string to appear more than once).
            #
            # When the ID is already known, we DO NOT emit a second
            # control. Instead we re-point `current_control` at the
            # existing one so the following body lines land as prose on
            # the original control — this is important for the case
            # where the FIRST occurrence was in a TOC entry (no body)
            # and the SECOND was the real Article header followed by
            # the actual body prose. Skipping outright would lose that
            # body; overwriting would lose earlier state; appending is
            # the safe choice.
            existing = seen_control_ids.get(control_id)
            if existing is not None:
                # Prefer the longer title if the first occurrence was a
                # skeletal TOC entry (short title, empty prose) and the
                # second occurrence is the body header (a proper title).
                if safe_title and len(safe_title) > len(existing.get("title") or ""):
                    existing["title"] = safe_title
                # Attach the same-line prose seed, if any, to the
                # existing control.
                if prose_seed:
                    if existing.get("prose"):
                        existing["prose"] += "\n" + prose_seed
                    else:
                        existing["prose"] = prose_seed
                current_control = existing
                continue

            # If the helper judged the same-line remainder to be body
            # prose (not a title), that text becomes the FIRST line of
            # this control's statement — otherwise it would be lost.
            current_control = {
                "id": control_id,
                "title": safe_title,
                "prose": prose_seed or "",
                "label": section_num,
            }
            seen_control_ids[control_id] = current_control

            continue

        # Add to prose
        if current_control:
            if current_control["prose"]:
                current_control["prose"] += "\n"
            current_control["prose"] += line

    # Add last group/control — same double-append guard as the two
    # save-previous branches above.
    if current_control and current_group and current_control not in current_group["controls"]:
        current_group["controls"].append(current_control)
    if current_group and current_group not in groups:
        groups.append(current_group)

    # FIX POINT for Rule 2: Remove empty groups
    groups = [g for g in groups if g.get("controls")]

    # FIX POINT for Rule 3: Sort controls within each group by numeric label/id
    def control_sort_key(control: dict):
        """
        Generate a sort key for natural ordering of controls.
        Handles patterns like: AC-1, AC-2, AC-11 (numeric sort, not lexicographic)
        Also handles: 1.1, 1.2, 1.10 and mixed patterns.
        """
        # Try label first, fall back to id
        sort_value = control.get("label", "") or control.get("id", "")
        if not sort_value:
            return (999999, "", 0)

        # Split by common delimiters
        parts = re.split(r'[-_.]', sort_value)
        result = []
        for part in parts:
            if part.isdigit():
                result.append((0, int(part), ""))
            else:
                # Check for mixed alphanumeric like "1a", "1b"
                match = re.match(r'^(\d+)([a-z]*)$', part.lower())
                if match:
                    num, suffix = match.groups()
                    result.append((0, int(num), suffix if suffix else ""))
                else:
                    result.append((1, 0, part.lower()))
        return tuple(result) if result else (999999, "", 0)

    for group in groups:
        group["controls"].sort(key=control_sort_key)

    return groups


def main():
    parser = argparse.ArgumentParser(
        description=f"Extract catalog from {CONFIG['name']} PDF"
    )
    parser.add_argument("input_pdf", help="Input PDF file")
    parser.add_argument("output_dir", help="Output directory")
    args = parser.parse_args()

    # Verify configuration
    if CONFIG["name"] == "CHANGE_ME":
        print("Error: Please edit CONFIG['name'] before running")
        print("Edit this script and set the PDF-specific configuration")
        return 1

    # Prepare output directory
    pages_dir = os.path.join(args.output_dir, f"{CONFIG['name']}_pages")
    os.makedirs(pages_dir, exist_ok=True)

    # Phase 1: Split PDF into pages
    print("=" * 60)
    print("Phase 1: Splitting PDF")
    print("=" * 60)
    pdf_files = split_pdf(args.input_pdf, pages_dir)

    # Phase 2: Convert to images
    print("\n" + "=" * 60)
    print("Phase 2: Converting to images")
    print("=" * 60)
    image_files = convert_to_images(pdf_files)

    # Phase 3: Extract text
    print("\n" + "=" * 60)
    print("Phase 3: Extracting text")
    print("=" * 60)
    text_files = []
    for pdf_file, png_file in zip(pdf_files, image_files):
        text = extract_text_from_page(pdf_file, png_file)
        txt_file = pdf_file.replace(".pdf", ".txt")
        with open(txt_file, "w", encoding="utf-8") as f:
            f.write(text)
        text_files.append(txt_file)
        print(f"Created: {txt_file}")

    # Phase 4: Merge pages
    print("\n" + "=" * 60)
    print("Phase 4: Merging pages")
    print("=" * 60)
    merged_path = os.path.join(args.output_dir, "merged.txt")
    full_text = merge_pages(text_files, merged_path)

    # Phase 5: Parse structure and generate catalog
    print("\n" + "=" * 60)
    print("Phase 5: Generating catalog")
    print("=" * 60)
    groups = parse_structure(full_text)
    catalog_path = os.path.join(args.output_dir, "catalog.json")
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

    # Summary
    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)
    print(f"Pages directory: {pages_dir}/")
    print(f"  - PDF files:   {len(pdf_files)}")
    print(f"  - PNG files:   {len(image_files)}")
    print(f"  - TXT files:   {len(text_files)}")
    print(f"Merged text:     {merged_path}")
    print(f"Catalog:         {catalog_path}")

    # Next steps
    print("\nNext steps:")
    print("1. Review extracted text in pages directory")
    print("2. Compare images with text files for accuracy")
    print("3. Check merged text for page break issues")
    print("4. Validate catalog structure and completeness")
    print(f"\nRun validation (MANDATORY before proceeding):")
    print(f"  python skills/pdf-extractor-dev/postprocess_catalog.py --validate {catalog_path}")
    print(f"\nIf validation passes, run post-processing:")
    print(f"  python skills/pdf-extractor-dev/postprocess_catalog.py {catalog_path}")
    print(f"\nRun detailed verification:")
    print(f"  python skills/pdf-extractor-dev/verify_extraction.py {catalog_path} {merged_path}")

    return 0


if __name__ == "__main__":
    exit(main())
