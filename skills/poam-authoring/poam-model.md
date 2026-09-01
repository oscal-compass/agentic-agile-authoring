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

A POA&M can also carry (all optional): `local-definitions` (system `components`, `inventory-items`,
`assessment-assets`), top-level `observations` / `risks`, and top-level **`findings`** — the latter
three record what an assessment saw. Path C uses all of these (see below).

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

## Path C — component-definition-driven (pre-define, then reference)

Path C uses two `build_poam.py` subcommands instead of the `build` input above.

### Phase 1 — `from-component-definition`

Input is a trestle-style `component-definition.json`. The builder joins every component on
`Rule_Id`: **service** components map `Rule_Id → control-id`(s); **validation** components map
`Rule_Id → Check_Id` + the validation-component title. It emits a **pre-defined POA&M**:

- `local-definitions.components` — one `SystemComponent` per component (type `service`/`validation`,
  status `operational`), each carrying the **`rule-id` / `check-id` props** it declares, **grouped by
  the component-definition's verbatim `remarks` rule-set token** (e.g. `rule_set_09`) — the props of
  one rule-set share one `remarks` value, mirroring the CD. **This is the consolidated home for the
  static content**: on a **validation** component, each rule-set also carries its
  `Weakness_Name`/`Weakness_Description`/`Risk_Rating`/`POC`/`Scheduled_Completion_Date`/
  `Remediation_Plan`/`Milestone` props **verbatim from the CD** (no `ns`, so they mirror the CD
  exactly), under the same token. (These land here only when the CD carries them — the `remarks`
  token is unique *within one component*, and the consolidated props live only on the validation
  rule-sets, so the validation token is the home.)
- `local-definitions.inventory-items` — one per service component (with an `implemented-component`
  back-reference).
- `local-definitions.assessment-assets.assessment-platforms` — one per validation component.
- `poam-items` — one per rule/check, anchored by a **`check-id`** prop (the phase-2 link key) plus
  `control-id`(s), `validation-component`(s), and a **`rule-id`** prop (the rule's `Rule_Id`),
  relating the item back to its consolidated local-definitions group.
  `uuid` is `uuid5` of the check-id (stable so phase 2 can find it). No observations/findings yet.
- `risks` — one top-level OSCAL `risk` per item (OSCAL forbids risks *inside* `local-definitions`, so
  the risk object stays top-level). It carries the same **`rule-id`** join prop and holds the
  remediation (`remediations[]`). Its `description`/`statement` are OSCAL-required.

**No duplication (the goal).** The static weakness/risk/remediation content lives in **one place** —
the local-definitions rule-set group (+ the top-level `risk`). A poam-item does **not** repeat it:
it carries only the anchors (`poam-id`/`control-id`/`check-id`/`rule-id`/`validation-component`)
and the OSCAL-required `title`/`description` (the human-readable weakness name/description — the one
unavoidable overlap), and **references** its group by `rule-id`. The item's `risk-rating`/
`point-of-contact`/`scheduled-completion-date`/`milestone` props and remediation `remarks` are gone
from path C; a reader (or the markdown preview) recovers them by dereferencing `rule-id` → the
group / the linked risk. (**Fallback:** a rule with *no* validation rule-set has no group to point
at, so such an item inlines the descriptive props itself — nothing is lost. Path A always inlines,
since it has no local-definitions.)

Optional **`remediations.json`** maps a check-id (or rule-id) to remediation fields — the same
per-item fields as path A (`weakness_name`, `weakness_description`, `remediation_plan`,
`risk_rating`/`severity`, `poc`, `scheduled_completion_date`, `milestones`, `phase`, `poam_id`):

```json
{ "allowed-base-images": { "weakness_name": "…", "remediation_plan": "…", "risk_rating": "High",
                           "poc": "…", "milestones": [{"description": "…", "target_date": "…"}] } }
```

### Phase 2 — `link-assessment`

Inputs: the phase-1 POA&M (`--poam`) + an `assessment-results.json` (`--assessment`). The builder
handles both **explicit `findings[]`** and **observation-only** results (real PVP output such as
Auditree/Kyverno/OCM, which has observations but no findings). In the observation-only case it
**derives** a finding per observation from the observation's **subject-level `result` props** (any
failing subject ⇒ `not-satisfied`, else `satisfied`), carries the full observation (all evaluated
subjects) across as evidence, and emits a top-level `Finding` (objective-id target). Either way it
**cross-links the existing pre-defined poam-item**, matched by the observation's rule identifier —
`check-id` → `assessment-rule-id` → `rule-id` — against the item's `check-id` prop (fallback: the
finding's control `target-id` vs the item's `control-id`). No new poam-items. Keep-all: satisfied
checks stay (linked to a satisfied finding); a rule the assessment didn't cover keeps its item with
no finding.

## Verified library facts (for anyone editing `build_poam.py`)

- Import paths: `from trestle.oscal.poam import PlanOfActionAndMilestones, PoamItem, LocalDefinitions,
  RelatedFinding`;
  `from trestle.oscal.common import Metadata, Property, SystemId, Observation, Risk,
  RelatedObservation, AssociatedRisk, SystemComponent, Status, Finding, FindingTarget,
  ObjectiveStatus, InventoryItem, AssessmentAssets, AssessmentPlatform, ImplementedComponent,
  UsesComponent`; `from trestle.oscal import OSCAL_VERSION` (NOT `trestle.common.const`).
- `system_id` is a **`SystemId` object** (`SystemId(id="…")`), not a bare string.
- `SystemComponent` needs `status=Status(state="operational")`; a top-level finding uses
  `FindingTarget(type="objective-id", target_id=<control>, status=ObjectiveStatus(state=
  "not-satisfied"|"satisfied"))`; a poam-item references it via
  `related_findings=[RelatedFinding(finding_uuid=…)]`. `ObjectiveStatus.state` is an enum — read it
  as `.value`, not `.root`.
- poam-item cross-links: `related_observations=[RelatedObservation(observation_uuid=…)]` and
  `related_risks=[AssociatedRisk(risk_uuid=…)]` (the field is `related-risks`, its element is
  `AssociatedRisk` — do **not** use a bare `associated-risks` field on the poam-item).
- `Observation` requires `methods` (list) + `collected` (tz-aware datetime); `Risk` requires
  `statement` + `status` (e.g. `"open"`).
- `Property` carries an optional **`remarks`** field — used to carry the CD's rule-set token onto
  local-definitions props so they group into rule-sets. `Property.value` must be non-empty
  (`^\S(.*\S)?$`) — strip and skip empties. Consolidated props are emitted with **no `ns`** (mirror
  the CD verbatim); anchors (`rule-id`/`check-id`) keep the skill's `NS_PROP`.
- `local-definitions` legally holds only components / inventory-items / assessment-assets / remarks —
  **not `risk`**; the risk object is top-level and links back via the `rule-id` prop.
- `metadata.last_modified` must be a timezone-aware `datetime`.
- There is **no reverse task** (OSCAL → xlsx / human view) — the markdown preview is built by us
  (see [poam-preview.md](poam-preview.md)).
