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

## Inputs

- An **assessment result** — either the `assessment` skill's markdown table, or an OSCAL
  `assessment-results.json`. Only its **failed / non-compliant findings** become POA&M items.
- If no assessment result is available, take a list of weaknesses directly from the user.

## Sub-skills (follow in order)

1. [setup-env.md](setup-env.md) — **DO THIS FIRST.** Provision an isolated environment with the
   `trestle` library (uv → venv → hard stop). Never install trestle globally.
2. [from-assessment.md](from-assessment.md) — Extract failed findings → draft weakness rows;
   fill missing control/component context via a tiered fallback.
3. [poam-model.md](poam-model.md) — What an OSCAL POA&M is; the input JSON the builder consumes.
4. [build-poam.md](build-poam.md) — Run `build_poam.py` in the isolated env → generate + validate
   `plan-of-action-and-milestones.json`.
5. [poam-preview.md](poam-preview.md) — Render the POA&M as a human-readable markdown table for
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

## Key rules

- **Never pollute the global Python environment.** trestle is used only inside an isolated
  venv / `uv run` env. See [setup-env.md](setup-env.md).
- **Only failed findings become POA&M items.** Compliant controls are not weaknesses. If the
  assessment has zero failed findings, there is nothing to remediate — say so; do not fabricate.
- **The remediation plan is the user's, not yours.** Draft weaknesses from the assessment; ask the
  user for the plan/milestones/owner/dates.
- **OSCAL is the source of truth.** Always validate the generated JSON before presenting it.
- **No MCP required.** This skill builds the POA&M with the trestle library. A trestle MCP server,
  if present, is optional and only useful for extra validation.
