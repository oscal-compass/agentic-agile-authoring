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

"""CONFIG for validate.py — NIST SP 800-171 Revision 3.

Document: 'Protecting Controlled Unclassified Information in Nonfederal
Systems and Organizations' (NIST SP 800-171r3, May 2024). Section 3
'The Security Requirements' contains 17 requirement families
(numbered 3.1 through 3.17), each of which becomes a top-level OSCAL
group. Each family holds N zero-padded security requirements of the
form 03.NN.MM (e.g. 03.01.01 Account Management). 33 of the 130
requirements are marked 'Withdrawn' — they are kept in the catalog as
short controls (their prose is a one-sentence pointer to the requirement
that superseded them), because they are still numbered units in the
source document and removing them would leave numbering gaps that
Rule 10 would flag.
"""

CONFIG = {
    # ---------------- Identity + expected shape --------------------------
    "name": "nist-sp-800-171-r3",
    # Auto-derived from len(required_groups) - len(excluded_units._groups).
    "expected_groups": None,
    # 130 requirements in Section 3 of the PDF.
    "expected_controls_min": 128,
    "expected_controls_max": 132,

    # ---------------- Required-group / required-control checks -----------
    # Top-level groups = the 17 requirement families under Section 3.
    # Titles as they appear in merged.txt (e.g. "3.1. Access Control").
    # Rule 6a does a case-insensitive substring match, so listing the
    # family NAME is what actually matches "family 1 Access Control".
    "required_sections": [],
    "required_groups": [
        "Access Control",
        "Awareness and Training",
        "Audit and Accountability",
        "Configuration Management",
        "Identification and Authentication",
        "Incident Response",
        "Maintenance",
        "Media Protection",
        "Personnel Security",
        "Physical Protection",
        "Risk Assessment",
        "Security Assessment and Monitoring",
        "System and Communications Protection",
        "System and Information Integrity",
        "Planning",
        "System and Services Acquisition",
        "Supply Chain Risk Management",
    ],
    # No hierarchical structure below family; controls are flat within each.
    "required_controls_in_groups": {},

    # ---------------- Rule 12 group-pattern override ---------------------
    # NIST SP 800-171r3 uses "3.N. Family Name" as its family (group)
    # header — a shape none of the default Part/Chapter/Schedule/Annex
    # patterns match. Leaving this as None means Rule 12 finds no groups
    # in merged.txt and returns early (Rule 6a still enforces the
    # required_groups list). Overriding with r"^(3)\.(\d+)\.\s+[A-Z]"
    # would work in principle but the normalized "3 N" form does not
    # match the extracted group titles ("family N ..."), producing
    # spurious Rule 12 errors. Rule 6a is sufficient coverage for this
    # PDF's group set.
    "merged_text_group_patterns": None,

    # ---------------- Rule-specific skip flags ---------------------------
    # No known intentional numbering gaps in the source doc; every
    # 03.NN.MM slot up to the family's declared maximum is present
    # (including Withdrawn placeholders).
    "skip_rule_3_sequential_order": False,
    "skip_rule_10_sequential_gaps": False,

    # Leave as True (default) — excluded_units.json is empty in this
    # run but the flag has no cost.
    "respect_excluded_units_for_rule_10": True,

    # ---------------- Content-hygiene patterns ---------------------------
    # NIST-specific page furniture. The running header on every page is
    # "NIST SP 800-171r3   Protecting Controlled Unclassified Information"
    # followed by a bare "May 2024" date line — both are already stripped
    # by generate.py's page_number_patterns but keep them here as a
    # belt-and-braces guard in case any leak through into a control title.
    "garbage_title_patterns": [
        r"^May\s+\d{4}$",
        r"^NIST\s+SP\s+800-171r3",
        r"^\d{4}$",
        r"^Page\s+\d+",
    ],
    # Line-anchored prose contamination for the NIST running header/date
    # footer and generic page-number lines.
    "prose_contamination_patterns": [
        r"^NIST\s+SP\s+800-171r3\s+Protecting\s+Controlled\s+Unclassified\s+Information\s*$",
        r"^May\s+2024\s*$",
        r"^Page\s+\d+\s+of\s+\d+",
    ],
    # No known mid-sentence header artifacts on this PDF; leave empty.
    "prose_contamination_patterns_anywhere": [],
}
