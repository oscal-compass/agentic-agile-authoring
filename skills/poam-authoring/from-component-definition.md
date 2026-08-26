# From a component-definition → a pre-defined POA&M (path C, phase 1)

This is the **inverse** of [from-assessment.md](from-assessment.md). Instead of reacting to an
assessment's failed findings, you **pre-define** the whole weakness catalog from a
`component-definition.json` *before* any assessment runs, because every rule/check in the
component-definition is a testable assertion that could fail.

The output is a **pre-defined POA&M**: one poam-item per rule/check (each a *potential* weakness)
with remediation authored up front, `local-definitions` (components / inventory-items /
assessment-assets) filled from the component-definition, and **one top-level `risk` per item** (its
rating → a characterization facet, remediation plan → a recommendation response, due date →
`deadline`; status `open`). It carries **no** observations/findings yet — those get layered on later
by [link-assessment.md](link-assessment.md) (phase 2), which also flips a risk to `closed` when its
check comes back satisfied.

## Step 1 — Locate the component-definition

A trestle-style `component-definition.json` (exactly what the `component-definition` skill
produces). It has `component-definition.components[]`, each with:

- a **type**: `service` (implements controls) or `validation` (checks that rules are enforced);
- component-level **props** grouped into rule-sets (by a shared `remarks` like `rule_set_09`):
  `Rule_Id`, `Rule_Description`, `Check_Id`, `Check_Description`;
- `control-implementations[].implemented-requirements[]` mapping a **control-id** to one or more
  `Rule_Id` props.

Ask the user for the path if it is not obvious. (A `.csv` sibling is the authoring source; read the
`.json` — it is the OSCAL truth.) *In a trestle workspace, don't ask — read
`component-definitions/*/component-definition.json` (see [trestle-workspace.md](trestle-workspace.md)).*

## Step 2 — Join on `Rule_Id` to build the weakness list

`build_poam.py` does this join for you; understand it so you can sanity-check the result:

- **Service** components' `implemented-requirements` give **`Rule_Id → control-id`(s)**
  (a `control-id` of `na` means "not a control mapping" and is skipped).
- **Validation** components' props give **`Rule_Id → Check_Id` + the validation-component title**
  (the tool that performs the check, e.g. Kyverno / Auditree / OCM).

So each rule/check becomes one pre-defined weakness anchored by **`check-id`** (the stable link key
used in phase 2) plus its **`control-id`(s)** and the **`validation-component`(s)** that test it.

Example (from the demo component-definition): `allowed-base-images` → control `cm-2`, checked by
`Kyverno`; `policy-high-scan` → `cm-6` / `OCM`; `test_members_is_not_empty` → `ac-2` / `Auditree`.

## Step 3 — Author remediation up front (optional but recommended)

Because the weaknesses are known now, you can write the remediation plan now — before an assessment
ever fails. Ask the user for a remediation per rule/check, and assemble a **`remediations.json`**
keyed by check-id (or rule-id). Every field is optional; a good weakness name/description names the
*potential failure*, not the requirement:

```json
{
  "allowed-base-images": {
    "poam_id": "POAM-001",
    "weakness_name": "Base image not restricted to an approved allow list",
    "weakness_description": "Containers may run base images outside the approved allow list (CM-2).",
    "risk_rating": "High",
    "poc": "Platform Security Team",
    "scheduled_completion_date": "2026-12-31",
    "remediation_plan": "Define an allowed base-image list; enforce with the Kyverno policy.",
    "milestones": [{"description": "Publish allow list", "target_date": "2026-10-01"}]
  }
}
```

If you omit an entry, the builder still creates the poam-item using the check/rule description as a
generic "Potential weakness: …" name. Fill in whatever the user can provide.

**How remediation lands in OSCAL.** Each item gets a top-level `risk` whose **`remediations[]`** (an
OSCAL *response*) holds the fix; `remediation_plan` → the response description, and each
**`milestone` → a response `task` (`type: milestone`, `target_date` → `on-date` timing)**. The
remediation is **pass-through / reference-driven**: instead of the simple fields above, an entry may
supply a full `remediations` array (any valid `response` shape — `lifecycle`, `props`, `origins`,
`required-assets`, `tasks` with timing/responsible-roles), or a whole `risk` object, and it is
written through verbatim and trestle-validated — no code change for a new remediation format. (This
is the same pass-through the scan-tool path uses — see [from-scan-remediations.md](from-scan-remediations.md).)

### Consolidating remediation onto the component-definition (single source)

