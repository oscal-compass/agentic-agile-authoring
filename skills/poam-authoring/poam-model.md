# The OSCAL POA&M model + the builder's input JSON

## What a POA&M is

An OSCAL **Plan of Action and Milestones** (`plan-of-action-and-milestones`) records known
**weaknesses** and the plan to remediate each. Minimum valid document:

- `uuid`
- `metadata` (title, last-modified, version, oscal-version)
- `poam-items[]` — at least one; each needs `title` + `description`

Catalog / component-definition / SSP are **not** required references — a POA&M validates without
them. The affected control ID and component are optional enrichments (this skill attaches them as
props). Verified against **trestle 5.0.0 / OSCAL 1.2.1**.

## How this skill represents a weakness

The unit is the **weakness** (`poam-item`), not the control. `build_poam.py` keeps everything on the
poam-item (plus optional linked observation/risk) so the output is always schema-valid:

- `title` ← weakness name
- `description` ← weakness description
- `remarks` ← remediation plan
- `props` (namespaced) ← `poam-id`; **anchors**: one `control-id` per control, `check-id`, `cve`,
  `source-identifier`, one `affected-files` per file; plus `severity`, `risk-rating`, `phase`,
  `point-of-contact`, `scheduled-completion-date`, one `milestone` per milestone
- `related-observations` / `related-risks` ← cross-links to a generated Observation / Risk, when the
  item supplies `observation` / `risk`
- `uuid` ← deterministic `uuid5` of the poam-id + name (re-running the build is stable)

`control-id` is **optional** — a weakness can be anchored by `check-id`/`cve` instead (scanner
findings). The builder warns if a weakness has no anchor at all. When an item supplies `observation`
and/or `risk`, the builder adds them to the POA&M's top-level `observations`/`risks` and cross-links
them from the poam-item.

## Builder input JSON (`poam_input.json`)

Only `weakness_name` and `weakness_description` are required per item; everything else is optional.
Below shows both a scanner-anchored weakness and a control-anchored one. See the full field list in
the `build_poam.py` header.

```json
{
  "title": "Kubernetes Cluster POA&M",
  "version": "1.0",
  "system_id": "k8s-prod",
  "items": [
    {
      "poam_id": "POAM-001",
      "weakness_name": "Hardcoded secret in library",
      "weakness_description": "A credential is committed in src/lib/config.py.",
      "check_id": "QGUARD-CHECK-LIB-0007",
      "affected_files": ["src/lib/config.py"],
      "severity": "critical",
      "phase": "phase-1-immediate",
      "observation": {"description": "Scanner flagged a hardcoded token.", "methods": ["TEST"]},
      "risk": {"statement": "Leaked credential enables unauthorized access.", "status": "open"},
      "remediation_plan": "Remove the secret; rotate it; move to a secret manager.",
      "milestones": [{"description": "Rotate credential", "target_date": "2026-10-01"}],
      "poc": "Platform Security Team",
      "scheduled_completion_date": "2026-12-31"
    },
    {
      "poam_id": "POAM-002",
      "weakness_name": "MFA not enforced on admin accounts",
      "weakness_description": "Cluster admin accounts can authenticate without MFA.",
      "controls": ["ac-2", "ia-2"],
      "risk_rating": "High",
      "observation": {"description": "3 admin accounts without MFA.", "methods": ["EXAMINE"]},
      "risk": {"statement": "Weak auth on privileged accounts.", "status": "open"}
    }
  ]
}
```

## Verified library facts (for anyone editing `build_poam.py`)

- Import paths: `from trestle.oscal.poam import PlanOfActionAndMilestones, PoamItem`;
  `from trestle.oscal.common import Metadata, Property, SystemId, Observation, Risk,
  RelatedObservation, AssociatedRisk`; `from trestle.oscal import OSCAL_VERSION`
  (NOT `trestle.common.const`).
- `system_id` is a **`SystemId` object** (`SystemId(id="…")`), not a bare string.
- poam-item cross-links: `related_observations=[RelatedObservation(observation_uuid=…)]` and
  `related_risks=[AssociatedRisk(risk_uuid=…)]` (the field is `related-risks`, its element is
  `AssociatedRisk` — do **not** use a bare `associated-risks` field on the poam-item).
- `Observation` requires `methods` (list) + `collected` (tz-aware datetime); `Risk` requires
  `statement` + `status` (e.g. `"open"`).
- `metadata.last_modified` must be a timezone-aware `datetime`.
- There is **no reverse task** (OSCAL → xlsx / human view) — the markdown preview is built by us
  (see [poam-preview.md](poam-preview.md)).
