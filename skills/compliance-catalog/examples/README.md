# compliance-catalog · examples

Public-domain / openly-licensed compliance documents you can point this
skill at without any procurement steps. Use them to demo the skill, run
the end-to-end pipeline against a real regulation, or exercise the
Update flow (v1 → v2 of the same document).

## Contents

| File                              | Source / license                                                                                                                              | Suggested use                                                                                          |
| :-------------------------------- | :-------------------------------------------------------------------------------------------------------------------------------------------- | :----------------------------------------------------------------------------------------------------- |
| `EU-GDPR.pdf`                     | EU Regulation 2016/679 (General Data Protection Regulation). EU public law; unrestricted redistribution.                                       | Baseline catalog generation demo — a well-known legal framework, ~90 controls, ~90 pages.              |
| `NSA-K8s-Hardening-v1.0.pdf`      | NSA / CISA *Kubernetes Hardening Guidance* v1.0. U.S. Federal Government work; public domain (17 USC §105).                                    | Second-domain example — a technical hardening guide rather than a legal regulation.                    |
| `NIST_SP-800-171_rev2.pdf`        | NIST Special Publication 800-171 Revision 2 — *Protecting Controlled Unclassified Information in Nonfederal Systems and Organizations*. U.S. Federal Government work; public domain (17 USC §105). | Baseline for the Update-flow demo: the older-version catalog you generate first. ~80 pages, 110 controls. |
| `NIST_SP-800-171_rev3.pdf`        | NIST Special Publication 800-171 Revision 3 (finalized May 2024). Same U.S. public-domain provenance.                                          | **Update-flow** demo — pair with the Rev 2 output as the previous run. ~100 pages; controls restructured into 17 families with parameters. |

## Use with the skill

Point `input_pdf` at any of the files above; pick any writable output dir.
The skill's Phase 0-pre stage auto-starts a live viewer at
`http://127.0.0.1:8850/` so the operator can watch the pipeline progress
in the browser.

### Baseline generation

Give the skill a PDF and a fresh output directory:

```text
Convert skills/compliance-catalog/examples/NIST_SP-800-171_rev2.pdf
into an OSCAL Catalog under /tmp/nist-800-171-r2.
```

The pipeline runs Phases 1-6 top-to-bottom: analyse the PDF, author
`generate.py`, extract, author `validate.py`, iterate the fix loop,
verify, write `report.md`.

### Update flow (v1 → v2)

After a baseline run has completed successfully in some output dir, run
the skill again against the same output dir with the newer PDF. The
skill's Phase 0 will detect the existing `generate.py` / `validate.py`
/ `catalog.json` and enter *re-run mode*: Phases 1-3 are skipped, and
only Phase 4 (validate/fix loop) is re-executed against the new PDF.
Because the extractor script is reused, control IDs stay stable across
versions — a Rev 2 control that also appears in Rev 3 keeps the same
`ac-1`, `au-2`, `sc-7`, etc. ID.

```text
Update the OSCAL Catalog for a revised version of the source document.

Existing output dir: /tmp/nist-800-171-r2
New input PDF:       skills/compliance-catalog/examples/NIST_SP-800-171_rev3.pdf
```

If you want to `diff` the before/after later, snapshot the Rev 2 catalog
first: `cp /tmp/nist-800-171-r2/catalog.json /tmp/nist-800-171-r2/catalog.v1.json`.

## Provenance notes

- The GDPR PDF is an unmodified rendering of the consolidated public
  text as published on eur-lex.europa.eu. No IBM-internal content.
- Both NIST SP 800-171 PDFs are unmodified from the NIST CSRC release
  pages under `nvlpubs.nist.gov/nistpubs/SpecialPublications/`. They
  are U.S. Federal Government work, which under 17 USC §105 is not
  subject to copyright inside the United States.
- The NSA Kubernetes Hardening Guidance PDF is unmodified from its
  original NSA release. Same U.S. public-domain provenance.
- Nothing under this directory is derived from IBM-internal frameworks
  (e.g. ITSS). Do not add such files here.
