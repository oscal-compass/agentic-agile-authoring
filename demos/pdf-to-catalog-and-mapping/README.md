---
name: pdf-to-catalog-and-mapping
skills: [compliance-catalog, compliance-mapping]
---

# Demo: PDF → OSCAL Catalog → Mapping Collection

Framework onboarding end-to-end: convert a compliance PDF into a validated OSCAL
Catalog, then map it against an existing framework catalog — driven by two installed
skills, no orchestrator persona.

Two scenarios, each a single prompt:

- **[Scenario 1 — PDF → OSCAL Catalog](#scenario-1--pdf--oscal-catalog)**: convert
  NIST SP 800-171 Rev 3 into a validated `catalog.json` (`compliance-catalog`).
- **[Scenario 2 — Catalog × Catalog → Mapping Collection](#scenario-2--catalog--catalog--mapping-collection)**:
  map the SP 800-171 catalog against NIST SP 800-53 Rev 5 High baseline and produce
  `mapping_collection.json` + a browsable `report.html` (`compliance-mapping`).

Resources shipped with this demo (US government works, public domain):

| File | Description |
|------|-------------|
| [`../resources/pdfs/NIST.SP.800-171r3.pdf`](../resources/pdfs/NIST.SP.800-171r3.pdf) | NIST SP 800-171 Rev 3 — Protecting CUI (May 2024) |
| [`../resources/oscal/NIST_SP-800-53_rev5_HIGH-baseline-resolved-profile_catalog.json`](../resources/oscal/NIST_SP-800-53_rev5_HIGH-baseline-resolved-profile_catalog.json) | NIST SP 800-53 Rev 5.1.1 High baseline — 188 controls (from [usnistgov/oscal-content](https://github.com/usnistgov/oscal-content)) |

## Install

Prerequisite: **[`uv`](https://docs.astral.sh/uv/)** (provides `uvx`). No Node required.

```bash
# into Claude Code:
uvx \
  --from "git+https://github.com/oscal-compass/agentic-agile-authoring.git@main#subdirectory=tools" \
  compliance-authoring-skills install --demo pdf-to-catalog-and-mapping --target claude

# …or into OpenCode:
uvx \
  --from "git+https://github.com/oscal-compass/agentic-agile-authoring.git@main#subdirectory=tools" \
  compliance-authoring-skills install --demo pdf-to-catalog-and-mapping --target opencode

# …or into IBM Bob:
uvx \
  --from "git+https://github.com/oscal-compass/agentic-agile-authoring.git@main#subdirectory=tools" \
  compliance-authoring-skills install --demo pdf-to-catalog-and-mapping --target bob
```

This copies `compliance-catalog` and `compliance-mapping` into the harness's native
skill dir. Neither skill requires an MCP server — all pipeline stages run as Python
subprocesses or locally-embedded sentence-transformers inference inside the harness session.

---

## Scenario 1 — PDF → OSCAL Catalog

Convert the NIST SP 800-171 Rev 3 PDF into a validated OSCAL Catalog JSON.

### Step 1 — Generate the catalog

> Follow `compliance-catalog` skill to convert
> `demos/resources/pdfs/NIST.SP.800-171r3.pdf` into an OSCAL Catalog.
> Write the output to `output/800-171-catalog/`.

The agent runs the deterministic extraction pipeline (PDF → text → structure parse →
OSCAL emit → iterative fix loop until `validate.py` exits 0). It produces:

- `output/800-171-catalog/catalog.json` — validated OSCAL Catalog
- `output/800-171-catalog/report.md` — extraction summary

Reference output from a real run:
[`expected-output/800-171-catalog/catalog.json`](expected-output/800-171-catalog/catalog.json)

Wall clock: ~10–20 minutes.

### Expected result (validation) — check these invariants, not exact strings

- `catalog.json` validates **VALID** (`trestle partial-object-validate -e catalog`, or the
  skill's own `validate.py`)
- SP 800-171r3 has **17 control families** and **110 base security requirements** (§3.1–§3.17)
  — expect roughly **110+ controls** across 17 groups
- Control IDs follow the document's own numbering (e.g. `3.1.1`, `3.1.2`, …)
- `report.md` is written alongside `catalog.json`
- *Varies:* exact control count depends on whether discussion/supplemental sections are
  extracted as controls; the invariants above are the stable anchors.

---

## Scenario 2 — Catalog × Catalog → Mapping Collection

Map the SP 800-171 catalog (source — the framework to show coverage for) against the NIST
SP 800-53 Rev 5 High baseline (target — the reference framework), and produce a validated
OSCAL Mapping Collection and a browsable HTML report.

> SP 800-171 was derived from SP 800-53, so the overlap is substantial and the agent
> will find rich, specific mapping links.

### Step 1 — Map 800-171 → 800-53

> Follow `compliance-mapping` skill to map two OSCAL Catalogs.
> - source_catalog: `output/800-171-catalog/catalog.json`
> - target_catalog: `demos/resources/oscal/NIST_SP-800-53_rev5_HIGH-baseline-resolved-profile_catalog.json`
> - output_dir: `output/800-171-to-800-53/`

The agent runs the full pipeline: embed both catalogs → blocking (top-K candidates per
control) → parallel judge subagents (one per chunk) → score → aggregate → emit OSCAL →
validate → generate HTML report.

Reference output from a real run:
[`expected-output/800-171-to-800-53/mapping_collection.json`](expected-output/800-171-to-800-53/mapping_collection.json)

Wall clock: ~5–15 minutes depending on catalog size and concurrent subagent throughput.

### Expected result (validation) — check these invariants, not exact strings

- `output/800-171-to-800-53/mapping_collection.json` exists and validates **VALID**
  (`trestle partial-object-validate -e mapping-collection`)
- `output/800-171-to-800-53/report.html` exists and is non-empty (open in a browser)
- Non-zero mapping links found — SP 800-171 and SP 800-53 share a common lineage so the
  majority of 800-171 controls map to one or more 800-53 controls
- `mapping_collection.metadata.title` is auto-derived from the two catalogs' own titles
- *Varies:* exact link count, confidence scores, and rationale text vary run-to-run;
  the HTML report's filter panel lets you explore by confidence and relationship type.

---

## Running both scenarios with `make`

A [`Makefile`](Makefile) is provided that drives each scenario via a single agent prompt.

```bash
# Scenario 1 — generate the catalog from the PDF:
make catalog

# Scenario 2 — map 800-171 against 800-53 (requires catalog output from Scenario 1):
make mapping

# Both in sequence:
make all

# Remove generated output (catalog + mapping):
make clean
```

See the [`Makefile`](Makefile) for the exact prompts and harness configuration.

<details>
<summary>Example run — <code>make all</code> (IBM Bob, ~33 min, ~$32.68)</summary>

```console
$ make all

Select harness:
  1) bob      (IBM Bob Shell)
  2) claude   (Claude Code)
  3) opencode (OpenCode)
Choice [1]: 1

Enter BOB_API_KEY:

=== Scenario 1: Building OSCAL Catalog from PDF ===
  task    : Convert NIST SP 800-171r3 PDF → validated OSCAL catalog.json
  skill   : compliance-catalog  (skills/compliance-catalog/SKILL.md)
  harness : bob
  input   : ../../demos/resources/pdfs/NIST.SP.800-171r3.pdf
  output  : ../../demos/pdf-to-catalog-and-mapping/output/800-171-catalog/

  command : bob run --trust --accept-license --format stream-json \
              "Follow `skills/compliance-catalog/SKILL.md` to build an OSCAL Catalog from a PDF. - input_pdf: ../../demos/resources/pdfs/NIST.SP.800-171r3.pdf - output_dir: ../../demos/pdf-to-catalog-and-mapping/output/800-171-catalog"

  started : 16:09:16
  log     : ../../demos/pdf-to-catalog-and-mapping/output/800-171-catalog/agent.jsonl
  timeout : 45 min  (deadline 16:54:16)

  [catalog] 1m00s  | 44 min left | Now proceeding to Phase 2.
  [catalog] 2m00s  | 43 min left | Now proceeding to Phase 2.
  [catalog] 3m00s  | 42 min left | Now proceeding to Phase 2.
  [catalog] 4m00s  | 41 min left | Now proceeding to Phase 3.
  [catalog] 5m00s  | 40 min left | Empty control titles in groups 4 and 17
  [catalog] 6m00s  | 39 min left | Empty control titles in groups 4 and 17
  [catalog] 7m00s  | 38 min left | Empty control titles in groups 4 and 17
  [catalog] 8m00s  | 37 min left | Building fix prompt 2.
  [catalog] 9m00s  | 36 min left | Building fix prompt 2.
  [catalog] 10m00s | 35 min left | Retry iteration 2 with a fresh subagent.
  [catalog] 11m00s | 34 min left | Retry iteration 2 with a fresh subagent.
  [catalog] 12m00s | 33 min left | Retry iteration 2 with a fresh subagent.
  [catalog] 13m00s | 32 min left | Let me check what the validate_config.py says:
  [catalog] 14m00s | 31 min left | Now proceeding to Phase 5 — spot-check.

  [catalog] finished in 15m0s
  [catalog] cost: $14.0791  (bob session_costs; 14m37s)

  OK: ../../demos/pdf-to-catalog-and-mapping/output/800-171-catalog/catalog.json written.

=== Scenario 2: Mapping NIST SP 800-171 → NIST SP 800-53 ===
  task    : Map 800-171 controls against 800-53 High baseline → mapping_collection.json + report.html
  skill   : compliance-mapping  (skills/compliance-mapping/SKILL.md)
  harness : bob
  source  : ../../demos/pdf-to-catalog-and-mapping/output/800-171-catalog/catalog.json
  target  : ../../demos/resources/oscal/NIST_SP-800-53_rev5_HIGH-baseline-resolved-profile_catalog.json
  output  : ../../demos/pdf-to-catalog-and-mapping/output/800-171-to-800-53/

  command : bob run --trust --accept-license --format stream-json \
              "Follow `skills/compliance-mapping/SKILL.md` to map two OSCAL Catalogs. - source_catalog: ../../demos/pdf-to-catalog-and-mapping/output/800-171-catalog/catalog.json - target_catalog: ../../demos/resources/oscal/NIST_SP-800-53_rev5_HIGH-baseline-resolved-profile_catalog.json - output_dir: ../../demos/pdf-to-catalog-and-mapping/output/800-171-to-800-53"

  started : 16:24:16
  log     : ../../demos/pdf-to-catalog-and-mapping/output/800-171-to-800-53/agent.jsonl
  timeout : 30 min  (deadline 16:54:16)

  [mapping] 1m00s  | 29 min left | Now Stage 3 — blocking:
  [mapping] 2m00s  | 28 min left | Starting batch 1 — chunks 0–19 in parallel:
  [mapping] 3m00s  | 27 min left | Starting batch 1 — chunks 0–19 in parallel:
  [mapping] 4m00s  | 26 min left | Starting batch 1 — chunks 0–19 in parallel:
  [mapping] 5m00s  | 25 min left | Starting batch 1 — chunks 0–19 in parallel:
  [mapping] 6m00s  | 24 min left | Now batch 2 — chunks 20–39:
  [mapping] 7m00s  | 23 min left | Now batch 2 — chunks 20–39:
  [mapping] 8m00s  | 22 min left | Now batch 2 — chunks 20–39:
  [mapping] 9m00s  | 21 min left | Let me verify and re-spawn it, then continue with batch 3 (chunks 40–59):
  [mapping] 10m00s | 20 min left | Let me verify and re-spawn it, then continue with batch 3 (chunks 40–59): Chunk 29 is missing — re-sp
  [mapping] 11m00s | 19 min left | Let me verify and re-spawn it, then continue with batch 3 (chunks 40–59): Chunk 29 is missing — re-sp
  [mapping] 12m00s | 18 min left | Let me verify and re-spawn it, then continue with batch 3 (chunks 40–59): Chunk 29 is missing — re-sp
  [mapping] 13m00s | 17 min left | Let me verify and re-spawn it, then continue with batch 3 (chunks 40–59): Chunk 29 is missing — re-sp
  [mapping] 14m01s | 15 min left | Now batch 4 (chunks 60–73) plus retry of chunk 40:
  [mapping] 15m01s | 14 min left | Now batch 4 (chunks 60–73) plus retry of chunk 40:
  [mapping] 16m01s | 13 min left | Now batch 4 (chunks 60–73) plus retry of chunk 40:
  [mapping] 17m01s | 12 min left | Now batch 4 (chunks 60–73) plus retry of chunk 40:

  [mapping] finished in 18m1s
  [mapping] cost: $18.5980  (bob session_costs; 17m32s)

  OK: mapping_collection.json and report.html written.
  Open: ../../demos/pdf-to-catalog-and-mapping/output/800-171-to-800-53/report.html
```

</details>

---

## Uninstall

Non-destructive — user-authored skills and user-defined MCP servers are never touched.

```bash
# from Claude Code:
uvx \
  --from "git+https://github.com/oscal-compass/agentic-agile-authoring.git@main#subdirectory=tools" \
  compliance-authoring-skills uninstall --skill compliance-catalog,compliance-mapping --target claude

# …or from OpenCode:
uvx \
  --from "git+https://github.com/oscal-compass/agentic-agile-authoring.git@main#subdirectory=tools" \
  compliance-authoring-skills uninstall --skill compliance-catalog,compliance-mapping --target opencode

# …or from IBM Bob:
uvx \
  --from "git+https://github.com/oscal-compass/agentic-agile-authoring.git@main#subdirectory=tools" \
  compliance-authoring-skills uninstall --skill compliance-catalog,compliance-mapping --target bob
```
