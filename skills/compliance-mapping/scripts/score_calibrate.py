#!/usr/bin/env python3
# Copyright OSCAL Compass Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Stage 4: Score.

Combines signals (LLM confidence, embedding similarity as a secondary
signal) into a final score per link, then applies the spec's static
thresholds to flag which links pass. No LLM involved — this is
deterministic post-processing of Stage 3 output.

Usage:
    python score_calibrate.py <judgments.json> <candidates.json> --output <scored.json> \
        [--spec <mapping_spec.json>]
"""
import argparse
import json
import sys

from mapping_spec import load_spec


def build_embedding_lookup(candidates_data):
    lookup = {}
    for entry in candidates_data["pairs"]:
        left_id = entry.get("source_id") or entry.get("left_id")
        for c in entry["candidates"]:
            right_id = c.get("target_id") or c.get("right_id")
            lookup[(left_id, right_id)] = c["score"]
    return lookup


def main():
    parser = argparse.ArgumentParser(description="Score judge verdicts against static thresholds")
    parser.add_argument("judgments", help="Output of judge_apply.py")
    parser.add_argument("candidates", help="Output of blocking.py (for embedding scores)")
    parser.add_argument("--output", required=True)
    parser.add_argument("--spec", default=None, help="Path to mapping spec profile")
    args = parser.parse_args()

    spec = load_spec(args.spec)

    with open(args.judgments, "r", encoding="utf-8") as f:
        judgments = json.load(f)
    with open(args.candidates, "r", encoding="utf-8") as f:
        candidates_data = json.load(f)

    embedding_lookup = build_embedding_lookup(candidates_data)
    thresholds = spec["thresholds"]

    scored_links = []
    for v in judgments["verdicts"]:
        embedding_score = embedding_lookup.get((v["source_id"], v["target_id"]))
        passes_threshold = (
            v["confidence"] >= thresholds["confidence"] and v["coverage"] >= thresholds["coverage"]
        )
        scored_links.append(
            {
                **v,
                "embedding_score": embedding_score,
                "passes_threshold": passes_threshold,
            }
        )

    output = {
        "source_catalog_id": judgments["source_catalog_id"],
        "target_catalog_id": judgments["target_catalog_id"],
        "thresholds_applied": thresholds,
        "links": scored_links,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    passing = sum(1 for l in scored_links if l["passes_threshold"])
    print(
        f"score: {len(scored_links)} links scored, {passing} pass thresholds "
        f"(confidence>={thresholds['confidence']}, coverage>={thresholds['coverage']}) -> {args.output}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
