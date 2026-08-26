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
"""Build a valid OSCAL Plan of Action and Milestones (POA&M) with the trestle LIBRARY
(no MCP, no xlsx). Three modes (argparse subcommands):

  build                        (default) assessment/weakness list -> POA&M  [path A]
  from-component-definition    component-definition.json -> PRE-DEFINED POA&M  [path C, phase 1]
  link-assessment              pre-defined POA&M + assessment-results.json -> linked POA&M  [phase 2]

Run inside an ISOLATED environment (see setup-env.md) so trestle never pollutes global site-packages:

    uv run --with 'compliance-trestle>=3.0' python build_poam.py --input poam_input.json --output-dir out/
    .venv-poam/bin/python build_poam.py --input poam_input.json --output-dir out/   # no-uv fallback

(A bare `--input/--output-dir` with no subcommand still runs `build`, for back-compat.)

The unit of a POA&M is a WEAKNESS (poam-item), not a control. A weakness may carry zero or more
anchors (control-id / check-id / cve / source-identifier); control-id is OPTIONAL and the output is
schema-valid without it. Fill an anchor whenever the source (assessment-results / a control<->check
mapping / a component-definition.json / a catalog) provides one — see from-assessment.md.

── build (path A) input JSON (only weakness_name/weakness_description are required per item):

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
          # --- free-form pass-through (fill these from a customer's reference/sample) ---
          "extra_props": [                 # -> extra poam-item props, verbatim (any name/ns/value)
            {"name": "<any>", "ns": "<any-uri>", "value": "..."}
          ],
          # --- optional evidence/risk carried from the assessment result ---
          "observation": {"description": "...", "methods": ["TEST"], "title": "..."},
          # "risk" is written through to OSCAL AS-IS (validated by trestle) — put whatever shape a
          # customer's remediation reference calls for; only uuid/title/description/statement/status
          # default in when omitted. This is how an arbitrary remediation format gets filled in:
          "risk": {
            "status": "open", "deadline": "2026-12-31T00:00:00+00:00",
            "props": [{"name": "vendor-finding-id", "ns": "<uri>", "value": "F-42"}],
            "characterizations": [ ... ],   # e.g. likelihood/impact facets under any system uri
            "remediations": [               # THE remediation lives here (OSCAL `response`)
              {"lifecycle": "planned", "title": "...", "description": "...",
               "props": [ ... ], "origins": [ ... ], "required-assets": [ ... ],
               "tasks": [ {"type": "milestone", "title": "...", "timing": { ... },
                           "responsible-roles": [ ... ]} ]}
            ]
          }
        }
      ]
    }

If an item includes "observation" and/or "risk", a paired OSCAL Observation/Risk is created at the
POA&M top level and cross-linked from the poam-item (related-observations / related-risks). The
"risk" object (and "extra_props") are pass-through: their exact shape is whatever a mapping/reference
specifies, so a new scanner or platform remediation format needs no code change — see
from-scan-remediations.md.

── from-component-definition (path C, phase 1): --input component-definition.json
   [--remediations remediations.json] [--system-id ID] [--title T] [--version V]
   [--risk-style {generic|fedramp}]   (risk[] prop/namespace conventions; default generic)
   A validation component declares CHECKS and a service component declares RULES mapped to controls.
   Because each check is a testable assertion, the full weakness catalog is known BEFORE assessment.
   Emits a PRE-DEFINED POA&M: one poam-item per rule/check (each a potential weakness) with
   remediation authored up front, and local-definitions (components / inventory-items /
   assessment-assets) filled from the component-definition, plus one top-level Risk per item
   (rating/remediation/deadline from the consolidated props; status `open` until assessed). No
   observations/findings yet.
   Remediation/risk can come from two sources (props are the base; the file overrides per field):
     1. Consolidated on the component-definition itself — a validation rule-set's props carry
        Remediation_Plan / Risk_Rating / POC / Scheduled_Completion_Date / Weakness_Name /
        Weakness_Description, plus repeatable Milestone props ("<target_date>: <desc>"). Then the
        component-definition is the single source and no --remediations file is needed. (The POA&M
        ID is NOT carried here — it is assigned when the POA&M is built, closed within the POA&M.)
     2. remediations.json (optional) maps a rule/check id to the same fields, overriding the props:
       {"allowed-base-images": {"remediation_plan": "...", "risk_rating": "High",
                                 "poc": "...", "scheduled_completion_date": "2026-12-31",
                                 "milestones": [{"description": "...", "target_date": "..."}]},
        ...}

── link-assessment (phase 2): --poam predefined-poam.json --assessment assessment-results.json
   [--output-dir out/]
   Layers assessment results onto the pre-defined POA&M: each finding becomes a top-level Finding
   (+ its Observation, + an optional Risk) and is cross-linked to the EXISTING pre-defined poam-item
   for the same check (matched by the observation's/finding's check-id prop, else control-id). No new
   poam-items are created — keep-all: satisfied checks stay too, marked by a satisfied finding.

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
    AssessmentAssets, AssessmentPlatform, AssociatedRisk, Characterization, Facet, Finding,
    FindingTarget, ImplementedComponent, InventoryItem, Metadata, Observation, ObjectiveStatus,
    Origin, OriginActor, Property, RelatedObservation, Response, Risk, Status, SystemComponent,
    SystemId, UsesComponent,
)
from trestle.oscal.poam import (
    LocalDefinitions, PlanOfActionAndMilestones, PoamItem, RelatedFinding,
)

_NS = uuid.UUID("6f0c9d2e-0000-5000-a000-706f616d0000")
NS_PROP = "https://oscal-compass.github.io/compliance-authoring-skills/ns/poam"

# anchor props that give a weakness traceability (>=1 recommended)
_ANCHOR_KEYS = ("controls", "check_id", "cve", "source_identifier")

# OSCAL system-component `type` allows free tokens; we normalize the CD's type labels to these.
_COMPONENT_TYPES = {"service", "validation"}


def _u5(*parts: str) -> str:
    return str(uuid.uuid5(_NS, "|".join(parts)))


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _first_prop(item: dict, name: str) -> str | None:
    for p in item.get("props") or []:
        if p.get("name") == name:
            return p.get("value")
    return None


def _props_by_name(item: dict, name: str) -> list[str]:
    return [p.get("value") for p in item.get("props") or [] if p.get("name") == name]


def _prop(name: str, value: str) -> Property:
    return Property(name=name, value=value, ns=NS_PROP)


def _fill_task_uuids(tasks, seed: str) -> None:
    for j, t in enumerate(tasks or []):
        if isinstance(t, dict):
            t.setdefault("uuid", _u5(seed, "task", str(j)))
            _fill_task_uuids(t.get("tasks"), _u5(seed, str(j)))


def _ensure_risk_uuids(rk: dict, seed: str) -> None:
    """Backfill the uuid on a pass-through risk and its nested remediations/tasks/required-assets
    so a reference-shaped risk dict validates even when the caller omitted machine ids."""
    rk.setdefault("uuid", _u5("risk", seed))
    for i, rem in enumerate(rk.get("remediations") or []):
        if not isinstance(rem, dict):
            continue
        rem.setdefault("uuid", _u5("response", seed, str(i)))
        for k, ra in enumerate(rem.get("required-assets") or rem.get("required_assets") or []):
            if isinstance(ra, dict):
                ra.setdefault("uuid", _u5("asset", seed, str(i), str(k)))
        _fill_task_uuids(rem.get("tasks"), _u5("rem", seed, str(i)))
    for m, mf in enumerate(rk.get("mitigating-factors") or rk.get("mitigating_factors") or []):
        if isinstance(mf, dict):
            mf.setdefault("uuid", _u5("mf", seed, str(m)))


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
    # pass-through: any additional item props exactly as a reference/mapping specifies them
    # (free-form name / ns / value — OSCAL props are an extension point).
    for p in raw.get("extra_props") or []:
        props.append(Property.model_validate(p))

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

    # --- optional Risk (pass-through) ---
    # The `risk` object is written through to OSCAL as-is: whatever shape a reference/mapping gives
    # it — remediations[] (with lifecycle/props/origins/required-assets/tasks[timing]),
    # characterizations[], deadline, free-form props, mitigating-factors — is validated by trestle.
    # So a customer's remediation format is filled here by mapping onto this object, no code change.
    # Only light defaults (uuid, title, description, statement, status) fill in when omitted.
    rk = raw.get("risk")
    if rk:
        rk = dict(rk)  # don't mutate the caller's input
        rk.setdefault("title", f"Risk: {name}")
        rk.setdefault("description", desc)
        rk.setdefault("statement", rk.get("description") or desc)
        rk.setdefault("status", "open")
        _ensure_risk_uuids(rk, poam_id)
        risk_obj = Risk.model_validate(rk)
        risks.append(risk_obj)
        related_risks = [AssociatedRisk(risk_uuid=risk_obj.uuid)]

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


# ─────────────────────────────────────────────────────────────────────────────
# path C, phase 1 — from a component-definition -> a PRE-DEFINED POA&M
# ─────────────────────────────────────────────────────────────────────────────

# prop name (on a validation rule-set) -> remediation dict key consumed by _predefined_item
_REMEDIATION_PROPS = {
    "Remediation_Plan": "remediation_plan",
    "Risk_Rating": "risk_rating",
    "Severity": "severity",
    "Phase": "phase",
    "POC": "poc",
    "Scheduled_Completion_Date": "scheduled_completion_date",
    "Weakness_Name": "weakness_name",
    "Weakness_Description": "weakness_description",
    # NOTE: no POAM_Id here on purpose — the POA&M ID is assigned when the POA&M is built
    # (auto POAM-001…, or from a --remediations file), never carried on the component-definition.
}


def _remediation_from_slot(slot: dict) -> dict:
    """Pull consolidated remediation/risk out of one rule-set's props (path C, single-source).

    Milestones are carried as repeatable `Milestone` props, value `"<target_date>: <description>"`
    (the target date is optional — a value with no `": "` is treated as the description).
    """
    rem: dict = {}
    for prop_name, key in _REMEDIATION_PROPS.items():
        val = slot.get(prop_name)
        if val:
            rem[key] = val
    milestones: list[dict] = []
    for mval in slot.get("__milestones__") or []:
        mval = (mval or "").strip()
        if not mval:
            continue
        if ": " in mval:
            target, desc = mval.split(": ", 1)
            milestones.append({"target_date": target.strip(), "description": desc.strip()})
        else:
            milestones.append({"description": mval})
    if milestones:
        rem["milestones"] = milestones
    return rem


# deterministic actor for risks/remediations authored by this builder from the component-definition
_BUILDER_ACTOR = _u5("actor", "poam-authoring/build_poam.py")
_FEDRAMP_NS = "http://fedramp.gov/ns/oscal"  # OSCAL-recognized naming system (NamingSystemValidValues)
RISK_STYLES = ("generic", "fedramp")


def _parse_deadline(s: str):
    """`YYYY-MM-DD` (or full ISO) -> an aware UTC datetime, or None if unparseable."""
    if not s:
        return None
    try:
        d = datetime.date.fromisoformat(str(s)[:10])
        return datetime.datetime(d.year, d.month, d.day, tzinfo=datetime.timezone.utc)
    except ValueError:
        return None


def _milestones_to_tasks(milestones) -> list:
    """Map remediation milestones -> OSCAL response `tasks[]` (type=milestone; a `target_date`
    becomes the task's `on-date` timing)."""
    tasks = []
    for ms in milestones or []:
        d = (ms.get("description") or "").strip()
        if not d:
            continue
        t = {"type": "milestone", "title": d}
        end = _parse_deadline(ms.get("target_date"))
        if end:
            t["timing"] = {"on-date": {"date": end}}
        tasks.append(t)
    return tasks


def _predefined_risk(check_id: str, controls: list, name: str, desc: str, rem: dict,
                     style: str = "generic") -> Risk:
    """Build one top-level OSCAL Risk for a pre-defined weakness. Built as a dict + `model_validate`
    so the remediation is **pass-through / reference-driven**: whatever remediation shape the source
    (remediations.json entry or consolidated props) provides is written through and validated.

    Rating conventions depend on `style` (see from-component-definition.md):
    - **generic** (default) — rating in a plain `original-risk-rating` prop, lifecycle `planned`.
    - **fedramp** — rating as `likelihood` + `impact` facets under `http://fedramp.gov/ns/oscal`,
      lifecycle `recommendation`.

    Remediation source, in priority order:
    1. `rem["remediations"]` — a full OSCAL `response[]` (lifecycle/props/origins/required-assets/
       tasks[timing/responsible-roles]) written through verbatim (reference-driven).
    2. else `rem["remediation_plan"]` — one Response, with `rem["milestones"]` mapped to its `tasks[]`.
    A `rem["risk"]` dict can further extend/override the risk (except uuid/status, kept for linking).

    No control-id is placed on the risk (it's on the poam-item + finding). Status is `open` at
    pre-define time; link-assessment flips it to `closed` for a satisfied finding.
    """
    fedramp = style == "fedramp"
    rating = str(rem["risk_rating"]) if rem.get("risk_rating") else None
    rk: dict = {
        "uuid": _u5("risk", check_id),
        "title": f"Risk: {name}",
        "description": desc,
        "statement": (f"Until the check '{check_id}' is enforced, this weakness represents an open "
                      f"risk to the affected control(s): {', '.join(controls) or 'n/a'}."),
        "status": "open",
    }
    dl = _parse_deadline(rem.get("scheduled_completion_date"))
    if dl:
        rk["deadline"] = dl
    if fedramp and rating:
        rk["characterizations"] = [{
            "origin": {"actors": [{"type": "tool", "actor-uuid": _BUILDER_ACTOR}]},
            "facets": [{"name": n, "system": _FEDRAMP_NS, "value": rating.lower()}
                       for n in ("likelihood", "impact")],
        }]
    elif rating:  # generic (xlsx-style): a plain rating prop, no namespace, no characterization
        rk["props"] = [{"name": "original-risk-rating", "ns": NS_PROP, "value": rating}]

    if rem.get("remediations"):                 # 1) reference-supplied response(s), verbatim
        rk["remediations"] = rem["remediations"]
    elif rem.get("remediation_plan"):           # 2) build one response; milestones -> its tasks
        resp = {
            "lifecycle": "recommendation" if fedramp else "planned",
            "title": f"Remediation for {name}",
            "description": str(rem["remediation_plan"]),
            "origins": [{"actors": [{"type": "tool", "actor-uuid": _BUILDER_ACTOR}]}],
        }
        tasks = _milestones_to_tasks(rem.get("milestones"))
        if tasks:
            resp["tasks"] = tasks
        rk["remediations"] = [resp]

    if isinstance(rem.get("risk"), dict):       # optional full pass-through extend/override
        rk.update({k: v for k, v in rem["risk"].items() if k not in ("uuid", "status")})

    _ensure_risk_uuids(rk, check_id)
    return Risk.model_validate(rk)


def parse_component_definition(cd_doc: dict) -> tuple[list[dict], dict]:
    """Return (rules, components) from a trestle-style component-definition.json.

    Join every component on Rule_Id:
      - a SERVICE component's implemented-requirements give Rule_Id -> control-id(s)
        (control-id == "na" means "not a control mapping" and is skipped);
      - a VALIDATION component's props give Rule_Id -> Check_Id + validation-component title.
    Each returned rule dict = {rule_id, description, check_id, controls[], validation_components[],
    service_components[]}. `components` = {title: {"type", "description"}} for local-definitions.
    """
    cd = cd_doc.get("component-definition") or cd_doc
    rules: dict[str, dict] = {}
    components: dict[str, dict] = {}

    def rule(rid: str) -> dict:
        return rules.setdefault(rid, {
            "rule_id": rid, "description": "", "check_id": None,
            "controls": [], "validation_components": [], "service_components": [],
        })

    for comp in cd.get("components") or []:
        title = comp.get("title") or "component"
        ctype = (comp.get("type") or "").strip().lower()
        components[title] = {
            "type": ctype if ctype in _COMPONENT_TYPES else (ctype or "service"),
            "description": comp.get("description") or title,
            "rules": [],  # [{"rule_id", "check_id"}] this component declares (for local-def props)
        }
        # component-level props carry the rule_set details (Rule_Id/Description, Check_Id/Description)
        # and, optionally, consolidated remediation/risk (Remediation_Plan / Risk_Rating / POC /
        # Scheduled_Completion_Date / Weakness_Name / Weakness_Description / POAM_Id / Milestone).
        by_set: dict[str, dict] = {}
        for p in comp.get("props") or []:
            key = p.get("remarks") or "__flat__"
            slot = by_set.setdefault(key, {})
            name = p.get("name")
            if name == "Milestone":  # repeatable within a rule_set — collect, don't overwrite
                slot.setdefault("__milestones__", []).append(p.get("value"))
            else:
                slot[name] = p.get("value")
        for slot in by_set.values():
            rid = slot.get("Rule_Id")
            if not rid:
                continue
            pair = {"rule_id": rid, "check_id": slot.get("Check_Id")}
            if pair not in components[title]["rules"]:
                components[title]["rules"].append(pair)
            r = rule(rid)
            if slot.get("Rule_Description") and not r["description"]:
                r["description"] = slot["Rule_Description"]
            if slot.get("Check_Description"):
                r["description"] = slot["Check_Description"] or r["description"]
            if slot.get("Check_Id"):
                r["check_id"] = slot["Check_Id"]
            if ctype == "validation" and title not in r["validation_components"]:
                r["validation_components"].append(title)
            # consolidated remediation carried on the rule-set props (single-source path C).
            # Only keys that are present are set, so it merges cleanly with a --remediations file
            # (the file overrides these per field). First non-empty rule-set wins per key.
            rem_props = _remediation_from_slot(slot)
            if rem_props:
                existing = r.setdefault("remediation", {})
                for k, v in rem_props.items():
                    existing.setdefault(k, v)
        # implemented-requirements: Rule_Id -> control-id (service comps carry the real mapping)
        for ci in comp.get("control-implementations") or []:
            for ir in ci.get("implemented-requirements") or []:
                cid = (ir.get("control-id") or "").strip()
                for rid in _props_by_name(ir, "Rule_Id"):
                    r = rule(rid)
                    if ctype == "service" and title not in r["service_components"]:
                        r["service_components"].append(title)
                    if cid and cid.lower() != "na" and cid not in r["controls"]:
                        r["controls"].append(cid)

    # keep only rules that are actually checked (have a check_id or a validation component)
    checked = [r for r in rules.values() if r["check_id"] or r["validation_components"]]
    return (checked or list(rules.values())), components


def _local_definitions(components: dict, system_id: str | None) -> LocalDefinitions:
    sys_components: list[SystemComponent] = []
    inv_items: list[InventoryItem] = []
    platforms: list[AssessmentPlatform] = []
    for title, meta in components.items():
        cuuid = _u5("comp", title)
        # carry the rule-id / check-id this component declares (from the component-definition)
        cprops: list[Property] = []
        for pair in meta.get("rules") or []:
            if pair.get("rule_id"):
                cprops.append(_prop("rule-id", str(pair["rule_id"])))
            if pair.get("check_id"):
                cprops.append(_prop("check-id", str(pair["check_id"])))
        sys_components.append(SystemComponent(
            uuid=cuuid, type=meta["type"], title=title,
            description=meta["description"], status=Status(state="operational"),
            props=cprops or None,
        ))
        if meta["type"] == "service":
            inv_items.append(InventoryItem(
                uuid=_u5("inv", title),
                description=f"{title} — {meta['description']}",
                implemented_components=[ImplementedComponent(component_uuid=cuuid)],
            ))
        elif meta["type"] == "validation":
            platforms.append(AssessmentPlatform(
                uuid=_u5("ap", title), title=title,
                uses_components=[UsesComponent(component_uuid=cuuid)],
            ))
    ld = LocalDefinitions(components=sys_components or None)
    if inv_items:
        ld.inventory_items = inv_items
    if platforms:
        ld.assessment_assets = AssessmentAssets(assessment_platforms=platforms)
    return ld


def _predefined_item(rule: dict, index: int, remediations: dict, risks: list,
                     risk_style: str = "generic") -> PoamItem:
    rid = rule["rule_id"]
    check_id = rule.get("check_id") or rid
    # Base: remediation consolidated on the component-definition props (if any).
    # Overlay: an optional --remediations file entry, which wins per field.
    file_rem = remediations.get(check_id) or remediations.get(rid) or {}
    rem = {**(rule.get("remediation") or {}), **file_rem}

    poam_id = str(rem.get("poam_id") or f"POAM-{index + 1:03d}")
    name = (rem.get("weakness_name")
            or f"Potential weakness: {rule.get('description') or rid}").strip()
    desc = (rem.get("weakness_description") or rule.get("description")
            or f"The check '{check_id}' may fail, indicating this weakness.").strip()

    props: list[Property] = [_prop("poam-id", poam_id)]
    for cid in rule.get("controls") or []:
        props.append(_prop("control-id", str(cid)))
    props.append(_prop("check-id", str(check_id)))
    for vc in rule.get("validation_components") or []:
        props.append(_prop("validation-component", str(vc)))
    if rem.get("risk_rating"):
        props.append(_prop("risk-rating", str(rem["risk_rating"])))
    if rem.get("severity"):
        props.append(_prop("severity", str(rem["severity"])))
    if rem.get("phase"):
        props.append(_prop("phase", str(rem["phase"])))
    if rem.get("poc"):
        props.append(_prop("point-of-contact", str(rem["poc"])))
    if rem.get("scheduled_completion_date"):
        props.append(_prop("scheduled-completion-date", str(rem["scheduled_completion_date"])))
    for ms in rem.get("milestones") or []:
        d = (ms.get("description") or "").strip()
        if not d:
            continue
        target = ms.get("target_date")
        props.append(_prop("milestone", f"{d} (target: {target})" if target else d))

    # one top-level Risk per pre-defined weakness (the CD's rating/remediation/deadline live here);
    # the item references it via related-risks.
    risk = _predefined_risk(check_id, rule.get("controls") or [], name, desc, rem, risk_style)
    risks.append(risk)

    return PoamItem(
        uuid=_u5("item", check_id),
        title=name,
        description=desc,
        props=props,
        remarks=rem.get("remediation_plan") or None,
        related_risks=[AssociatedRisk(risk_uuid=risk.uuid)],
    )


def build_from_component_definition(cd_doc: dict, remediations: dict, meta: dict) -> PlanOfActionAndMilestones:
    rules, components = parse_component_definition(cd_doc)
    if not rules:
        raise ValueError("no rules/checks found in the component-definition — nothing to pre-define")
    title = meta.get("title") or "Pre-defined Plan of Action and Milestones"
    risk_style = meta.get("risk_style") or "generic"
    risks: list = []
    poam_items = [_predefined_item(r, i, remediations, risks, risk_style) for i, r in enumerate(rules)]
    poam = PlanOfActionAndMilestones(
        uuid=_u5("poam", title),
        metadata=Metadata(
            title=title, last_modified=_now(),
            version=str(meta.get("version") or "1.0"), oscal_version=OSCAL_VERSION,
        ),
        local_definitions=_local_definitions(components, meta.get("system_id")),
        poam_items=poam_items,
    )
    if risks:
        poam.risks = risks
    if meta.get("system_id"):
        poam.system_id = SystemId(id=str(meta["system_id"]))
    return poam


# ─────────────────────────────────────────────────────────────────────────────
# path C, phase 2 — layer assessment results onto a pre-defined POA&M
# ─────────────────────────────────────────────────────────────────────────────

def _index_items_by_anchor(poam: PlanOfActionAndMilestones) -> tuple[dict, dict]:
    """Map check-id -> poam-item and control-id -> poam-item for reference linking."""
    by_check: dict[str, PoamItem] = {}
    by_control: dict[str, PoamItem] = {}
    for it in poam.poam_items:
        for p in it.props or []:
            if p.name == "check-id":
                by_check[p.value] = it
            elif p.name == "control-id":
                by_control.setdefault(p.value, it)
    return by_check, by_control


# result prop values (on a subject) that count as a failing check
_FAIL_RESULTS = {"failure", "fail", "failed", "error", "not-satisfied", "noncompliant", "non-compliant"}

# observation props that name the rule/check an observation is about (link keys, in priority order)
_RULE_PROP_NAMES = ("check-id", "assessment-rule-id", "rule-id")


def _obs_rule_key(src: dict) -> str | None:
    for name in _RULE_PROP_NAMES:
        v = _first_prop(src, name)
        if v:
            return v
    return None


def _derive_state(src: dict) -> tuple[str, int, int]:
    """Derive a finding state from an observation's subject-level `result` props.

    Returns (state, n_fail, n_total). A rule is not-satisfied if ANY evaluated subject failed;
    satisfied if subjects were evaluated and none failed. With no per-subject result at all, we
    treat the observation's mere existence as a concern -> not-satisfied (conservative).
    """
    n_fail = n_total = 0
    for s in src.get("subjects") or []:
        for p in s.get("props") or []:
            if p.get("name") == "result":
                n_total += 1
                if str(p.get("value") or "").strip().lower() in _FAIL_RESULTS:
                    n_fail += 1
    if n_total == 0:
        return "not-satisfied", 0, 0
    return ("not-satisfied" if n_fail else "satisfied"), n_fail, n_total


def _carry_observation(src: dict, seen_obs: set, observations: list) -> str:
    """Faithfully carry an assessment observation (subjects + props + collected) into the POA&M.
    Returns the observation uuid used."""
    new_uuid = src.get("uuid") or _u5("obs", _obs_rule_key(src) or src.get("title") or "obs")
    if new_uuid in seen_obs:
        return new_uuid
    data = dict(src)
    data["uuid"] = new_uuid
    data.setdefault("description", data.get("title") or "observation")
    data.setdefault("methods", ["EXAMINE"])
    if not data.get("collected"):
        data["collected"] = _now().isoformat()
    try:
        obs = Observation.model_validate(data)  # preserves subjects, props, collected
    except Exception:  # noqa: BLE001 — fall back to a minimal valid observation
        obs = Observation(
            uuid=new_uuid, title=src.get("title") or f"Observation {new_uuid[:8]}",
            description=data["description"], methods=data["methods"],
            collected=src.get("collected") or _now(),
        )
    observations.append(obs)
    seen_obs.add(new_uuid)
    return new_uuid


def link_assessment(poam: PlanOfActionAndMilestones, ar_doc: dict) -> tuple[int, int]:
    """Layer an assessment-results.json onto the pre-defined POA&M in place.

    Two sources of truth are handled:
      1. Explicit `findings[]` (target status + related observations) — used as-is.
      2. Observation-only results (no findings) — a finding is DERIVED per observation from its
         subject-level `result` props (any failing subject -> not-satisfied), which is how real PVP
         output (Auditree/Kyverno/OCM) looks.
    Either way each Finding/Observation is cross-linked to the EXISTING pre-defined poam-item,
    matched by the observation's check-id / assessment-rule-id (control target-id fallback). No new
    poam-items are created. Returns (n_findings_linked, n_unmatched).
    """
    ar = ar_doc.get("assessment-results") or ar_doc
    by_check, by_control = _index_items_by_anchor(poam)
    observations = list(poam.observations or [])
    risks = list(poam.risks or [])
    findings_out = list(poam.findings or [])
    seen_obs = {o.uuid for o in observations}
    seen_risk = {r.uuid for r in risks}
    # pre-defined risks indexed for status sync (distinct name: the per-result loop below reuses
    # `risk_by_uuid` for the assessment's own risks).
    predef_risk_by_uuid = {r.uuid: r for r in risks}
    linked = 0
    unmatched = 0

    def _sync_risk(check_key, state):
        """Flip a pre-defined Risk's status from the assessed finding: satisfied -> closed."""
        if not check_key:
            return
        r = predef_risk_by_uuid.get(_u5("risk", check_key))
        if r is not None:
            r.status = "closed" if state == "satisfied" else "open"

    def _attach(item, f_uuid, rel_obs, rel_risks):
        if item is None:
            return False
        item.related_findings = (item.related_findings or []) + [RelatedFinding(finding_uuid=f_uuid)]
        if rel_obs:
            item.related_observations = (item.related_observations or []) + rel_obs
        if rel_risks:
            item.related_risks = (item.related_risks or []) + rel_risks
        return True

    for result in ar.get("results") or []:
        obs_by_uuid = {o.get("uuid"): o for o in result.get("observations") or []}
        risk_by_uuid = {r.get("uuid"): r for r in result.get("risks") or []}
        covered_obs: set = set()  # observation uuids already emitted via an explicit finding

        # ── 1) explicit findings ────────────────────────────────────────────────
        for finding in result.get("findings") or []:
            target = finding.get("target") or {}
            control_id = target.get("target-id")
            state = ((target.get("status") or {}).get("state")) or "not-satisfied"

            rule_key = None
            related_observations = []
            for ro in finding.get("related-observations") or []:
                ou = ro.get("observation-uuid")
                src = obs_by_uuid.get(ou)
                if not src:
                    continue
                rule_key = rule_key or _obs_rule_key(src)
                new_uuid = _carry_observation(src, seen_obs, observations)
                covered_obs.add(ou)
                related_observations.append(RelatedObservation(observation_uuid=new_uuid))

            item = (by_check.get(rule_key) if rule_key else None) or by_control.get(control_id)

            related_risks = []
            for rr in finding.get("related-risks") or []:
                ru = rr.get("risk-uuid")
                src = risk_by_uuid.get(ru)
                if src and ru not in seen_risk:
                    risks.append(Risk(
                        uuid=ru, title=src.get("title") or "Risk",
                        description=src.get("description") or "",
                        statement=src.get("statement") or "See linked finding.",
                        status=src.get("status") or "open",
                    ))
                    seen_risk.add(ru)
                if ru:
                    related_risks.append(AssociatedRisk(risk_uuid=ru))

            f_uuid = finding.get("uuid") or _u5("finding", rule_key or control_id or str(linked))
            findings_out.append(Finding(
                uuid=f_uuid,
                title=finding.get("title") or f"Finding for {rule_key or control_id}",
                description=finding.get("description") or "",
                target=FindingTarget(
                    type="objective-id",
                    target_id=control_id or (item and _first_prop_obj(item, "control-id")) or "na",
                    status=ObjectiveStatus(state=state),
                ),
                related_observations=related_observations or None,
                related_risks=related_risks or None,
            ))
            if _attach(item, f_uuid, related_observations, related_risks):
                linked += 1
                _sync_risk(rule_key, state)
            else:
                unmatched += 1
                sys.stderr.write(
                    f"warning: finding {f_uuid[:8]} (rule={rule_key!r}, control={control_id!r}) "
                    "matched no pre-defined poam-item; recorded anyway.\n")

        # ── 2) observation-only results → derive a finding per rule-keyed observation ──
        for src in result.get("observations") or []:
            if src.get("uuid") in covered_obs:
                continue
            rule_key = _obs_rule_key(src)
            if not rule_key:
                continue  # not tied to a rule/check — nothing to reference
            item = by_check.get(rule_key) or by_control.get(rule_key)
            state, n_fail, n_total = _derive_state(src)
            new_uuid = _carry_observation(src, seen_obs, observations)
            control_id = item and _first_prop_obj(item, "control-id")
            if state == "not-satisfied":
                desc = (f"Check '{rule_key}' failed for {n_fail} of {n_total} evaluated subject(s)."
                        if n_total else f"Check '{rule_key}' produced an observation without a pass result.")
            else:
                desc = f"Check '{rule_key}' passed for all {n_total} evaluated subject(s)."
            f_uuid = _u5("finding", rule_key)
            findings_out.append(Finding(
                uuid=f_uuid,
                title=f"{rule_key}: {'not satisfied' if state == 'not-satisfied' else 'satisfied'}",
                description=desc,
                target=FindingTarget(
                    type="objective-id", target_id=control_id or "na",
                    status=ObjectiveStatus(state=state),
                ),
                related_observations=[RelatedObservation(observation_uuid=new_uuid)],
            ))
            if _attach(item, f_uuid, [RelatedObservation(observation_uuid=new_uuid)], None):
                linked += 1
                _sync_risk(rule_key, state)
            else:
                unmatched += 1
                sys.stderr.write(
                    f"warning: observation for rule {rule_key!r} matched no pre-defined poam-item; "
                    "its derived finding/observation are still recorded.\n")

    poam.observations = observations or None
    poam.risks = risks or None
    poam.findings = findings_out or None
    return linked, unmatched


def _first_prop_obj(item: PoamItem, name: str) -> str | None:
    for p in item.props or []:
        if p.name == name:
            return p.value
    return None


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _write(poam: PlanOfActionAndMilestones, output_dir: str) -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "plan-of-action-and-milestones.json"
    poam.oscal_write(out)
    PlanOfActionAndMilestones.oscal_read(out)  # round-trip = schema validation
    return out


def _cmd_build(args: argparse.Namespace) -> int:
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if args.title:
        data["title"] = args.title
    if args.version:
        data["version"] = args.version
    poam = build_poam(data)
    out = _write(poam, args.output_dir)
    print(
        f"OK: wrote {out} ({len(poam.poam_items)} poam-item(s), "
        f"{len(poam.observations or [])} observation(s), {len(poam.risks or [])} risk(s)); "
        "re-read validates."
    )
    print("Next: run `trestle validate -t plan-of-action-and-milestones` for authoritative "
          "validation (see build-poam.md).")
    return 0


def _cmd_from_cd(args: argparse.Namespace) -> int:
    cd_doc = json.loads(Path(args.input).read_text(encoding="utf-8"))
    remediations = {}
    if args.remediations:
        remediations = json.loads(Path(args.remediations).read_text(encoding="utf-8"))
    poam = build_from_component_definition(cd_doc, remediations, {
        "title": args.title, "version": args.version, "system_id": args.system_id,
        "risk_style": args.risk_style,
    })
    out = _write(poam, args.output_dir)
    print(
        f"OK: wrote pre-defined {out} ({len(poam.poam_items)} poam-item(s) from rules/checks, "
        f"{len(poam.risks or [])} {args.risk_style} risk(s), local-definitions filled); re-read validates."
    )
    print("Next: layer an assessment with `build_poam.py link-assessment` (see link-assessment.md).")
    return 0


def _cmd_link(args: argparse.Namespace) -> int:
    poam = PlanOfActionAndMilestones.oscal_read(Path(args.poam))
    ar_doc = json.loads(Path(args.assessment).read_text(encoding="utf-8"))
    linked, unmatched = link_assessment(poam, ar_doc)
    out = _write(poam, args.output_dir)
    def _state(f: Finding) -> str:
        st = f.target.status.state if (f.target and f.target.status) else None
        return getattr(st, "value", st)

    n_open = sum(1 for f in (poam.findings or []) if _state(f) == "not-satisfied")
    def _rstatus(r):
        s = r.status
        while hasattr(s, "root"):  # RiskStatus.root -> TokenDatatype.root -> str
            s = s.root
        return str(s)
    n_risk_closed = sum(1 for r in (poam.risks or []) if _rstatus(r) == "closed")
    print(
        f"OK: wrote linked {out} ({len(poam.poam_items)} poam-item(s), "
        f"{len(poam.findings or [])} finding(s): {n_open} open / "
        f"{len(poam.findings or []) - n_open} satisfied; "
        f"{len(poam.risks or [])} risk(s): {len(poam.risks or []) - n_risk_closed} open / "
        f"{n_risk_closed} closed; {linked} linked, {unmatched} unmatched); re-read validates."
    )
    print("Next: run `trestle validate -t plan-of-action-and-milestones` for authoritative "
          "validation (see build-poam.md).")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build an OSCAL POA&M with the trestle library.")
    sub = ap.add_subparsers(dest="command")

    b = sub.add_parser("build", help="assessment / weakness-list JSON -> POA&M (path A, default)")
    b.add_argument("--input", required=True, help="path to the POA&M input JSON")
    b.add_argument("--output-dir", required=True, help="directory to write the POA&M JSON into")
    b.add_argument("--title", help="override the POA&M title")
    b.add_argument("--version", help="override the POA&M version")
    b.set_defaults(func=_cmd_build)

    c = sub.add_parser("from-component-definition",
                       help="component-definition.json -> pre-defined POA&M (path C, phase 1)")
    c.add_argument("--input", required=True, help="path to component-definition.json")
    c.add_argument("--remediations", help="optional JSON mapping rule/check id -> remediation fields")
    c.add_argument("--output-dir", required=True, help="directory to write the POA&M JSON into")
    c.add_argument("--system-id", help="system id for the POA&M / inventory")
    c.add_argument("--title", help="POA&M title")
    c.add_argument("--version", help="POA&M version")
    c.add_argument("--risk-style", choices=RISK_STYLES, default="generic",
                   help="prop/namespace conventions for the generated risks[]: 'generic' (default; "
                        "mirrors trestle's xlsx-to-oscal-poam output) or 'fedramp' (FedRAMP ns + "
                        "impacted-control-id + likelihood/impact facets)")
    c.set_defaults(func=_cmd_from_cd)

    lk = sub.add_parser("link-assessment",
                        help="pre-defined POA&M + assessment-results.json -> linked POA&M (phase 2)")
    lk.add_argument("--poam", required=True, help="path to the pre-defined POA&M JSON")
    lk.add_argument("--assessment", required=True, help="path to assessment-results.json")
    lk.add_argument("--output-dir", required=True, help="directory to write the linked POA&M into")
    lk.set_defaults(func=_cmd_link)

    # back-compat: bare `--input/--output-dir` (no subcommand) still runs `build`.
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0].startswith("-"):
        argv = ["build"] + argv

    args = ap.parse_args(argv)
    if not getattr(args, "command", None):
        ap.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(2)
