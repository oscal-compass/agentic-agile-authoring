# Generation summary — NIST SP 800-171 Revision 3

## Summary

From `NIST_SP-800-171_rev3.pdf` the agent produced an OSCAL Catalog of
130 controls across 17 groups, validated with 16 built-in structural
and content checks plus the OSCAL trestle schema validator, in a
single fix-loop iteration. Every numbered security requirement in the
source PDF (03.01.01 through 03.17.03, including the 33 units the
source marks as "Withdrawn") is present in the catalog; no content
was removed.

## What was built

- **Source PDF:** NIST Special Publication 800-171, Revision 3,
  *Protecting Controlled Unclassified Information in Nonfederal
  Systems and Organizations* — May 2024, 120 pages, text-native,
  authored by Ron Ross and Victoria Pillitteri (NIST Computer Security
  Division).
- **Catalog shape:** 130 controls organised under the 17 security
  requirement families defined in Section 3 of the source document.
  The families and their control counts:
  - Access Control — 22
  - Awareness and Training — 3
  - Audit and Accountability — 9
  - Configuration Management — 12
  - Identification and Authentication — 12
  - Incident Response — 5
  - Maintenance — 6
  - Media Protection — 9
  - Personnel Security — 2
  - Physical Protection — 8
  - Risk Assessment — 4
  - Security Assessment and Monitoring — 5
  - System and Communications Protection — 16
  - System and Information Integrity — 8
  - Planning — 3
  - System and Services Acquisition — 3
  - Supply Chain Risk Management — 3
- **Control identifiers:** every control is identified by its native
  source ID with a document prefix, e.g. `nist-sp-800-171-r3-03-01-01`
  for requirement 03.01.01 (Account Management). IDs use hyphens
  rather than dots because OSCAL NCName rules do not permit dot-form
  identifiers as top-level catalog IDs.
- **Prose length:** control statements range from 20 characters (the
  briefest Withdrawn placeholders, e.g. "Incorporated into 03.14.02.")
  through a median of ~1080 characters up to ~3600 characters for the
  longest multi-part requirements. Each statement includes the
  requirement body, the source-document DISCUSSION prose, and the
  REFERENCES section verbatim.
- **Extraction technique:** used `pdfplumber` to pull text page-by-page
  from the text-native PDF, skipped the front matter (cover, abstract,
  table of contents, Sections 1–2 background narrative) and the back
  matter (References, Appendices A–F on acronyms, glossary, tailoring
  criteria, ODPs, mappings and control summaries), and joined the
  remaining pages (pp. 16–84 of the source) into a single text stream
  before parsing family and control headings by regular expression.

## Validation approach

The catalog passed 16 built-in structural and content checks plus the
OSCAL trestle validator. In plain terms, that safety net covered:

- **Identifier hygiene** — no duplicate control or group IDs; every
  identifier is a valid OSCAL NCName; no table-of-contents entries
  leaked into the control set.
- **Structural integrity** — controls are numerically sequential
  within each family with no gaps (03.01.01 through 03.01.22,
  03.02.01 through 03.02.03, and so on), no empty groups exist, and
  the catalog is a well-formed two-level tree of families → controls.
- **Content completeness** — every family header found in the
  extracted text produced a group in the catalog, and every control
  has a non-empty title and statement.
- **Schema compliance** — the file passes the `trestle validate` OSCAL
  schema check as an out-of-process gate.

No built-in rules were intentionally skipped for this document; the
full rule set was enforced.

Two extractor behaviours worth stating explicitly, both by design:

- Words that the PDF hyphenated across page breaks (`per-\nsonal
  data`) are re-joined into single tokens in the output.
- The 33 controls the source marks "Withdrawn" (e.g. 03.01.13, 03.14.04)
  are kept in the catalog with their one-line pointer to the
  requirement that superseded them. They are numbered slots in the
  source document, and removing them would produce numbering gaps
  that would misrepresent the requirement set as it was published.

## Points for human review

- **Group labels use a synthetic "family" token.** The source
  document numbers its 17 top-level requirement families as
  `3.1. Access Control`, `3.2. Awareness and Training`, and so on —
  there is no explicit "Family" or "Chapter" keyword in the PDF. The
  catalog names them `nist-sp-800-171-r3-family-1` through
  `nist-sp-800-171-r3-family-17`, with group titles rendered as
  "family N &lt;family name&gt;". If a downstream consumer expects a
  different casing (`Family` vs. `family`) or a different noun
  altogether, that convention is worth confirming before the catalog
  is committed.
- **Control ID form is hyphen-dotted, not dot-dotted.** The source
  ID `03.14.06` appears in the catalog as `nist-sp-800-171-r3-03-14-06`.
  Downstream tooling that keys off `03.14.06` verbatim (rather than
  the OSCAL control ID) will need a mapping step. The `label` field
  on each control preserves the original dotted form
  (e.g. `"label": "03.14.06"`).
- **Withdrawn controls are retained.** The 33 items the source marks
  "Withdrawn" are present in the catalog with their pointer prose. If
  the downstream use of this catalog is authoring or assessment
  (i.e. only enforceable requirements matter), the reviewer may want
  to decide whether to filter them out at that later step. The
  extractor deliberately does not drop them so that the catalog
  matches the source document 1:1 by numbered slot.
- **DISCUSSION and REFERENCES prose is embedded in the control
  statement.** Each control's statement includes both the normative
  requirement text AND the non-normative DISCUSSION and REFERENCES
  blocks that follow it in the source. If downstream consumers want
  those in separate OSCAL parts (`part.name = "guidance"` for
  DISCUSSION, a link collection for REFERENCES), that split would need
  a follow-up pass — the current catalog keeps them inline as the
  simplest faithful representation of what the PDF prints.

## Known limitations

- Only the normative body (Section 3, "The Security Requirements",
  pp. 16–84 of the source) was extracted. The Introduction, "The
  Fundamentals" narrative, References, and Appendices A–F (Acronyms,
  Glossary, Tailoring Criteria, Organization-Defined Parameters,
  SP 800-53 Mapping, Control Summaries) were skipped by design —
  they are supporting material, not requirements to be authored
  against.
- Figures and tables inside the body (e.g. Table 1 "Security
  Requirement Families") were not extracted as structured data. Their
  text content is present in the surrounding prose where the PDF
  places them.
- Organization-defined parameter (ODP) markers appear inline in the
  control text as `[Assignment: organization-defined ...]` and
  `[Selection: ...]`, exactly as printed in the source. The catalog
  does not currently promote them to OSCAL `param` elements; that
  would require a separate cross-reference pass against Appendix D of
  the source document.
