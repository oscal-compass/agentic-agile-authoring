#!/usr/bin/env python3
"""Stage 1: Ingest / Normalize.

Parses an OSCAL Catalog JSON file into the internal "working catalog"
representation (see internal_model.py). No LLM involved.

Usage:
    python ingest_normalize.py <oscal_catalog.json> <output_working_catalog.json>
"""
import argparse
import sys

from internal_model import new_working_catalog, make_control, save_working_catalog


def collect_prose(part):
    """Recursively concatenate prose text from an OSCAL part tree."""
    chunks = []
    prose = part.get("prose")
    if prose:
        chunks.append(prose.strip())
    for sub in part.get("parts", []):
        chunks.append(collect_prose(sub))
    return "\n".join(c for c in chunks if c)


def control_text(oscal_control):
    """Build the flattened text body: statement + guidance-relevant parts."""
    chunks = []
    for part in oscal_control.get("parts", []):
        name = part.get("name", "")
        if name in ("statement", "guidance", "item"):
            text = collect_prose(part)
            if text:
                chunks.append(text)
    return "\n".join(chunks).strip()


def flatten_controls(oscal_controls, family=None, out=None):
    """Recursively flatten OSCAL controls (including nested enhancements)."""
    if out is None:
        out = []
    for oc in oscal_controls or []:
        cid = oc["id"]
        title = oc.get("title", "")
        text = control_text(oc)
        params = [p.get("id") for p in oc.get("params", []) if p.get("id")]
        links = [
            {"href": l.get("href"), "rel": l.get("rel")}
            for l in oc.get("links", [])
        ]
        out.append(make_control(cid, title, text, family=family, params=params, links=links))
        # OSCAL nests control enhancements under the same "controls" key
        if oc.get("controls"):
            flatten_controls(oc["controls"], family=family, out=out)
    return out


def flatten_groups(groups, out=None):
    if out is None:
        out = []
    for g in groups or []:
        family = g.get("id")
        out.extend(flatten_controls(g.get("controls", []), family=family))
        if g.get("groups"):
            flatten_groups(g["groups"], out=out)
    return out


def ingest(oscal_path):
    import json

    with open(oscal_path, "r", encoding="utf-8") as f:
        doc = json.load(f)

    catalog = doc.get("catalog")
    if catalog is None:
        raise ValueError(f"{oscal_path} does not contain a top-level 'catalog' key")

    catalog_id = catalog.get("uuid", oscal_path)
    controls = flatten_groups(catalog.get("groups", []))
    # top-level controls not inside any group
    controls.extend(flatten_controls(catalog.get("controls", [])))

    controls = [c for c in controls if c["text"] or c["title"]]

    wc = new_working_catalog(catalog_id, oscal_path, controls)
    return wc


def main():
    parser = argparse.ArgumentParser(description="Ingest an OSCAL catalog into internal working format")
    parser.add_argument("oscal_catalog", help="Path to OSCAL catalog JSON")
    parser.add_argument("output", help="Path to write working catalog JSON")
    args = parser.parse_args()

    wc = ingest(args.oscal_catalog)
    save_working_catalog(args.output, wc)
    print(
        f"Ingested {len(wc['controls'])} controls from {args.oscal_catalog} -> {args.output}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
