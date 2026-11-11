Use the `trestle_task_csv_to_oscal_cd` MCP tool to convert a CSV file into an OSCAL component definition.

Key points are summarized below. For the full spec, see
`docs/tutorials/Transformers_and_Tasks/csv_to_oscal_cd.md` in the compliance-trestle repository;
the installed task also describes itself, column names and notes included, via
`trestle task csv-to-oscal-cd --info`, which has the advantage of matching the version you have.

## CSV authoring rules

**Row layout:** Row 1 = headings, Row 2 = descriptions (not parsed), Row 3+ = data.

**Column prefixes:**
- `$$` = required column
- `$`  = optional column
- `#`  = comment column (ignored)

## Columns

trestle matches columns **by name, not by position**: `_CsvMgr.get_col_index()` searches the
header row for the name, after stripping leading `$` and title-casing each word. Any order
works, and the order below is only a readable convention — the demo's own CSV interleaves the
parameter columns and converts cleanly.

What does matter: every required name is present (a missing one fails with
`Missing columns: [...]`), the names are spelled the way trestle spells them, and every row has
the same number of fields as the header.

**Service Component Columns (Row 1):**
```
$$Component_Title	$$Component_Description	$$Component_Type	$$Control_Id_List	$$Rule_Id	$$Rule_Description	$$Profile_Source	$$Profile_Description	$$Namespace	$Target_Component
```

**Validation Component Columns (Row 1):**
```
$$Component_Title	$$Component_Description	$$Component_Type	$$Control_Id_List	$$Rule_Id	$$Rule_Description	$Check_Id	$Check_Description	$$Profile_Source	$$Profile_Description	$$Namespace	$Target_Component
```

**Combined (Service + Validation in one CSV):**
```
$$Component_Title	$$Component_Description	$$Component_Type	$$Control_Id_List	$$Rule_Id	$$Rule_Description	$Check_Id	$Check_Description	$$Profile_Source	$$Profile_Description	$$Namespace	$Target_Component
```

**Key Points:**
- All rows (header, description, data) must have the same number of columns
- For service-only rows: leave `$Check_Id` and `$Check_Description` empty
- For validation-only rows: leave `$$Control_Id_List`, `$$Rule_Description`, `$$Profile_Source`, `$$Profile_Description` empty
- Column *names* must match; their order is free, and their case is normalised before matching
- A column name starting with `#` is dropped. Any other unrecognised column is **not** dropped —
  it becomes an extra property on the rule set, named after the column

**Component types and their column requirements:**

| Column | service | validation |
|--------|---------|------------|
| `$$Component_Title` | required | required |
| `$$Component_Description` | required | required |
| `$$Component_Type` | `service` | `validation` |
| `$$Rule_Id` | required | required |
| `$$Rule_Description` | required | ignored |
| `$$Profile_Source` | required — see below | ignored |
| `$$Profile_Description` | required | ignored |
| `$$Control_Id_List` | required | ignored |
| `$$Namespace` | required | required |
| `$Check_Id` | optional | **required** |
| `$Check_Description` | optional | **required** |
| `$Target_Component` | optional | recommended (prevents Rule_Id collisions) |

For validation type, leave `$$Rule_Description`, `$$Profile_Source`, `$$Profile_Description`, `$$Control_Id_List` empty — they are silently ignored.

### `$$Profile_Source` is a profile reference, not a label

It is not the control family and not a free-text source name. trestle hands every distinct
`$$Profile_Source` value to `ProfileResolver.get_resolved_profile_catalog()`, and the value lands
unchanged as the `source` of the generated `control-implementation`. Use the workspace-relative
path of the profile the controls were selected in — `profiles/<name>/profile.json` — or an
`https://` URL of a profile.

With `validate_controls="on"` (below) this is load-bearing: the control list is checked against
the catalog resolved from that profile, so a value that does not resolve fails the conversion
instead of validating anything. `$$Profile_Description` is free text describing that profile; it
becomes the `control-implementation` description, and two rows with the same source but different
descriptions produce two separate control implementations.

## When to write a service CSV vs a validation CSV

- **service**: the component *implements* controls (firewall, OS, middleware)
- **validation**: the component *checks* that another component's rules are met (scanner, audit tool)

Both types can coexist in one CSV and will be merged into a single `component-definition.json`.

## Example CSV skeletons

### Service

```
$$Component_Title,$$Component_Description,$$Component_Type,$$Rule_Id,$$Rule_Description,$$Profile_Source,$$Profile_Description,$$Control_Id_List,$$Namespace
<descriptions row>
MyApp,My application,service,rule-001,Rule description,profiles/myprofile/profile.json,NIST SP 800-53 Rev 5 selection for MyApp,ac-3,https://myorg.example.com
```

