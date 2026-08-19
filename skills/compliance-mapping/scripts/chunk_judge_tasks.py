#!/usr/bin/env python3
"""Stage 3b: Chunk judge_tasks.json into fixed-size batches.

Splits judge_tasks.json (produced by judge_prep.py) into per-chunk files,
each containing at most N tasks (default 5). Each chunk file preserves
the top-level keys (source_catalog_id, target_catalog_id) plus a sliced
tasks[] array — same shape as the parent, so a chunk file is itself a
valid judge_tasks.json.

Output filenames use NO zero-padding: `judge_chunk_0.json`,
`judge_chunk_1.json`, ..., `judge_chunk_10.json`, `judge_chunk_11.json`.
This matters because the Stage 3d fan-out loop in SKILL.md pairs each
chunk file with a same-suffix verdicts file (`agent_verdicts_N.jsonl`)
and log file (`judge_N.log`) — those must match. Do not switch to a
zero-padded scheme without updating SKILL.md and build_judge_prompt.py
in the same commit.

Fixed chunking (as opposed to letting the Agent decide sizes) is the
whole point: uniform chunk size → uniform per-chunk latency → predictable
total time when running run_agent.sh in parallel.

Usage:
    python chunk_judge_tasks.py <judge_tasks.json> <output_dir> [--size 5]
"""
import argparse
import json
import os
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("tasks_file", help="judge_tasks.json from judge_prep.py")
    parser.add_argument("output_dir", help="Directory to write judge_chunk_N.json files into")
    parser.add_argument("--size", type=int, default=5, help="Targets per chunk (default 5)")
    args = parser.parse_args()

    with open(args.tasks_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    tasks = data.get("tasks", [])
    if not tasks:
        print(f"chunk_judge_tasks: 0 tasks in {args.tasks_file}, nothing to chunk", file=sys.stderr)
        sys.exit(0)

    os.makedirs(args.output_dir, exist_ok=True)

    n_chunks = (len(tasks) + args.size - 1) // args.size
    total_pairs = 0
    for i in range(n_chunks):
        chunk_tasks = tasks[i * args.size : (i + 1) * args.size]
        chunk = {
            "source_catalog_id": data.get("source_catalog_id"),
            "target_catalog_id": data.get("target_catalog_id"),
            "tasks": chunk_tasks,
        }
        out_path = os.path.join(args.output_dir, f"judge_chunk_{i}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(chunk, f, indent=2, ensure_ascii=False)
        pair_count = sum(len(t.get("candidates", [])) for t in chunk_tasks)
        total_pairs += pair_count

    print(
        f"chunk_judge_tasks: {len(tasks)} tasks -> {n_chunks} chunks "
        f"({args.size} targets/chunk, {total_pairs} total pairs) -> {args.output_dir}/judge_chunk_[0..{n_chunks - 1}].json"
    )


if __name__ == "__main__":
    main()
