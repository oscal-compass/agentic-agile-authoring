---
name: poam-authoring
skills: [poam-authoring]
---

# Demo: authoring a POA&M

Produce a valid OSCAL **Plan of Action and Milestones** (`plan-of-action-and-milestones.json`) in
natural language — one installed skill, no orchestrator persona. Three scenarios exercise the
input paths:

- **Scenario 1 — component-definition → pre-defined POA&M → assessment linking** (closes the
  ecosystem loop): pre-define one weakness per rule/check from a `component-definition.json` with
  remediation authored up front (a separate `remediations.json`), then layer an assessment result in
  as observations/findings that *reference* the pre-defined items.
- **Scenario 2 — FedRAMP POA&M xlsx → POA&M**: convert a FedRAMP-format spreadsheet you already
  maintain.
- **Scenario 3 — trestle workspace + consolidated component-definition**: the same path C as
  scenario 1, but run **inside a trestle workspace** (inputs found deterministically from the
  directory layout — no paths given) and with remediation/risk **consolidated onto the
  component-definition's props** (no separate `remediations.json`). Produces the *same* POA&M as
  scenario 1.

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
- [`scenario1/assessment-results.json`](scenario1/assessment-results.json) — a **real** PVP
  assessment over those checks (Auditree / Kyverno / OCM). It has **observations only, no findings**:
  each observation names its rule via an `assessment-rule-id` prop and records per-subject
  `result: pass|failure` on the actual cluster resources it evaluated.

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

The assessment carries no findings, so the agent **derives** one per observation from its
subject-level `result` props — any failing subject ⇒ the rule is `not-satisfied`, otherwise
`satisfied` — then **references the existing pre-defined poam-item** for that rule (matched by
`assessment-rule-id` ⇄ the item's `check-id`), carrying the observation (with all its evaluated
subjects) across. No new poam-items are created; satisfied checks stay too (keep-all catalog), and a
rule the assessment didn't cover simply keeps its pre-defined item with no finding. (path C phase 2)

### What you'll see (process log)

```console
$ command -v uv && echo "→ using uv (isolated)"     # else falls back to python -m venv
→ using uv (isolated)
# phase 1 — pre-define from the component-definition:
$ uv run --with 'compliance-trestle>=3.0' python build_poam.py from-component-definition \
    --input component-definition.json --remediations remediations.json \
    --system-id k8s-prod --title "Kubernetes Cluster POA&M" --output-dir predefined/
OK: wrote pre-defined predefined/plan-of-action-and-milestones.json (7 poam-item(s) from rules/checks, local-definitions filled); re-read validates.
# phase 2 — link the assessment (derive findings from pass/fail, reference existing items):
$ uv run --with 'compliance-trestle>=3.0' python build_poam.py link-assessment \
    --poam predefined/plan-of-action-and-milestones.json \
    --assessment assessment-results.json --output-dir poam/
OK: wrote linked poam/plan-of-action-and-milestones.json (7 poam-item(s), 6 finding(s): 4 open / 2 satisfied; 6 linked, 0 unmatched); re-read validates.
$ trestle validate -t plan-of-action-and-milestones
VALID: Model .../plan-of-action-and-milestones.json passed the Validator ...
```

### Result

