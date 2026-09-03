---
name: poam-authoring
skills: [poam-authoring]
---

# Demo: authoring a POA&M

Produce a valid OSCAL **Plan of Action and Milestones** (`plan-of-action-and-milestones.json`) in
natural language — one installed skill, no orchestrator persona. Three scenarios exercise the
input paths:

- **[`01-component-definition`](01-component-definition/) — component-definition → pre-defined POA&M
  → assessment linking** (closes the ecosystem loop): pre-define one weakness per rule/check from a
  `component-definition.json` with remediation authored up front (a separate `remediations.json`),
  then layer an assessment result in as observations/findings that *reference* the pre-defined items.
- **[`02-trestle-workspace`](02-trestle-workspace/) — trestle workspace + consolidated
  component-definition**: the same path C as scenario 01, but run **inside a trestle workspace**
  (inputs found deterministically from the directory layout — no paths given) and with
  remediation/risk **consolidated onto the component-definition's props** (no separate
  `remediations.json`). Produces the *same* POA&M as scenario 01.
- **[`03-fedramp-xlsx`](03-fedramp-xlsx/) — FedRAMP POA&M xlsx → POA&M**: convert a FedRAMP-format
  spreadsheet you already maintain.

> The classic **reactive** path — draft weaknesses from an assessment's failed findings, then author
> remediation (`poam-authoring`, path A) — is also supported; scenario 01 shows the newer
> component-definition-driven path (path C) instead.

> **These demos double as validation.** Each scenario lists an **Expected result** — but an agent
> produces the output, so it varies run-to-run: the **title text, POAM-ID ordering, exact wording,
> and which isolated-env command (`uv` vs venv) is used will differ**, and a weaker model may need a
> more explicit prompt. Don't diff byte-for-byte; check the **stable invariants** each scenario
> lists (they hold regardless): first and foremost `trestle validate … → VALID`, then the item /
> finding / risk **counts** and each item's anchors.

## Install

Prerequisite: **[`uv`](https://docs.astral.sh/uv/)** (provides `uvx`; `poam-authoring` also uses it
to run the `trestle` library/CLI in an isolated environment — no global install). No Node required.

```bash
# into Claude Code:
uvx \
  --from "git+https://github.com/oscal-compass/agentic-agile-authoring.git@main#subdirectory=tools" \
  compliance-authoring-skills install --demo poam-authoring --target claude

# …or into OpenCode:
uvx \
  --from "git+https://github.com/oscal-compass/agentic-agile-authoring.git@main#subdirectory=tools" \
  compliance-authoring-skills install --demo poam-authoring --target opencode

# …or into IBM Bob:
uvx \
  --from "git+https://github.com/oscal-compass/agentic-agile-authoring.git@main#subdirectory=tools" \
  compliance-authoring-skills install --demo poam-authoring --target bob
```

