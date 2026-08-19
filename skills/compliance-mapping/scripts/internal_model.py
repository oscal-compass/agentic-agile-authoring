#!/usr/bin/env python3
"""Internal control representation shared by all pipeline stages.

Control {
  id, title, text,
  family, params, links
}

A "working catalog" JSON file (our internal format, distinct from OSCAL)
has the shape:

{
  "catalog_id": ...,
  "source_href": ...,
  "generation": 0,
  "controls": [Control, ...]
}
"""
import json


def new_working_catalog(catalog_id, source_href, controls, generation=0):
    return {
        "catalog_id": catalog_id,
        "source_href": source_href,
        "generation": generation,
        "controls": controls,
    }


def load_working_catalog(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_working_catalog(path, wc):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(wc, f, indent=2, ensure_ascii=False)


def make_control(id_, title, text, family=None, params=None, links=None):
    return {
        "id": id_,
        "title": title or "",
        "text": text,
        "family": family,
        "params": params or [],
        "links": links or [],
    }


def control_effective_text(control):
    """Text used for embedding: title + body."""
    title = control.get("title") or ""
    text = control.get("text") or ""
    if title and title not in text:
        return f"{title}\n{text}".strip()
    return text.strip()


def control_units(wc):
    """Returns the list of (unit_id, unit_text) to use for Blocking/Judge."""
    return [(c["id"], control_effective_text(c)) for c in wc["controls"]]


def unit_kind(wc, unit_id):
    del wc, unit_id
    return "control"


def make_atom(atom_id, text, derived_from=None):
    """Create an atom dictionary for decomposed control units."""
    return {
        "id": atom_id,
        "text": text,
        "derived_from": derived_from or [],
    }
