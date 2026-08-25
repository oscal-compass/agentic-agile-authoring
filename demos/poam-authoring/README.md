---
name: poam-authoring
skills: [poam-authoring]
---

# Demo: authoring a POA&M

Produce a valid OSCAL **Plan of Action and Milestones** (`plan-of-action-and-milestones.json`) in
natural language — one installed skill, no orchestrator persona. Two scenarios exercise the two
input paths:

- **Scenario 1 — assessment result → POA&M** (the common path): draft weaknesses from an
  assessment's non-compliant findings, then author the remediation plan.
- **Scenario 2 — FedRAMP POA&M xlsx → POA&M**: convert a FedRAMP-format spreadsheet you already
  maintain.

## Install

Prerequisite: **[`uv`](https://docs.astral.sh/uv/)** (provides `uvx`; `poam-authoring` also uses it
to run the `trestle` library/CLI in an isolated environment — no global install). No Node required.

```bash
# into OpenCode:
uvx compliance-authoring-skills install --demo poam-authoring --target opencode
# …or into Claude Code:
uvx compliance-authoring-skills install --demo poam-authoring --target claude
```

This copies `poam-authoring` into the harness's native skill dir. It declares **no MCP server** —
it builds and validates the POA&M with the `trestle` library/CLI inside an isolated env (`uv` or a
venv; never a global install), so nothing is wired into the harness's MCP config. If you *do* wire
the trestle MCP (`compliance-trestle-mcp` >= 0.2.0), the skill prefers its tools and otherwise falls
back to the venv — same result. Open the target project in the harness so it picks up the skill.

---

## Scenario 1 — assessment result → POA&M

Run in a working directory with an assessment result. This demo ships a sample OSCAL assessment
result — [`assessment-results.json`](assessment-results.json) (a valid `assessment-results` for the
`k8s-prod` cluster; copy it into your working dir first).

### Step 1 — Ask for a POA&M

> From assessment-results.json, create a Plan of Action and Milestones (POA&M) for the
> non-compliant findings.

The agent reads the OSCAL assessment result, keeps **only the findings whose status is
`not-satisfied`** (here AC-2, AU-2, and SC-8; the satisfied AC-3 and CM-6 are skipped), and drafts
one weakness per failed finding — naming the *failure*, not the requirement (e.g. "MFA not enforced
on admin accounts") and carrying the finding's evidence and control id across. It then asks you for
the remediation details the assessment does not contain. (`poam-authoring`, path A)

### Step 2 — Provide the remediation plan

> AC-2: enforce MFA via the IdP for all admin bindings; milestone "Enable MFA policy in IdP" by
> 2026-10-01; owner Platform Security Team; complete by 2026-12-31; risk High.
> AU-2: configure the kube-apiserver audit policy; milestone "Deploy audit policy" by 2026-11-01;
> owner Platform Team; complete by 2026-11-30; risk Moderate.
> SC-8: enable etcd peer TLS on all control-plane nodes; milestone "Roll out etcd peer certs" by
> 2026-10-15; owner Platform Team; complete by 2026-12-15; risk High.

The agent provisions an isolated environment (prefers `uv`, else a local venv; if neither works it
stops and asks you to enable one rather than polluting your Python), writes `poam_input.json`, runs
the skill's `build_poam.py`, and produces the POA&M — valid OSCAL — with each weakness carrying its
controls, evidence (observation), risk, remediation plan, milestones, owner, and due date. It then
shows a markdown preview to confirm.

### What you'll see (process log)

```console
$ command -v uv && echo "→ using uv (isolated)"     # else falls back to python -m venv
→ using uv (isolated)
# the skill drafts weaknesses, you supply the plan, it writes poam_input.json, then builds:
$ uv run --with 'compliance-trestle>=3.0' python build_poam.py --input poam_input.json --output-dir poam/
OK: wrote poam/plan-of-action-and-milestones.json (3 poam-item(s), 3 observation(s), 3 risk(s)); re-read validates.
$ trestle validate -t plan-of-action-and-milestones
VALID: Model .../plan-of-action-and-milestones.json passed the Validator ...
```

### Result

Markdown preview shown for confirmation:

```markdown
# Kubernetes Cluster POA&M — Remediation Plan
**System:** k8s-prod · **Version:** 1.0 · **OSCAL:** 1.2.1

| POAM ID  | Weakness                            | Controls | Risk     | POC                    | Due        | Milestones                              |
|----------|-------------------------------------|----------|----------|------------------------|------------|-----------------------------------------|
| POAM-001 | MFA not enforced on admin accounts  | ac-2     | High     | Platform Security Team | 2026-12-31 | Enable MFA (target: 2026-10-01)         |
| POAM-002 | API audit logging not configured    | au-2     | Moderate | Platform Team          | 2026-11-30 | Deploy audit policy (target: 2026-11-01)|
| POAM-003 | etcd peer traffic not encrypted     | sc-8     | High     | Platform Team          | 2026-12-15 | Roll out etcd peer certs (2026-10-15)   |

**Total open items:** 3
```

Full validated OSCAL output (3 poam-items, each cross-linked to a generated observation and risk):
**[`expected-output/scenario1-assessment-to-poam.json`](expected-output/scenario1-assessment-to-poam.json)**

---

## Scenario 2 — FedRAMP POA&M xlsx → POA&M

For teams who already maintain the POA&M in the FedRAMP spreadsheet. This demo ships a sample —
[`sample-poam.xlsx`](sample-poam.xlsx) (sheet `Open POA&M Items`, row 5 headers, two k8s weaknesses;
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
**[`expected-output/scenario2-xlsx-to-poam.json`](expected-output/scenario2-xlsx-to-poam.json)**

> This path is **control-centric** (the FedRAMP template requires the `Controls` column). If your
> spreadsheet has no controls (e.g. a scanner export keyed only by check id), use Scenario 1
> instead — there the weakness is the unit and control-id is an optional anchor.

## Uninstall

Non-destructive — user-authored skills and user-defined MCP servers are never touched.

```bash
uvx compliance-authoring-skills uninstall --skill poam-authoring --target opencode
```
