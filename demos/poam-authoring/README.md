---
name: poam-authoring
skills: [poam-authoring]
---

# Demo: authoring a POA&M

Produce a valid OSCAL **Plan of Action and Milestones** (`plan-of-action-and-milestones.json`) in
natural language — one installed skill, no orchestrator persona. Two scenarios exercise two
input paths:

- **Scenario 1 — component-definition → pre-defined POA&M → assessment linking** (closes the
  ecosystem loop): pre-define one weakness per rule/check from a `component-definition.json` with
  remediation authored up front, then layer an assessment result in as observations/findings that
  *reference* the pre-defined items.
- **Scenario 2 — FedRAMP POA&M xlsx → POA&M**: convert a FedRAMP-format spreadsheet you already
  maintain.

> The classic **reactive** path — draft weaknesses from an assessment's failed findings, then author
> remediation (`poam-authoring`, path A) — is also supported; scenario 1 shows the newer
> component-definition-driven path (path C) instead.

## Install

Prerequisite: **[`uv`](https://docs.astral.sh/uv/)** (provides `uvx`; `poam-authoring` also uses it
to run the `trestle` library/CLI in an isolated environment — no global install). No Node required.

```bash
# into OpenCode:
uvx compliance-authoring-skills install --demo poam-authoring --target opencode
# …or into Claude Code:
uvx compliance-authoring-skills install --demo poam-authoring --target claude
```

