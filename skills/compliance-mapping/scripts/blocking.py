#!/usr/bin/env python3
"""Stage 2: Blocking (candidate generation).

For each target control, finds the top-K most similar source controls by
embedding cosine similarity.  This target-driven direction ensures every
target control gets a chance to find matching sources, preventing recall
loss when the target catalog is larger than K.

Results are grouped by target_id — each entry is one target with its
top-K source candidates.

Usage:
    python blocking.py <source_working_catalog.json> <target_working_catalog.json> \
        --output <candidates.json> [--k 20] [--cache <embedding_cache.json>] [--min-score 0.0]
"""
import argparse
import json
import sys

from internal_model import load_working_catalog, control_units, unit_kind
from embedding_utils import embed_texts, ANNIndex, backend_name


def main():
    parser = argparse.ArgumentParser(description="Generate candidate pairs via embedding similarity")
    parser.add_argument("source_catalog")
    parser.add_argument("target_catalog")
    parser.add_argument("--output", required=True)
    parser.add_argument("--k", type=int, default=20, help="Top-K source candidates per target unit")
    parser.add_argument("--cache", default=None, help="Embedding cache path")
    parser.add_argument("--min-score", type=float, default=0.0, help="Drop candidates below this cosine score")
    args = parser.parse_args()

    source_wc = load_working_catalog(args.source_catalog)
    target_wc = load_working_catalog(args.target_catalog)

    source_units = control_units(source_wc)
    target_units = control_units(target_wc)

    source_emb = embed_texts(source_units, cache_path=args.cache)
    target_emb = embed_texts(target_units, cache_path=args.cache)

    # Build ANN index over the source side
    source_ids = [uid for uid, _ in source_units]
    source_vectors = [source_emb[uid] for uid in source_ids]
    index = ANNIndex(source_ids, source_vectors)

    # For each target unit, find top-K similar source units
    candidates = []
    for tid, _text in target_units:
        hits = index.search(target_emb[tid], k=args.k)
        source_hits = [
            {"source_id": sid, "source_kind": unit_kind(source_wc, sid), "score": round(score, 4)}
            for sid, score in hits
            if score >= args.min_score
        ]
        candidates.append(
            {
                "target_id": tid,
                "target_kind": unit_kind(target_wc, tid),
                "candidates": source_hits,
            }
        )

    output = {
        "source_catalog_id": source_wc["catalog_id"],
        "target_catalog_id": target_wc["catalog_id"],
        "source_generation": source_wc["generation"],
        "target_generation": target_wc["generation"],
        "k": args.k,
        "search_direction": "target-to-source",
        "ann_backend": backend_name(),
        "channel": "embedding",
        "pairs": candidates,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    total_candidates = sum(len(c["candidates"]) for c in candidates)
    print(
        f"blocking: {len(target_units)} target units x top-{args.k} sources over {len(source_units)} source units "
        f"-> {total_candidates} candidate pairs (backend={backend_name()}) -> {args.output}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
