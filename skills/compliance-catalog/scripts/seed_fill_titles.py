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

"""Fill empty control / group titles in a newly generated OSCAL Catalog
from the corresponding titles in a *seed catalog* (a previous generation
of the same framework).

Rationale
=========

When a catalog is regenerated from a new PDF while inheriting IDs from a
seed catalog (see ``build_author_prompt.py`` --seed-catalog), the
extractor sometimes cannot capture the section title from the PDF body
— the title may live only in a running header or a TOC that the
extractor has stripped, so the resulting control ends up with an empty
``title``.  OSCAL Rule 15 flags this as fatal, and the Phase 4 fix loop
then spends ~10 minutes teaching the extractor to catch those cases
one-by-one.

Because the seed catalog *already* holds the correct title for every
control ID (that's why we chose it as the seed in the first place),
the pragmatic recovery is to borrow the seed's title verbatim whenever
the new catalog has that control's ID but an empty title.  This
targets a real failure mode (title-only mismatch) without touching
prose, which must still come from the new PDF per the
anti-hallucination principle.

Only ``title`` is copied.  ``prose`` is never copied — an empty prose
is still surfaced as a validation error so a human can decide whether
the section was legitimately removed from the new PDF (rare) or the
extractor missed it (common; fix loop still needed).

Behaviour
=========

Reads a target ``catalog.json`` and a seed ``catalog.json``.  For every
group and control that shares an ID between the two, if the target's
title is empty but the seed's is non-empty, copy the seed's title into
the target and write the result back in place (unless ``--output`` is
given).

Prints a short report to stdout:

  seed_fill_titles: filled 32 control title(s), 0 group title(s)
  seed_fill_titles: no missing group titles

Exit code is 0 if the file was mutated OR if there was nothing to fill.
Exit code 2 if either file is missing / not JSON.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _index_seed(seed_catalog: dict) -> tuple[dict[str, str], dict[str, str]]:
    """Return (group_id -> title, control_id -> title) for lookup."""
    groups: dict[str, str] = {}
    controls: dict[str, str] = {}
    root = seed_catalog.get("catalog", seed_catalog)
    for g in root.get("groups") or []:
        gid = g.get("id")
        gtitle = (g.get("title") or "").strip()
        if gid and gtitle:
            groups[gid] = gtitle
        for c in g.get("controls") or []:
            cid = c.get("id")
            ctitle = (c.get("title") or "").strip()
            if cid and ctitle:
                controls[cid] = ctitle
    return groups, controls


def _fill(target: dict, group_titles: dict[str, str],
          control_titles: dict[str, str]) -> tuple[int, int]:
    """Mutate ``target`` in place.  Returns (controls_filled, groups_filled)."""
    controls_filled = 0
    groups_filled = 0
    root = target.get("catalog", target)
    for g in root.get("groups") or []:
        gid = g.get("id")
        gtitle = (g.get("title") or "").strip()
        if not gtitle and gid in group_titles:
            g["title"] = group_titles[gid]
            groups_filled += 1
        for c in g.get("controls") or []:
            cid = c.get("id")
            ctitle = (c.get("title") or "").strip()
            if not ctitle and cid in control_titles:
                c["title"] = control_titles[cid]
                controls_filled += 1
    return controls_filled, groups_filled


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target_catalog", type=Path,
                        help="Path to the freshly generated catalog.json to fix")
    parser.add_argument("seed_catalog", type=Path,
                        help="Path to the seed catalog that supplies titles")
    parser.add_argument("--output", type=Path, default=None,
                        help="Write to this path instead of overwriting the target")
    args = parser.parse_args()

    if not args.target_catalog.is_file():
        print(f"seed_fill_titles: ERROR: target not found: {args.target_catalog}",
              file=sys.stderr)
        return 2
    if not args.seed_catalog.is_file():
        print(f"seed_fill_titles: ERROR: seed not found: {args.seed_catalog}",
              file=sys.stderr)
        return 2

    try:
        target = json.loads(args.target_catalog.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"seed_fill_titles: ERROR: target JSON parse failed: {e}",
              file=sys.stderr)
        return 2
    try:
        seed = json.loads(args.seed_catalog.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"seed_fill_titles: ERROR: seed JSON parse failed: {e}",
              file=sys.stderr)
        return 2

    group_titles, control_titles = _index_seed(seed)
    c_filled, g_filled = _fill(target, group_titles, control_titles)

    out_path = args.output or args.target_catalog
    out_path.write_text(
        json.dumps(target, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"seed_fill_titles: filled {c_filled} control title(s), "
          f"{g_filled} group title(s)")
    if c_filled == 0 and g_filled == 0:
        print("seed_fill_titles: nothing to fill (all titles already present)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
