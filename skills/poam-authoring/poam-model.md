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

`build_poam.py` keeps every field on the `poam-item` so the output is always schema-valid:

- `title` ← weakness name
- `description` ← weakness description
- `remarks` ← remediation plan
- `props` (namespaced) ← `poam-id`, one `control-id` per control, `point-of-contact`,
  `risk-rating`, `scheduled-completion-date`, and one `milestone` per milestone
- `uuid` ← deterministic `uuid5` of the poam-id + name (re-running the build is stable)

> v1 keeps it simple: weaknesses are self-contained poam-items. Separate OSCAL `observations` /
> `risks` (with cross-links) are intentionally **not** generated — the minimal form is valid and
> sufficient. Add them later only if a consumer needs them.

## Builder input JSON (`poam_input.json`)

Only `weakness_name` and `weakness_description` are required per item; everything else is optional.

```json
{
  "title": "Kubernetes Cluster POA&M",
  "version": "1.0",
  "system_id": "k8s-prod",
  "items": [
    {
      "poam_id": "POAM-001",
      "weakness_name": "MFA not enforced on admin accounts",
      "weakness_description": "Cluster admin accounts can authenticate without MFA.",
      "controls": ["ac-2", "ia-2"],
      "remediation_plan": "Enforce MFA via the IdP for all cluster-admin bindings.",
      "milestones": [
        {"description": "Enable MFA policy in IdP", "target_date": "2026-10-01"},
        {"description": "Audit all admin bindings", "target_date": "2026-11-15"}
      ],
      "poc": "Platform Security Team",
      "scheduled_completion_date": "2026-12-31",
      "risk_rating": "High"
    }
  ]
}
```

## Verified library facts (for anyone editing `build_poam.py`)

- Import paths: `from trestle.oscal.poam import PlanOfActionAndMilestones, PoamItem`;
  `from trestle.oscal.common import Metadata, Property, SystemId`;
  `from trestle.oscal import OSCAL_VERSION` (NOT `trestle.common.const`).
- `system_id` is a **`SystemId` object** (`SystemId(id="…")`), not a bare string.
- `metadata.last_modified` must be a timezone-aware `datetime`.
- There is **no reverse task** (OSCAL → xlsx / human view) — the markdown preview is built by us
  (see [poam-preview.md](poam-preview.md)).
