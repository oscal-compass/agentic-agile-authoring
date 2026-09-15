---
name: catalogs-to-mapping
skills: [compliance-mapping]
---

# Demo: Catalog → Catalog Mapping (with live progress UI)

Map every control in one OSCAL Catalog to related controls in another — driven
in natural language by the `compliance-mapping` skill, with the multi-stage
judge pipeline visualised in the browser as it runs. One installed skill, no
orchestrator persona.

The skill spins up a small **live progress viewer** (FastAPI + a self-contained
SPA at `http://127.0.0.1:8850/`) as its Stage 0, so the operator can watch each
of Stage 1 → 8 turn from *running* to *done*, see the source/target control
counts land as Stage 1 finishes, follow the **judge-chunk fan-out** (chunks
done / total) live as Stage 4d spawns its subagents 5 at a time, and inspect
`report.html` when it's emitted — all without tailing a jsonl.

## Movie

▶ [**Watch the walkthrough (mp4, ~25 MB)**](assets/catalogs-to-mapping.mp4) —
a full run: `install → generate mapping → live viewer with judge fan-out →
compare against the authoritative NIST CUI Overlay`.

## Install

Prerequisite: **[`uv`](https://docs.astral.sh/uv/)** (provides `uvx`; no Node
required). The live viewer needs `fastapi` and `uvicorn` — they're listed in
`skills/compliance-mapping/scripts/requirements.txt`; install them into the
Python your harness will use:

```bash
pip install -r skills/compliance-mapping/scripts/requirements.txt
```

Then install the skill:

```bash
# into OpenCode:
uvx compliance-authoring-skills install --skill compliance-mapping --target opencode
# …or into Claude Code:
uvx compliance-authoring-skills install --skill compliance-mapping --target claude
```

> If `fastapi`/`uvicorn` aren't installed, the launcher exits immediately and
> the pipeline continues without the viewer — the run still succeeds, you just
> don't get the browser view.

## Walkthrough

Copy the two catalogs from [`inputs/`](inputs/) into an empty working directory:

- [`inputs/NIST_SP-800-53_rev5_MODERATE-baseline-resolved-profile_catalog.json`](inputs/NIST_SP-800-53_rev5_MODERATE-baseline-resolved-profile_catalog.json)
  — the **source** catalog (177 controls, NIST 800-53 rev5 MODERATE baseline,
  resolved-profile form; NIST's own public OSCAL edition).
- [`inputs/NIST_SP-800-171_rev3_generated_catalog.json`](inputs/NIST_SP-800-171_rev3_generated_catalog.json)
  — the **target** catalog (97 requirements + 33 withdrawn = 130 controls).
  This is the catalog produced by the [`pdf-to-catalog`](../pdf-to-catalog/)
  demo; in this repo it's a symlink to that demo's `expected-output/catalog.json`
  so you can see the two skills compose end-to-end.

Then give the agent this prompt:

> Map `NIST_SP-800-53_rev5_MODERATE-baseline-resolved-profile_catalog.json`
> onto `NIST_SP-800-171_rev3_generated_catalog.json`. Write the result under
> `./out/nist-53-to-171`.

The skill runs **Stage 0** first: it starts the live viewer in the background
and prints the URL to `out/nist-53-to-171/.live_server.log`. Your browser
opens automatically at `http://127.0.0.1:8850/`, and from there you watch:

- Stage 1 → 8 progress with **running / done / error** icons
- source / target control counts once Stage 1 lands them
- **judge-chunk fan-out** (Stage 4d): chunks done / total, updating live as
  each 5-subagent batch returns its `agent_verdicts_<N>.jsonl`
- link count and relationship mix (`equivalent-to` / `subset-of` /
  `intersects-with` / `superset-of`) once `mapping_collection.json` exists
- tail of the agent log
- `report.html` link once emitted
- an **Approve / Reject** verdict recorded to `.reviewed.json`

The full expected output — the same files the agent produced in the movie — is
under [`expected-output/`](expected-output/):

- [`expected-output/mapping_collection.json`](expected-output/mapping_collection.json)
  — the OSCAL mapping-collection (285 pairs across 97 requirements, valid
  OSCAL 1.2.1).
- [`expected-output/report.html`](expected-output/report.html) — a
  self-contained HTML report of every mapping decision, per-source and
  per-target, with the judge's rationale for each pair.
- [`expected-output/judge_pipeline.log`](expected-output/judge_pipeline.log)
  — the deterministic-stages log (Stages 1–3 and 5–8; Stage 4d is the
  subagent fan-out, whose per-chunk verdicts are the 88 `agent_verdicts_*.jsonl`
  the report is built from).

## Compare against the authoritative NIST CUI Overlay

The [`comparison/`](comparison/) folder pits this generated mapping against
NIST's own authoritative mapping — derived from the `sp800-171r3-cui-overlay.xlsx`
that NIST publishes alongside SP 800-171 Rev. 3 — bundled at
[`comparison/reference/mapping_collection.json`](comparison/reference/mapping_collection.json)
(see [`comparison/README.md`](comparison/README.md) for provenance and license).

```bash
cd comparison
python3 compare.py           # writes comparison.json, report.md, and 3 CSVs
python3 serve.py             # optional: browse the report locally
```

The full pre-generated report is at
[`comparison/report.md`](comparison/report.md). Headline result:

| metric | value |
|---|---|
| Exact agreement | 144 |
| Reference-only (missed by generator) | 12 |
| Generated-only (extra vs. reference) | 141 |
| Relationship disagreements on shared pairs | 123 |
| **Precision** | 0.505 |
| **Recall** | **0.923** |
| **F1** | 0.653 |

The generator captures **92.3% of the ground-truth pairs** (12 misses out of 156);
its lower precision is dominated by *extra* pairs — 141 links the NIST Overlay
did not assert — which are review candidates (some are legitimate related-control
links NIST tailored out for the CUI overlay, not evidence of NIST omission). The
per-family coverage table and full CSV breakdown live in the report.

## Uninstall

Non-destructive — user-authored skills are never touched.

```bash
uvx compliance-authoring-skills uninstall --skill compliance-mapping --target opencode
```
