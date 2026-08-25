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

Run inside an ISOLATED environment (see setup-env.md) so trestle never pollutes global site-packages:

    uv run --with 'compliance-trestle>=3.0' python build_poam.py --input poam_input.json --output-dir out/
    .venv-poam/bin/python build_poam.py --input poam_input.json --output-dir out/   # no-uv fallback

The unit of a POA&M is a WEAKNESS (poam-item), not a control. A weakness may carry zero or more
anchors (control-id / check-id / cve / source-identifier); control-id is OPTIONAL and the output is
schema-valid without it. Fill an anchor whenever the source (assessment-results / a control<->check
mapping / a component-definition.json / a catalog) provides one — see from-assessment.md.

Input JSON (only weakness_name/weakness_description are required per item):

    {
      "title": "System X POA&M",          # optional
      "version": "1.0",                    # optional
      "system_id": "system-x",             # optional
      "items": [
        {
          "poam_id": "POAM-001",           # optional; stable id + a prop
          "weakness_name": "...",          # REQUIRED
          "weakness_description": "...",    # REQUIRED
          # --- anchors (all optional; >=1 recommended for traceability) ---
          "controls": ["ac-2", "ia-2"],    # -> control-id props (from assessment/mapping/comp-def)
          "check_id": "QGUARD-CHECK-...",  # -> check-id prop (scanner rule id)
          "cve": "CVE-2025-1234",          # -> cve prop
          "source_identifier": "...",      # -> source-identifier prop (detector's weakness id)
          "affected_files": ["a.py"],      # -> affected-files props (one per file)
          # --- other props (optional) ---
          "severity": "critical",          # -> severity prop (scanner style)
          "risk_rating": "High",           # -> risk-rating prop (control-assessment style)
          "phase": "phase-1-immediate",    # -> phase prop
          "poc": "Security Team",          # -> point-of-contact prop
          "scheduled_completion_date": "2026-12-31",  # -> scheduled-completion-date prop
          "milestones": [{"description": "...", "target_date": "2026-10-01"}],  # -> milestone props
          "remediation_plan": "...",       # -> poam-item remarks
          # --- optional evidence/risk carried from the assessment result ---
          "observation": {"description": "...", "methods": ["TEST"], "title": "..."},
          "risk": {"statement": "...", "status": "open", "title": "...", "description": "..."}
        }
      ]
    }

If an item includes "observation" and/or "risk", a paired OSCAL Observation/Risk is created at the
POA&M top level and cross-linked from the poam-item (related-observations / related-risks).
Everything is schema-validated by round-tripping through oscal_read before exit.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
import uuid
from pathlib import Path

from trestle.oscal import OSCAL_VERSION
from trestle.oscal.common import (
    AssociatedRisk, Metadata, Observation, Property, RelatedObservation, Risk, SystemId,
)
from trestle.oscal.poam import PlanOfActionAndMilestones, PoamItem

_NS = uuid.UUID("6f0c9d2e-0000-5000-a000-706f616d0000")
NS_PROP = "https://oscal-compass.github.io/compliance-authoring-skills/ns/poam"

# anchor props that give a weakness traceability (>=1 recommended)
_ANCHOR_KEYS = ("controls", "check_id", "cve", "source_identifier")


def _u5(*parts: str) -> str:
    return str(uuid.uuid5(_NS, "|".join(parts)))


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _prop(name: str, value: str) -> Property:
    return Property(name=name, value=value, ns=NS_PROP)


