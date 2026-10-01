# Comparison: generated NIST 800-171 Rev. 3 catalog vs. official NIST OSCAL

This folder scores the OSCAL Catalog the `compliance-catalog` skill generated
from `../inputs/NIST_SP-800-171_rev3.pdf` against NIST's own official OSCAL
edition of SP 800-171 Rev. 3 — as a **ground truth**, not a target-to-match.
The skill's job is to distill the PDF into valid, faithful OSCAL; NIST's
edition is the closest thing there is to a canonical answer, so a
head-to-head is the sharpest way to see where the generator succeeds and
where it drifts.

## Files

| File | What it is |
|---|---|
| `nist-sp-800-171-rev3-catalog-official.json` | **Reference (ground truth)** — NIST's official OSCAL edition of SP 800-171 Rev. 3. |
| `postprocess.py` | Strips two well-known PDF-extraction artifacts from the generated catalog (trailing `REFERENCES` blocks, soft-hyphen line breaks) → `catalog.cleaned.json`. |
| `catalog.cleaned.json` | Output of `postprocess.py`; the input to `compare_catalogs.py`. |
| `compare_catalogs.py` | Compares the cleaned generated catalog against the official OSCAL edition; prints a summary and, with `--markdown`, regenerates `README_COMPARE_REPORT.md` + `images/compare_chart.svg`. |
| `README_COMPARE_REPORT.md` | The full pre-generated report (per-baseline summary, per-family recall, the 24 worst-similarity controls with side-by-side prose diffs). |
| `images/compare_chart.svg` | Prose-similarity bar chart, one bar per control. |
| `serve.py` | Optional local HTTP server for browsing the report. |

## Reference provenance and license

**Source of the reference file (`nist-sp-800-171-rev3-catalog-official.json`):**

- Repository: [`usnistgov/oscal-content`](https://github.com/usnistgov/oscal-content)
- File path in that repo:
  `nist.gov/SP800-171/rev3/json/NIST_SP-800-171-r3_catalog.json`
- Publisher: **National Institute of Standards and Technology (NIST)**,
  U.S. Department of Commerce.
- License: **Public domain** — as a work of the U.S. Federal Government it is
  not subject to copyright protection in the United States
  ([17 USC §105](https://www.law.cornell.edu/uscode/text/17/105)). See the
  `oscal-content` repo's `LICENSE.md` for NIST's own statement.

Redistributed here unchanged (renamed for clarity from
`NIST_SP-800-171-r3_catalog.json` to `nist-sp-800-171-rev3-catalog-official.json`
so its role in this demo — the *official* baseline against the *generated* one
— is unambiguous).

## How the score is computed

`compare_catalogs.py` flattens both catalogs into `{control_id → control}` maps
(normalizing IDs like `nist-sp-800-171-r3-03-01-01` and `SP_800_171_03.01.01`
to the canonical `03.01.01`) and, for every control present in **both**:

- Counts control-level presence (matched / missing / extra).
- Compares control titles (title Δ).
- Scores prose similarity with word-level Jaccard overlap on normalized
  tokens after stripping OSCAL parameter references (`{{ insert: param, … }}`),
  PDF assignment placeholders (`[Assignment: …]`), and `Related Control(s): …`
  lines (PDF artifact). Score is `|A ∩ B| / |A ∪ B|`; a length-ratio outside
  `[0.4, 2.5]` caps the score at 0.5 to defang noise; one-side-blank pairs
  score 0.
