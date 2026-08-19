#!/usr/bin/env python3
"""Mapping spec profile — framework-pair comparison configuration.

Per design doc section 8, comparison behavior (relationship vocabulary,
thresholds, blocking K) is externalized as a profile so it can be swapped
per framework pair without touching pipeline code.

A profile is a small YAML or JSON file:

    relationship_types:
      - intersects-with      # default for most entries (95%+)
      - equivalent-to        # near-identical controls (<1%)
      - superset-of          # source fully covers target plus more (<2%)
      - subset-of            # source covers strict subset of target (<2%)
      - no-relationship      # gap entries only
    direction_semantics: "source implements target"
    thresholds:
      confidence: 0.75
      coverage: 0.15
    blocking:
      k: 20
      search_direction: target-to-source

If no profile is given, DEFAULT_SPEC is used.
"""
import json
import os

DEFAULT_SPEC = {
    "relationship_types": ["intersects-with", "equivalent-to", "superset-of", "subset-of", "no-relationship"],
    "direction_semantics": "source implements target",
    "thresholds": {"confidence": 0.75, "coverage": 0.15},
    "blocking": {"k": 20, "search_direction": "target-to-source"},
}


def load_spec(path=None):
    if not path:
        return dict(DEFAULT_SPEC)
    if not os.path.exists(path):
        raise FileNotFoundError(f"mapping spec not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        if path.endswith((".yaml", ".yml")):
            import yaml

            spec = yaml.safe_load(f)
        else:
            spec = json.load(f)
    merged = dict(DEFAULT_SPEC)
    merged.update(spec)
    for key in ("thresholds", "blocking"):
        if key in spec:
            merged[key] = {**DEFAULT_SPEC[key], **spec[key]}
    return merged


if __name__ == "__main__":
    import sys

    spec = load_spec(sys.argv[1] if len(sys.argv) > 1 else None)
    print(json.dumps(spec, indent=2, ensure_ascii=False))
