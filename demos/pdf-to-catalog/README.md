---
name: pdf-to-catalog
skills: [compliance-catalog]
---

# Demo: PDF → OSCAL Catalog (with live progress UI)

Convert a real-world compliance PDF into a validated OSCAL Catalog in natural
language, watching the pipeline build itself in the browser — one installed
skill, no orchestrator persona.

The `compliance-catalog` skill spins up a small **live progress viewer**
(FastAPI + a self-contained SPA at `http://127.0.0.1:8850/`) as its very first
phase, so the operator can watch each phase (`ingest → author → validate →
report`) turn from *running* to *done*, see the control/group counts land in
`catalog.json` as they're written, follow the validate-error series across
`_validate_*.txt` iterations, and read `report.md` when it's emitted — all
without tailing a jsonl.

## Movie

▶ [**Watch the walkthrough (mp4, ~75 MB)**](assets/pdf-to-catalog.mp4) — a
full run: `install → generate → live viewer → compare against the official
NIST OSCAL edition`.

## Install

Prerequisite: **[`uv`](https://docs.astral.sh/uv/)** (provides `uvx`; no Node
required). The live viewer needs `fastapi` and `uvicorn` — they're listed in
`skills/compliance-catalog/scripts/requirements.txt`; install them into the
Python your harness will use:

```bash
pip install -r skills/compliance-catalog/scripts/requirements.txt
```

Then install the skill:

```bash
# into OpenCode:
uvx compliance-authoring-skills install --skill compliance-catalog --target opencode
# …or into Claude Code:
uvx compliance-authoring-skills install --skill compliance-catalog --target claude
```

This copies `compliance-catalog` into the harness's native skill dir. Open the
target project in the harness so it picks the skill up.

> If `fastapi`/`uvicorn` aren't installed, the launcher exits immediately and
> the pipeline continues without the viewer — the run still succeeds, you just
> don't get the browser view.

## Walkthrough

Copy [`inputs/NIST_SP-800-171_rev3.pdf`](inputs/NIST_SP-800-171_rev3.pdf) into
an empty working directory and give the agent this prompt:

> Convert `NIST_SP-800-171_rev3.pdf` into an OSCAL Catalog under
> `./out/nist-800-171-r3`.

The skill runs **Phase 0-pre** first: it starts the live viewer in the
background and prints the URL to `out/nist-800-171-r3/.live_server.log`. Your
browser opens automatically at `http://127.0.0.1:8850/`, and from there you
watch:

- Phase 1 → 6 progress with **running / done / error** icons
- `catalog.json` control + group counts as soon as Phase 5 emits them
- the validate-error count across each `_validate_*.txt` iteration
- tail of the agent log
- `report.md` once written
- an **Approve / Reject** verdict recorded to `.reviewed.json`

The full expected output — the same files the agent produced in the movie — is
under [`expected-output/`](expected-output/). Highlights:

- [`expected-output/catalog.json`](expected-output/catalog.json) — the OSCAL
  Catalog (130 controls in 17 families, valid OSCAL)
- [`expected-output/report.md`](expected-output/report.md) — the agent's own
  summary of what it did and any exclusions
- [`expected-output/generate.py`](expected-output/generate.py),
  [`expected-output/validate.py`](expected-output/validate.py),
  [`expected-output/validate_config.py`](expected-output/validate_config.py) —
  the deterministic Python the agent authored for extraction and validation
  (the skill's template-first design: LLM writes code, the code produces the
  catalog)
- [`expected-output/excluded_units.json`](expected-output/excluded_units.json)
  — units the agent deliberately excluded (with reasons)

## Compare against the official NIST OSCAL edition

The [`comparison/`](comparison/) folder pits the generated catalog against
NIST's own OSCAL edition of SP 800-171 Rev. 3 — that same file is included in
this repo at
[`comparison/nist-sp-800-171-rev3-catalog-official.json`](comparison/nist-sp-800-171-rev3-catalog-official.json)
(see [`comparison/README.md`](comparison/README.md) for provenance and license).

```bash
cd comparison
python3 postprocess.py       # strip PDF-extraction artifacts → catalog.cleaned.json
python3 compare_catalogs.py --markdown   # regenerates README_COMPARE_REPORT.md + SVG chart
python3 serve.py             # optional: browse the report locally
```

The full pre-generated report is at
[`comparison/README_COMPARE_REPORT.md`](comparison/README_COMPARE_REPORT.md).
Headline result:

| Baseline | Generated | Official | Delta | Missing | Extra | Title Δ | Avg prose sim | Dissimilar |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| sp-800-171-rev3 | 130 | 130 | +0 | 0 | 0 | 0 | **95%** | 24 |

130/130 controls reproduced, 0 missing, 0 extra, 95% average word-level Jaccard
similarity on control prose. The 24 dissimilar controls (worst 25%) are enumerated
in the report so you can eyeball where the generator diverged — nearly all cases
are the generator inlining the resolved parameter value where NIST OSCAL keeps a
`{{ insert: param, … }}` placeholder.

## Uninstall

Non-destructive — user-authored skills are never touched.

```bash
uvx compliance-authoring-skills uninstall --skill compliance-catalog --target opencode
```
