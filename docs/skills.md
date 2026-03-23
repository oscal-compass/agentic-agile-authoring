# Skills

## Overview

| Skill | Description |
|-------|-------------|
| `catalog-authoring` | Import NIST OSCAL assets, edit parameters, generate CSV templates, deploy Markdown catalogs |
| `component-definition` | Map abstract controls to component-specific rules and validation checks; generate `component-definition.json` |
| `assessment` | Evaluate control compliance from component definitions and validation scan results |
| `git-workflow` | Two-branch Git strategy for change tracking and PR review of compliance documents (opt-in) |

---

## Catalog Authoring

Support custom catalog operations using NIST OSCAL catalogs and profiles, from parameter editing to Markdown deployment using trestle MCP tools.

### Main Tasks

1. Research and import OSCAL assets (catalogs, profiles)
2. Parameter editing and CSV template generation
3. Markdown deployment and assembly
4. Organizational distribution and data preparation

### Workflow

- **Phase 1: Setup** — Asset acquisition and structure organization
- **Phase 2: Editing & Embedding** — Parameter editing to profile/catalog deployment

### Rules

- Always use trestle MCP tools, never CLI commands
- Never use `trestle_root` parameter — omit it from all MCP tool calls
- Use profile-based control selection — edit profile's `include-controls` to specify desired controls
- Confirm CSV content with user before parameter reflection
- After markdown conversion, never read `catalog.json` directly

---

## Component Definition

Given a component (a concrete system element such as a service, OS, or audit tool), translate high-level abstract controls defined in an OSCAL catalog or profile into component-specific, actionable control implementations.

### Concepts

- **Service component**: implements controls directly (firewall, OS, middleware, application)
- **Validation component**: verifies that another component's rules are actually enforced (scanner, audit tool, monitoring agent)

### Workflow

1. Confirm the trestle workspace and target profile/catalog with the user
2. Identify components and their types (ask user for validation component if not specified)
3. For each component, enumerate rules and map them to control IDs
4. **Author CSV using Python `csv.writer()`**
5. **Generate markdown preview** for user review
6. Confirm CSV content with the user before generating
7. Invoke `trestle_task_csv_to_oscal_cd` to produce `component-definition.json`

### Key Learnings

Most csv-to-oscal failures are due to CSV authoring errors, not the conversion tool:

- **Always use Python `csv.writer()`** — never manual string concatenation
- **Verify column counts programmatically** before invoking trestle
- **All rows must have identical column counts** — this is the #1 failure cause
- **Validate namespace URLs** — must be valid URLs with scheme

---

## Assessment

Given a component definition with service component rules and validation component checks, generate an OSCAL assessment that evaluates whether controls are satisfied.

### Control-Rule-Check Mapping

The mapping chain is:

```
Control ID -> Service Component Rule -> Validation Component Check -> Compliance Status
```

Example:

- Control: AC-2 (Account Management)
- Rule: "All user accounts must have MFA enabled"
- Check: "Scan for accounts without MFA"
- Status: Compliant (0 accounts without MFA found)

### Workflow

1. Confirm the component definition source
2. Load component definition JSON or markdown
3. Extract service component rules and their control mappings
4. Extract validation component checks and their rule mappings
5. Build control-rule-check mapping matrix
6. For each control, evaluate compliance based on validation check results
7. Generate assessment table with compliance status and evidence
8. Output in markdown table format

---

## Git Workflow

!!! warning "Opt-in Only"
    This workflow is **not executed by default**. Only use when the user explicitly requests Git version control, PR creation, or change tracking.

Provides version control and change tracking for OSCAL compliance documents using a two-branch strategy.

### Branch Strategy

- `<id>-initial`: Baseline branch containing the initial state
- `<id>-review`: Review branch containing changes

### Phases

1. **Setup** (after markdown deployment): Create baseline branch
2. **Review** (after editing completion): Create review branch and pull request

### Rules

- Never execute Git operations unless user explicitly requests
- Always confirm branch identifier with user before creating branches
- Protect `<id>-initial` branch from direct commits
- Squash commits before PR creation for clean history