Instead of a separate `remediations.json`, you can carry the remediation/risk **on the
component-definition itself** — as extra props on each **validation** rule-set (the same rule-set,
matched by its `remarks`, that already holds `Rule_Id` / `Check_Id`). Then the component-definition
is the *single source* for pre-defining the POA&M and no `--remediations` file is needed:

| Prop name (on the validation rule-set) | Maps to |
|---|---|
| `Remediation_Plan` | `remediation_plan` (item `remarks`) |
| `Risk_Rating` | `risk-rating` |
| `POC` | `point-of-contact` |
| `Scheduled_Completion_Date` | `scheduled-completion-date` |
| `Weakness_Name` / `Weakness_Description` | item title / description |
| `Milestone` (repeatable) | one milestone; value `"<target_date>: <description>"` |

**Not on the component-definition:** the **POA&M ID** is deliberately *not* a component-definition
prop — it is assigned when the POA&M is built (auto `POAM-001…` in rule order, or from a
`--remediations` file entry), so the identifier stays closed within the POA&M.

**Precedence:** the props are the base; a `--remediations` file, if also supplied, **overrides** them
per field. So a check with everything on its props needs no file; a file can still tweak individual
fields at build time. (The **`02-trestle-workspace`** demo ships a component-definition with these
props consolidated and passes **no** `--remediations` — see [the demo](../../demos/poam-authoring/README.md).)

### Pick the risk style: `--risk-style generic` (default) or `fedramp`

Each pre-defined item gets a top-level OSCAL `risk`. OSCAL fixes the risk *structure* but leaves its
`props`/characterization `facets` as extension points (name/value under a namespace), so **the agent
chooses the convention up front** by asking one question: **is this POA&M for FedRAMP?**

| | `--risk-style generic` (default) | `--risk-style fedramp` |
|---|---|---|
| When | any non-FedRAMP deliverable | a FedRAMP submission |
| Rating | `original-risk-rating` prop (no FedRAMP ns) — mirrors what trestle's own `xlsx-to-oscal-poam` task emits | `likelihood` + `impact` characterization facets, `system = http://fedramp.gov/ns/oscal` |
| Remediation lifecycle | `planned` | `recommendation` |

Neither style puts a control-id **on the risk** — the impacted control is already on the poam-item
(`control-id` prop) and the finding target, so it isn't duplicated onto the risk.

If you don't know the target, default to **generic** (the xlsx-style shape). Only pass
`--risk-style fedramp` when the user says the POA&M is for FedRAMP. (Both validate identically; the
difference is only which namespace/props the risks carry.)

> **On a control-id on the risk.** FedRAMP's rule `poam-risk-impacted-control` wants a `risk/prop`
> naming the impacted control, but the exact `prop.name` isn't in published FedRAMP sources. Since
> the control is already traceable via the poam-item and finding, this skill **omits** it from the
> risk by default; add it (e.g. `impacted-control-id` under the FedRAMP ns) only if a user needs it.

## Step 4 — Build the pre-defined POA&M

Set up the isolated environment ([setup-env.md](setup-env.md)), then run the
`from-component-definition` subcommand of `build_poam.py`:

```bash
# uv:
uv run --with 'compliance-trestle>=3.0' python "$SKILL_DIR/build_poam.py" from-component-definition \
  --input component-definition.json --remediations remediations.json \
  --system-id k8s-prod --title "Kubernetes Cluster POA&M" --output-dir poam/
# venv:
.venv-poam/bin/python "$SKILL_DIR/build_poam.py" from-component-definition \
  --input component-definition.json --remediations remediations.json \
  --system-id k8s-prod --title "Kubernetes Cluster POA&M" --output-dir poam/
```

`--remediations`, `--system-id`, `--title`, `--version`, `--risk-style` are all optional
(`--risk-style` defaults to `generic`). The result
(`poam/plan-of-action-and-milestones.json`) is valid OSCAL — one poam-item per rule/check plus
`local-definitions` — round-tripped through `oscal_read`. Each component in `local-definitions`
also carries the **`rule-id` / `check-id` props** it declares in the component-definition (a service
component lists all its rules; a validation component lists the checks it runs), so the component's
scope is traceable directly on the component entry.

## Next

- To turn this catalog into an assessed POA&M (mark which weaknesses are currently open), layer an
  assessment result on with [link-assessment.md](link-assessment.md).
- To preview it, use [poam-preview.md](poam-preview.md).

> **Why pre-define?** It closes the ecosystem loop `component-definition → POA&M → assessment`: the
> same rule/check model the `component-definition` skill authored becomes the POA&M's weakness list,
> and the assessment only needs to *reference* those pre-existing items — never invent new ones.
