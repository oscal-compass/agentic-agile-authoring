#!/usr/bin/env python3
"""Stage 6: Emit.

Produces an OSCAL Mapping Collection JSON from the aggregated links.

Links are emitted at control granularity — `Mab` and the input catalogs
share the same unit IDs. Each `map` entry carries relationship,
confidence-score, coverage, and a mapping-rationale prop with the LLM's
rationale text.

Also computes `target-gap-summary`: target-side controls that never
appear as a target in any emitted map entry.

Usage:
    python emit_oscal.py <aggregated.json> \
        --source-original <source_original_oscal.json> --source-href <path> \
        --target-original <target_original_oscal.json> --target-href <path> \
        --target-working <target_working_catalog.json> \
        --output <mapping_collection.json> [--title "..."] [--description "..."]
"""
import argparse
import datetime
import json
import sys
import uuid
from collections import defaultdict

from internal_model import control_units, load_working_catalog


def _load_catalog_metadata(oscal_path):
    with open(oscal_path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    catalog = doc.get("catalog", {}) or {}
    return catalog.get("uuid"), (catalog.get("metadata", {}) or {})


def get_catalog_uuid(oscal_path):
    uuid_, _ = _load_catalog_metadata(oscal_path)
    return uuid_


def get_catalog_title(oscal_path):
    """Return the OSCAL catalog's `metadata.title`, or None if absent.

    The title is authoritative — every OSCAL catalog carries one, and it is
    the string a reviewer expects to see on the mapping. Falling back to a
    filename would produce ugly titles like "catalog.json to catalog.json"
    for the common case where both inputs are named `catalog.json` under
    different directories.
    """
    _, md = _load_catalog_metadata(oscal_path)
    title = md.get("title")
    if not title or not str(title).strip():
        return None
    return str(title).strip()


def derive_mapping_title(source_oscal_path, target_oscal_path):
    """Compose the mapping-collection title from the two catalogs' own titles.

    Convention (documented in SPEC.md §10 and SKILL.md Stage 6):
        "<source metadata.title> to <target metadata.title>"

    If either side is missing a title, fall back to whichever one is present
    with an explanatory suffix, or to a generic label. Callers that need a
    hand-authored title should pass `--title` explicitly — that override
    takes precedence over the auto-derived value.
    """
    s = get_catalog_title(source_oscal_path)
    t = get_catalog_title(target_oscal_path)
    if s and t:
        return f"{s} to {t}"
    if s:
        return f"{s} to (target catalog title missing)"
    if t:
        return f"(source catalog title missing) to {t}"
    return "Compliance Mapping"


def derive_mapping_description(source_oscal_path, target_oscal_path):
    """Compose the mapping-collection description from the two catalogs' own titles.

    Convention (documented in SPEC.md §10 and SKILL.md Stage 6):
        "Mapping collection from <source metadata.title> to <target metadata.title>"

    Same shape as `derive_mapping_title`, wrapped in the fixed prefix
    "Mapping collection from …" to match the trestle.ws/mapping-collections
    corpus convention. Callers that need a hand-authored description should
    pass `--description` explicitly — that override takes precedence over
    the auto-derived value.
    """
    s = get_catalog_title(source_oscal_path)
    t = get_catalog_title(target_oscal_path)
    if s and t:
        return f"Mapping collection from {s} to {t}"
    if s:
        return f"Mapping collection from {s} to (target catalog title missing)"
    if t:
        return f"Mapping collection from (source catalog title missing) to {t}"
    return "Compliance mapping"


def build_resource(oscal_path, href):
    return {
        "type": "catalog",
        "href": href,
        "props": [
            {
                "name": "catalog_uuid",
                "value": get_catalog_uuid(oscal_path),
                "ns": "https://example.com/custom/ns/oscal",
            }
        ],
    }


def group_links(controls_report):
    """Group links by (relationship, target_id) at the control level."""
    groups = defaultdict(lambda: {"sources": set(), "confidences": [], "coverages": [], "rationales": set()})

    for control_report in controls_report:
        for link in control_report["links"]:
            key = (link["relationship"], (link["target_id"],))
            g = groups[key]
            g["sources"].add(link["source_id"])
            g["confidences"].append(link["confidence"])
            g["coverages"].append(link["coverage"])
            if link.get("rationale"):
                g["rationales"].add(link["rationale"])

    return groups


def compute_target_gap(maps, target_wc):
    """Target-side controls that never appear as a target in any map entry."""
    all_unit_ids = {unit[0] for unit in control_units(target_wc)}
    mapped_ids = {t["id-ref"] for m in maps for t in m["targets"]}
    return sorted(all_unit_ids - mapped_ids)


def main():
    parser = argparse.ArgumentParser(description="Emit OSCAL Mapping Collection from aggregated links")
    parser.add_argument("aggregated", help="Output of aggregate.py")
    parser.add_argument("--source-original", required=True, help="Original source OSCAL catalog path (for uuid)")
    parser.add_argument("--source-href", required=True, help="href to record for the source resource")
    parser.add_argument("--target-original", required=True)
    parser.add_argument("--target-href", required=True)
    parser.add_argument("--target-working", required=True, help="Target working catalog (for target-gap-summary)")
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--title",
        default=None,
        help=(
            "Override the mapping-collection metadata.title. If omitted, "
            "the title is auto-derived from the two catalogs' own "
            "metadata.title fields as '<source title> to <target title>' "
            "(see SPEC.md §10)."
        ),
    )
    parser.add_argument(
        "--description",
        default=None,
        help=(
            "Override the mapping-collection provenance.mapping-description. "
            "If omitted, the description is auto-derived from the two catalogs' "
            "own metadata.title fields as "
            "'Mapping collection from <source title> to <target title>' "
            "(see SPEC.md §10)."
        ),
    )
    args = parser.parse_args()

    title = args.title or derive_mapping_title(args.source_original, args.target_original)
    description = args.description or derive_mapping_description(args.source_original, args.target_original)

    with open(args.aggregated, "r", encoding="utf-8") as f:
        aggregated = json.load(f)

    target_wc = load_working_catalog(args.target_working)

    groups = group_links(aggregated["controls"])

    maps = []
    for (relationship, target_ids), g in groups.items():
        avg_confidence = sum(g["confidences"]) / len(g["confidences"])
        avg_coverage = sum(g["coverages"]) / len(g["coverages"])
        rationale_text = " | ".join(sorted(g["rationales"]))[:2000]

        maps.append(
            {
                "uuid": str(uuid.uuid4()),
                "relationship": relationship.lower().replace("_", "-"),
                "sources": [{"type": "control", "id-ref": sid} for sid in sorted(g["sources"])],
                "targets": [{"type": "control", "id-ref": tid} for tid in target_ids],
                "confidence-score": {"percentage": round(avg_confidence, 3)},
                "coverage": {"target-coverage": round(avg_coverage, 3)},
                "props": [
                    {
                        "name": "mapping-rationale",
                        "value": rationale_text,
                        "ns": "https://example.com/custom/ns/oscal",
                    }
                ],
            }
        )

    mapping_entry = {
        "uuid": str(uuid.uuid4()),
        "source-resource": build_resource(args.source_original, args.source_href),
        "target-resource": build_resource(args.target_original, args.target_href),
        "maps": maps,
    }

    unmapped_ids = compute_target_gap(maps, target_wc)
    if unmapped_ids:
        mapping_entry["target-gap-summary"] = {
            "uuid": str(uuid.uuid4()),
            "unmapped-controls": [{"with-ids": unmapped_ids}],
        }

    mapping_collection = {
        "mapping-collection": {
            "uuid": str(uuid.uuid4()),
            "metadata": {
                "title": title,
                "last-modified": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "version": "1.0",
                "oscal-version": "1.2.1",
            },
            "provenance": {
                "method": "automation",
                "matching-rationale": "semantic",
                "status": "complete",
                "mapping-description": description,
            },
            "mappings": [mapping_entry],
        }
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(mapping_collection, f, indent=2, ensure_ascii=False)

    print(
        f"emit_oscal: {len(maps)} map entries, {len(unmapped_ids)} unmapped target units, "
        f"title={title!r} -> {args.output}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
