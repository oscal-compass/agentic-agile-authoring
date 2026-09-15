# Comparison: generated NIST 800-53 → 800-171 mapping vs. authoritative NIST CUI Overlay

This folder scores the mapping-collection the `compliance-mapping` skill
generated (mapping every NIST 800-53 rev5 MODERATE control onto the NIST
800-171 rev3 catalog produced by the [`pdf-to-catalog`](../../pdf-to-catalog/)
demo) against NIST's own authoritative mapping — the **NIST CUI Overlay** for
SP 800-171 Rev. 3. The Overlay is a per-requirement declaration of which 800-53
controls each 800-171 requirement is tailored from; treating it as ground truth
lets us compute precision, recall, and F1 on this pair-recovery task.

## Files

| File | What it is |
|---|---|
| `reference/mapping_collection.json` | **Reference (ground truth)** — OSCAL mapping-collection derived from NIST's `sp800-171r3-cui-overlay.xlsx`. 156 pairs across 97 requirements, all labelled `subset-of` (the Overlay convention: 800-171 is a tailored subset of 800-53). |
| `compare.py` | Loads reference + generated, normalizes IDs (`nist-sp-800-171-r3-03-01-01` → `03.01.01`), computes precision/recall/F1 at the (source, target) pair level, writes `comparison.json`, `report.md`, and 3 CSVs. |
| `comparison.json` | Full comparison result as JSON — overall metrics, per-family counts, relationship-label breakdown, top missed / top extra requirements. |
| `report.md` | Human-readable rendering of `comparison.json`. |
| `shared-pairs.csv` | Pairs both sides agree on (144 rows), with each side's relationship label so disagreements are visible. |
| `generated-only-pairs.csv` | Pairs the generator produced that the reference did not (141 rows) — review candidates, not evidence of NIST omission. |
| `reference-only-pairs.csv` | Pairs the reference asserts that the generator missed (12 rows) — false negatives against the baseline. |
| `serve.py` | Optional local HTTP server for browsing the report. |

## Reference provenance and license

**Source of the reference file (`reference/mapping_collection.json`):**

- Originating NIST publication:
  [`sp800-171r3-cui-overlay.xlsx`](https://csrc.nist.gov/pubs/sp/800/171/r3/final)
  — NIST's *SP 800-171 Rev. 3 CUI Overlay*, published alongside the final Rev. 3
  release (May 14, 2024). The overlay declares, per requirement, which 800-53
  controls it tailors from, plus the tailoring decision (`CUI only`, `NCO`,
  etc.).
- Publisher: **National Institute of Standards and Technology (NIST)**,
  U.S. Department of Commerce.
- License: **Public domain** — as a work of the U.S. Federal Government it is
  not subject to copyright protection in the United States
  ([17 USC §105](https://www.law.cornell.edu/uscode/text/17/105)).

**Conversion (xlsx → OSCAL mapping-collection):** The `mapping_collection.json`
form used here was produced by an offline pass that (a) filtered the Overlay to
the `CUI only` tailoring decision (97 requirement-level entries), and
(b) rewrote each `(800-53 control, 800-171 requirement)` pair as an OSCAL
mapping with `relationship = subset-of` (the Overlay convention). The
conversion is mechanical — no relationships were re-labelled — so the file
retains the Overlay's authority as ground truth.

## How the score is computed

`compare.py` normalizes both sides to a set of `(source_control_id,
target_requirement_id)` pairs, then computes:

- **Exact agreement** — pairs present on both sides.
- **Reference-only** — pairs present in the Overlay but not in the generated
  mapping (false negatives against the baseline).
- **Generated-only** — pairs present in the generated mapping but not in the
  Overlay (review candidates).
- **Precision** = `|exact| / (|exact| + |generated-only|)`.
- **Recall** = `|exact| / (|exact| + |reference-only|)`.
- **F1** = harmonic mean.
- **Relationship disagreements** — on shared pairs where the two sides carry
  a different relationship label. Since the reference labels every pair
  `subset-of`, any disagreement is on the generator's side; a generator label
  of `equivalent-to` is a *stronger* claim than the Overlay makes, while
  `intersects-with` is weaker.

Per-family recall, top-missed and top-extra requirements, and a
relationship-distribution breakdown are all in `report.md`.
