---
name: poam-authoring
description: Author an OSCAL Plan of Action and Milestones (POA&M). Use when the user has an assessment result (or lists open weaknesses) and wants a remediation plan tracking each weakness with a plan, milestones, owner, and due date — or wants to pre-define the POA&M from a component-definition.json (one item per rule/check, remediation up front, local-definitions filled) and later reference those items from an assessment. Output is a valid plan-of-action-and-milestones.json.
argument-hint: Optional path to an assessment result (markdown or OSCAL) or a system name
license: Complete terms in LICENSE.txt
---

# POA&M Authoring

## Purpose

Turn the **open weaknesses** an assessment surfaced into a valid OSCAL **Plan of Action and
Milestones** (`plan-of-action-and-milestones.json`) — each weakness tracked with a remediation
plan, milestones, owner (POC), and due date.

This is the last step of the lifecycle: `catalog → component-definition → assessment → **POA&M**`.

## Two halves of the job (read this first)

A POA&M is **assessment-seeded but authored with the user** — it is NOT a pure auto-conversion:

- **Drafted automatically from the assessment** (the *what's wrong*): POAM ID, weakness name &
  description, affected control ID(s), evidence.
- **Elicited from the user** (the *plan* — not in the assessment): remediation plan, milestones,
  point of contact, scheduled completion date, risk rating.

Draft the first half, then ask the user for the second half. Do not invent remediation plans.

## Inputs (four paths)

- **A) Assessment result → POA&M (default).** An `assessment` skill markdown table, or an OSCAL
  `assessment-results.json`. Only its **failed / non-compliant findings** become POA&M items. If no
  assessment result is available, take a list of weaknesses directly from the user.
- **B) FedRAMP POA&M `.xlsx` → POA&M.** The user already has a FedRAMP-format POA&M spreadsheet
  (`Open POA&M Items` sheet; required columns `POAM ID`, `Weakness Name`, `Weakness Description`,
  `Controls`). Convert it with the trestle `xlsx-to-oscal-poam` task — see
  [xlsx-to-oscal-poam.md](xlsx-to-oscal-poam.md). This path is control-centric (Controls required by
  the FedRAMP template) and less common; most users take path A.
- **C) Component-definition → pre-defined POA&M (+ optional assessment linking).** A
  `component-definition.json` (from the `component-definition` skill) declares, per component, the
  **rules/checks** mapped to controls. Because each check is a testable assertion, the full weakness
  catalog is known *before* assessment: **pre-define** one poam-item per rule/check with remediation
  authored up front, filling `local-definitions` from the component-definition
  ([from-component-definition.md](from-component-definition.md)). Then, at assessment time,
  **reference** those pre-existing items — layer the assessment results in as observations/findings
  linked to the matching item, creating no new items ([link-assessment.md](link-assessment.md)).
  This closes the loop `component-definition → POA&M → assessment`. Path A is reactive
  (findings → items); path C is pre-defined (items → then assessed).
- **D) Scan-tool remediation data → POA&M (reference-driven).** A scanner/security tool emits its own
  **remediation data** (fix + severity + assets + owners/dates per weakness), to be held as a POA&M
  (often for another platform). You learn the tool's format and the desired output shape from a
  **sample/reference the user provides**, then map each record onto a pass-through `risk`
  (remediation in `risk.remediations[]`, tool-specific fields as free-form props) — **no per-tool
  code** ([from-scan-remediations.md](from-scan-remediations.md)). Path D is path A with the
  remediation/props filled from a customer reference rather than fixed fields.

## Sub-skills (follow in order)

1. [setup-env.md](setup-env.md) — **DO THIS FIRST.** Provision an isolated environment with the
   `trestle` library (uv → venv → hard stop). Never install trestle globally.
2. [from-assessment.md](from-assessment.md) — (path A) Extract failed findings → draft weaknesses;
   resolve control-id from the assessment / a mapping / a `component-definition.json` / a catalog.
3. [poam-model.md](poam-model.md) — What an OSCAL POA&M is; the input JSON the builder consumes.
4. [build-poam.md](build-poam.md) — (path A) Run `build_poam.py` in the isolated env → generate +
   validate `plan-of-action-and-milestones.json`.
5. [from-scan-remediations.md](from-scan-remediations.md) — (path D) Map a scan tool's remediation
   export onto pass-through `risk`/props from a user-provided reference/sample, then build via path A.
   Reference-driven, no per-tool code.
6. [xlsx-to-oscal-poam.md](xlsx-to-oscal-poam.md) — (path B) Convert a FedRAMP POA&M xlsx via the
   trestle `xlsx-to-oscal-poam` task (MCP tool if wired, else the venv trestle CLI).
7. [from-component-definition.md](from-component-definition.md) — (path C, phase 1) Join a
   `component-definition.json`'s rules/checks → a **pre-defined POA&M** (one item per rule/check +
   `local-definitions`), via `build_poam.py from-component-definition`.
8. [link-assessment.md](link-assessment.md) — (path C, phase 2) Layer an `assessment-results.json`
   onto the pre-defined POA&M — observations/findings that **reference** the existing items (matched
   by check-id), via `build_poam.py link-assessment`. No new items.
9. [poam-preview.md](poam-preview.md) — Render the POA&M as a human-readable markdown table for
   review (there is no reverse trestle task — we build the preview ourselves).
