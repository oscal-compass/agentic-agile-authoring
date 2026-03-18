# CSV Authoring for Component Definitions

This skill provides detailed guidance on authoring CSV files for OSCAL component definitions. Proper CSV construction is critical—failures in csv-to-oscal conversion are almost always due to CSV authoring errors, not the conversion tool itself.

## Core Principle: Use Python CSV Writer, Never Manual Text Construction

**CRITICAL:** Always use Python's `csv.writer()` module to construct CSV files. Never manually concatenate strings or use `write_to_file` with raw CSV text.

**Why:**
- Manual text construction causes column misalignment
- Extra commas, missing values, or escaped quotes create phantom columns
- Column count mismatches are the #1 cause of csv-to-oscal failures
- Python's `csv.writer()` guarantees structural integrity

## CSV Structure Overview

### Row Layout
```
Row 1: Header (column names with $$ and $ prefixes)
Row 2: Descriptions (optional, not parsed by trestle)
Row 3+: Data rows (component rules and mappings)
```

### Column Prefix Meanings
- `$$` = Required column (must have value in every data row)
- `$` = Optional column (can be empty)
- `#` = Comment column (ignored by trestle)

## Unified CSV Schema (Service + Validation Components)

When combining service and validation components in one CSV, use this exact column order:

```
$$Component_Title
$$Component_Description
$$Component_Type
$$Control_Id_List
$$Rule_Id
$$Rule_Description
$$Profile_Source
$$Profile_Description
$$Namespace
$Check_Id
$Check_Description
$Target_Component
```

**Critical constraint:** All rows (header, description, data) must have **exactly the same number of columns**.

## Column Requirements by Component Type

### Service Component Rows
Service components **implement** controls (firewall, OS, middleware, Kubernetes platform).

| Column | Required? | Value |
|--------|-----------|-------|
| `$$Component_Title` | YES | Component name (e.g., "Kubernetes Platform") |
| `$$Component_Description` | YES | What the component does |
| `$$Component_Type` | YES | Literal string: `service` |
| `$$Control_Id_List` | YES | Control ID (e.g., `AC-2`, `AC-3`) |
| `$$Rule_Id` | YES | Unique rule identifier (e.g., `K8S-AC-2.1`) |
| `$$Rule_Description` | YES | How this rule implements the control |
| `$$Profile_Source` | YES | Control family or source (e.g., `AC-2`, `Account Management`) |
| `$$Profile_Description` | YES | Control title/description |
| `$$Namespace` | YES | Valid URL with scheme (e.g., `https://kubernetes.io`) |
| `$Check_Id` | NO | Leave **empty string** `""` |
| `$Check_Description` | NO | Leave **empty string** `""` |
| `$Target_Component` | NO | Component name (recommended: same as `$$Component_Title`) |

### Validation Component Rows
Validation components **verify** that service rules are enforced (scanner, audit tool, policy engine).

| Column | Required? | Value |
|--------|-----------|-------|
| `$$Component_Title` | YES | Validator name (e.g., "Kyverno Policy Engine") |
| `$$Component_Description` | YES | What the validator does |
| `$$Component_Type` | YES | Literal string: `validation` |
| `$$Control_Id_List` | NO | Leave **empty string** `""` |
| `$$Rule_Id` | YES | Unique check identifier (e.g., `KYVERNO-AC-2.1`) |
| `$$Rule_Description` | NO | Leave **empty string** `""` |
| `$$Profile_Source` | NO | Leave **empty string** `""` |
| `$$Profile_Description` | NO | Leave **empty string** `""` |
| `$$Namespace` | YES | Valid URL with scheme (e.g., `https://kyverno.io`) |
| `$Check_Id` | YES | Unique check ID (e.g., `KYVERNO-AC-2.1`) |
| `$Check_Description` | YES | What this check validates |
| `$Target_Component` | NO | Leave **empty string** `""` (or service component name) |

## Python CSV Construction Template

Use this template to construct CSV files programmatically:

```python
import csv

# Define data as list of lists
data = [
    # Header row (MUST match unified schema exactly)
    ['$$Component_Title', '$$Component_Description', '$$Component_Type', 
     '$$Control_Id_List', '$$Rule_Id', '$$Rule_Description', 
     '$$Profile_Source', '$$Profile_Description', '$$Namespace', 
     '$Check_Id', '$Check_Description', '$Target_Component'],
    
    # Description row (optional, not parsed)
    ['Component', 'Description', 'Type', 'Control', 'Rule ID', 'Rule Desc',
     'Profile Source', 'Profile Desc', 'Namespace', 'Check ID', 'Check Desc', 'Target'],
    
    # Service component rows
    ['Kubernetes Platform', 'Kubernetes container orchestration...', 'service',
     'AC-2', 'K8S-AC-2.1', 'RBAC policies enforce role-based access control...',
     'AC-2', 'Account Management', 'https://kubernetes.io',
     '', '', 'Kubernetes Platform'],
    
    # Validation component rows
    ['Kyverno Policy Engine', 'Policy engine for Kubernetes...', 'validation',
     '', 'KYVERNO-AC-2.1', '',
     '', '', 'https://kyverno.io',
     'KYVERNO-AC-2.1', 'Validates RBAC policies are correctly configured', ''],
]

# Write CSV using csv.writer (NEVER manual string concatenation)
with open('component.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerows(data)

print("✓ CSV written successfully")
```

