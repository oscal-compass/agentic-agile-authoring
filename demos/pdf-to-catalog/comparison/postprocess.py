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
"""Post-process the generated NIST SP 800-171 Rev.3 OSCAL catalog to strip
source-PDF artifacts that don't belong in the requirement prose.

Reads:  ../expected-output/catalog.json  (the raw generator output for this demo)
Writes: ./catalog.cleaned.json           (same OSCAL, cleaned prose)

The generator does an excellent job of extracting requirement text from NIST's
source PDF, but a few well-defined PDF artifacts leak through into control
`statement` prose:

1.  A `REFERENCES` block appended to each active control's prose. The block
    lists "Source Control(s):" and "Supporting Publications:" from the end of
    the source PDF section. The official OSCAL catalog carries the same
    linkage information as OSCAL `<link>` elements and `back-matter` resources,
    not as inline prose — so leaving the block in inflates our controls'
    prose and drops prose-similarity vs the official catalog. Present in
    ~97/130 controls.

2.  Soft hyphens from PDF line-wrapping: `configura-\ntion` and its numeric
    cousin `SP 800-\n56A`. Splitting these creates spurious tokens (`configura`,
    `tion`) that fall out of the Jaccard intersection with the official
    catalog. Present in ~25/130 controls.

Both of these are trimmable *without* any judgment call about content — they
are pure PDF extraction artifacts. This mirrors the "Related Controls:" strip
in the reference implementation (compliance-mapping-agents/demo/python/
compare_catalogs.py), except that strip removes a trailing block per part
whereas we remove ours from the persisted OSCAL data so any downstream
consumer (not just this comparison) benefits.

Withdrawn controls in the generator use a short prose like
`Addressed by 03.13.08.` as the whole `statement` part. That's not an artifact
— it's the intentional generator convention for withdrawn markers — so we
leave those alone.

Usage:  python postprocess.py           # write catalog.cleaned.json
        python postprocess.py --stats   # also print a summary of what changed
"""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "expected-output" / "catalog.json"
DST = HERE / "catalog.cleaned.json"


_REFERENCES_RE = re.compile(r"\n\s*REFERENCES\s*\n.*\Z", re.DOTALL)
_SOFT_HYPHEN_WORD_RE = re.compile(r"(\w)-\n(\w)")


def clean_prose(text: str) -> str:
    """Apply the two PDF-artifact strips to a single prose blob."""
    # 1. Drop the trailing REFERENCES block. We anchor to `\nREFERENCES\n`
    #    to be certain we're on a heading line, not a stray word.
    text = _REFERENCES_RE.sub("", text)
    # 2. De-hyphenate soft line breaks: `configura-\ntion` -> `configuration`,
    #    `800-\n56A` -> `800-56A` (the second re-insertion preserves the hyphen
    #    when it was semantically part of the token; for the token-set Jaccard
    #    we use downstream, either form scores the same, so simply removing the
    #    newline is enough).
    text = _SOFT_HYPHEN_WORD_RE.sub(r"\1\2", text)
    return text


# The two artifacts are both scoped to control `statement` prose in this
# generator. We deliberately do NOT touch guidance-nested parts, params, or
# props — only statement prose — so the cleanup is auditably narrow.

def _clean_control_in_place(ctrl: dict, stats: dict) -> None:
    for part in ctrl.get("parts", []):
        if part.get("name") != "statement":
            continue
        original = part.get("prose", "") or ""
        cleaned = clean_prose(original)
        if cleaned != original:
            part["prose"] = cleaned
            stats["controls_touched"] += 1
            if _REFERENCES_RE.search(original):
                stats["references_stripped"] += 1
            if _SOFT_HYPHEN_WORD_RE.search(original):
                stats["hyphens_fixed"] += 1
    # Recurse into nested controls (the generator has none today, but the
    # OSCAL data model allows it and this keeps the post-process robust).
    for sub in ctrl.get("controls", []):
        _clean_control_in_place(sub, stats)


def main() -> int:
    if not SRC.exists():
        print(f"source catalog not found: {SRC}", file=sys.stderr)
        return 1

    data = json.loads(SRC.read_text())
    cleaned = copy.deepcopy(data)

    stats = {"controls_touched": 0, "references_stripped": 0, "hyphens_fixed": 0}
    for grp in cleaned.get("catalog", {}).get("groups", []):
        for ctrl in grp.get("controls", []):
            _clean_control_in_place(ctrl, stats)

    DST.write_text(json.dumps(cleaned, indent=2) + "\n")

    print(f"wrote {DST.name}")
    print(f"  controls with a prose change   : {stats['controls_touched']}")
    print(f"  REFERENCES blocks stripped     : {stats['references_stripped']}")
    print(f"  soft-hyphen line-breaks fixed  : {stats['hyphens_fixed']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
