---
name: compliance-mapping
description: Generate an OSCAL Mapping Collection between two compliance frameworks expressed as OSCAL Catalogs, and produce a browsable HTML report. Use when the user wants to map/compare controls across two frameworks, produce a mapping-collection artefact, or refresh an existing mapping after either catalog changes.
argument-hint: Path to the source OSCAL Catalog JSON, path to the target OSCAL Catalog JSON, and an output directory
license: Complete terms in LICENSE.txt
---

# Compliance Mapping

Map controls between two OSCAL Catalogs and emit an OSCAL Mapping Collection. The system separates **adaptive agent judgment** (threshold selection, parallelism decisions) from a **deterministic pipeline** (ingest, embedding-based candidate generation, scoring, aggregation, emission). All semantic judgment (relationship/confidence/coverage) is performed by subagents you spawn — no external LLM API is ever called. Embedding and nearest-neighbor search run locally via `sentence-transformers` and FAISS (no API key required).

```text
┌─ Mapping Agent (you: orchestration) ────────────────────────────────┐
│  ┌─ Deterministic Pipeline (scripts/) ────────────────────────────┐ │
│  │ Ingest → (Stage 2: reserved) → Blocking → Judge → Score        │ │
│  │       → Aggregate → Emit → Validate + Report                    │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

**Note on stage numbering.** Stages are numbered 1, 3, 4, 5, 6, 7, 8 (no Stage 2) so this file lines up with the 8-stage numbering used on the `downstream` branch, where Stage 2 (Granularity Align) is inserted between Ingest and Blocking. The OSS variant here does not run Stage 2 — controls are compared at their input granularity — so the number is simply skipped.

## Trigger

Use this skill when asked to map/compare controls between two compliance frameworks expressed as OSCAL Catalogs, or to produce/update an OSCAL Mapping Collection.

## Inputs

- `source_catalog` (required): Path to the source-side OSCAL Catalog JSON (the framework whose controls you are trying to show coverage for).
- `target_catalog` (required): Path to the target-side OSCAL Catalog JSON (the reference framework).
- `output_dir` (required): Directory to write all intermediate and final artifacts.
- `mapping_spec` (optional): Path to a JSON/YAML profile (see `scripts/mapping_spec.py`) overriding thresholds, relationship vocabulary, or blocking K. If omitted, built-in defaults are used (confidence≥0.75, coverage≥0.15, K=20).

Relationship direction follows the spec's `direction_semantics` (default: "source implements target"). Relationship types are: `intersects-with` (default, 95%+), `equivalent-to`, `superset-of`, `subset-of`, `no-relationship`.

## Setup

All scripts live in `scripts/` next to this file and are invoked with `python3 scripts/<name>.py ...` from wherever is convenient (they use relative imports of sibling modules, so run them with `scripts/` on `PYTHONPATH` or `cd` into `scripts/`).

Required Python packages: `sentence-transformers`, `numpy`, `compliance-trestle` (provides the `trestle` CLI used in Stage 8 to validate the emitted mapping). Optional but recommended: `faiss-cpu` (falls back automatically to a pure-numpy brute-force cosine search if not installed — functionally identical, just slower on large catalogs). Install once per environment:

```bash
pip install sentence-transformers faiss-cpu compliance-trestle
```

## How subagents are spawned

Stage 4 (Judge) is the only stage that needs LLM-driven work, and it is delegated to **subagents you spawn via your harness's native subagent tool** — one call per `judge_chunk_*_prompt.txt`, run in parallel. The three supported harnesses each provide such a tool:

- **bob v2** — `spawn_subagent`
- **claude** — `Task`
- **opencode** — `task`

All three run synchronously (return once the subagent has finished) and inherit the parent's credentials, so no per-subagent environment setup is needed. The exact tool name and parameter shape differ by harness, but the pattern is identical: hand the subagent a short prompt telling it to read one `judge_chunk_<N>_prompt.txt` file and write `agent_verdicts_<N>.jsonl` alongside it. See Stage 4d below for the concrete instruction to include in each subagent's prompt.

## Pipeline

Create a working directory under `output_dir` for intermediate state, e.g. `output_dir/work/`. Suggested file layout (scripts don't enforce names, but stay consistent so re-runs and caches line up):

```text
output_dir/
  work/
    source_wc_gen0.json
    target_wc_gen0.json
    embedding_cache.json
    judge_cache.json
    candidates.json
    judge_tasks.json / agent_verdicts.jsonl
    judgments.json
    scored.json
    aggregated.json
  mapping_collection.json              # final Stage 7 output
  report.html                          # final Stage 8 output