### Validation

```
$$Component_Title,$$Component_Description,$$Component_Type,$$Rule_Id,$$Rule_Description,$$Profile_Source,$$Profile_Description,$$Control_Id_List,$$Namespace,$Check_Id,$Check_Description,$Target_Component
<descriptions row>
MyScanner,Compliance scanner,validation,rule-001,,,,,https://myorg.example.com,check-001,Verify rule-001 is active,MyApp
```

## Parameters a rule needs

A rule that a policy template is generated from usually needs values — a signer identity, an
approved registry, a label key. Carry them in the optional parameter columns rather than burying
them in the rule description:

```
$Parameter_Id   $Parameter_Description   $Parameter_Value_Default   $Parameter_Value_Alternatives
```

- One set of four columns carries one parameter. For a second, third, … parameter on the same
  rule, repeat the four names with a **common suffix per set**: `$Parameter_Id_2`,
  `$Parameter_Description_2`, `$Parameter_Value_Default_2`, `$Parameter_Value_Alternatives_2`.
  trestle finds them by prefix, so the suffix only has to be consistent within its own set.
- `$Parameter_Value_Default` is the value that becomes the rule's set-parameter;
  `$Parameter_Value_Alternatives` is a comma-separated list of other allowed values.
- Parameter columns are **ignored on validation rows** — a parameter belongs to the service rule,
  not to the check that verifies it.
- A row with an empty `$Parameter_Id` carries no parameter and the other three are not read, so a
  rule that needs no parameter costs nothing.

## Invoking the MCP tool

```python
trestle_task_csv_to_oscal_cd(
    title="<component definition title>",
    version="<version>",
    csv_file="<absolute path to CSV>",
    output_dir="<absolute path to output dir>",
    trestle_root="<absolute path to trestle workspace>",
    validate_controls="on",
)
```

The tool generates the required INI config internally — do not ask the user for a config file path.

Pass `csv_file` and `output_dir` as absolute paths. **Pass `trestle_root` as well whenever a
`$$Profile_Source` is workspace-relative** — it is what decides the directory that value resolves
against.

trestle itself is not what makes that work. The task sets its own workspace to `os.getcwd()`
(`trestle/tasks/base_task.py`, `_configure_csv_common`, checked against trestle 5.2.0) and never
consults `--trestle-root` when resolving a profile. The MCP wrapper is what makes it work: it
makes the `--trestle-root` value absolute and runs the subprocess *inside* that directory
(`_working_directory` in `trestle_mcp/libs/trestle.py`), so `os.getcwd()` is the workspace. Omit
`trestle_root` and `profiles/<name>/profile.json` resolves against wherever the client started the
server, which is the project root far more often than it is the workspace.

One thing to know about that mechanism: the wrapper uses the path only if the directory exists. A
root with a typo in it is skipped without a word, and resolution falls back to the server's start
directory. So when a `$$Profile_Source` that is certainly present cannot be found, check the root
you passed before you start editing the CSV.

### `validate_controls` — pass `"on"`, do not take the default

The tool's default is `"off"`. Leave it there and every `$$Control_Id_List` entry is accepted
without being checked against the resolved profile, so a control that is **in no baseline at
all** produces a component definition that looks correct and asserts coverage the framework
never selected. The failure is silent at authoring time and expensive later: the mapping is
wrong, not malformed, so no schema validation downstream will find it.

Controls that look like obvious choices and are selected by none of the NIST SP 800-53 rev 5
LOW, MODERATE or HIGH baselines include `cm-14` Signed Components, `cm-2.1`, `sr-4` Provenance
and `sr-11.3`. With `validate_controls="on"` the conversion fails on the row that cites one,
which is the only automatic check that catches it.

Use `"warn"` only when the profile is deliberately narrower than the controls being documented
and the author has decided to accept that; never `"off"`.

### Other optional parameters

| Parameter | Default | Use |
|---|---|---|
| `validate_controls` | `"off"` | **Always pass `"on"`** — see above |
| `component_definition` | none | Path to an existing component-definition to update rather than create |
| `output_overwrite` | `True` | Replace existing output |
| `class_column_mappings` | none | Map a column to a CSS class, e.g. `{"Rule_Id": "scc_class"}` |
| `verbose` | `False` | Verbose output when a conversion fails and the error is not obvious |

## Checklist before invoking

1. Trestle workspace is initialized (`trestle_init` or pre-existing)
2. CSV exists at the specified path
3. Output directory path is chosen — **do not create it**. trestle creates it: `_execute()` in
   `trestle/tasks/csv_to_oscal_cd.py` calls `opth.mkdir(exist_ok=True, parents=True)` on the
   unconditional main path before writing (checked against trestle 5.2.0). A `mkdir` step added
   "to be safe" buys nothing and costs a tool-approval prompt that stalls an unattended run
