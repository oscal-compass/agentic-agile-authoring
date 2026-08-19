#!/usr/bin/env python3
"""Stage 3a: Judge — batch prep.

For each target control and its blocked source-candidates (from blocking),
builds one judge "task": target text + K source texts (with their precomputed
embedding similarity as a hint). The Agent consumes these tasks, judges
each candidate pair's relationship/confidence/coverage/rationale, and
passes results to judge_apply.py.

Splits tasks into already-cached (pair previously judged, same texts) vs
needs-judgment, so repeated runs skip LLM calls for unchanged pairs.

Usage:
    python judge_prep.py <candidates.json> <source_working_catalog.json> <target_working_catalog.json> \
        --cache <judge_cache.json> --output <judge_tasks.json>
"""
import argparse
import hashlib
import json
import os
import sys

from internal_model import load_working_catalog, control_units


def pair_hash(source_text, target_text):
    return hashlib.sha256(f"{source_text}␟{target_text}".encode("utf-8")).hexdigest()


def load_cache(path):
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def main():
    parser = argparse.ArgumentParser(description="Prepare Judge batches for the Agent")
    parser.add_argument("candidates", help="Output of blocking/merge")
    parser.add_argument("source_catalog")
    parser.add_argument("target_catalog")
    parser.add_argument("--cache", default=None, help="Judge cache path (pair_hash -> verdict)")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    with open(args.candidates, "r", encoding="utf-8") as f:
        cand_data = json.load(f)

    source_wc = load_working_catalog(args.source_catalog)
    target_wc = load_working_catalog(args.target_catalog)
    source_text_by_id = dict(control_units(source_wc))
    target_text_by_id = dict(control_units(target_wc))

    cache = load_cache(args.cache)

    tasks = []
    cached_verdicts = []

    for entry in cand_data["pairs"]:
        target_id = entry["target_id"]
        target_text = target_text_by_id.get(target_id, "")
        candidate_items = []
        for c in entry["candidates"]:
            source_id = c["source_id"]
            source_text = source_text_by_id.get(source_id, "")
            h = pair_hash(source_text, target_text)
            if h in cache:
                cached_verdicts.append({"source_id": source_id, "target_id": target_id, "hash": h, **cache[h]})
            else:
                candidate_items.append(
                    {
                        "source_id": source_id,
                        "text": source_text,
                        "embedding_score": c["score"],
                        "hash": h,
                    }
                )
        if candidate_items:
            tasks.append(
                {
                    "target_id": target_id,
                    "target_text": target_text,
                    "candidates": candidate_items,
                }
            )

    output = {
        "source_catalog_id": cand_data["source_catalog_id"],
        "target_catalog_id": cand_data["target_catalog_id"],
        "tasks": tasks,
        "cached_verdicts": cached_verdicts,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    total_pairs_to_judge = sum(len(t["candidates"]) for t in tasks)
    print(
        f"judge_prep: {len(tasks)} target units need judging "
        f"({total_pairs_to_judge} new pairs, {len(cached_verdicts)} cache hits) -> {args.output}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