def build_item(raw: dict, index: int, observations: list, risks: list) -> PoamItem:
    name = (raw.get("weakness_name") or "").strip()
    desc = (raw.get("weakness_description") or "").strip()
    if not name or not desc:
        raise ValueError(
            f"item #{index}: 'weakness_name' and 'weakness_description' are both required"
        )

    poam_id = str(raw.get("poam_id") or f"POAM-{index + 1:03d}")
    props: list[Property] = [_prop("poam-id", poam_id)]

    # --- anchors + other props (only what's present) ---
    for cid in raw.get("controls") or []:
        props.append(_prop("control-id", str(cid)))
    if raw.get("check_id"):
        props.append(_prop("check-id", str(raw["check_id"])))
    if raw.get("cve"):
        props.append(_prop("cve", str(raw["cve"])))
    if raw.get("source_identifier"):
        props.append(_prop("source-identifier", str(raw["source_identifier"])))
    for fpath in raw.get("affected_files") or []:
        props.append(_prop("affected-files", str(fpath)))
    if raw.get("severity"):
        props.append(_prop("severity", str(raw["severity"])))
    if raw.get("risk_rating"):
        props.append(_prop("risk-rating", str(raw["risk_rating"])))
    if raw.get("phase"):
        props.append(_prop("phase", str(raw["phase"])))
    if raw.get("poc"):
        props.append(_prop("point-of-contact", str(raw["poc"])))
    if raw.get("scheduled_completion_date"):
        props.append(_prop("scheduled-completion-date", str(raw["scheduled_completion_date"])))
    for ms in raw.get("milestones") or []:
        d = (ms.get("description") or "").strip()
        if not d:
            continue
        target = ms.get("target_date")
        props.append(_prop("milestone", f"{d} (target: {target})" if target else d))

    related_observations = None
    related_risks = None

    # --- optional Observation carried from the assessment result ---
    obs = raw.get("observation")
    if obs:
        obs_uuid = _u5("obs", poam_id)
        observations.append(Observation(
            uuid=obs_uuid,
            title=obs.get("title") or f"Observation for {poam_id}",
            description=(obs.get("description") or desc),
            methods=obs.get("methods") or ["EXAMINE"],
            collected=_now(),
        ))
        related_observations = [RelatedObservation(observation_uuid=obs_uuid)]

    # --- optional Risk carried from the assessment result ---
    rk = raw.get("risk")
    if rk:
        risk_uuid = _u5("risk", poam_id)
        risks.append(Risk(
            uuid=risk_uuid,
            title=rk.get("title") or f"Risk: {name}",
            description=rk.get("description") or desc,
            statement=rk.get("statement") or f"The system does not satisfy the requirement: {name}.",
            status=rk.get("status") or "open",
        ))
        related_risks = [AssociatedRisk(risk_uuid=risk_uuid)]

    if not any(raw.get(k) for k in _ANCHOR_KEYS):
        sys.stderr.write(
            f"warning: item {poam_id} ('{name}') has no anchor "
            "(control-id / check-id / cve / source-identifier) — POA&M is valid but the weakness "
            "is not traceable to a control or check. Fill one if a source provides it.\n"
        )

    return PoamItem(
        uuid=_u5("item", poam_id, name),
        title=name,
        description=desc,
        props=props,
        remarks=raw.get("remediation_plan") or None,
        related_observations=related_observations,
        related_risks=related_risks,
    )


def build_poam(data: dict) -> PlanOfActionAndMilestones:
    items = data.get("items") or []
    if not items:
        raise ValueError(
            "no 'items' to author — a POA&M needs at least one open weakness "
            "(if the assessment has no failed findings, no POA&M is required)"
        )
    title = data.get("title") or "Plan of Action and Milestones"
    observations: list = []
    risks: list = []
    poam_items = [build_item(it, i, observations, risks) for i, it in enumerate(items)]

    poam = PlanOfActionAndMilestones(
        uuid=_u5("poam", title),
        metadata=Metadata(
            title=title,
            last_modified=_now(),
            version=str(data.get("version") or "1.0"),
            oscal_version=OSCAL_VERSION,
        ),
        poam_items=poam_items,
    )
    if data.get("system_id"):
        poam.system_id = SystemId(id=str(data["system_id"]))
    if observations:
        poam.observations = observations
    if risks:
        poam.risks = risks
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
    PlanOfActionAndMilestones.oscal_read(out)  # round-trip = schema validation

    n_obs = len(poam.observations or [])
    n_risk = len(poam.risks or [])
    print(
        f"OK: wrote {out} ({len(poam.poam_items)} poam-item(s), "
        f"{n_obs} observation(s), {n_risk} risk(s)); re-read validates."
    )
    print("Next: run `trestle validate -t plan-of-action-and-milestones` for authoritative "
          "validation (see build-poam.md).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(2)