This copies `poam-authoring` into the harness's native skill dir **and wires the `trestle` MCP
server** (`compliance-trestle-mcp` >= 0.2.0, declared in the skill's `apm.yml`) into the harness's
native MCP config. The MCP is not strictly required — the skill builds and validates the POA&M with
the `trestle` library/CLI inside an isolated env (`uv` or a venv; never a global install), preferring
the MCP tools when they're present and falling back to the venv when they're not. Open the target
project in the harness so it picks up the skill + `trestle`.

---

## Scenario 01 — component-definition → pre-defined POA&M → assessment linking

This closes the loop `component-definition → POA&M → assessment`. The demo ships (copy into your
working dir first):

> **This scenario also shows the remediation shape.** Each item's fix lands in OSCAL's
> `risk.remediations[]` (a *response*), with milestones as response **`tasks[]`** (`on-date` timing).
> That remediation is **pass-through / reference-driven** — the builder writes through whatever
> remediation shape the source supplies (free-form props, `tasks`, `lifecycle`, …). A scan tool's own
> remediation export can be mapped in the very same way — see
> [from-scan-remediations.md](../../skills/poam-authoring/from-scan-remediations.md) (path D).

- [`01-component-definition/component-definition.json`](01-component-definition/component-definition.json) —
  a `k8s-prod` component-definition with **service** components (GitHub, Managed Kubernetes) that map
  rules to controls, and **validation** components (Auditree, Kyverno, OCM) that carry the checks.
- [`01-component-definition/remediations.json`](01-component-definition/remediations.json) —
  remediation authored up front, keyed by check id (optional input; supply your own or let the agent
  elicit it).
- [`01-component-definition/assessment-results.json`](01-component-definition/assessment-results.json) —
  a **real** PVP assessment over those checks (Auditree / Kyverno / OCM). It has **observations only,
  no findings**: each observation names its rule via an `assessment-rule-id` prop and records
  per-subject `result: pass|failure` on the actual cluster resources it evaluated.

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
OK: wrote pre-defined predefined/plan-of-action-and-milestones.json (7 poam-item(s) from rules/checks, 7 risk(s), local-definitions filled); re-read validates.
# phase 2 — link the assessment (derive findings from pass/fail, reference existing items):
$ uv run --with 'compliance-trestle>=3.0' python build_poam.py link-assessment \
    --poam predefined/plan-of-action-and-milestones.json \
    --assessment assessment-results.json --output-dir poam/
OK: wrote linked poam/plan-of-action-and-milestones.json (7 poam-item(s), 6 finding(s): 4 open / 2 satisfied; 7 risk(s): 5 open / 2 closed; 6 linked, 0 unmatched); re-read validates.
# validate the standalone file — no trestle workspace (MCP trestle_validate if wired, else this):
$ trestle partial-object-validate -f poam/plan-of-action-and-milestones.json -e plan-of-action-and-milestones
VALID: .../plan-of-action-and-milestones.json for plan-of-action-and-milestones
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

Full validated OSCAL output (7 pre-defined poam-items + `local-definitions`; a top-level **`risk`
per item** — generic/xlsx-style: rating → `original-risk-rating` prop, remediation → response, due
date → deadline — of which 2 are `closed` once their check passed; 6 findings/observations — derived
from the assessment's per-subject pass/fail — cross-linked to the existing items):
**[`01-component-definition/plan-of-action-and-milestones.json`](01-component-definition/plan-of-action-and-milestones.json)**

**Expected result (validation)** — check these invariants, not exact strings:
- validates **VALID** as a standalone file — no workspace (MCP `trestle_validate`, or `trestle partial-object-validate -e plan-of-action-and-milestones`)
- **7 poam-items**, each anchored by a `check-id` prop (+ `control-id` where the CD maps one) and a `rule-id` prop (the rule's `Rule_Id`), relating the item back to its `local-definitions` group. The items **do not duplicate** the static content — no `risk-rating`/`point-of-contact`/`scheduled-completion-date`/`milestone` props and no remediation `remarks`; that lives once in the local-def group (+ the risk)
- `local-definitions` validation components carry the consolidated weakness/risk/remediation props **grouped by the CD's verbatim `remarks` token**, alongside `rule-id`/`check-id`. Here the CD carries none — they come from **`remediations.json`** — but the builder still merges the file's fields **into local-definitions**, so the groups are fully populated (same shape as scenario 02, which sources them from the CD)
- **6 findings** = **4 `not-satisfied` / 2 `satisfied`** (1 rule — `test_supported_versions` — not assessed, so it keeps its item with no finding)
- **7 risks**, **2 `closed`** (the satisfied checks) / 5 `open`; generic style → rating in an `original-risk-rating` prop, no characterizations; each risk also carries the `rule-id` join prop and holds the remediation
- each risk's **`remediations[]`** holds the fix (lifecycle `planned`), with the remediation's milestones as response **`tasks[]`** (`type: milestone`, `on-date` timing)
- *Varies:* the title text, the POAM-ID ↔ check mapping/order, and whether `uv` or a venv was used.

---

## Scenario 02 — trestle workspace + consolidated component-definition

Same authoring path as scenario 01 (component-definition → pre-defined POA&M → assessment linking),
but it shows two conveniences that remove all the manual plumbing:

1. **The cwd is a trestle workspace.** `02-trestle-workspace/` has a `.trestle/` marker and the
   standard per-model directories, so the agent finds every input by its canonical path and writes
   the POA&M into place — **you give no file paths**.
2. **Remediation/risk is consolidated onto the component-definition.** Each *validation* rule-set
   carries `Remediation_Plan` / `Risk_Rating` / `POC` / `Scheduled_Completion_Date` /
   `Weakness_Name` / `Weakness_Description` / `Milestone` props, so the component-definition is the
   **single source** — there is no `remediations.json`. (The **POA&M ID** is *not* on the
   component-definition — it is assigned when the POA&M is built, so it stays closed within the POA&M.)

The demo ships this ready-made workspace (copy the whole `02-trestle-workspace/` tree into your
working dir):

```
02-trestle-workspace/                         # = a trestle workspace (.trestle/ present)
  component-definitions/k8s-prod/component-definition.json   # remediation/risk consolidated on validation props
  assessment-results/k8s-prod/assessment-results.json        # the same real PVP assessment as scenario 01
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
workspace: /…/02-trestle-workspace
# phase 1 — pre-define from the CONSOLIDATED component-definition (note: no --remediations):
$ uv run --with 'compliance-trestle>=3.0' python build_poam.py from-component-definition \
    --input component-definitions/k8s-prod/component-definition.json \
    --system-id k8s-prod --title "Kubernetes Cluster POA&M" --output-dir predefined/
OK: wrote pre-defined predefined/plan-of-action-and-milestones.json (7 poam-item(s) from rules/checks, 7 risk(s), local-definitions filled); re-read validates.
# phase 2 — link the assessment, writing to the canonical workspace path:
$ uv run --with 'compliance-trestle>=3.0' python build_poam.py link-assessment \
    --poam predefined/plan-of-action-and-milestones.json \
    --assessment assessment-results/k8s-prod/assessment-results.json \
    --output-dir plan-of-action-and-milestones/k8s-prod/
OK: wrote linked plan-of-action-and-milestones/k8s-prod/plan-of-action-and-milestones.json (7 poam-item(s), 6 finding(s): 4 open / 2 satisfied; 7 risk(s): 5 open / 2 closed; 6 linked, 0 unmatched); re-read validates.
$ trestle validate -t plan-of-action-and-milestones      # no mkdir/cp — already in place
VALID: Model .../plan-of-action-and-milestones.json passed the Validator ...
```

### Result

The **same weaknesses, remediation, risk, and findings as scenario 01** (7 items / 6 findings; item
UUIDs are keyed by check-id, so they match too) — the *inputs* differ (consolidated props instead of
a `remediations.json`, and deterministic workspace discovery instead of supplied paths), and because
the POA&M ID lives in the POA&M (not on the component-definition) the items are **auto-numbered
`POAM-001…` in rule order** rather than carrying scenario 01's hand-assigned IDs.

Because the CD here **consolidates the weakness/remediation/risk props on its validation rule-sets**,
those props are carried **verbatim into `local-definitions`** — each validation component's rule-set
group (keyed by its `remarks` token, e.g. `rule_set_09`) holds `Weakness_Name`/`Weakness_Description`/
`Risk_Rating`/`POC`/`Scheduled_Completion_Date`/`Remediation_Plan`/`Milestone` alongside its
`Rule_Id`/`Check_Id`. This is the **same fully-populated `local-definitions`** as scenario 01 — the
two just source the content differently (scenario 01 merges it from `remediations.json`, scenario 02
from the CD props); either way the poam-items reference the group by `rule-id` and never duplicate
it, and all counts and item/risk UUIDs match.
**[`02-trestle-workspace/plan-of-action-and-milestones/k8s-prod/plan-of-action-and-milestones.json`](02-trestle-workspace/plan-of-action-and-milestones/k8s-prod/plan-of-action-and-milestones.json)**

> Prefer keeping remediation in a separate file, or need to tweak a field at build time? Pass
> `--remediations remediations.json` as well — its fields **override** the consolidated props.

> **Risk conventions.** The generated `risks[]` default to the **generic** (xlsx-style) shape —
> rating in an `original-risk-rating` prop, no FedRAMP-specific props. For a FedRAMP submission, add
> `--risk-style fedramp` to emit the rating as `likelihood`/`impact` facets under the
> `http://fedramp.gov/ns/oscal` namespace instead. Neither style puts a control-id on the risk (the
> control is already on the poam-item + finding); the agent picks the style from whether the POA&M is
> for FedRAMP (see [from-component-definition.md](../../skills/poam-authoring/from-component-definition.md)).

**Expected result (validation)** — check these invariants, not exact strings:
- `trestle validate -t plan-of-action-and-milestones` → **VALID**, with the file written to `plan-of-action-and-milestones/k8s-prod/` (no `mkdir`/`cp` — the workspace's canonical path)
- inputs were found **with no paths given** (workspace discovery) and with **no `remediations.json`** (rating/remediation came from the CD's validation props)
- `local-definitions` is **fully consolidated**: each validation component's rule-set group (keyed by its verbatim `remarks` token) carries the `Weakness_Name`/`Weakness_Description`/`Risk_Rating`/`POC`/`Scheduled_Completion_Date`/`Remediation_Plan`/`Milestone` props verbatim (no `ns`) alongside `rule-id`/`check-id`; every poam-item and risk carries a matching `rule-id` prop and the items **do not duplicate** the static content (same de-duplicated shape as scenario 01)
- same counts as scenario 01: **7 items / 6 findings (4 open · 2 satisfied) / 7 risks (2 `closed`)**; risks default to the generic `original-risk-rating` shape, each with a `remediations[]` whose milestones are response **`tasks[]`** (`on-date` timing)
- *Varies:* the title text and the `POAM-001…` numbering order. If run with a weak model, be explicit ("path C: pre-define from the component-definition, then link the assessment") and make sure it installs **`compliance-trestle`** (not the unrelated PyPI `trestle`).

---

## Scenario 03 — FedRAMP POA&M xlsx → POA&M

For teams who already maintain the POA&M in the FedRAMP spreadsheet. This demo ships a sample —
[`03-fedramp-xlsx/sample-poam.xlsx`](03-fedramp-xlsx/sample-poam.xlsx) (sheet `Open POA&M Items`, row 5 headers, two k8s weaknesses;
required columns `POAM ID` / `Weakness Name` / `Weakness Description` / `Controls`). Copy it into
your working dir first.

### Step 1 — Convert the spreadsheet

> Convert sample-poam.xlsx (a FedRAMP POA&M spreadsheet) into an OSCAL POA&M and validate it.

The agent sets up the isolated env and runs the trestle `xlsx-to-oscal-poam` task (the MCP tool
`trestle_task_xlsx_to_oscal_poam` if wired, else the venv `trestle` CLI). It produces a standalone
`plan-of-action-and-milestones.json` — valid OSCAL, no workspace needed — with the converter
auto-generating the `observations[]`/`risks[]` and cross-linking each poam-item to them. It then
shows a markdown preview. (`poam-authoring`, path B)

### What you'll see (process log)

```console
# MCP tool `trestle_task_xlsx_to_oscal_poam` if wired, else the venv CLI (same result):
$ trestle task xlsx-to-oscal-poam --config poam.config
Created POAM with 2 items
Output: .../plan-of-action-and-milestones.json
Task: xlsx-to-oscal-poam executed successfully.
# validate the standalone file — no workspace (MCP trestle_validate if wired, else this):
$ trestle partial-object-validate -f plan-of-action-and-milestones.json -e plan-of-action-and-milestones
VALID: plan-of-action-and-milestones.json for plan-of-action-and-milestones
```

### Result

Full validated OSCAL output (2 poam-items; the converter auto-generates a linked observation and
risk for each, with deterministic UUIDs):
**[`03-fedramp-xlsx/plan-of-action-and-milestones.json`](03-fedramp-xlsx/plan-of-action-and-milestones.json)**

> This path is **control-centric** (the FedRAMP template requires the `Controls` column). If your
> spreadsheet has no controls (e.g. a scanner export keyed only by check id), use scenario 01
> instead — there the weakness is the unit and control-id is an optional anchor.

**Expected result (validation)** — check these invariants, not exact strings:
- validates **VALID** as a standalone file — no workspace (MCP `trestle_validate`, or `trestle partial-object-validate`)
- **2 poam-items** (one per spreadsheet row), each with a `control-id` prop from the `Controls` column
- **2 observations** and **2 risks**, one linked to each item (deterministic UUIDs, so a re-run is byte-stable here — this path is the trestle task, not the agent)
- *Varies:* nothing material — the xlsx converter is deterministic; only the surrounding prose the agent prints will differ.

## Uninstall

Non-destructive — user-authored skills and user-defined MCP servers are never touched.

```bash
# from Claude Code:
uvx \
  --from "git+https://github.com/oscal-compass/agentic-agile-authoring.git@main#subdirectory=tools" \
  compliance-authoring-skills uninstall --skill poam-authoring --target claude

# …or from OpenCode:
uvx \
  --from "git+https://github.com/oscal-compass/agentic-agile-authoring.git@main#subdirectory=tools" \
  compliance-authoring-skills uninstall --skill poam-authoring --target opencode

# …or from Bob:
uvx \
  --from "git+https://github.com/oscal-compass/agentic-agile-authoring.git@main#subdirectory=tools" \
  compliance-authoring-skills uninstall --skill poam-authoring --target bob
```
