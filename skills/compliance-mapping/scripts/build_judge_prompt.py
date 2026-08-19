#!/usr/bin/env python3
"""Stage 3c: Build self-contained prompt files for each judge chunk.

For each judge_chunk_N.json in the input dir, writes a
judge_chunk_N_prompt.txt containing:
  - Complete judge instructions (relationship vocabulary, confidence/coverage
    ranges, rationale requirements, output format)
  - Relative filename of the chunk file to Read
  - Relative filename of the verdicts file to Write

The prompt is fully self-contained — the sub-agent invoked via run_agent.sh
does NOT need to read SKILL.md. This avoids ~30KB of context re-loading
per sub-agent, which was a measured bottleneck.

**Paths are relative** (basenames only) so the sub-agent's harness workspace
constraint (e.g. bob refuses read/write outside its workspace) can be handled
by launching the sub-agent with cwd = this chunk_dir via `run_agent.sh -w`.
The caller is responsible for setting the working directory.

Usage:
    python build_judge_prompt.py <chunk_dir> [--source-name ISCF] [--target-name GovRAMP-Low]
"""
import argparse
import glob
import json
import os
import re
import sys


PROMPT_TEMPLATE = """You are a compliance mapping judge. For each target control, pick the source controls it has a real semantic relationship with.

CONTEXT:
- Source catalog: {source_name}
- Target catalog: {target_name}
- Direction: "source implements target" — for each pair you emit, the SOURCE control's requirement is satisfied by / implements / overlaps with the TARGET control's requirement.

RELATIONSHIP VOCABULARY (pick exactly one for each pair you EMIT):
- "intersects-with": the two controls have overlapping concerns / operational mechanisms. (Expect this for 95%+ of emitted pairs.)
- "equivalent-to": near-identical controls (rare, <1%).
- "superset-of": source fully covers target plus more (<2%).
- "subset-of": source covers a strict subset of target (<2%).

CONFIDENCE (0-1): how sure you are of the chosen relationship.
COVERAGE (0-1): what fraction of the source unit's requirement is satisfied by / addressed via the target unit.

RATIONALE: one short sentence that cites specific content from the actual source and target texts. Do NOT emit generic templates like "Partial overlap in compliance mechanisms." Aim for 10-25 words.

CRITICAL RULES:
1. Judge on IMPLEMENTATION OVERLAP, not domain origin. Two controls from different regulatory domains often mandate the same operational mechanism (access control, encryption, logging, incident response, governance, testing, etc.). If both require the same type of activity or capability, they intersect-with regardless of stated purpose or industry framing.
2. The embedding similarity score is only a HINT. Trust your reading of the actual texts over it.
3. **DO NOT emit "no-relationship" verdicts.** Any candidate pair you do not emit is treated as no-relationship automatically by downstream processing. This is the whole point of this task — you are FILTERING, not exhaustively labelling.
4. If a target has zero relevant sources, emit zero lines for that target.
5. NEVER produce verdicts programmatically. Read each pair and reason about it.

OUTPUT FORMAT — one JSON object per line, exactly these keys, only for pairs with a real relationship:
{{"source_id": "...", "target_id": "...", "hash": "...", "relationship": "intersects-with|equivalent-to|superset-of|subset-of", "confidence": 0.0-1.0, "coverage": 0.0-1.0, "rationale": "..."}}

Use the "hash" from the input candidate entry verbatim.

TASK:
1. Load `{chunk_path}` (relative to your current working directory). **Do NOT use the Read tool** — that tool has a 256 KB cap that this file frequently exceeds. Use bash + `python3` (or `jq`) to stream / iterate it, e.g. `python3 -c "import json; d=json.load(open('{chunk_path}')); ..."`. It contains a "tasks" array. Each task has target_id, target_text, and a "candidates" array. Each candidate has source_id, text, embedding_score, and hash.
2. For every task, look at every candidate and decide whether the source implements/overlaps the target. Emit a verdict line ONLY for candidates that do — skip the rest silently.
3. Write ALL emitted verdicts to `{verdicts_path}` (relative to your current working directory) using the Write tool in one shot (a single Write with all lines concatenated as newline-separated JSON).
4. If NO candidate for any target has a real relationship, still write an empty file at `{verdicts_path}` (0 bytes is fine) so downstream sees the chunk as processed.
5. When you're done, print "DONE" and stop.

**IMPORTANT — paths are relative filenames only, not absolute paths.** Do NOT prepend directories. Read/Write the files by the exact basenames given above. Your workspace is already the correct directory.
"""


def build_prompt(chunk_path, verdicts_path, source_name, target_name):
    return PROMPT_TEMPLATE.format(
        source_name=source_name,
        target_name=target_name,
        chunk_path=chunk_path,
        verdicts_path=verdicts_path,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("chunk_dir", help="Directory containing judge_chunk_N.json files")
    parser.add_argument("--source-name", default="source catalog")
    parser.add_argument("--target-name", default="target catalog")
    args = parser.parse_args()

    chunk_files = sorted(
        glob.glob(os.path.join(args.chunk_dir, "judge_chunk_*.json")),
        key=lambda p: int(re.search(r"judge_chunk_(\d+)\.json", p).group(1)),
    )
    if not chunk_files:
        print(f"build_judge_prompt: no judge_chunk_*.json in {args.chunk_dir}", file=sys.stderr)
        sys.exit(1)

    for chunk_path in chunk_files:
        m = re.search(r"judge_chunk_(\d+)\.json", chunk_path)
        idx = m.group(1)
        prompt_path = os.path.join(args.chunk_dir, f"judge_chunk_{idx}_prompt.txt")
        chunk_basename = f"judge_chunk_{idx}.json"
        verdicts_basename = f"agent_verdicts_{idx}.jsonl"
        prompt = build_prompt(
            chunk_path=chunk_basename,
            verdicts_path=verdicts_basename,
            source_name=args.source_name,
            target_name=args.target_name,
        )
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(prompt)

    print(f"build_judge_prompt: wrote {len(chunk_files)} prompt files in {args.chunk_dir}")


if __name__ == "__main__":
    main()