```

### Stage 1 — Ingest / Normalize (deterministic)

```bash
python3 scripts/ingest_normalize.py <source_catalog> work/source_wc_gen0.json
python3 scripts/ingest_normalize.py <target_catalog> work/target_wc_gen0.json
```

Parses the OSCAL Catalog (including nested groups and control enhancements) into the internal working-catalog format (`internal_model.py`): each control gets `id`, `title`, flattened `text` (statement + guidance prose), `family`, `params`, `links`. `generation: 0`. These files are the input to every downstream stage.

### Stage 2 — (reserved, downstream-only Granularity Align)

This stage is intentionally empty in the OSS variant. The `downstream` branch inserts a Granularity Align stage here that samples both sides, judges abstraction levels, and decomposes the coarser side when needed. The OSS variant skips it — controls are compared at their input granularity — so Stage 2 has no commands to run. The number is reserved so that Stage 3 (Blocking), Stage 4 (Judge), etc. line up across the two variants.

### Stage 3 — Blocking (deterministic)

```bash
python3 scripts/blocking.py work/source_wc_gen0.json work/target_wc_gen0.json \
    --output work/candidates.json --k 20 --cache work/embedding_cache.json
```

For each target control, finds the top-K most similar source controls by cosine similarity. `k` means top-K **source** candidates per **target** unit (from `mapping_spec.blocking.k`, default 20). Automatically uses FAISS if installed, otherwise a numpy brute-force fallback — check stderr for which backend ran; both give identical results, FAISS is just faster on large catalogs.

Blocking here uses the **embedding channel only**. Pairs whose surface text is very different but which nonetheless refer to the same domain concept (e.g. "vulnerability scanning" ↔ "maintain security capability w.r.t. vulnerabilities") may be missed at this stage — if a review of the final output shows systemic gaps of that shape, consider re-running with a larger `--k`.

### Stage 4 — Judge (LLM-driven, subagent-based)

Judge splits the work into fixed-size chunks and dispatches one subagent per chunk. You (the orchestrating Agent) do NOT judge pairs inline, do NOT decide chunk sizes yourself, and do NOT hand-write per-chunk prompts.

**Prep steps (4a–4c) — run these in whatever tool calls you like:**

```bash
# 4a. Build the task list (target × K source candidates per task).
python3 scripts/judge_prep.py work/candidates.json work/source_wc_gen0.json work/target_wc_gen0.json \
    --cache work/judge_cache.json --output work/judge_tasks.json

# 4b. Split into fixed-size chunks (5 targets per chunk).
# Produces work/judge_chunk_0.json, work/judge_chunk_1.json, ... (no zero-padding).
python3 scripts/chunk_judge_tasks.py work/judge_tasks.json work --size 5

