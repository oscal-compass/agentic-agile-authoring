---
name: poam-authoring
skills: [poam-authoring]
---

# Demo: assessment result → POA&M

Turn the **non-compliant findings** of an assessment result into a valid OSCAL **Plan of Action
and Milestones** (`plan-of-action-and-milestones.json`), in natural language — one installed skill,
no orchestrator persona. This is the remediation-planning step of the OSCAL lifecycle.

## Install

Prerequisite: **[`uv`](https://docs.astral.sh/uv/)** (provides `uvx`; `poam-authoring` also uses it
to run the `trestle` **library** in an isolated environment — no global install). No Node required.

```bash
# skill only, one step — into OpenCode:
uvx compliance-authoring-skills install --demo poam-authoring --target opencode

# …or into Claude Code:
uvx compliance-authoring-skills install --demo poam-authoring --target claude
```

This copies `poam-authoring` into the harness's native skill dir. Unlike the catalog/component
skills, `poam-authoring` declares **no MCP server** — it builds the POA&M with the `trestle` Python
library inside an isolated env (`uv` or a venv; never a global install), so nothing is wired into
the harness's MCP config. Open the target project in the harness so it picks up the skill.

## Walkthrough

Run these in a working directory that has an assessment result. This demo ships a sample OSCAL
assessment result — [`assessment-results.json`](assessment-results.json) (a valid
`assessment-results` for the `k8s-prod` cluster; copy it into your working dir first).

### Step 1 — Ask for a POA&M

> From assessment-results.json, create a Plan of Action and Milestones (POA&M) for the
> non-compliant findings.

The agent reads the OSCAL assessment result, keeps **only the findings whose status is
`not-satisfied`** (here AC-2, AU-2, and SC-8; the satisfied AC-3 and CM-6 are skipped), and drafts
one weakness per failed finding — naming the *failure*, not the requirement (e.g. "MFA not enforced
on admin accounts") and carrying the finding's evidence and control id across. It then asks you for
the remediation details the assessment does not contain. (`poam-authoring`)

### Step 2 — Provide the remediation plan

> AC-2: enforce MFA via the IdP for all admin bindings; milestone "Enable MFA policy in IdP" by
> 2026-10-01; owner Platform Security Team; complete by 2026-12-31; risk High.
> AU-2: configure the kube-apiserver audit policy; milestone "Deploy audit policy" by 2026-11-01;
> owner Platform Team; complete by 2026-11-30; risk Moderate.

The agent provisions an isolated environment (prefers `uv`, else a local venv; if neither works it
stops and asks you to enable one rather than polluting your Python), writes `poam_input.json`, runs
the skill's `build_poam.py`, and produces `poam/plan-of-action-and-milestones.json` — valid OSCAL
(`trestle validate`). It then shows a markdown preview of the POA&M for you to confirm.
(`poam-authoring`)

The result is a schema-valid OSCAL POA&M with each weakness carrying its controls, remediation
plan, milestones, owner, due date, and risk rating.

## Uninstall

Non-destructive — user-authored skills and user-defined MCP servers are never touched.

```bash
uvx compliance-authoring-skills uninstall --skill poam-authoring --target opencode
```