Markdown preview shown for confirmation (`not-satisfied` = open, `satisfied` = passed, blank = the
assessment didn't cover that rule):

```markdown
# Kubernetes Cluster POA&M
**System:** k8s-prod · **Version:** 1.0 · **OSCAL:** 1.2.1

| POAM ID  | Weakness                                  | Ctrl   | Validation | Status        | Risk     | POC                    |
|----------|-------------------------------------------|--------|------------|---------------|----------|------------------------|
| POAM-001 | Base image not restricted to allow list   | cm-2   | Kyverno    | not-satisfied | High     | Platform Security Team |
| POAM-002 | GitHub API version may be unsupported      | cm-2   | Auditree   | (not assessed)| —        | DevOps Team            |
| POAM-003 | GitHub organization may be empty           | ac-2   | Auditree   | satisfied     | —        | DevOps Team            |
| POAM-004 | Added Linux capabilities not disallowed    | cm-2.1 | Kyverno    | not-satisfied | Moderate | Platform Security Team |
| POAM-005 | Deployment minimum-replica not guaranteed  | cm-2   | OCM        | not-satisfied | —        | Platform Team          |
| POAM-006 | Disallowed cluster roles in use            | ac-1   | OCM        | satisfied     | Moderate | Platform Team          |
| POAM-007 | High-level vulnerability scan not enabled  | cm-6   | OCM        | not-satisfied | High     | Platform Team          |

**Total items:** 7 (4 open · 2 satisfied · 1 not assessed)
```

Full validated OSCAL output (7 pre-defined poam-items + `local-definitions`; 6 findings/observations
— derived from the assessment's per-subject pass/fail — cross-linked to the existing items):
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

---

## Scenario 3 — trestle workspace + consolidated component-definition

Same authoring path as scenario 1 (component-definition → pre-defined POA&M → assessment linking),
but it shows two conveniences that remove all the manual plumbing:

1. **The cwd is a trestle workspace.** `scenario3/` has a `.trestle/` marker and the standard
   per-model directories, so the agent finds every input by its canonical path and writes the POA&M
   into place — **you give no file paths**.
2. **Remediation/risk is consolidated onto the component-definition.** Each *validation* rule-set
   carries `Remediation_Plan` / `Risk_Rating` / `POC` / `Scheduled_Completion_Date` /
   `Weakness_Name` / `Weakness_Description` / `Milestone` props, so the component-definition is the
   **single source** — there is no `remediations.json`. (The **POA&M ID** is *not* on the
   component-definition — it is assigned when the POA&M is built, so it stays closed within the POA&M.)

The demo ships this ready-made workspace (copy the whole `scenario3/` tree into your working dir):

```
scenario3/                                   # = a trestle workspace (.trestle/ present)
  component-definitions/k8s-prod/component-definition.json   # remediation/risk consolidated on validation props
  assessment-results/k8s-prod/assessment-results.json        # the same real PVP assessment as scenario 1
  plan-of-action-and-milestones/k8s-prod/…                   # where the POA&M is written (and validated in place)
  catalogs/  profiles/  system-security-plans/  …            # the rest of the workspace skeleton
```

### Step 1 — Author the POA&M (no paths, no remediations file)

> I'm in a trestle workspace. Build the POA&M from the component-definition and the assessment
> result in it.

The agent detects the `.trestle/` root, resolves the component-definition and assessment-results
from their canonical directories, reads remediation/risk **from the component-definition's validation
props** (no `remediations.json`), pre-defines one item per rule/check, links the assessment, and
writes straight to `plan-of-action-and-milestones/k8s-prod/` — the location `trestle validate`
expects, so no copy step. (`poam-authoring`, path C + [trestle-workspace.md])

### What you'll see (process log)

```console
$ d="$PWD"; while [ "$d" != / ]; do [ -d "$d/.trestle" ] && echo "workspace: $d" && break; d=$(dirname "$d"); done
workspace: /…/scenario3
# phase 1 — pre-define from the CONSOLIDATED component-definition (note: no --remediations):
$ uv run --with 'compliance-trestle>=3.0' python build_poam.py from-component-definition \
    --input component-definitions/k8s-prod/component-definition.json \
    --system-id k8s-prod --title "Kubernetes Cluster POA&M" --output-dir predefined/
OK: wrote pre-defined predefined/plan-of-action-and-milestones.json (7 poam-item(s) from rules/checks, local-definitions filled); re-read validates.
# phase 2 — link the assessment, writing to the canonical workspace path:
$ uv run --with 'compliance-trestle>=3.0' python build_poam.py link-assessment \
    --poam predefined/plan-of-action-and-milestones.json \
    --assessment assessment-results/k8s-prod/assessment-results.json \
    --output-dir plan-of-action-and-milestones/k8s-prod/
OK: wrote linked plan-of-action-and-milestones/k8s-prod/plan-of-action-and-milestones.json (7 poam-item(s), 6 finding(s): 4 open / 2 satisfied; 6 linked, 0 unmatched); re-read validates.
$ trestle validate -t plan-of-action-and-milestones      # no mkdir/cp — already in place
VALID: Model .../plan-of-action-and-milestones.json passed the Validator ...
```

### Result

The **same weaknesses, remediation, risk, and findings as scenario 1** (7 items / 6 findings; item
UUIDs are keyed by check-id, so they match too) — the *inputs* differ (consolidated props instead of
a `remediations.json`, and deterministic workspace discovery instead of supplied paths), and because
the POA&M ID lives in the POA&M (not on the component-definition) the items are **auto-numbered
`POAM-001…` in rule order** rather than carrying scenario 1's hand-assigned IDs.
**[`scenario3/plan-of-action-and-milestones/k8s-prod/plan-of-action-and-milestones.json`](scenario3/plan-of-action-and-milestones/k8s-prod/plan-of-action-and-milestones.json)**

> Prefer keeping remediation in a separate file, or need to tweak a field at build time? Pass
> `--remediations remediations.json` as well — its fields **override** the consolidated props.

## Uninstall

Non-destructive — user-authored skills and user-defined MCP servers are never touched.

```bash
uvx compliance-authoring-skills uninstall --skill poam-authoring --target opencode
```