# 4c. Generate a self-contained prompt file per chunk.
# --source-name and --target-name are cosmetic labels for the judge prompt; use the catalog display names.
python3 scripts/build_judge_prompt.py work --source-name "<SOURCE_CATALOG_NAME>" --target-name "<TARGET_CATALOG_NAME>"
```

**Troubleshooting — only if subagents fail with a Read size cap.** Always start with the default `--size 5`. Do NOT lower it preventively — a smaller size means more subagent invocations and can easily double wall-clock time (observed: same catalog pair took ~10 min at `--size 5` vs. ~24 min at mixed lower sizes on 2026-08-07). Only after you have **evidence in this run's per-chunk logs** that the Read cap fired — literally look for the string `exceeds maximum allowed size` — should you drop the size. Then:

1. Delete the failed chunks + prompts: `rm work/judge_chunk_*.json work/judge_chunk_*_prompt.txt` (verdicts you already wrote stay, the fan-out is idempotent).
2. Re-run 4b with `--size 3` (or `--size 4` if 3 feels excessive).
3. Re-run 4c to rebuild prompts, then continue at Stage 4d.

Do NOT re-run 4b multiple times with different sizes back-to-back; that overwrites the chunks and rebuilds every prompt each time, which can leave the pipeline in an inconsistent state where completed verdicts refer to chunk IDs that no longer describe the same tasks. Pick one size after seeing the error and commit to it for this run.

### Stage 4d — fan out to subagents (one per chunk)

For each `work/judge_chunk_<N>_prompt.txt` file, spawn a subagent via your harness's native subagent tool. Issue multiple spawn calls **in the same turn** to fan out in parallel — that is the throughput lever for this stage.

Each subagent's prompt should be exactly this (interpolate `<N>` and the absolute path to `work/`):

```text
Read the prompt file at <WORK_DIR>/judge_chunk_<N>_prompt.txt and follow its instructions verbatim. It is fully self-contained: it lists the target/source pairs to judge, defines the verdict format, and tells you where to write output. Write your verdicts JSONL to <WORK_DIR>/agent_verdicts_<N>.jsonl and reply with a one-line summary "chunk <N>: wrote M verdicts". Do not read any other files.
```

Notes:

- **Idempotent skip.** Before spawning, list `<WORK_DIR>/agent_verdicts_*.jsonl` and skip any chunk `<N>` whose file already exists and is non-empty. Only spawn subagents for missing/empty ones.
- **Batch size — cap at your harness's concurrent-subagent limit.** Claude Code caps at **20 concurrent subagents** per session (raise via `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`). Opencode and bob have similar limits. Do NOT issue more than 20 spawn calls in a single turn — the extra ones fail with a "concurrent subagent limit reached" tool error and you cannot retry them from that same turn. If you have more than 20 chunks, issue the first 20 in one turn, wait for them to return, then issue the next batch — the API keeps track of "concurrent" count, not "total issued this run".
- **After each batch, verify.** Once the batch's subagents have all returned, list `agent_verdicts_*.jsonl` again and re-spawn any chunk whose file is missing or empty (only those — successful ones stay).
- **Do NOT** shell out to another `bob run` / `opencode run` / `claude` process to launch subagents. The point of using the harness's native subagent tool is that no new CLI invocation is involved — the subagent lives inside the parent's process.
- **Read tool cap — the subagent prompt already tells the subagent to avoid `Read` on the chunk file** (Claude Code's Read tool caps at 256 KB and chunk files can exceed that). If you see subagents failing with "File content exceeds maximum allowed size", they're ignoring that guidance — the fix is to make the prompt more emphatic; do NOT lower `--size` first, because more chunks means more parallel-fan-out pressure against the concurrent-subagent limit above.

When every chunk has a non-empty `agent_verdicts_<N>.jsonl`, proceed to Stage 4e.

### Stages 4e–8 — run the packaged downstream script

Stages 4e (concatenate verdicts) through 8 (validate + report) are packaged as a single deterministic shell script. Invoke it once, foreground, and wait for it to exit:

```bash
bash scripts/run_judge_pipeline.sh \
    --output-dir <OUTPUT_DIR> \
    --source-catalog <SOURCE_CATALOG> \
    --source-href <SOURCE_HREF> \
    --target-catalog <TARGET_CATALOG> \
    --target-href <TARGET_HREF>
