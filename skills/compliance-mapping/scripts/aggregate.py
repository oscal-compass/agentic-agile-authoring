#!/usr/bin/env python3
"""Stage 5: Aggregate / Post.

Rolls scored links up to per-source-control coverage (fraction of that
control's units covered by at least one passing target-side link) and
flags low-coverage controls as informational output.

Conflict resolution: when a source control has multiple target-side links,
they are all kept (1-to-many is expected — see design doc section 5), but
links below threshold are dropped from the "accepted" set while still
being retained in the record for traceability.

Deterministic. `low_coverage_controls` is emitted as informational output
for a human reviewer; this script does not itself retry Blocking/Judge.

Usage:
    python aggregate.py <scored.json> <source_working_catalog.json> \
        --output <aggregated.json> [--low-coverage-threshold 0.5]
"""
import argparse
import json
import sys
from collections import defaultdict

from internal_model import load_working_catalog


def main():
    parser = argparse.ArgumentParser(description="Aggregate scored links into per-control coverage")
    parser.add_argument("scored", help="Output of score_calibrate.py")
    parser.add_argument("source_catalog")
    parser.add_argument("--output", required=True)
    parser.add_argument("--low-coverage-threshold", type=float, default=0.5)
    args = parser.parse_args()

    with open(args.scored, "r", encoding="utf-8") as f:
        scored = json.load(f)

    source_wc = load_working_catalog(args.source_catalog)

    # unit_id -> set of accepted target links
    accepted_by_unit = defaultdict(list)
    all_by_unit = defaultdict(list)
    for link in scored["links"]:
        all_by_unit[link["source_id"]].append(link)
        if link["passes_threshold"]:
            accepted_by_unit[link["source_id"]].append(link)

    control_reports = []
    low_coverage = []

    for control in source_wc["controls"]:
        unit_ids = [control["id"]]
        covered_units = [uid for uid in unit_ids if accepted_by_unit.get(uid)]
        coverage_ratio = len(covered_units) / len(unit_ids) if unit_ids else 0.0

        links_for_control = []
        for uid in unit_ids:
            links_for_control.extend(accepted_by_unit.get(uid, []))

        report = {
            "control_id": control["id"],
            "unit_count": len(unit_ids),
            "covered_unit_count": len(covered_units),
            "coverage_ratio": round(coverage_ratio, 3),
            "links": links_for_control,
            "has_any_candidate": bool(all_by_unit.get(control["id"])),
        }
        control_reports.append(report)

        if coverage_ratio < args.low_coverage_threshold:
            low_coverage.append(
                {
                    "control_id": control["id"],
                    "coverage_ratio": round(coverage_ratio, 3),
                    "reason": "no_candidates" if not report["has_any_candidate"] else "below_threshold",
                }
            )

    output = {
        "source_catalog_id": scored["source_catalog_id"],
        "target_catalog_id": scored["target_catalog_id"],
        "controls": control_reports,
        "low_coverage_controls": low_coverage,
        "summary": {
            "total_controls": len(control_reports),
            "fully_covered": sum(1 for r in control_reports if r["coverage_ratio"] >= 0.999),
            "partially_covered": sum(0 < r["coverage_ratio"] < 0.999 for r in control_reports),
            "uncovered": sum(1 for r in control_reports if r["coverage_ratio"] == 0.0),
        },
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    s = output["summary"]
    print(
        f"aggregate: {s['total_controls']} controls — "
        f"{s['fully_covered']} fully covered, {s['partially_covered']} partial, {s['uncovered']} uncovered; "
        f"{len(low_coverage)} flagged low-coverage (<{args.low_coverage_threshold}) -> {args.output}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
