---
name: catalog-to-assessment
skills: [catalog-authoring, component-definition, assessment]
---

# Scenario: catalog → component → assessment

The full OSCAL authoring lifecycle end-to-end, in natural language: tailor a NIST SP 800-53
catalog, map its controls to a Kubernetes component, and generate an assessment result — driven
by three installed skills, no orchestrator persona.

https://github.com/user-attachments/assets/628ebb15-f9cc-4cef-88de-86f026bce499

## Install

Prerequisite: **[`uv`](https://docs.astral.sh/uv/)** (provides `uvx`; also runs the `uvx`-based
`trestle` MCP server). No Node required.

```bash
# skills + MCP wiring, one step — into Claude Code:
uvx ag-au-skills install --scenario catalog-to-assessment --target claude

# …or into OpenCode:
uvx ag-au-skills install --scenario catalog-to-assessment --target opencode
```

This copies `catalog-authoring`, `component-definition`, and `assessment` into the harness's
native skill dir and wires the `trestle` MCP server (declared by the first two) into the harness's
native MCP config. Open the target project in the harness so it picks up the skills + `trestle`.

## Walkthrough

Give the agent each prompt in order, in an empty working directory.

### Step 1 — Create a custom catalog

> Create regulatory controls for our organization, based on NIST SP 800-53 and limited to
> access control.

The agent scopes the work to NIST SP 800-53 access control (AC), prepares a regulatory document,
and asks whether you want to customize the wording. (`catalog-authoring`)

### Step 2 — Generate the OSCAL catalog

> For now, proceed with the default wording. Please create the OSCAL JSON for this custom catalog.

`catalogs/ac_controls_catalog/catalog.json` is created (valid OSCAL — `trestle validate`).
(`catalog-authoring`)

### Step 3 — Define a component (Kubernetes)

> Apply our organization's regulatory controls (catalogs/ac_controls_catalog) to Kubernetes.
> At this stage, please create the component definition.

The agent produces a human-readable implementation guide (Markdown + CSV) per control, then the
OSCAL `component-definition.json` (valid OSCAL), referencing the catalog from Step 2.
(`component-definition`)

### Step 4 — Generate assessment results

> Using the component definition, create the assessment results.

Provide your security tool's scan output and the agent generates an assessment posture; with no
scan output it generates a mock posture and says so. (`assessment`)

## Uninstall

Non-destructive — a shared MCP server is pruned only once no remaining installed skill needs it;
user-authored skills and user-defined MCP servers are never touched.

```bash
# remove one skill:
uvx ag-au-skills uninstall --skill assessment --target claude

# remove the whole scenario set:
uvx ag-au-skills uninstall --skill catalog-authoring,component-definition,assessment --target claude
```