4. All required columns are present in the CSV header row
5. For validation type: `$Check_Id` and `$Check_Description` columns are present
6. **Data row validation**: All data rows have same column count as header
7. **Column completeness**: Validation component rows include all required columns (even if empty)
   - `$$Profile_Source` and `$$Profile_Description` must be present (can be empty) — they are on
     the header-checked list, so an absent column fails even where the value is ignored
   - `$Target_Component` is optional. A CSV without the column at all converts (verified against
     trestle 5.2.0; the `poam-authoring` demo's CSV does not carry it). Add it when two rows would
     otherwise share a rule key — see `csv-authoring.md`
8. **URL validation**: `$$Namespace` contains valid URLs with scheme (e.g., `https://kubernetes.io`)
9. **`validate_controls="on"` is passed** — the default is `off`, which accepts a control that is
   in no baseline and produces a silently wrong mapping

## Two failures that do not look like failures

### A service row with no control is dropped silently

`_CsvMgr._is_no_control()` skips any non-validation row whose `$$Control_Id_List` is empty, and
it does so in the row generator — before the required-column check that would otherwise reject
it. There is no error and no warning: the rule is simply absent from `component-definition.json`
and the conversion reports success. If a rule you authored is missing from the output, look at
that column first. (On a validation row the same emptiness is legitimate and the row is kept.)

### The tool reports failure in its return value, not as an exception

`trestle_task_csv_to_oscal_cd` always returns a string. Success starts with `✅`, failure with
`❌ Failed to convert CSV to OSCAL component definition` followed by trestle's stderr. It does
not raise, so an agent that does not read the return value will report success on a conversion
that wrote nothing — the one failure mode that matters most in an unattended run. Read it back,
and expect:

- `Unresolved controls: [...]` — `validate_controls="on"` rejected those control ids. Fix the row
  or widen the profile; do not turn validation off.
- `Missing columns: [...]` — a required header name is absent or misspelled.
- `row "N" missing value for "X"` — a required cell is empty on that row, **or the `X` column is
  misspelled or absent from the header**. `get_row_value()` answers `''` for a column it cannot
  find, and `$Check_Id` / `$Check_Description` are not among the names the header check looks at,
  so a misspelling of those two surfaces here rather than as `Missing columns`. Read the header
  before hunting for an empty cell.
- `row "N" contains duplicate Rule_Id "..."` — two rows share component title, component type,
  rule id, check id and target component.
- `Command timed out after 600 seconds` — the MCP wrapper caps the trestle subprocess, and this
  task gets the long limit (600 s). That is a timeout, not a CSV defect, so do not start editing a
  CSV that is correct. Ten minutes almost always means a remote `$$Profile_Source` is being fetched
  and resolved, so check that reference before re-running. The number is the wrapper's, not
  trestle's, and it may differ in your deployment.

## Common Issues and Fixes

### Column Count Mismatch
**Error:** `IndexError: list index out of range`

**Cause:** Data rows have fewer columns than header row.

**Fix:**
- Validation component rows must include all columns from header
- Use Python to verify and fix:
```python
import csv
with open('file.csv', 'r') as f:
    reader = csv.reader(f)
    rows = list(reader)
    header_cols = len(rows[0])
    for i, row in enumerate(rows[1:], 1):
        if len(row) < header_cols:
            row.extend([''] * (header_cols - len(row)))
```

### Invalid Namespace URL
**Error:** `invalid or missing URL scheme`

**Cause:** `$$Namespace` contains non-URL value (e.g., `Kubernetes` instead of `https://kubernetes.io`)

**Fix:** Ensure all namespace values are valid URLs:
```python
# Invalid: 'Kubernetes', 'kyverno'
# Valid: 'https://kubernetes.io', 'https://kyverno.io'
```

### A missing optional column is not an error

An optional column that is absent from the header does **not** raise. `get_row_value()` returns
its default (`''`) when `get_col_index()` answers `-1`, so a CSV with no `$Target_Component`
column converts cleanly — verified against trestle 5.2.0, and the `poam-authoring` demo ships
such a CSV.

The two things that *are* errors look similar enough to be worth separating:

- a data row **shorter than the header** — that is the `IndexError` above, and it is real;
- a **misspelled** `$Check_Id` / `$Check_Description` — the column counts as absent, so the value
  reads as empty and a validation row fails with `row "N" missing value for "Check_Id"`.

So do not add empty optional columns "to be safe". Add a column when you have something to put in
it.
