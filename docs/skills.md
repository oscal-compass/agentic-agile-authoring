# Skills

## Overview

| Skill | Description | MCP dep |
|-------|-------------|---------|
| `catalog-authoring` | Import NIST OSCAL assets, edit parameters, generate CSV templates, deploy Markdown catalogs | `trestle` |
| `component-definition` | Map abstract controls to component-specific rules and validation checks; generate `component-definition.json` | `trestle` |
| `assessment` | Evaluate control compliance from component definitions and validation scan results | — |
| `poam-authoring` | Author an OSCAL POA&M from an assessment's failed findings — remediation plan, milestones, POC, due date | — |
| `compliance-catalog` | Convert a compliance-document PDF (law, regulation, standard) into a validated OSCAL Catalog | — |
| `compliance-mapping` | Map controls between two OSCAL Catalogs into an OSCAL Mapping Collection + browsable HTML report | — |
| `git-workflow` | Two-branch Git strategy for change tracking and PR review of compliance documents (opt-in) | — |

The lifecycle skills compose `catalog-authoring → component-definition → assessment →
poam-authoring`; `compliance-catalog` and `compliance-mapping` are framework-onboarding skills
(PDF → catalog, and catalog ↔ catalog) that produce the OSCAL Catalogs the lifecycle consumes.

