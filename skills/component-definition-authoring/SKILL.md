---
name: component-definition-authoring
description: Translate high-level abstract controls defined in an OSCAL catalog/profile into concrete, component-specific control implementations. Use when user wants to define how a specific component (service, tool, middleware) satisfies controls, author component definitions, or generate OSCAL component-definition.json from CSV.
argument-hint: Optional component name or type (e.g., "firewall", "scanner")
license: Complete terms in LICENSE.txt
---

# Component Definition Authoring

## Purpose

Given a component (a concrete system element such as a service, OS, or audit tool), translate the high-level abstract controls defined in an OSCAL catalog or profile into component-specific, actionable control implementations.

This skill bridges the gap between **what a control requires in the abstract** and **how a specific component fulfills or checks it in practice**.

## Concepts

- **service component**: implements controls directly (firewall, OS, middleware, application)
- **validation component**: verifies that another component's rules are actually enforced (scanner, audit tool, monitoring agent)

A component definition captures rules per component, maps them to catalog controls, and optionally links validation checks to service rules.

## Main Tasks

1. Identify which components are in scope and their type (service / validation)
2. Map catalog/profile controls to component-level rules
3. Author CSV expressing those rules and mappings
4. Generate `component-definition.json` from the CSV

## Sub-skills

- [csv-authoring.md](csv-authoring.md) — **START HERE** — Detailed guide to authoring CSV files for component definitions using Python csv.writer()
- [csv-to-markdown.md](csv-to-markdown.md) — Generate human-readable markdown preview of component definition CSV before OSCAL conversion
- [csv-to-oscal-cd.md](csv-to-oscal-cd.md) — Convert an authored CSV into an OSCAL component definition using the `trestle_task_csv_to_oscal_cd` MCP tool

## Workflow

1. Confirm the trestle workspace and target profile/catalog with the user
2. Identify components and their types (ask the user for the validation component if it is not
   specified and someone is there to answer)
3. For each component, enumerate the rules and map them to control IDs
4. **Author CSV using Python csv.writer()** (see [csv-authoring.md](csv-authoring.md) for detailed guidance)
   - Use Python lists, not manual string concatenation
   - Verify column counts and namespace URLs programmatically
   - Never use `write_to_file` for CSV construction
5. **Generate markdown preview** using `csv_to_markdown.py` to show component vs control vs rule/check mappings
6. Confirm CSV content with the user before generating — when a human is in the loop; otherwise
   see [Running with no human in the loop](#running-with-no-human-in-the-loop)
7. Invoke `trestle_task_csv_to_oscal_cd` to produce `component-definition.json`

## Running with no human in the loop

The confirmation steps above assume someone is watching. Settle that question once, at the
start: the run is unattended when the request already fixes the decisions it would otherwise
ask about (the prompt, or an instructions file in the workspace that it points at, pins them),
when it is a recorded or batch run, or when the user has said to go ahead without asking.

When the run is unattended:

- **Do not stop at the approval gate.** Still generate the markdown preview — it is the record of
  what was converted — then run the conversion in the same pass.
- **Let the conversion be the review.** `validate_controls="on"` and the required-column checks
  reject exactly the rows a reviewer would have caught. Fix the row it names and run it again.
- **Where a question would have supplied a missing fact**, take it from the pinned instructions,
  and name the choice you made in your summary. Do not invent one silently.
- **Never ask a question that cannot be answered.** With no human present a question does not
  slow the run down, it ends it.

## Key Learnings

### CSV Authoring is the Critical Step

**Most csv-to-oscal failures are due to CSV authoring errors, not the conversion tool.**

See [csv-authoring.md](csv-authoring.md) for comprehensive guidance. Key points:
- **Always use Python `csv.writer()`** — never manual string concatenation
- **Verify column counts programmatically** before invoking trestle
- **All rows must have identical column counts** — this is the #1 failure cause
- **Use Python lists, not strings** — ensures proper escaping and alignment

### Why csv-to-oscal Fails: Root Causes

**Error 1: Column Count Mismatch**
- Cause: Manual CSV construction creates inconsistent column counts
- Fix: Use Python `csv.writer()` to guarantee all rows have same column count
- Prevention: Verify programmatically before invoking trestle

**Error 2: Missing Required Columns**
- Cause: Validation component rows omit service-only columns (e.g., `$$Control_Id_List`)
- Fix: Include all columns in header; leave service-only columns empty for validation rows
- Prevention: Use unified schema with all columns present

**Error 3: Invalid Namespace URLs**
- Cause: `$$Namespace` contains non-URL values (e.g., `Kubernetes` instead of `https://kubernetes.io`)
- Fix: Ensure all namespace values are valid URLs with scheme
- Prevention: Validate URLs programmatically before invoking trestle

**Error 4: Column Position Misalignment**
- Cause: Manual text construction causes columns to shift between rows
- Fix: Use Python `csv.writer()` which maintains consistent column indexing
- Prevention: Never manually concatenate CSV strings

### CSV to Markdown Preview

Use Python script to convert CSV into readable markdown tables showing:
- Service component rules mapped to controls
- Validation component checks mapped to rules
- Clear visualization of control → rule → check relationships

This helps users review the mapping before OSCAL generation.

### Workflow Improvement: Markdown Preview Before OSCAL Conversion

Generate markdown preview **before** attempting csv-to-oscal conversion. This allows:
- User to review control-to-rule mappings
- Early detection of mapping errors
- Approval before OSCAL generation, where there is someone to give it
- Reduced wasted conversion attempts on invalid CSV

Order: CSV authoring → Markdown preview → user approval, when a human is in the loop → OSCAL
conversion. Unattended, the preview is still written and the conversion follows in the same
pass.

### Validation Component Integration

Ask the user which validation tool/component they use (e.g., Kyverno, Falco, OPA). With no human
in the loop, take the engines from the pinned instructions — they are part of the decomposition,
not a detail to invent.
Include validation component in the same CSV alongside service component.
Validation component checks should reference the service component rules they verify.