## Verification Checklist

After constructing the CSV, verify it programmatically:

```python
import csv

with open('component.csv', 'r') as f:
    reader = csv.reader(f)
    rows = list(reader)

# Check 1: All rows have same column count
header_cols = len(rows[0])
print(f"Header columns: {header_cols}")

all_valid = True
for i, row in enumerate(rows[1:], 1):
    if len(row) != header_cols:
        print(f"❌ Row {i+1}: {len(row)} columns (expected {header_cols})")
        all_valid = False

if all_valid:
    print("✓ All rows have correct column count")

# Check 2: Namespace URLs are valid
for i, row in enumerate(rows[2:], 2):  # Skip header and description
    namespace = row[8]  # Column index 8 is $$Namespace
    if namespace and not namespace.startswith(('http://', 'https://')):
        print(f"❌ Row {i+1}: Invalid namespace URL: '{namespace}'")
        all_valid = False

if all_valid:
    print("✓ All namespace URLs are valid")

# Check 3: Required columns are not empty
for i, row in enumerate(rows[2:], 2):  # Skip header and description
    component_type = row[2]  # Column index 2 is $$Component_Type
    
    if component_type == 'service':
        required_cols = [0, 1, 2, 3, 4, 5, 6, 7, 8]  # Indices for required columns
        for col_idx in required_cols:
            if not row[col_idx]:
                print(f"❌ Row {i+1}: Required column {col_idx} is empty")
                all_valid = False
    
    elif component_type == 'validation':
        required_cols = [0, 1, 2, 4, 8, 9, 10]  # Indices for validation required columns
        for col_idx in required_cols:
            if not row[col_idx]:
                print(f"❌ Row {i+1}: Required column {col_idx} is empty")
                all_valid = False

if all_valid:
    print("✓ All required columns have values")
```

## Common CSV Authoring Mistakes

### Mistake 1: Manual String Concatenation
❌ **WRONG:**
```python
csv_text = "$$Component_Title,$$Component_Description,$$Component_Type\n"
csv_text += "Kubernetes,Platform,service\n"
with open('file.csv', 'w') as f:
    f.write(csv_text)
```

✅ **CORRECT:**
```python
import csv
data = [
    ['$$Component_Title', '$$Component_Description', '$$Component_Type'],
    ['Kubernetes', 'Platform', 'service'],
]
with open('file.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerows(data)
```

**Why:** Manual concatenation causes:
- Inconsistent escaping of special characters
- Extra commas from string formatting
- Column count mismatches between rows

### Mistake 2: Inconsistent Column Counts
❌ **WRONG:**
```python
data = [
    ['col1', 'col2', 'col3', 'col4', 'col5'],  # 5 columns
    ['val1', 'val2', 'val3', 'val4'],           # 4 columns (MISMATCH!)
]
```

✅ **CORRECT:**
```python
data = [
    ['col1', 'col2', 'col3', 'col4', 'col5'],  # 5 columns
    ['val1', 'val2', 'val3', 'val4', ''],      # 5 columns (empty string for missing)
]
```

**Why:** trestle reads columns by index. If row 2 has fewer columns, accessing column index 4 fails.

### Mistake 3: Missing Empty Strings for Optional Columns
❌ **WRONG:**
```python
# Service row with validation columns omitted
['Kubernetes', 'Platform', 'service', 'AC-2', 'K8S-AC-2.1', '...', '...', '...', 'https://k8s.io']
# Missing $Check_Id and $Check_Description columns entirely
```

✅ **CORRECT:**
```python
# Service row with validation columns as empty strings
['Kubernetes', 'Platform', 'service', 'AC-2', 'K8S-AC-2.1', '...', '...', '...', 'https://k8s.io', '', '', 'Kubernetes']
# All 12 columns present, validation columns are empty strings
```

**Why:** The header defines 12 columns. Every data row must have 12 columns, even if some are empty.

### Mistake 4: Invalid Namespace URLs
❌ **WRONG:**
```python
['Kubernetes', 'Platform', 'service', 'AC-2', 'K8S-AC-2.1', '...', '...', '...', 'Kubernetes']
# Namespace is 'Kubernetes' (not a URL)
```

