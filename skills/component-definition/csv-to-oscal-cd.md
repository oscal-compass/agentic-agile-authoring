Use the `trestle_task_csv_to_oscal_cd` MCP tool to convert a CSV file into an OSCAL component definition.

Refer to `docs/command-specs/task/csv-to-oscal-cd.md` for the full spec. Key points are summarized below.

## CSV authoring rules

**Row layout:** Row 1 = headings, Row 2 = descriptions (not parsed), Row 3+ = data.

**Column prefixes:**
- `$$` = required column
- `$`  = optional column
- `#`  = comment column (ignored)

## Column Ordering

The correct column order for CSV files is critical for proper OSCAL generation. Use this exact sequence:

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
- Column order must match exactly — do not rearrange columns

**Component types and their column requirements:**

| Column | service | validation |
|--------|---------|------------|
| `$$Component_Title` | required | required |
| `$$Component_Description` | required | required |
| `$$Component_Type` | `service` | `validation` |
| `$$Rule_Id` | required | required |
| `$$Rule_Description` | required | ignored |
| `$$Profile_Source` | required | ignored |
| `$$Profile_Description` | required | ignored |
| `$$Control_Id_List` | required | ignored |
| `$$Namespace` | required | required |
| `$Check_Id` | optional | **required** |
| `$Check_Description` | optional | **required** |
| `$Target_Component` | optional | recommended (prevents Rule_Id collisions) |

For validation type, leave `$$Rule_Description`, `$$Profile_Source`, `$$Profile_Description`, `$$Control_Id_List` empty — they are silently ignored.

## When to write a service CSV vs a validation CSV

- **service**: the component *implements* controls (firewall, OS, middleware)
- **validation**: the component *checks* that another component's rules are met (scanner, audit tool)

Both types can coexist in one CSV and will be merged into a single `component-definition.json`.

## Example CSV skeletons

### Service

```
$$Component_Title,$$Component_Description,$$Component_Type,$$Rule_Id,$$Rule_Description,$$Profile_Source,$$Profile_Description,$$Control_Id_List,$$Namespace
<descriptions row>
MyApp,My application,service,rule-001,Rule description,https://example.com/catalog.json,NIST SP 800-53 Rev 5,ac-3,https://myorg.example.com
```

### Validation

```
$$Component_Title,$$Component_Description,$$Component_Type,$$Rule_Id,$$Rule_Description,$$Profile_Source,$$Profile_Description,$$Control_Id_List,$$Namespace,$Check_Id,$Check_Description,$Target_Component
<descriptions row>
MyScanner,Compliance scanner,validation,rule-001,,,,,https://myorg.example.com,check-001,Verify rule-001 is active,MyApp
```

## Invoking the MCP tool

```python
trestle_task_csv_to_oscal_cd(
    title="<component definition title>",
    version="<version>",
    csv_file="<absolute path to CSV>",
    output_dir="<absolute path to output dir>",
    trestle_root="<absolute path to trestle workspace>"
)
```

The tool generates the required INI config internally — do not ask the user for a config file path.

## Checklist before invoking

1. Trestle workspace is initialized (`trestle_init` or pre-existing)
2. CSV exists at the specified path
3. Output directory exists (trestle will error if it does not)
4. All required columns are present in the CSV header row
5. For validation type: `$Check_Id` and `$Check_Description` columns are present
6. **Data row validation**: All data rows have same column count as header
7. **Column completeness**: Validation component rows include all required columns (even if empty)
   - `$$Profile_Source` and `$$Profile_Description` must be present (can be empty)
   - `$Target_Component` must be present for all rows
8. **URL validation**: `$$Namespace` contains valid URLs with scheme (e.g., `https://kubernetes.io`)

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

### Missing Optional Columns
**Error:** Column index out of range during property creation

**Cause:** Optional columns like `$Target_Component` are missing from some rows.

**Fix:** Ensure all optional columns are present in header and all data rows have values (can be empty string).
