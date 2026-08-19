#!/usr/bin/env bash
# ============================================================================
# run_judge_pipeline.sh — Stages 4e through 8 of the compliance-mapping skill.
#
# By the time this script runs, the outer agent must have already:
#   1. Ingested and blocked the two catalogs (Stages 1 + 3).
#   2. Built judge_chunk_*_prompt.txt files (Stages 4a-4c).
#   3. Fanned out to subagents (one per chunk) via its native subagent tool
#      (bob's spawn_subagent, claude's Task, opencode's task) — each subagent
#      writes work/agent_verdicts_<N>.jsonl.
#
# This script then runs stages 4e-8 deterministically: concatenate the
# per-chunk verdicts, apply them, score, aggregate, emit the OSCAL Mapping
# Collection, validate, and generate the HTML report. No LLM calls.
#
# Stage numbering aligns with SKILL.md / SPEC.md:
#   1 Ingest, (2 reserved for downstream Granularity Align), 3 Blocking,
#   4 Judge (this script picks up from 4e), 5 Score, 6 Aggregate,
#   7 Emit + validate, 8 Report.
#
# Usage:
#   run_judge_pipeline.sh --output-dir <output_dir> \
#       --source-catalog <path> --source-href <href> \
#       --target-catalog <path> --target-href <href> \
#       [--work-dir <dir>]
#
# All paths must be absolute; the script cds to output_dir and drives work/
# under it. Exit 0 on success, non-zero on failure — the caller reads the
# exit code directly, no completion-marker file needed.
# ============================================================================
set -uo pipefail

# ---- args ------------------------------------------------------------------

OUTPUT_DIR=""
WORK_DIR=""
SOURCE_CATALOG=""
SOURCE_HREF=""
TARGET_CATALOG=""
TARGET_HREF=""

while [ $# -gt 0 ]; do
  case "$1" in
    --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
    --work-dir) WORK_DIR="$2"; shift 2 ;;
    --source-catalog) SOURCE_CATALOG="$2"; shift 2 ;;
    --source-href) SOURCE_HREF="$2"; shift 2 ;;
    --target-catalog) TARGET_CATALOG="$2"; shift 2 ;;
    --target-href) TARGET_HREF="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$OUTPUT_DIR" ] || [ -z "$SOURCE_CATALOG" ] || [ -z "$SOURCE_HREF" ] \
    || [ -z "$TARGET_CATALOG" ] || [ -z "$TARGET_HREF" ]; then
  echo "usage: run_judge_pipeline.sh --output-dir DIR --source-catalog PATH --source-href HREF --target-catalog PATH --target-href HREF [--work-dir DIR]" >&2
  exit 2
fi

if [ -z "$WORK_DIR" ]; then
  WORK_DIR="$OUTPUT_DIR/work"
fi

# Locate this script's directory so we can find the sibling python scripts
# even when invoked from an arbitrary cwd. generate_report.py + its
# template.html live right here alongside the pipeline scripts, so the
# skill is self-contained under skills/compliance-mapping/.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORT_GEN="$SCRIPT_DIR/generate_report.py"

LOG="$OUTPUT_DIR/judge_pipeline.log"

# Tee all output to the log for post-run inspection while still surfacing it
# to the caller.
exec > >(tee -a "$LOG") 2>&1

echo "=== run_judge_pipeline.sh starting at $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "OUTPUT_DIR   = $OUTPUT_DIR"
echo "WORK_DIR     = $WORK_DIR"
echo "SOURCE_CAT   = $SOURCE_CATALOG"
echo "TARGET_CAT   = $TARGET_CATALOG"

cd "$OUTPUT_DIR"

# ---- prerequisites ---------------------------------------------------------

if [ ! -d "$WORK_DIR" ]; then
  echo "FATAL: WORK_DIR $WORK_DIR does not exist — run Stages 4a-4c first" >&2
  exit 2
fi
if ! ls "$WORK_DIR"/agent_verdicts_*.jsonl >/dev/null 2>&1; then
  echo "FATAL: no agent_verdicts_*.jsonl under $WORK_DIR — the outer agent" >&2
  echo "       must fan out to subagents (via its native subagent tool) and" >&2
  echo "       drop one verdict file per judge_chunk_*_prompt.txt before" >&2
  echo "       invoking this script." >&2
  exit 2
fi

# ---- Stage 4e: concatenate per-chunk verdicts ------------------------------
cat "$WORK_DIR"/agent_verdicts_*.jsonl > "$WORK_DIR/agent_verdicts.jsonl" 2>/dev/null || true

# Refuse to proceed if we have zero verdicts — that means every sub-agent
# dropped an empty file and the downstream stages would just produce an
# empty mapping.
if [ ! -s "$WORK_DIR/agent_verdicts.jsonl" ]; then
  echo "FATAL: no verdicts landed in work/agent_verdicts.jsonl — inspect" >&2
  echo "       each work/agent_verdicts_<N>.jsonl to find which subagents" >&2
  echo "       emitted nothing." >&2
  exit 3
fi

# ---- Stage 4f: apply verdicts, validate, update cache ----------------------
echo "--- Stage 4f: judge_apply ---"
python3 "$SCRIPT_DIR/judge_apply.py" \
    "$WORK_DIR/judge_tasks.json" "$WORK_DIR/agent_verdicts.jsonl" \
    --cache "$WORK_DIR/judge_cache.json" --output "$WORK_DIR/judgments.json"

# ---- Stage 5: score --------------------------------------------------------
echo "--- Stage 5: score_calibrate ---"
python3 "$SCRIPT_DIR/score_calibrate.py" \
    "$WORK_DIR/judgments.json" "$WORK_DIR/candidates.json" \
    --output "$WORK_DIR/scored.json"

# ---- Stage 6: aggregate ----------------------------------------------------
echo "--- Stage 6: aggregate ---"
python3 "$SCRIPT_DIR/aggregate.py" \
    "$WORK_DIR/scored.json" "$WORK_DIR/source_wc_gen0.json" \
    --output "$WORK_DIR/aggregated.json" --low-coverage-threshold 0.5

# ---- Stage 7: emit OSCAL Mapping Collection + validate ---------------------
echo "--- Stage 7: emit_oscal + validate_oscal ---"
python3 "$SCRIPT_DIR/emit_oscal.py" "$WORK_DIR/aggregated.json" \
    --source-original "$SOURCE_CATALOG" --source-href "$SOURCE_HREF" \
    --target-original "$TARGET_CATALOG" --target-href "$TARGET_HREF" \
    --target-working "$WORK_DIR/target_wc_gen0.json" \
    --output "$OUTPUT_DIR/mapping_collection.json"

python3 "$SCRIPT_DIR/validate_oscal.py" --mapping "$OUTPUT_DIR/mapping_collection.json"

# ---- Stage 8: generate report ---------------------------------------------
echo "--- Stage 8: generate report ---"
python3 "$REPORT_GEN" "$OUTPUT_DIR/mapping_collection.json" \
    --work-dir "$WORK_DIR" \
    --output "$OUTPUT_DIR/report.html"

echo "=== DONE at $(date -u +%Y-%m-%dT%H:%M:%SZ). mapping_collection.json and report.html are ready. ==="
exit 0