✅ **CORRECT:**
```python
['Kubernetes', 'Platform', 'service', 'AC-2', 'K8S-AC-2.1', '...', '...', '...', 'https://kubernetes.io']
# Namespace is a valid URL with scheme
```

**Why:** trestle validates that `$$Namespace` is a valid URL with scheme (http:// or https://).

### Mistake 5: Wrong Column Order
❌ **WRONG:**
```python
# Reordering columns from the unified schema
['$$Component_Title', '$$Component_Type', '$$Component_Description', ...]
```

✅ **CORRECT:**
```python
# Exact order from unified schema
['$$Component_Title', '$$Component_Description', '$$Component_Type', ...]
```

**Why:** trestle reads columns by index position, not by header name. Column order must match exactly.

## Real-World Example: Kubernetes AC Component

```python
import csv

data = [
    # Header (12 columns, unified schema)
    ['$$Component_Title', '$$Component_Description', '$$Component_Type', 
     '$$Control_Id_List', '$$Rule_Id', '$$Rule_Description', 
     '$$Profile_Source', '$$Profile_Description', '$$Namespace', 
     '$Check_Id', '$Check_Description', '$Target_Component'],
    
    # Description row
    ['Component', 'Description', 'Type', 'Control', 'Rule ID', 'Rule Description',
     'Profile Source', 'Profile Description', 'Namespace', 'Check ID', 'Check Description', 'Target'],
    
    # Service rows (13 rows)
    ['Kubernetes Platform', 'Kubernetes container orchestration platform', 'service',
     'AC-2', 'K8S-AC-2.1', 'RBAC policies enforce role-based access control',
     'AC-2', 'Account Management', 'https://kubernetes.io',
     '', '', 'Kubernetes Platform'],
    
    ['Kubernetes Platform', 'Kubernetes container orchestration platform', 'service',
     'AC-3', 'K8S-AC-3.1', 'Network policies restrict traffic between pods',
     'AC-3', 'Access Enforcement', 'https://kubernetes.io',
     '', '', 'Kubernetes Platform'],
    
    # ... more service rows ...
    
    # Validation rows (6 rows)
    ['Kyverno Policy Engine', 'Policy engine for Kubernetes', 'validation',
     '', 'KYVERNO-AC-2.1', '',
     '', '', 'https://kyverno.io',
     'KYVERNO-AC-2.1', 'Validates RBAC policies are correctly configured', ''],
    
    ['Falco Runtime Security', 'Runtime security monitoring', 'validation',
     '', 'FALCO-AC-7.1', '',
     '', '', 'https://falco.org',
     'FALCO-AC-7.1', 'Monitors and detects unauthorized access attempts', ''],
]

# Write CSV
with open('kubernetes_ac_component.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerows(data)

# Verify
with open('kubernetes_ac_component.csv', 'r') as f:
    reader = csv.reader(f)
    rows = list(reader)

print(f"✓ CSV written with {len(rows)-2} data rows")
print(f"✓ All rows have {len(rows[0])} columns")
```

## Workflow Integration

1. **Enumerate components and rules** (identify service vs validation)
2. **Construct data list** using Python lists (not strings)
3. **Write CSV using `csv.writer()`** (never manual text)
4. **Verify column counts and URLs** programmatically
5. **Generate markdown preview** to show mappings to user
6. **User approves** markdown content
7. **Invoke trestle csv-to-oscal-cd** (conversion should succeed if CSV is correct)

## Troubleshooting

If csv-to-oscal conversion fails:

1. **First, verify the CSV structure:**
   ```python
   import csv
   with open('file.csv', 'r') as f:
       reader = csv.reader(f)
       rows = list(reader)
   
   # Print first few rows to inspect
   for i, row in enumerate(rows[:5]):
       print(f"Row {i}: {len(row)} columns - {row}")
   ```

2. **Check for column count mismatches:**
   ```python
   header_cols = len(rows[0])
   for i, row in enumerate(rows[1:], 1):
       if len(row) != header_cols:
           print(f"Row {i+1}: {len(row)} columns (expected {header_cols})")
   ```

3. **Verify namespace URLs:**
   ```python
   for i, row in enumerate(rows[2:], 2):
       namespace = row[8]
       if not namespace.startswith(('http://', 'https://')):
           print(f"Row {i+1}: Invalid namespace: {namespace}")
   ```

4. **Check for empty required columns:**
   ```python
   for i, row in enumerate(rows[2:], 2):
       if not row[0] or not row[1] or not row[8]:  # Title, Description, Namespace
           print(f"Row {i+1}: Missing required column")
   ```

If all checks pass but conversion still fails, the issue is likely in the trestle tool itself, not the CSV.