10. [trestle-workspace.md](trestle-workspace.md) — **(optional)** When the cwd is (or should be) a
    trestle workspace: detect/`trestle init` it, locate inputs deterministically from the directory
    layout (don't ask for paths), and write the POA&M straight to its canonical path. Orthogonal to
    paths A/B/C.

## Workflow

1. **Set up the isolated environment** ([setup-env.md](setup-env.md)). If neither `uv` nor
   `python -m venv` works, STOP and ask the user to enable one — do not fall back to a global
   install.
   - *(optional)* If the cwd is a **trestle workspace** (or the user wants one), first read
     [trestle-workspace.md](trestle-workspace.md): resolve inputs from the directory layout instead
     of asking for paths, and write the POA&M to its canonical path. This is orthogonal to the path
     you run below.
2. **Locate the assessment result** and extract its **failed findings** only
   ([from-assessment.md](from-assessment.md)). If control/component context is missing, ask the
   user or recover it from the catalog/component-definition.
3. **Draft the weakness rows** (POAM ID, weakness name/description, controls) and show them.
4. **Ask the user** for the remediation plan, milestones, POC, due date, and risk rating per
   weakness.
5. **Write `poam_input.json`** (shape in [poam-model.md](poam-model.md)).
6. **Generate + validate** with `build_poam.py` ([build-poam.md](build-poam.md)) →
   `plan-of-action-and-milestones.json`. **Default to a standalone file** (no trestle workspace);
   validate it in place with `trestle partial-object-validate` (the builder also round-trips it via
   `oscal_read`). Only create a workspace (`trestle init` + `trestle validate -t`) if the user wants
   the workspace shape — ask if unsure ([trestle-workspace.md](trestle-workspace.md)).
7. **Preview** the result as markdown ([poam-preview.md](poam-preview.md)) and confirm with the user.

(For path B, replace steps 2–6 with [xlsx-to-oscal-poam.md](xlsx-to-oscal-poam.md), then preview.)

(For path D, replace steps 2–4 with [from-scan-remediations.md](from-scan-remediations.md): derive
the field mapping from the user's remediation export + reference/sample, then write `poam_input.json`
with pass-through `risk`/`extra_props` and build as in steps 5–7.)

**Path C (component-definition-driven)** — after step 1 (setup-env):

- **Phase 1 — pre-define.** Read the `component-definition.json`, join its rules/checks to controls
  and validation components, author remediation up front, and build the **pre-defined POA&M** with
  `build_poam.py from-component-definition` ([from-component-definition.md](from-component-definition.md)).
  The static weakness/risk/remediation content is **consolidated once into `local-definitions`**,
  grouped per check by the CD's verbatim `remarks` rule-set token (merged from the CD props and any
  `--remediations` file, so it lands there even when the content came from an external file); each
  poam-item and risk links back via a **`rule-id`** prop instead of duplicating the content.
- **Phase 2 — link (when an assessment exists).** Layer an `assessment-results.json` onto the
  pre-defined POA&M with `build_poam.py link-assessment` — each finding references the existing
  poam-item for its check ([link-assessment.md](link-assessment.md)). No new items are created.
- **Filling optional fields** (weakness/risk/remediation) resolves in order: (1) CD rule-set props,
  (2) the assessment-results after linking, (3) ask the user per missing field — never invent them.
- Validate + preview each artifact as in steps 6–7. Both the pre-defined and the linked POA&M are
  independently valid OSCAL.

## Validation (MCP-optional — use it if present, else the venv trestle)

The trestle MCP is a runtime convenience, not a dependency. Decide at run time:

1. If `mcp__trestle__trestle_validate` is in the tool list, validate the POA&M with it.
2. Otherwise, validate with the venv trestle library/CLI (`oscal_read` round-trip, or
   `trestle validate -t plan-of-action-and-milestones`).

Treat the result schema and pass/fail identically across both paths. The same rule applies to the
xlsx conversion: use `mcp__trestle__trestle_task_xlsx_to_oscal_poam` if wired, else the venv
`trestle task xlsx-to-oscal-poam` (see [xlsx-to-oscal-poam.md](xlsx-to-oscal-poam.md)).

## Key rules

- **Never pollute the global Python environment.** trestle is used only inside an isolated
  venv / `uv run` env. See [setup-env.md](setup-env.md).
- **Only failed findings become POA&M items (paths A/B).** Compliant controls are not weaknesses.
  If the assessment has zero failed findings, there is nothing to remediate — say so; do not
  fabricate.
- **Path C is different — the catalog is pre-defined.** Here every rule/check in the
  component-definition becomes a poam-item (a *potential* weakness) up front, with control-id known
  from the component-definition. A linked assessment then marks each item open (`not-satisfied`) or
  satisfied via a finding; items are **kept regardless** and never invented at assessment time.
- **The remediation plan is the user's, not yours.** Draft weaknesses from the assessment (or the
  component-definition, path C); ask the user for the plan/milestones/owner/dates.
- **OSCAL is the source of truth.** Always validate the generated JSON before presenting it.
- **In a trestle workspace, don't ask for paths.** If the cwd is a workspace (`.trestle/` present),
  resolve inputs from the directory layout and write the POA&M to its canonical path
  ([trestle-workspace.md](trestle-workspace.md)). Optional — only when a workspace is in play.
- **Default to a standalone POA&M file; don't create a workspace unasked.** Most users just want one
  `plan-of-action-and-milestones.json`. Validate it in place (`trestle partial-object-validate`, plus
  the builder's `oscal_read` round-trip) — **never `trestle init` the user's directory just to
  validate** (it litters it with `.trestle/` + model folders + `dist/`). If you need `trestle
  validate -t`, use a throwaway temp workspace; only make the user's own dir a workspace when it
  already is one or they explicitly want that shape ([build-poam.md](build-poam.md)).
- **MCP is optional, never required.** Everything works with the venv trestle (library/CLI). If a
  trestle MCP server is wired, prefer its tools; if it is absent or fails to start (0 tools), fall
  back to the venv — same result either way. See the Validation section.
