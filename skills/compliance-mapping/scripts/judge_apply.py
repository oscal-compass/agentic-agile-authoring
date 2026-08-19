#!/usr/bin/env python3
"""Stage 3f: Judge — apply / validate / cache.

Consumes the Agent's judge verdicts, validates their shape, merges them
with cache hits carried over from judge_prep.py, updates the judge cache,
and writes the unified verdict list used by Score (Stage 4).

The agent's prompt template asks it to emit verdicts ONLY for pairs with
a real relationship (intersects-with / equivalent-to / superset-of /
subset-of). Any pair present in judge_tasks.json but absent from the
agent's verdicts is auto-filled here as no-relationship (confidence 0.9,
coverage 0.0, empty rationale). That auto-filled no-rel goes into the
cache so it isn't re-judged next run, but is dropped from the active
verdict set downstream.

Supported input formats:
  1. JSONL (preferred): one verdict JSON object per line
  2. Legacy JSON: {"verdicts": [...]}

Verdict schema (from the agent):
  {"source_id": ..., "target_id": ..., "hash": "<from judge_prep task>",
   "relationship": "intersects-with|equivalent-to|superset-of|subset-of",
   "confidence": 0.0-1.0, "coverage": 0.0-1.0, "rationale": "short text"}

Usage:
    python judge_apply.py <judge_tasks.json> <agent_verdicts.json> \
        --cache <judge_cache.json> --output <judgments.json>
"""
import argparse
import json
import os
import sys

VALID_RELATIONSHIPS = {"intersects-with", "equivalent-to", "superset-of", "subset-of", "no-relationship"}


def validate_verdict(v):
    errors = []
    if v.get("relationship") not in VALID_RELATIONSHIPS:
        errors.append(f"invalid relationship: {v.get('relationship')!r}")
    for field in ("confidence", "coverage"):
        val = v.get(field)
        if not isinstance(val, (int, float)) or not (0.0 <= val <= 1.0):
            errors.append(f"invalid {field}: {val!r} (must be 0-1)")
    if not v.get("source_id") or not v.get("target_id"):
        errors.append("missing source_id/target_id")
    return errors


def _load_verdicts(path):
    """Load verdicts from JSONL (one verdict per line) or legacy JSON format."""
    if path.endswith(".jsonl"):
        with open(path, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    with open(path, "r", encoding="utf-8") as f:
        agent_data = json.load(f)
    if isinstance(agent_data, list):
        return agent_data
    return agent_data.get("verdicts", [])


def main():
    parser = argparse.ArgumentParser(description="Apply and validate Agent judge verdicts")
    parser.add_argument("judge_tasks", help="Output of judge_prep.py")
    parser.add_argument("agent_verdicts", help="Agent's judge results JSON")
    parser.add_argument("--cache", default=None)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    with open(args.judge_tasks, "r", encoding="utf-8") as f:
        prep_data = json.load(f)
    new_verdicts = _load_verdicts(args.agent_verdicts)

    rejected = []
    accepted = []
    for v in new_verdicts:
        errors = validate_verdict(v)
        if errors:
            rejected.append({"verdict": v, "errors": errors})
        else:
            accepted.append(v)

    # Build the set of every pair the judge was asked to look at.
    # Each candidate carries its own hash; pair identity = (source_id, target_id, hash).
    all_asked_hashes = {}  # hash -> (source_id, target_id)
    for task in prep_data.get("tasks", []):
        tid = task.get("target_id")
        for cand in task.get("candidates", []):
            h = cand.get("hash")
            sid = cand.get("source_id")
            if h and sid and tid:
                all_asked_hashes[h] = (sid, tid)

    accepted_hashes = {v["hash"] for v in accepted if v.get("hash")}

    # Auto-fill: every hash the judge did not emit a verdict for is no-relationship.
    autofilled = []
    for h, (sid, tid) in all_asked_hashes.items():
        if h in accepted_hashes:
            continue
        autofilled.append({
            "source_id": sid,
            "target_id": tid,
            "hash": h,
            "relationship": "no-relationship",
            "confidence": 0.9,
            "coverage": 0.0,
            "rationale": "",
        })

    cache = {}
    if args.cache and os.path.exists(args.cache):
        with open(args.cache, "r", encoding="utf-8") as f:
            cache = json.load(f)

    for v in accepted + autofilled:
        h = v.get("hash")
        if h:
            cache[h] = {
                "relationship": v["relationship"],
                "confidence": v["confidence"],
                "coverage": v["coverage"],
                "rationale": v.get("rationale", ""),
            }

    if args.cache:
        with open(args.cache, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)

    all_verdicts = accepted + autofilled + prep_data.get("cached_verdicts", [])
    active_verdicts = [v for v in all_verdicts if v["relationship"] != "no-relationship"]

    output = {
        "source_catalog_id": prep_data["source_catalog_id"],
        "target_catalog_id": prep_data["target_catalog_id"],
        "verdicts": active_verdicts,
        "no_relationship_count": len(all_verdicts) - len(active_verdicts),
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(
        f"judge_apply: {len(accepted)} accepted, {len(rejected)} rejected, "
        f"{len(autofilled)} auto-filled no-relationship, "
        f"{len(prep_data.get('cached_verdicts', []))} cache hits merged -> "
        f"{len(active_verdicts)} active relationship links -> {args.output}",
        file=sys.stderr,
    )
    if rejected:
        print(f"WARNING: {len(rejected)} verdicts failed validation:", file=sys.stderr)
        for r in rejected[:10]:
            print(f"  {r['verdict'].get('source_id')}->{r['verdict'].get('target_id')}: {r['errors']}", file=sys.stderr)
        if len(rejected) > 10:
            print(f"  ... and {len(rejected) - 10} more", file=sys.stderr)


if __name__ == "__main__":
    main()
