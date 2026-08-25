---
name: poam-authoring
description: Author an OSCAL Plan of Action and Milestones (POA&M) from the failed findings of an assessment result. Use when the user has an assessment result (or lists open weaknesses) and wants a remediation plan — a POA&M — that tracks each weakness with a plan, milestones, owner, and due date, output as a valid plan-of-action-and-milestones.json.
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

## Inputs (two paths)

- **A) Assessment result → POA&M (default).** An `assessment` skill markdown table, or an OSCAL
  `assessment-results.json`. Only its **failed / non-compliant findings** become POA&M items. If no
  assessment result is available, take a list of weaknesses directly from the user.
- **B) FedRAMP POA&M `.xlsx` → POA&M.** The user already has a FedRAMP-format POA&M spreadsheet
  (`Open POA&M Items` sheet; required columns `POAM ID`, `Weakness Name`, `Weakness Description`,
  `Controls`). Convert it with the trestle `xlsx-to-oscal-poam` task — see
  [xlsx-to-oscal-poam.md](xlsx-to-oscal-poam.md). This path is control-centric (Controls required by
  the FedRAMP template) and less common; most users take path A.

## Sub-skills (follow in order)

1. [setup-env.md](setup-env.md) — **DO THIS FIRST.** Provision an isolated environment with the
   `trestle` library (uv → venv → hard stop). Never install trestle globally.
2. [from-assessment.md](from-assessment.md) — (path A) Extract failed findings → draft weaknesses;
   resolve control-id from the assessment / a mapping / a `component-definition.json` / a catalog.
3. [poam-model.md](poam-model.md) — What an OSCAL POA&M is; the input JSON the builder consumes.
4. [build-poam.md](build-poam.md) — (path A) Run `build_poam.py` in the isolated env → generate +
   validate `plan-of-action-and-milestones.json`.
5. [xlsx-to-oscal-poam.md](xlsx-to-oscal-poam.md) — (path B) Convert a FedRAMP POA&M xlsx via the
   trestle `xlsx-to-oscal-poam` task (MCP tool if wired, else the venv trestle CLI).
6. [poam-preview.md](poam-preview.md) — Render the POA&M as a human-readable markdown table for
   review (there is no reverse trestle task — we build the preview ourselves).

## Workflow

1. **Set up the isolated environment** ([setup-env.md](setup-env.md)). If neither `uv` nor
   `python -m venv` works, STOP and ask the user to enable one — do not fall back to a global
   install.
2. **Locate the assessment result** and extract its **failed findings** only
   ([from-assessment.md](from-assessment.md)). If control/component context is missing, ask the
   user or recover it from the catalog/component-definition.
3. **Draft the weakness rows** (POAM ID, weakness name/description, controls) and show them.
4. **Ask the user** for the remediation plan, milestones, POC, due date, and risk rating per
   weakness.
5. **Write `poam_input.json`** (shape in [poam-model.md](poam-model.md)).
6. **Generate + validate** with `build_poam.py` ([build-poam.md](build-poam.md)) →
   `plan-of-action-and-milestones.json`. Confirm `trestle validate` says **VALID**.
7. **Preview** the result as markdown ([poam-preview.md](poam-preview.md)) and confirm with the user.

(For path B, replace steps 2–6 with [xlsx-to-oscal-poam.md](xlsx-to-oscal-poam.md), then preview.)

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
- **Only failed findings become POA&M items.** Compliant controls are not weaknesses. If the
  assessment has zero failed findings, there is nothing to remediate — say so; do not fabricate.
- **The remediation plan is the user's, not yours.** Draft weaknesses from the assessment; ask the
  user for the plan/milestones/owner/dates.
- **OSCAL is the source of truth.** Always validate the generated JSON before presenting it.
- **MCP is optional, never required.** Everything works with the venv trestle (library/CLI). If a
  trestle MCP server is wired, prefer its tools; if it is absent or fails to start (0 tools), fall
  back to the venv — same result either way. See the Validation section.
