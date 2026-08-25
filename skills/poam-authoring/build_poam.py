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

# /// script
# requires-python = ">=3.10"
# dependencies = ["compliance-trestle>=3.0"]
# ///
"""Build a valid OSCAL Plan of Action and Milestones (POA&M) from a simple JSON input,
using the trestle LIBRARY (no MCP, no xlsx).

Run this inside an ISOLATED environment so trestle never pollutes the global site-packages
(see setup-env.md). Two supported ways:

    uv run --with 'compliance-trestle>=3.0' python build_poam.py --input poam_input.json --output-dir out/
    # or, without uv, from a venv that has compliance-trestle installed:
    .venv-poam/bin/python build_poam.py --input poam_input.json --output-dir out/

Input JSON shape (all item fields except weakness_name/weakness_description are optional):

    {
      "title": "System X POA&M",          # optional (default: "Plan of Action and Milestones")
      "version": "1.0",                    # optional (default: "1.0")
      "system_id": "system-x",             # optional
      "items": [
        {
          "poam_id": "POAM-001",           # optional; used for a stable id + a prop
          "weakness_name": "MFA not enforced on admin accounts",     # REQUIRED
          "weakness_description": "Admin accounts can log in without MFA.",  # REQUIRED
          "controls": ["ac-2", "ia-2"],    # optional (from the assessment finding)
          "remediation_plan": "Enforce MFA via IdP policy.",         # optional -> remarks
          "milestones": [                   # optional
            {"description": "Enable MFA org-wide", "target_date": "2026-10-01"}
          ],
          "poc": "Security Team",          # optional
          "scheduled_completion_date": "2026-12-31",  # optional
          "risk_rating": "High"            # optional
        }
      ]
    }

Everything is attached to the poam-item as props/remarks so the output is always schema-valid.
The script writes <output-dir>/plan-of-action-and-milestones.json and round-trips it through
oscal_read (pydantic schema validation) before exiting.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
import uuid
from pathlib import Path

from trestle.oscal import OSCAL_VERSION
from trestle.oscal.common import Metadata, Property, SystemId
from trestle.oscal.poam import PlanOfActionAndMilestones, PoamItem

# Stable namespace so re-running on the same input yields the same UUIDs (deterministic uuid5).
_NS = uuid.UUID("6f0c9d2e-0000-5000-a000-706f616d0000")
NS_PROP = "https://oscal-compass.github.io/compliance-authoring-skills/ns/poam"


def _u5(*parts: str) -> str:
    return str(uuid.uuid5(_NS, "|".join(parts)))


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _prop(name: str, value: str) -> Property:
    return Property(name=name, value=value, ns=NS_PROP)


def build_item(raw: dict, index: int) -> PoamItem:
    name = (raw.get("weakness_name") or "").strip()
    desc = (raw.get("weakness_description") or "").strip()
    if not name or not desc:
        raise ValueError(
            f"item #{index}: 'weakness_name' and 'weakness_description' are both required"
        )

    poam_id = str(raw.get("poam_id") or f"POAM-{index + 1:03d}")
    props: list[Property] = [_prop("poam-id", poam_id)]

    for cid in raw.get("controls") or []:
        props.append(_prop("control-id", str(cid)))
    if raw.get("poc"):
        props.append(_prop("point-of-contact", str(raw["poc"])))
    if raw.get("risk_rating"):
        props.append(_prop("risk-rating", str(raw["risk_rating"])))
    if raw.get("scheduled_completion_date"):
        props.append(
            _prop("scheduled-completion-date", str(raw["scheduled_completion_date"]))
        )
    for ms in raw.get("milestones") or []:
        d = (ms.get("description") or "").strip()
        if not d:
            continue
        target = ms.get("target_date")
        props.append(_prop("milestone", f"{d} (target: {target})" if target else d))

    remarks = raw.get("remediation_plan") or None

    return PoamItem(
        uuid=_u5("item", poam_id, name),
        title=name,
        description=desc,
        props=props,
        remarks=remarks,
    )


def build_poam(data: dict) -> PlanOfActionAndMilestones:
    items = data.get("items") or []
    if not items:
        raise ValueError(
            "no 'items' to author — a POA&M needs at least one open weakness "
            "(if the assessment has no failed findings, no POA&M is required)"
        )
    title = data.get("title") or "Plan of Action and Milestones"
    poam = PlanOfActionAndMilestones(
        uuid=_u5("poam", title),
        metadata=Metadata(
            title=title,
            last_modified=_now(),
            version=str(data.get("version") or "1.0"),
            oscal_version=OSCAL_VERSION,
        ),
        poam_items=[build_item(it, i) for i, it in enumerate(items)],
    )
    if data.get("system_id"):
        poam.system_id = SystemId(id=str(data["system_id"]))
    return poam


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build an OSCAL POA&M from JSON (trestle library).")
    ap.add_argument("--input", required=True, help="path to the POA&M input JSON")
    ap.add_argument("--output-dir", required=True, help="directory to write the POA&M JSON into")
    ap.add_argument("--title", help="override the POA&M title")
    ap.add_argument("--version", help="override the POA&M version")
    args = ap.parse_args(argv)

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if args.title:
        data["title"] = args.title
    if args.version:
        data["version"] = args.version

    poam = build_poam(data)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "plan-of-action-and-milestones.json"
    poam.oscal_write(out)

    # Round-trip = pydantic schema validation. Raises if the model is not schema-valid.
    PlanOfActionAndMilestones.oscal_read(out)

    print(f"OK: wrote {out} ({len(poam.poam_items)} poam-item(s)); re-read validates.")
    print("Next: run `trestle validate -t plan-of-action-and-milestones` in a trestle workspace")
    print("for authoritative validation (see build-poam.md).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(2)