Each skill is **invoked independently** by the harness from its `description` — there is no
fixed cross-skill ordering baked into an orchestrator. They compose naturally (a catalog feeds
a component definition, which feeds an assessment), and a [demo](architecture.md#demos)
expresses a particular end-to-end ordering when one is needed.

**MCP dependency**: each skill carries an `apm.yml` package manifest; a skill that needs an MCP
server declares it there under `dependencies.mcp`. On install, the installer (OpenAPM, via
the `compliance-authoring-skills` wrapper) wires the declared server into the target harness's native MCP config,
and on uninstall prunes it only when no remaining installed skill needs it — see
[Architecture](architecture.md#installation--mcp-wiring). Only `catalog-authoring` and
`component-definition` declare `dependencies.mcp` (`trestle`); the rest declare none.
`compliance-catalog` and `compliance-mapping` still use `trestle`, but as a local CLI/library for
validation — not the MCP server — so they wire no MCP dependency on install.

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

## POA&M Authoring

Turn the **open weaknesses** an assessment surfaced into a valid OSCAL **Plan of Action and
Milestones** (`plan-of-action-and-milestones.json`) — each weakness tracked with a remediation
plan, milestones, point of contact (POC), and due date. This is the last step of the lifecycle:
`catalog → component-definition → assessment → POA&M`.

### Two halves of the job

A POA&M is **assessment-seeded but authored with the user** — not a pure auto-conversion:

- **Drafted automatically from the assessment** (the *what's wrong*): POAM ID, weakness name and
  description, affected control ID(s), evidence.
- **Elicited from the user** (the *plan* — not in the assessment): remediation plan, milestones,
  POC, scheduled completion date, risk rating.

Draft the first half, then ask the user for the second half. Never invent remediation plans.

### Inputs (two paths)

- **A) Assessment result → POA&M (default).** An `assessment` skill markdown table or an OSCAL
  `assessment-results.json`. Only its **failed / non-compliant findings** become POA&M items. With
  no assessment result, take a list of weaknesses directly from the user.
- **B) FedRAMP POA&M `.xlsx` → POA&M.** Convert an existing FedRAMP-format spreadsheet with the
  trestle `xlsx-to-oscal-poam` task. Control-centric and less common; most users take path A.

### Workflow

1. Set up an **isolated environment** for the `trestle` library (uv → venv → hard stop; never
   install trestle globally).
2. Locate the assessment result and extract its **failed findings only**.
3. Draft the weakness rows (POAM ID, name/description, controls) and show them.
4. Ask the user for the remediation plan, milestones, POC, due date, and risk rating per weakness.
5. Write `poam_input.json`, then generate + validate with `build_poam.py` →
   `plan-of-action-and-milestones.json` (confirm `trestle validate` says **VALID**).
6. Preview the result as a markdown table and confirm with the user.

### Key rules

- **Never pollute the global Python environment** — trestle runs only inside an isolated
  venv / `uv run` env.
- **Only failed findings become POA&M items.** If the assessment has zero failed findings, there is
  nothing to remediate — say so; do not fabricate.
- **Validation is MCP-optional**: use `mcp__trestle__trestle_validate` if the tool is wired,
  otherwise the venv trestle library/CLI. Same for the xlsx conversion. Treat the pass/fail result
  identically across both paths — the MCP server is a runtime convenience, not a declared
  dependency.

---

## Compliance Catalog

Convert a compliance-document PDF (law, regulation, industry standard) into a validated OSCAL
Catalog JSON, through an iterative loop between a **deterministic extraction script**
(`generate.py`) and a **comprehensive validator** (`validate.py`, 17 rules + trestle). Use it to
ingest a new framework into the OSCAL ecosystem, or to regenerate a catalog from a revised PDF while
keeping control IDs stable.

### Inputs

- `input_pdf` (required): the source PDF.
- `output_dir` (required): where `generate.py`, `validate.py`, `catalog.json`, `merged.txt`, and
  `pages/` are written.
- `reference_catalog` (optional): an existing catalog to merge metadata from when maintaining
  multiple versions of the same document.

### What counts as a control

OSCAL defines a control as a *requirement or guideline that reduces risk* — not "any numbered thing
in the document." Definitions, administrative articles (commencement dates, short titles), and other
non-normative units are **not** controls and must not survive into the final catalog. Extraction
stays mechanical and complete (extract every numbered unit); a separate, reviewable exclusion pass
(`excluded_units.json`) removes the non-requirements.

### Key rules

- **No hardcoding of catalog content.** The point of a script is to avoid hallucination — titles
  and text must be regex-captured from the PDF, never from static lookup tables. Only extraction
  parameters (`CONFIG`, `PATTERNS`) and non-extractable document metadata may be hand-set.
- **No external LLM API** — all semantic judgment (structure interpretation, CONFIG tuning, gap
  classification) is the agent's own reasoning.
- Uses `trestle` as a local CLI/library for validation, so it declares **no MCP dependency**.
  System deps: `poppler` + `tesseract` (for `pdf2image` / OCR fallback).

---

## Compliance Mapping

Map controls between two OSCAL Catalogs and emit an OSCAL **Mapping Collection**
(`mapping_collection.json`) plus a browsable HTML report. Use it to compare frameworks, show
coverage of one framework by another, or refresh a mapping after either catalog changes. The system
separates **adaptive agent judgment** (thresholds, parallelism) from a **deterministic pipeline**
(ingest → blocking → judge → score → aggregate → emit → validate + report).

### Inputs

- `source_catalog` (required): the framework whose coverage you want to show.
- `target_catalog` (required): the reference framework.
- `output_dir` (required): all intermediate and final artifacts.
- `mapping_spec` (optional): a JSON/YAML profile overriding thresholds, relationship vocabulary, or
  blocking K. Defaults: confidence ≥ 0.75, coverage ≥ 0.15, K = 20. Relationship types:
  `intersects-with` (default), `equivalent-to`, `superset-of`, `subset-of`, `no-relationship`.

### How it runs

- **No external LLM API.** Embedding and nearest-neighbor search run **locally** via
  `sentence-transformers` and FAISS (`faiss-cpu` optional — falls back to a pure-numpy cosine
  search). No API key required.
- The one LLM-driven stage (**Judge**) is delegated to **subagents spawned via the harness's native
  subagent tool** (`Task` on Claude, `task` on OpenCode) — one per judge chunk, in parallel. No
  external LLM call is ever made.
- Uses `trestle` as a local CLI for the final validation stage, so it declares **no MCP
  dependency**.

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