```

`<SOURCE_HREF>` / `<TARGET_HREF>` are the strings recorded in the mapping-collection's `source-resource` / `target-resource`. Passing the same absolute paths as `<SOURCE_CATALOG>` / `<TARGET_CATALOG>` is fine and matches what the shipped examples do.

Exit code 0 means the pipeline succeeded; any other value means a stage failed. Read `<OUTPUT_DIR>/judge_pipeline.log` for the traceback. Common failure exit codes:

- `2` — missing prerequisites (`work/` gone, or no `agent_verdicts_*.jsonl`)
- `3` — every subagent's verdicts file was empty. Inspect `work/agent_verdicts_<N>.jsonl` sizes to find which subagents produced nothing and re-spawn them.
- other non-zero — a downstream stage (`judge_apply` / `score_calibrate` / `aggregate` / `emit_oscal` / `validate_oscal` / `generate_report`) errored. Read the log.

**Restart semantics.** The whole pipeline is idempotent. Rerunning after a partial failure only re-executes stages whose outputs are missing. Chunks whose `agent_verdicts_<N>.jsonl` already exists and is non-empty are skipped during Stage 4d's re-fan-out; downstream stages simply overwrite `judgments.json` / `scored.json` / etc. from the concatenated verdicts. The correct action after a failure is almost always "run Stage 4d for the missing chunks, then run `run_judge_pipeline.sh` again."

### Stages 5–7 — what each stage does (for diagnosis, not invocation)

**These stages run inside `run_judge_pipeline.sh` — you do not invoke them separately.** What follows is a description of *what each stage does*, so you understand what to inspect if something looks off in the final output.

**Stage 5 — score_calibrate.py**: applies `mapping_spec.thresholds` (default confidence≥0.75, coverage≥0.15) to mark each link `passes_threshold`. The coverage threshold is intentionally low because the dominant relationship type (`intersects-with`) denotes partial overlap by nature — a link with conf=0.8, cov=0.20 means "high certainty that these controls partially intersect," which is a valid mapping. Coverage values are preserved so downstream consumers can apply stricter filters.

**Stage 6 — aggregate.py**: rolls links up to per-source-control coverage (fraction of that control's units that have at least one passing link) and reports `low_coverage_controls`.

`low_coverage_controls` is emitted as informational output. If a review shows coverage looks weak, the operator's options are: rerun the pipeline manually with a larger `--k` or lower thresholds, review individual cases via the authoring skill, or accept the gap and report it as-is. There is no automatic retry loop.

**Stage 7 — emit_oscal.py**:

Links are emitted at control granularity — `Mab` and the input catalogs share the same unit IDs. Each `map` entry in the output carries: `relationship`, `confidence-score.percentage`, `coverage.target-coverage`, and a `mapping-rationale` prop concatenating the distinct LLM rationales that contributed to that grouped link.

**Mapping-collection title**: the `mapping-collection.metadata.title` is auto-derived by `emit_oscal.py` as `"<source metadata.title> to <target metadata.title>"`, reading the two OSCAL catalogs' own `catalog.metadata.title` fields. This matches the convention used by the trestle.ws mapping-collections repository (e.g. `"IBM Sovereign Controls Framework (ISCF) to General Data Protection Regulation (EU) 2016/679"`). Do NOT pass `--title` to `emit_oscal.py` unless the user has explicitly supplied a hand-authored title — the automatic derivation is the intended behaviour and the full rule lives in SPEC.md §10.

**Mapping-collection description**: same shape. `mapping-collection.provenance.mapping-description` is auto-derived by `emit_oscal.py` as `"Mapping collection from <source metadata.title> to <target metadata.title>"`, again reading the two OSCAL catalogs' own `catalog.metadata.title` fields. This matches the corpus convention (e.g. `"Mapping collection from IBM Sovereign Controls Framework (ISCF) to Cloud Controls Matrix"`). Do NOT pass `--description` to `emit_oscal.py` unless the user has explicitly supplied a hand-authored description — the automatic derivation is the intended behaviour and the full rule lives in SPEC.md §10.

**target-gap-summary**: `emit_oscal.py` also computes which target-side controls (from `work/target_wc_gen0.json` — same granularity as `targets`) never appear as a target in any emitted `map` entry, and — if any exist — writes them to `mappings[0].target-gap-summary.unmapped-controls[0].with-ids`. This is a *different* signal from Stage 6's `low_coverage_controls`: that one flags source controls whose requirements aren't well covered; this one flags target controls that the source never touches at all.

**Stage 8 — validate_oscal.py + generate_report.py**: `validate_oscal.py` runs `trestle validate -f` inside a throwaway trestle workspace (you don't set one up yourself). `generate_report.py` produces a single self-contained HTML file (`report.html`) with the mapping data inlined — this is the primary deliverable for reviewers who don't have an agent CLI installed. Both are invoked by `run_judge_pipeline.sh` as its final steps.

**If validation fails**: read `trestle validate`'s error output (echoed to `judge_pipeline.log`), diagnose (usually a malformed value that slipped through Judge, or an incorrect emit argument), fix `mapping_collection.json` or the appropriate `work/*.json`, and re-run `run_judge_pipeline.sh` — its emit + validate + report steps are idempotent and will rebuild the report from the corrected inputs. The scripts themselves do not auto-fix anything.

## Completion criteria

The pipeline is complete when **both** of these files exist and are non-empty:

- `output_dir/mapping_collection.json`
- `output_dir/report.html`

If `run_judge_pipeline.sh` returned non-zero or either file is missing, inspect `<OUTPUT_DIR>/judge_pipeline.log` and re-run Stage 4d (for any chunks whose verdicts are missing) followed by `run_judge_pipeline.sh` again.

## Framework-pair profiles

If mapping the same two frameworks repeatedly, save a `mapping_spec` JSON/YAML (see `scripts/mapping_spec.py` for the schema: `relationship_types` (`intersects-with`, `equivalent-to`, `superset-of`, `subset-of`, `no-relationship`), `direction_semantics`, `thresholds`, `blocking.k`) so future runs are consistent without re-deciding thresholds each time.

## Notes

- Every cache (`embedding_cache.json`, `judge_cache.json`) is keyed by a hash of the *text* being processed, so reruns after small catalog edits only redo work for changed controls.
- Stage 4 (Judge) is the only stage that scales with N×K LLM calls; everything else is O(N+M) or embedding-only. For large catalogs, the fixed 5-targets-per-chunk + parallel subagent fan-out is what keeps the wall time bounded — do NOT substitute heuristics or scripts for actual LLM judgment regardless of catalog size.
- Never call an external LLM API (OpenAI, Anthropic API, etc.) from inside these scripts — all semantic judgment happens in subagents launched via your harness's native subagent tool.
- **Emit-only-real-relationships (v3 protocol):** The prompt template asks each subagent to emit verdicts ONLY for pairs with a real relationship (intersects-with / equivalent-to / superset-of / subset-of). `judge_apply.py` auto-fills every un-emitted pair as `no-relationship` (confidence 0.9, coverage 0.0, empty rationale) and writes those into the judge cache. This more than halves the subagent's output token count vs. the older "label every pair" protocol.

## Absolute prohibitions

- **NEVER** substitute Stage 4 with a Python script, shell heuristic, or inline judgment done by you (the orchestrator) instead of delegating to subagents. If you find yourself judging pairs directly (looking at texts and emitting verdicts in your own tool_use), stop — that path was tried and was both slow and prone to skipping the harder pairs.
- **NEVER** produce verdicts with generic/template rationales like "Partial overlap in compliance mechanisms" or "Shared security domain concepts." The prompt template already forbids this; if you see such rationales in the output, treat the affected chunks as failed and re-run them.
- If the task count is large (hundreds or thousands), that is expected. Parallel subagent fan-out handles it. Do NOT reduce chunk count by inlining, do NOT skip pairs, do NOT summarise. (`judge_apply.py` treats missing pairs as no-relationship — that is fine and expected. It is NOT a reason to widen the prompt.)
