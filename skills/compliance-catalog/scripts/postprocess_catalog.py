#!/usr/bin/env python3
"""
Post-process OSCAL catalog.json files to fix common text extraction issues:
1. Word tokenization errors (spaces inserted in words like "th e" -> "the")
2. Hyphenated line breaks ("re-\nquirements" -> "requirements")
3. Excessive whitespace normalization
4. Merge metadata from reference catalog (parties, props, published, remarks, title, version)
5. Sort groups and controls by their ID (natural order)
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


# Common word patterns that get broken by space insertion
# Format: (broken_pattern, fixed_word)
# These are ordered by frequency from corpus analysis
TOKENIZATION_FIXES = [
    # Highest frequency patterns (>100 occurrences)
    (r'\brefe r\b', 'refer'),
    (r'\bnecessar y\b', 'necessary'),
    (r'\bma y\b', 'may'),
    (r'\bcar r\b', 'carr'),
    (r'\bhav e\b', 'have'),
    (r'\bwhic h\b', 'which'),
    (r'\bla w\b', 'law'),
    (r'\ban y\b', 'any'),
    (r'\bth e\b', 'the'),
    (r'\bdela y\b', 'delay'),

    # High frequency patterns (50-100 occurrences)
    (r'\biat e\b', 'iate'),
    (r'\bcountr y\b', 'country'),
    (r'\binfor m\b', 'inform'),
    (r'\bte r\b', 'ter'),
    (r'\bprovid e\b', 'provide'),
    (r'\bthe r\b', 'ther'),
    (r'\btake n\b', 'taken'),
    (r'\bthe f\b', 'thef'),
    (r'\brepor t\b', 'report'),
    (r'\bpar t\b', 'part'),
    (r'\bthe y\b', 'they'),
    (r'\bdraf t\b', 'draft'),
    (r'\bof t\b', 'oft'),
    (r'\bfor m\b', 'form'),

    # Medium frequency patterns (20-50 occurrences)
    (r'\bregulator y\b', 'regulatory'),
    (r'\band f\b', 'andf'),
    (r'\bfo r\b', 'for'),
    (r'\bdesignate d\b', 'designated'),
    (r'\bstar t\b', 'start'),
    (r'\binte r\b', 'inter'),
    (r'\bintende d\b', 'intended'),
    (r'\bprovider s\b', 'providers'),
    (r'\bspecifi c\b', 'specific'),
    (r'\bsuppor t\b', 'support'),
    (r'\bcop y\b', 'copy'),
    (r'\bcour t\b', 'court'),
    (r'\brisk s\b', 'risks'),
    (r'\bresponsible f\b', 'responsiblef'),
    (r'\bcatego r\b', 'categor'),
    (r'\bsmar t\b', 'smart'),
    (r'\bwithdra w\b', 'withdraw'),
    (r'\bterm s\b', 'terms'),
    (r'\blega l\b', 'legal'),
    (r'\bdat e\b', 'date'),
    (r'\btha t\b', 'that'),
    (r'\bthe t\b', 'thet'),
    (r'\brequeste d\b', 'requested'),
    (r'\bho w\b', 'how'),
    (r'\bhar m\b', 'harm'),
    (r'\btak e\b', 'take'),
    (r'\bmak e\b', 'make'),
    (r'\bar e\b', 'are'),
    (r'\badvisor y\b', 'advisory'),
    (r'\bvisor y\b', 'visory'),
    (r'\bparagrap h\b', 'paragraph'),
    (r'\bor m\b', 'orm'),

    # Lower frequency but important patterns
    (r'\bwit h\b', 'with'),
    (r'\bused f\b', 'usedf'),
    (r'\bto f\b', 'tof'),
    (r'\bpaymen t\b', 'payment'),
    (r'\bexcep t\b', 'except'),
    (r'\bcompl y\b', 'comply'),
    (r'\bbreac h\b', 'breach'),
    (r'\brelate d\b', 'related'),
    (r'\bperfor m\b', 'perform'),
    (r'\bmanufacture r\b', 'manufacturer'),
    (r'\bite r\b', 'iter'),
    (r'\bfine s\b', 'fines'),
    (r'\bdata f\b', 'dataf'),
    (r'\badop t\b', 'adopt'),
    (r'\bthe p\b', 'thep'),
    (r'\bregar d\b', 'regard'),
    (r'\bprovided f\b', 'providedf'),
    (r'\bfacilitat e\b', 'facilitate'),
    (r'\bever y\b', 'every'),
    (r'\bed f\b', 'edf'),
    (r'\bplatfor m\b', 'platform'),
    (r'\bmicroenterp r\b', 'microenterpr'),
    (r'\binformatio n\b', 'information'),
    (r'\bwa y\b', 'way'),
    (r'\bvoluntar y\b', 'voluntary'),
    (r'\bthos e\b', 'those'),
    (r'\breasonably f\b', 'reasonablyf'),
    (r'\bInf ormation\b', 'Information'),
    (r'\binf ormation\b', 'information'),
    (r'\bonand\b', 'on and'),
    (r'\bothe r\b', 'other'),
    (r'\borga nizations\b', 'organizations'),
    (r'\bdevelo pment\b', 'development'),
    (r'\bthes e\b', 'these'),
    (r'\bwhil e\b', 'while'),
    (r'\bmai ntaining\b', 'maintaining'),
    (r'\bprotec tion\b', 'protection'),
    (r'\bFram ework\b', 'Framework'),
    (r'\bel ectronic\b', 'electronic'),
    (r'\bGu idelines\b', 'Guidelines'),
    (r'\bP rotection\b', 'Protection'),
    (r'\bindi viduals\b', 'individuals'),
    (r'\bGuidelin es\b', 'Guidelines'),
    (r'\bwit h\b', 'with'),
    (r'\bissu es\b', 'issues'),
    (r'\bbus iness\b', 'business'),
    (r'\bhighli ghting\b', 'highlighting'),
    (r'\bresp ect\b', 'respect'),
    (r'\bFr amework\b', 'Framework'),
    (r'\bprot ections\b', 'protections'),
    (r'\bin formation\b', 'information'),
    (r'\bpa rticularly\b', 'particularly'),
    (r'\bfre e\b', 'free'),
    (r'\bimplem ent\b', 'implement'),
    (r'\bapproach es\b', 'approaches'),
    (r'\bEm powering\b', 'Empowering'),
    (r'\bAuthorit ies\b', 'Authorities'),
    (r'\bmanda te\b', 'mandate'),
    (r'\bprotect individu al\b', 'protect individual'),
    (r'\binternation al\b', 'international'),
    (r'\bCr oss\b', 'Cross'),
    (r'\bBor der\b', 'Border'),
    (r'\bwi th\b', 'with'),
    (r'\btradin g\b', 'trading'),
    (r'\bE ncouraging\b', 'Encouraging'),
    (r'\bth eir\b', 'their'),
    (r'\bPr omoting\b', 'Promoting'),
    (r'\bCOMM ENTARY\b', 'COMMENTARY'),
    (r'\bdefi nitions\b', 'definitions'),
    (r'\bothe rorga nizations\b', 'other organizations'),
    (r'\bthes erealities\b', 'these realities'),
    (r'\bwhil emai ntaining\b', 'while maintaining'),
    (r'\bpla ce\b', 'place'),
    (r'\b1 980\b', '1980'),
    # Additional common patterns
    (r'\btw o\b', 'two'),
    (r'\bkep t\b', 'kept'),
    (r'\bdra w\b', 'draw'),
    (r'\bshal l\b', 'shall'),
    (r'\ballo w\b', 'allow'),
    (r'\bha s\b', 'has'),
    (r'\bda y\b', 'day'),
    (r'\bla y\b', 'lay'),
    (r'\bno t\b', 'not'),
    (r'\bfa r\b', 'far'),
    (r'\bkee p\b', 'keep'),
    (r'\bou t\b', 'out'),
    (r'\bthi s\b', 'this'),
    (r'\bit s\b', 'its'),
    (r'\bdo wn\b', 'down'),
    (r'\bprote cts\b', 'protects'),
    (r'\bpar ticular\b', 'particular'),
    (r'\bautomat ed\b', 'automated'),
    (r'\bfor m par t\b', 'form part'),
    (r'\bform par t\b', 'form part'),
    (r'\bfor m part\b', 'form part'),
    (r'\bfor mpar t\b', 'form part'),
    (r'\bformpar t\b', 'form part'),
    (r'\bf iling\b', 'filing'),
    (r'\bf alls\b', 'falls'),
    (r'\bf all\b', 'fall'),
    (r'\bChapt er\b', 'Chapter'),
    (r'\bcompet ent\b', 'competent'),
    (r'\bauthor ities\b', 'authorities'),
    (r'\bpur poses\b', 'purposes'),
    (r'\binve stigation\b', 'investigation'),
    (r'\bdet ection\b', 'detection'),
    (r'\bcr iminal\b', 'criminal'),
    (r'\bexecut ion\b', 'execution'),
    (r'\bsafeg uarding\b', 'safeguarding'),
    (r'\bU nion\b', 'Union'),
    (r'\bag encies\b', 'agencies'),
    (r'\bleg al\b', 'legal'),
    (r'\badap ted\b', 'adapted'),
    (r'\bconte xt\b', 'context'),
    (r'\bacontroller\b', 'a controller'),
    (r'\bregardl ess\b', 'regardless'),
    (r'\btak es\b', 'takes'),
    (r'\bUni on\b', 'Union'),
    (r'\boffer ing\b', 'offering'),
    (r'\bser vices\b', 'services'),
    (r'\bir respective\b', 'irrespective'),
    (r'\bpa yment\b', 'payment'),
    (r'\bmonitori ng\b', 'monitoring'),
    (r'\bf ar\b', 'far'),
    (r'\baplace\b', 'a place'),
    (r'\bvir tue\b', 'virtue'),
    (r'\bintern ational\b', 'international'),
    (r'\bpu rposes\b', 'purposes'),
    (r'\bsupplemen tary\b', 'supplementary'),
    (r'\bproc essed\b', 'processed'),
    (r'\bsubj ect\b', 'subject'),
    (r'\bid entification\b', 'identification'),
    (r'\binfo rmation\b', 'information'),
    (r'\bproces sor\b', 'processor'),
    (r'\bperso nal\b', 'personal'),
    (r'\bsect ions\b', 'sections'),
    (r'\bme ans\b', 'means'),
    (r'\bproc essing\b', 'processing'),
    (r'\bpr evention\b', 'prevention'),
    (r'\b1981 \b', '1981'),
    (r'\benti ties\b', 'entities'),
    (r'\bdig ital\b', 'digital'),
    (r'\bfo rm\b', 'form'),
    (r'\bi ndividual\b', 'individual'),
    (r'\bcompu ters\b', 'computers'),
    (r'\badistinguishing\b', 'a distinguishing'),
    (r'\baspecific\b', 'a specific'),
    (r'\bSensitiv e\b', 'Sensitive'),
    (r'\bo r\b', 'or'),
    (r'\bArticl e\b', 'Article'),
    (r'\bpara graph\b', 'paragraph'),
    (r'\bthep art\b', 'the part'),
    (r'\bpar tly\b', 'partly'),
    (r'\bState s\b', 'States'),
    (r'\bcarr ying\b', 'carrying'),
    (r'\binterm ediary\b', 'intermediary'),
    (r'\bser vice\b', 'service'),
    (r'\bpro viders\b', 'providers'),
    (r'\bpersona l\b', 'personal'),
    (r'\bscientifi c\b', 'scientific'),
    (r'\bollo w\b', 'ollow'),
    (r'\bte d\b', 'ted'),
    (r'\bar t\b', 'art'),
    (r'\bter r\b', 'terr'),
    (r'\bpar ty\b', 'party'),
    (r'\bsing le\b', 'single'),
    (r'\bthe re\b', 'there'),
    (r'\bdelegat ed\b', 'delegated'),
    (r'\badopt ed\b', 'adopted'),
    (r'\bref er\b', 'refer'),
    (r'\bprovid ed\b', 'provided'),
    (r'\brelat ed\b', 'related'),
    (r'\biter ia\b', 'iteria'),
    (r'\bent er\b', 'enter'),
    (r'\brequest ed\b', 'requested'),
    (r'\brepor ts\b', 'reports'),
    (r'\bprovid er\b', 'provider'),
    (r'\bexte nt\b', 'extent'),
    (r'\bsha ll\b', 'shall'),
    (r'\baccording ly\b', 'accordingly'),
    (r'\bpar ts\b', 'parts'),
    (r'\bthe te\b', 'thete'),
    (r'\bthe pr\b', 'thepr'),
    (r'\bthe cr\b', 'thecr'),
    (r'\bthe po\b', 'thepo'),
    (r'\bthe im\b', 'theim'),
    (r'\bthe fi\b', 'thefi'),
    (r'\benter pr\b', 'enterpr'),
    (r'\brelevant ti\b', 'relevanti'),
    (r'\bter ms\b', 'terms'),
    (r'\bmatt er\b', 'matter'),
    (r'\bcomp ly\b', 'comply'),
    (r'\brega rd\b', 'regard'),
    (r'\bpayme nt\b', 'payment'),
    (r'\bollowi ng\b', 'ollowing'),
    (r'\btak en\b', 'taken'),
    (r'\btoo ls\b', 'tools'),
    (r'\bthe ir\b', 'their'),
    (r'\badministrative fi\b', 'administrativefi'),
    (r'\breal wo\b', 'realwo'),
    (r'\bdata av\b', 'dataav'),
    (r'\baffect ed\b', 'affected'),
    (r'\baffe ct\b', 'affect'),
    (r'\bpreser ve\b', 'preserve'),
    (r'\bfulf il\b', 'fulfil'),
    (r'\bcour ts\b', 'courts'),
    (r'\bdata pr\b', 'datapr'),

    # Additional patterns from second analysis
    (r'\bperson al\b', 'personal'),
    (r'\bbenef its\b', 'benefits'),
    (r'\bbenefits\b', 'benefits'),
    (r'\bbenef i ts\b', 'benefits'),
    (r'\bbenef its\b', 'benefits'),
    (r'\bbenef it s\b', 'benefits'),
    (r'\bbenef its\b', 'benefits'),
    (r'\bben ef its\b', 'benefits'),
    (r'\bbenefi ts\b', 'benefits'),
    (r'\beffo rts\b', 'efforts'),
    (r'\befficien t\b', 'efficient'),
    (r'\bothe r\b', 'other'),
    (r'\bpla ce\b', 'place'),
    (r'\ban d\b', 'and'),
    (r'\ba nd\b', 'and'),
    (r'\bwhe n\b', 'when'),
    (r'\bwher e\b', 'where'),
    (r'\bunde r\b', 'under'),
    (r'\bove r\b', 'over'),
    (r'\baft er\b', 'after'),
    (r'\bbef ore\b', 'before'),
    (r'\bper son\b', 'person'),
    (r'\bne tworks\b', 'networks'),
    (r'\bco llect\b', 'collect'),
    (r'\bs tore\b', 'store'),
    (r'\bre liable\b', 'reliable'),
    (r'\bre gard\b', 'regard'),
    (r'\bre quire\b', 'require'),
    (r'\bse cure\b', 'secure'),
    (r'\bse curity\b', 'security'),
    (r'\bim plement\b', 'implement'),
    (r'\bap plic\b', 'applic'),
    (r'\bac cess\b', 'access'),
    (r'\bef forts\b', 'efforts'),
    (r'\bch oice\b', 'choice'),

]


def fix_generic_single_letter_splits(text: str) -> str:
    """
    Fix generic pattern where a single letter is split from the rest of a word.
    Pattern: "word X" where X is a single letter that completes the word.
    This is very conservative - only fix specific suffix patterns.
    """
    result = text

    # Fix patterns like "necessar y" -> "necessary" (ending in common suffixes)
    # Only fix when preceded by 4+ letters (to be more conservative)
    # and the single letter is a common word-ending letter
    result = re.sub(r'\b([a-z]{4,}) ([y])\b', r'\1\2', result)  # regulatory, country
    result = re.sub(r'\b([a-z]{4,}) ([e])\b', r'\1\2', result)  # provide, have
    result = re.sub(r'\b([a-z]{4,}) ([r])\b', r'\1\2', result)  # refer, other
    result = re.sub(r'\b([a-z]{4,}) ([t])\b', r'\1\2', result)  # report, start
    result = re.sub(r'\b([a-z]{4,}) ([n])\b', r'\1\2', result)  # taken
    result = re.sub(r'\b([a-z]{4,}) ([m])\b', r'\1\2', result)  # inform, perform
    result = re.sub(r'\b([a-z]{4,}) ([s])\b', r'\1\2', result)  # risks, terms
    result = re.sub(r'\b([a-z]{4,}) ([h])\b', r'\1\2', result)  # which, with
    result = re.sub(r'\b([a-z]{4,}) ([d])\b', r'\1\2', result)  # designated

    return result


def fix_tokenization_errors(text: str) -> str:
    """Fix known word tokenization errors where spaces were incorrectly inserted."""
    result = text
    for pattern, replacement in TOKENIZATION_FIXES:
        # Don't use IGNORECASE - preserve original case of text
        result = re.sub(pattern, replacement, result)
    return result


def fix_hyphenated_line_breaks(text: str) -> str:
    """
    Fix hyphenated line breaks where words were split across lines.
    Pattern: "word-\n  continuation" -> "wordcontinuation"
    But preserve intentional hyphenation like "third-party", "organization-defined"
    """
    # Fix hyphen followed by NEWLINE and lowercase continuation (line break in middle of word)
    # This catches patterns like "re-\nquirements" -> "requirements"
    result = re.sub(r'(\w)-\n\s*([a-z])', r'\1\2', text)

    # Fix hyphen followed by just space (not newline) - keep hyphen, remove extra space
    # "organization- defined" -> "organization-defined"
    result = re.sub(r'(\w)- ([a-z])', r'\1-\2', result)

    return result


def fix_line_break_word_splits(text: str) -> str:
    """
    Fix words that were split across lines without hyphen.
    This is very conservative - only fix specific known broken patterns.
    General newline-to-space conversion happens in normalize_whitespace.
    """
    result = text

    # Fix single letter orphaned at end of line that should join with next word
    # Pattern: "i\nnformation" -> "information" (clear word fragment)
    # Only match when a SINGLE letter is at the end of a word boundary (not part of a word)
    # This prevents "has\naccess" from becoming "hasaccess"
    result = re.sub(r'(?<= )([a-z])\n([a-z]+)\b', r'\1\2', result)

    # Known word-break patterns from PDF extraction
    # These are specific fragments that commonly get split
    known_breaks = [
        (r'Blue\nprint', 'Blueprint'),
        (r're\nliable', 'reliable'),
        (r'applic\nable', 'applicable'),
        (r'real\nities', 'realities'),
        (r'importa\nnt', 'important'),
        (r'develo\npment', 'development'),
        (r'ensuring\nthe', 'ensuring the'),
        (r'orpla\nce', 'or place'),
    ]
    for pattern, replacement in known_breaks:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

    return result


def normalize_whitespace(text: str) -> str:
    """Normalize excessive whitespace while preserving paragraph structure."""
    # Replace multiple spaces with single space (but preserve newlines for now)
    result = re.sub(r'[ \t]+', ' ', text)

    # Convert single newlines to spaces, but preserve paragraph breaks
    # A paragraph break is indicated by:
    # - Double newline (\n\n)
    # - Newline followed by a capital letter (new sentence/section)
    # Only convert newlines that are mid-sentence (lowercase continuation)
    result = re.sub(r'\n(?=[a-z])', ' ', result)

    # Normalize multiple newlines to double newline (paragraph break)
    result = re.sub(r'\n{3,}', '\n\n', result)

    # Clean up any resulting multiple spaces
    result = re.sub(r' +', ' ', result)

    return result.strip()


def fix_unicode_escapes(text: str) -> str:
    """
    Fix Unicode escape sequences that should be proper Unicode characters.
    Some PDF extractors or JSON serializers escape characters unnecessarily.

    Examples:
    - Länder -> Länder (ä = U+00E4)
    - controller’s -> controller's (' = U+2019, right single quotation mark)
    """
    # First, decode any raw \uXXXX escape sequences in the string
    # This handles cases where the escape sequence is literal text, not Python escapes
    def replace_unicode_escape(match):
        code_point = int(match.group(1), 16)
        return chr(code_point)

    # Match \uXXXX patterns (4 hex digits)
    result = re.sub(r'\\u([0-9a-fA-F]{4})', replace_unicode_escape, text)

    return result


def process_prose(text: str) -> str:
    """Apply all text fixes to a prose string."""
    if not text:
        return text

    result = text
    result = fix_unicode_escapes(result)  # Fix Unicode escapes first
    result = fix_line_break_word_splits(result)
    result = fix_hyphenated_line_breaks(result)
    result = fix_tokenization_errors(result)
    result = fix_generic_single_letter_splits(result)
    result = normalize_whitespace(result)
    return result


def process_value(obj: Any) -> Any:
    """Recursively process all prose and title fields in a JSON structure."""
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            if key == 'prose' and isinstance(value, str):
                result[key] = process_prose(value)
            elif key == 'title' and isinstance(value, str):
                # Fix Unicode escapes in titles (e.g., Länder, controller's)
                result[key] = fix_unicode_escapes(value)
            else:
                result[key] = process_value(value)
        return result
    elif isinstance(obj, list):
        return [process_value(item) for item in obj]
    else:
        return obj


def natural_sort_key(id_str: str):
    """
    Generate a sort key for natural ordering of IDs.

    Handles:
    - Arabic numerals: part-1, part-2, part-10
    - Roman numerals: chapter-i, chapter-ii, chapter-ix, chapter-x
    - Mixed patterns: adgm-dpr-part-2, eu-gdpr-chapter-iv
    - NIST-style IDs: ac-1, ac-2, ac-11 (sorted as ac-01, ac-02, ac-11)
    - Hierarchical IDs: ac-1.1, ac-1.2, ac-1.10
    """
    # Roman numeral mapping
    roman_values = {
        'i': 1, 'ii': 2, 'iii': 3, 'iv': 4, 'v': 5,
        'vi': 6, 'vii': 7, 'viii': 8, 'ix': 9, 'x': 10,
        'xi': 11, 'xii': 12, 'xiii': 13, 'xiv': 14, 'xv': 15,
        'xvi': 16, 'xvii': 17, 'xviii': 18, 'xix': 19, 'xx': 20,
    }

    def convert_part(part: str):
        """Convert a single part of the ID to a sortable value."""
        # Check if it's a pure number
        if part.isdigit():
            return (0, int(part), part)
        # Check if it's a roman numeral
        if part.lower() in roman_values:
            return (0, roman_values[part.lower()], part)
        # Check for mixed alphanumeric like "1a", "1b", "2a" or trailing letters
        match = re.match(r'^(\d+)([a-z]*)$', part.lower())
        if match:
            num, suffix = match.groups()
            # Return tuple that sorts by number first, then suffix
            return (0, int(num), suffix if suffix else '')
        # Otherwise return as string (alphabetic parts sort together)
        return (1, 0, part.lower())

    # Split by common delimiters and convert each part
    parts = re.split(r'[-_.]', id_str)
    return [convert_part(p) for p in parts]


def sort_groups_and_controls(catalog: dict) -> dict:
    """
    Sort groups and controls within the catalog by their ID in natural order.
    """
    if 'catalog' not in catalog:
        return catalog

    def sort_items(items: list) -> list:
        """Sort a list of items (groups or controls) by ID."""
        if not items:
            return items
        return sorted(items, key=lambda x: natural_sort_key(x.get('id', '')))

    def process_group(group: dict) -> dict:
        """Recursively process a group, sorting its controls and subgroups."""
        result = group.copy()
        if 'controls' in result:
            result['controls'] = sort_items(result['controls'])
            # Also sort any nested controls within controls
            for ctrl in result['controls']:
                if 'controls' in ctrl:
                    ctrl['controls'] = sort_items(ctrl['controls'])
        if 'groups' in result:
            result['groups'] = sort_items([process_group(g) for g in result['groups']])
        return result

    # Sort top-level groups
    if 'groups' in catalog['catalog']:
        catalog['catalog']['groups'] = sort_items(
            [process_group(g) for g in catalog['catalog']['groups']]
        )

    # Sort top-level controls if any
    if 'controls' in catalog['catalog']:
        catalog['catalog']['controls'] = sort_items(catalog['catalog']['controls'])

    return catalog


def merge_metadata_from_ref(catalog: dict, ref_catalog: dict) -> dict:
    """
    Merge metadata from reference catalog into the processed catalog.

    Copies from ref: parties, props, published, remarks, title, version
    Preserves from catalog: last-modified (updated to now), oscal-version
    """
    if 'catalog' not in catalog or 'catalog' not in ref_catalog:
        return catalog

    ref_meta = ref_catalog.get('catalog', {}).get('metadata', {})
    if not ref_meta:
        return catalog

    cat_meta = catalog.get('catalog', {}).get('metadata', {})

    # Fields to copy from reference
    fields_to_copy = ['parties', 'props', 'published', 'remarks', 'title', 'version']

    for field in fields_to_copy:
        if field in ref_meta:
            cat_meta[field] = ref_meta[field]

    # Update last-modified to current time
    cat_meta['last-modified'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00')

    catalog['catalog']['metadata'] = cat_meta
    return catalog


def collect_all_ids(obj: Any, ids: list = None) -> list:
    """Recursively collect all 'id' values from a JSON structure."""
    if ids is None:
        ids = []
    if isinstance(obj, dict):
        if 'id' in obj:
            ids.append(obj['id'])
        for v in obj.values():
            collect_all_ids(v, ids)
    elif isinstance(obj, list):
        for item in obj:
            collect_all_ids(item, ids)
    return ids


def count_controls(catalog: dict) -> int:
    """Count total number of controls in a catalog."""
    count = 0
    if 'catalog' not in catalog:
        return count

    def count_in_group(group: dict) -> int:
        total = len(group.get('controls', []))
        for subgroup in group.get('groups', []):
            total += count_in_group(subgroup)
        for ctrl in group.get('controls', []):
            total += len(ctrl.get('controls', []))
        return total

    for group in catalog['catalog'].get('groups', []):
        count += count_in_group(group)
    count += len(catalog['catalog'].get('controls', []))
    return count


def validate_catalog(catalog: dict, ref_catalog: dict = None) -> dict:
    """
    Validate a catalog for common issues.

    Returns dict with:
    - valid: bool
    - errors: list of error messages
    - warnings: list of warning messages
    - stats: dict with counts
    """
    from collections import Counter

    errors = []
    warnings = []
    stats = {}

    # Collect all IDs
    ids = collect_all_ids(catalog)
    stats['total_ids'] = len(ids)

    # Check for duplicate IDs
    id_counts = Counter(ids)
    duplicates = {id_: count for id_, count in id_counts.items() if count > 1}
    if duplicates:
        errors.append(f"DUPLICATE IDS FOUND: {len(duplicates)} IDs appear multiple times")
        for id_, count in sorted(duplicates.items()):
            errors.append(f"  - '{id_}' appears {count} times")
    stats['duplicate_ids'] = len(duplicates)

    # Count controls
    control_count = count_controls(catalog)
    stats['control_count'] = control_count

    # Compare with reference if provided
    if ref_catalog:
        ref_count = count_controls(ref_catalog)
        stats['ref_control_count'] = ref_count
        diff = control_count - ref_count
        stats['control_diff'] = diff

        if abs(diff) > ref_count * 0.1 and abs(diff) > 5:
            warnings.append(f"Significant control count difference: {control_count} vs reference {ref_count} ({diff:+d})")
        elif diff != 0:
            warnings.append(f"Minor control count difference: {control_count} vs reference {ref_count} ({diff:+d})")

    # Check for TOC contamination (dot leaders in titles)
    def check_toc_contamination(obj: Any, path: str = '') -> list:
        issues = []
        if isinstance(obj, dict):
            title = obj.get('title', '')
            if '...' in title or '…' in title or '……' in title:
                issues.append(f"{path}/{obj.get('id', 'unknown')}: TOC artifact in title: {title[:60]}")
            for g in obj.get('groups', []):
                issues.extend(check_toc_contamination(g, f"{path}/{obj.get('id', '')}"))
            for c in obj.get('controls', []):
                issues.extend(check_toc_contamination(c, f"{path}/{obj.get('id', '')}"))
        return issues

    toc_issues = check_toc_contamination(catalog.get('catalog', {}))
    if toc_issues:
        errors.extend(["TOC CONTAMINATION DETECTED:"] + toc_issues[:10])
        if len(toc_issues) > 10:
            errors.append(f"  ... and {len(toc_issues) - 10} more")
    stats['toc_contamination'] = len(toc_issues)

    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'warnings': warnings,
        'stats': stats
    }


def process_catalog(input_path: Path, output_path: Path, ref_path: Optional[Path] = None, validate: bool = True) -> dict:
    """Process a catalog.json file and write the fixed version."""
    with open(input_path, 'r', encoding='utf-8') as f:
        catalog = json.load(f)

    processed = process_value(catalog)

    # Sort groups and controls by ID
    processed = sort_groups_and_controls(processed)

    # Load reference catalog if provided
    ref_catalog = None
    if ref_path and ref_path.exists():
        try:
            with open(ref_path, 'r', encoding='utf-8') as f:
                ref_catalog = json.load(f)
            processed = merge_metadata_from_ref(processed, ref_catalog)
        except Exception as e:
            print(f"    Warning: Could not merge metadata from {ref_path}: {e}")

    # Validate the processed catalog
    validation_result = None
    if validate:
        validation_result = validate_catalog(processed, ref_catalog)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(processed, f, indent=2, ensure_ascii=False)

    return {
        'input': str(input_path),
        'output': str(output_path),
        'validation': validation_result
    }


def load_ref_mapping(jsonl_path: Path) -> dict:
    """
    Load reference file mapping from a JSONL file.

    Expected format per line:
    {"pdf_file": "...", "output_file": "...", "ref_file": "catalogs/Name/catalog.json"}

    Returns dict: {catalog_name: ref_file_path}
    """
    mapping = {}
    if not jsonl_path.exists():
        return mapping

    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                # Extract catalog name from output_file path
                output_file = entry.get('output_file', '')
                ref_file = entry.get('ref_file', '')
                if output_file and ref_file:
                    # e.g., "merged_output_14/EU-GDPR/catalog.json" -> "EU-GDPR"
                    parts = Path(output_file).parts
                    if len(parts) >= 2:
                        catalog_name = parts[-2]
                        mapping[catalog_name] = ref_file
            except json.JSONDecodeError:
                continue

    return mapping


def validate_single_catalog(catalog_path: Path, ref_path: Optional[Path] = None) -> bool:
    """Validate a single catalog file and print results."""
    with open(catalog_path, 'r', encoding='utf-8') as f:
        catalog = json.load(f)

    ref_catalog = None
    if ref_path and ref_path.exists():
        with open(ref_path, 'r', encoding='utf-8') as f:
            ref_catalog = json.load(f)

    result = validate_catalog(catalog, ref_catalog)

    print(f"Validation: {catalog_path}")
    print(f"  Total IDs: {result['stats'].get('total_ids', 0)}")
    print(f"  Control count: {result['stats'].get('control_count', 0)}")

    if ref_catalog:
        print(f"  Reference count: {result['stats'].get('ref_control_count', 0)}")
        diff = result['stats'].get('control_diff', 0)
        print(f"  Difference: {diff:+d}")

    if result['errors']:
        print(f"\n❌ ERRORS ({len(result['errors'])}):")
        for err in result['errors']:
            print(f"    {err}")

    if result['warnings']:
        print(f"\n⚠ WARNINGS ({len(result['warnings'])}):")
        for warn in result['warnings']:
            print(f"    {warn}")

    if result['valid'] and not result['warnings']:
        print("\n✓ Catalog is valid")

    return result['valid']


def main():
    # Check for --validate flag first
    if len(sys.argv) >= 2 and sys.argv[1] == '--validate':
        if len(sys.argv) < 3:
            print("Usage: postprocess_catalog.py --validate <catalog.json> [reference.json]")
            print("  Validates a single catalog file for common issues")
            sys.exit(1)
        catalog_path = Path(sys.argv[2])
        ref_path = Path(sys.argv[3]) if len(sys.argv) > 3 else None
        is_valid = validate_single_catalog(catalog_path, ref_path)
        sys.exit(0 if is_valid else 1)

    if len(sys.argv) < 3:
        print("Usage: postprocess_catalog.py <input_dir> <output_dir> [ref_mapping.jsonl]")
        print("       postprocess_catalog.py --validate <catalog.json> [reference.json]")
        print("")
        print("Batch mode: Processes all catalog.json files in subdirectories")
        print("  Optional: ref_mapping.jsonl provides reference catalog paths for metadata merge")
        print("")
        print("Validate mode: Checks a single catalog for issues (duplicate IDs, TOC artifacts, etc.)")
        sys.exit(1)

    input_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    ref_jsonl = Path(sys.argv[3]) if len(sys.argv) > 3 else None

    if not input_dir.exists():
        print(f"Error: Input directory '{input_dir}' does not exist")
        sys.exit(1)

    # Load reference mapping if provided
    ref_mapping = {}
    if ref_jsonl:
        ref_mapping = load_ref_mapping(ref_jsonl)
        print(f"Loaded {len(ref_mapping)} reference mappings from {ref_jsonl}")

    # Find all catalog.json files
    catalog_files = list(input_dir.glob('*/catalog.json'))

    if not catalog_files:
        print(f"No catalog.json files found in {input_dir}")
        sys.exit(1)

    print(f"Processing {len(catalog_files)} catalogs...")

    merged_count = 0
    for catalog_path in sorted(catalog_files):
        catalog_name = catalog_path.parent.name
        output_path = output_dir / catalog_name / 'catalog.json'

        # Find reference file if mapping exists
        ref_path = None
        if catalog_name in ref_mapping:
            ref_path = Path(ref_mapping[catalog_name])
            # Handle relative paths - try common base directories
            if not ref_path.exists():
                # Try with trestle.ws prefix
                alt_path = Path('trestle.ws') / ref_mapping[catalog_name]
                if alt_path.exists():
                    ref_path = alt_path

        try:
            result = process_catalog(catalog_path, output_path, ref_path)
            validation = result.get('validation')

            status_parts = []
            if ref_path and ref_path.exists():
                status_parts.append("+ metadata")
                merged_count += 1

            if validation:
                stats = validation.get('stats', {})
                if validation['valid']:
                    status_parts.append(f"{stats.get('control_count', '?')} controls")
                else:
                    print(f"  ❌ {catalog_name}: VALIDATION ERRORS")
                    for err in validation['errors'][:5]:
                        print(f"      {err}")
                    continue

                for warn in validation.get('warnings', []):
                    status_parts.append(f"⚠ {warn}")

            status = f" ({', '.join(status_parts)})" if status_parts else ""
            print(f"  ✓ {catalog_name}{status}")
        except Exception as e:
            print(f"  ✗ {catalog_name}: {e}")

    print(f"\nDone. Output written to {output_dir}")
    if ref_mapping:
        print(f"Metadata merged from reference: {merged_count}/{len(catalog_files)}")


if __name__ == '__main__':
    main()
