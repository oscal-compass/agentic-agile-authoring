# Path B — FedRAMP POA&M xlsx → OSCAL POA&M

Use this when the user already has a **FedRAMP-format POA&M spreadsheet** and wants the OSCAL
`plan-of-action-and-milestones.json`. Conversion is the trestle `xlsx-to-oscal-poam` task; the
converter auto-generates the `observations[]`/`risks[]` and cross-links each poam-item to them with
deterministic UUIDs.

> Most users take path A (assessment result → POA&M). Path B is for teams who maintain the FedRAMP
> POA&M xlsx directly. It is **control-centric**: the template's `Controls` column is required.

## Spreadsheet format (required)

- Sheet name: **`Open POA&M Items`** (override with `work_sheet_name` if different).
- Row 1: title. Rows 2–4: instructions (ignored). **Row 5: column headers. Row 6+: data.**
- **Required columns:** `POAM ID`, `Weakness Name`, `Weakness Description`, `Controls`.
- Common optional columns: `Weakness Detector Source`, `Weakness Source Identifier`, `CVE`,
  `Point of Contact`, `Original Risk Rating`, `Scheduled Completion Date`, `Planned Milestones`,
  `Service Name`, … (full FedRAMP set).

## Prerequisite

A trestle workspace (the task must run inside one): `trestle init` in the working dir, or pass its
path as `trestle_root`. Use the isolated env from [setup-env.md](setup-env.md).

## Convert — MCP tool if wired, else the venv trestle CLI

**1. If `mcp__trestle__trestle_task_xlsx_to_oscal_poam` is in the tool list**, call it:

```
mcp__trestle__trestle_task_xlsx_to_oscal_poam(
    title="<POA&M title>",
    version="<version>",
    xlsx_file="<abs path to .xlsx>",
    output_dir="<abs path to output dir>",
    trestle_root="<abs path to trestle workspace>",
    system_id="<optional>",           # work_sheet_name="Open POA&M Items" by default
)
```

**2. Otherwise (no MCP / 0 tools)**, run the same task via the venv trestle CLI. Write a config and
run it — identical result:

```ini
# poam.config
[task.xlsx-to-oscal-poam]
title = <POA&M title>
version = <version>
xlsx-file = <abs path to .xlsx>
output-dir = <abs path to output dir>
# optional: system-id = <...>   work-sheet-name = Open POA&M Items
```

```bash
# from inside the trestle workspace, with the isolated env's trestle:
.venv-poam/bin/trestle task xlsx-to-oscal-poam --config poam.config
# or: uv run --with 'compliance-trestle>=3.0' trestle task xlsx-to-oscal-poam --config poam.config
```

Both write `<output-dir>/plan-of-action-and-milestones.json`.

## Validate + preview

Validate the output (MCP `trestle_validate` if present, else `trestle validate -t
plan-of-action-and-milestones` in the venv), then render the markdown preview with
[poam-preview.md](poam-preview.md).

## Notes

- If the xlsx is **missing the required `Controls`** (e.g. it's a scanner export with only
  check ids), it does not fit the FedRAMP template — use **path A** instead
  ([from-assessment.md](from-assessment.md)), which treats the weakness as the unit and control-id
  as an optional anchor.
- `validate_required_fields` defaults to `warn`; set it to `on` to fail on missing required columns.