This copies `poam-authoring` into the harness's native skill dir **and wires the `trestle` MCP
server** (`compliance-trestle-mcp` >= 0.2.0, declared in the skill's `apm.yml`) into the harness's
native MCP config. The MCP is not strictly required — the skill builds and validates the POA&M with
the `trestle` library/CLI inside an isolated env (`uv` or a venv; never a global install), preferring
the MCP tools when they're present and falling back to the venv when they're not. Open the target
project in the harness so it picks up the skill + `trestle`.

---

## Scenario 1 — component-definition → pre-defined POA&M → assessment linking

This closes the loop `component-definition → POA&M → assessment`. The demo ships (copy into your
working dir first):

- [`scenario1/component-definition.json`](scenario1/component-definition.json) — a `k8s-prod`
  component-definition with **service** components (GitHub, Managed Kubernetes) that map rules to
  controls, and **validation** components (Auditree, Kyverno, OCM) that carry the checks.
- [`scenario1/remediations.json`](scenario1/remediations.json) — remediation authored up front,
  keyed by check id (optional input; supply your own or let the agent elicit it).
- [`scenario1/assessment-results.json`](scenario1/assessment-results.json) — a valid
  `assessment-results` over those checks (a subset `not-satisfied`, the rest `satisfied`), each
  observation carrying a `check-id` prop for linking.

### Step 1 — Pre-define the POA&M from the component-definition

> From component-definition.json, pre-define a POA&M — one weakness per rule/check with remediation
> up front — and fill its local-definitions from the components.

The agent joins the component-definition on `Rule_Id` (service components give the control-id;
validation components give the check-id + which tool checks it), then builds a **pre-defined POA&M**:
one poam-item per rule/check (a *potential* weakness), each anchored by `check-id` + `control-id` +
`validation-component`, with `local-definitions` (components / inventory-items / assessment-assets)
filled from the component-definition. No findings yet. (`poam-authoring`, path C phase 1)

### Step 2 — Link the assessment result (reference, don't recreate)

> Now layer assessment-results.json onto that pre-defined POA&M.

The agent adds each finding as a top-level `Finding` (+ observation, + risk), and **references the
existing pre-defined poam-item** for the same check (matched by `check-id`) — creating no new items.
Passed checks stay too, linked to a `satisfied` finding (keep-all catalog). (path C phase 2)

### What you'll see (process log)

```console
$ command -v uv && echo "→ using uv (isolated)"     # else falls back to python -m venv
→ using uv (isolated)
# phase 1 — pre-define from the component-definition:
$ uv run --with 'compliance-trestle>=3.0' python build_poam.py from-component-definition \
    --input component-definition.json --remediations remediations.json \
    --system-id k8s-prod --title "Kubernetes Cluster POA&M" --output-dir predefined/
OK: wrote pre-defined predefined/plan-of-action-and-milestones.json (7 poam-item(s) from rules/checks, local-definitions filled); re-read validates.
# phase 2 — link the assessment (reference existing items):
$ uv run --with 'compliance-trestle>=3.0' python build_poam.py link-assessment \
    --poam predefined/plan-of-action-and-milestones.json \
    --assessment assessment-results.json --output-dir poam/
OK: wrote linked poam/plan-of-action-and-milestones.json (7 poam-item(s), 7 finding(s): 3 open / 4 satisfied; 7 linked, 0 unmatched); re-read validates.
$ trestle validate -t plan-of-action-and-milestones
VALID: Model .../plan-of-action-and-milestones.json passed the Validator ...
```

### Result

Markdown preview shown for confirmation (open = `not-satisfied` finding, ✓ = satisfied):

```markdown
# Kubernetes Cluster POA&M
**System:** k8s-prod · **Version:** 1.0 · **OSCAL:** 1.2.1

| POAM ID  | Weakness                                  | Ctrl   | Validation | Status        | Risk     | POC                    |
|----------|-------------------------------------------|--------|------------|---------------|----------|------------------------|
| POAM-001 | Base image not restricted to allow list   | cm-2   | Kyverno    | not-satisfied | High     | Platform Security Team |
| POAM-002 | GitHub API version may be unsupported      | cm-2   | Auditree   | satisfied     | —        | DevOps Team            |
| POAM-003 | GitHub organization may be empty           | ac-2   | Auditree   | satisfied     | —        | DevOps Team            |
| POAM-004 | Added Linux capabilities not disallowed    | cm-2.1 | Kyverno    | satisfied     | Moderate | Platform Security Team |
| POAM-005 | Deployment minimum-replica not guaranteed  | cm-2   | OCM        | satisfied     | —        | Platform Team          |
| POAM-006 | Disallowed cluster roles in use            | ac-1   | OCM        | not-satisfied | Moderate | Platform Team          |
| POAM-007 | High-level vulnerability scan not enabled  | cm-6   | OCM        | not-satisfied | High     | Platform Team          |

**Total items:** 7 (3 open · 4 satisfied)
```

Full validated OSCAL output (7 pre-defined poam-items + `local-definitions`; 7 findings/observations
cross-linked to the existing items):
**[`scenario1/plan-of-action-and-milestones.json`](scenario1/plan-of-action-and-milestones.json)**

---

## Scenario 2 — FedRAMP POA&M xlsx → POA&M

For teams who already maintain the POA&M in the FedRAMP spreadsheet. This demo ships a sample —
[`scenario2/sample-poam.xlsx`](scenario2/sample-poam.xlsx) (sheet `Open POA&M Items`, row 5 headers, two k8s weaknesses;
required columns `POAM ID` / `Weakness Name` / `Weakness Description` / `Controls`). Copy it into
your working dir first.

### Step 1 — Convert the spreadsheet

> Convert sample-poam.xlsx (a FedRAMP POA&M spreadsheet) into an OSCAL POA&M and validate it.

The agent sets up the isolated env, ensures a trestle workspace, and runs the trestle
`xlsx-to-oscal-poam` task (the MCP tool `trestle_task_xlsx_to_oscal_poam` if wired, else the venv
`trestle` CLI). It produces `plan-of-action-and-milestones.json` — valid OSCAL — with the converter
auto-generating the `observations[]`/`risks[]` and cross-linking each poam-item to them. It then
shows a markdown preview. (`poam-authoring`, path B)

### What you'll see (process log)

```console
# MCP tool `trestle_task_xlsx_to_oscal_poam` if wired, else the venv CLI (same result):
$ trestle task xlsx-to-oscal-poam --config poam.config
Created POAM with 2 items
Output: .../plan-of-action-and-milestones.json
Task: xlsx-to-oscal-poam executed successfully.
$ trestle validate -t plan-of-action-and-milestones
VALID: Model plan-of-action-and-milestones.json passed the Validator ...
```

### Result

Full validated OSCAL output (2 poam-items; the converter auto-generates a linked observation and
risk for each, with deterministic UUIDs):
**[`scenario2/plan-of-action-and-milestones.json`](scenario2/plan-of-action-and-milestones.json)**

> This path is **control-centric** (the FedRAMP template requires the `Controls` column). If your
> spreadsheet has no controls (e.g. a scanner export keyed only by check id), use Scenario 1
> instead — there the weakness is the unit and control-id is an optional anchor.

## Uninstall

Non-destructive — user-authored skills and user-defined MCP servers are never touched.

```bash
uvx compliance-authoring-skills uninstall --skill poam-authoring --target opencode
```
