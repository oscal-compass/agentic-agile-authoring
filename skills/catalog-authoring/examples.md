# OSCAL Authoring Examples

Practical examples for common OSCAL authoring workflows.

## Example 1: Import NIST SP 800-53 Rev 5 LOW Baseline

### Step 1: Import Catalog
```
MCP tool: trestle_import
file: https://raw.githubusercontent.com/usnistgov/oscal-content/refs/heads/main/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json
output: nist_catalog
```

### Step 2: Import Profile
```
MCP tool: trestle_import
file: https://raw.githubusercontent.com/usnistgov/oscal-content/refs/heads/main/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_LOW-baseline_profile.json
output: nist_low
```

### Step 3: Edit Profile href
Edit `profiles/nist_low/profile.json`:
```json
"imports": [
  {
    "href": "catalogs/nist_catalog/catalog.json"
  }
]
```

### Step 4: Generate Markdown
```
MCP tool: trestle_author_catalog_generate
name: nist_catalog
output: md_catalog

MCP tool: trestle_author_profile_generate
name: nist_low
output: md_profile

MCP tool: trestle_author_profile_resolve
name: nist_low
output: catalog_resolved
show_values: true
bracket_format: "[.]"
value_not_assigned_prefix: "ORGANISATION TO DEFINE —"

MCP tool: trestle_author_catalog_generate
name: catalog_resolved
output: md_catalog_resolved
```

## Example 2: Edit AC-1 Control Parameters

### Step 1: Create CSV Template
File: `tmp/ac-1_params.csv`
```csv
"What's required","Value","Id"
"organization-defined frequency","annually","ac-01_odp.01"
"organization-defined personnel or roles","CISO, Security Team","ac-01_odp.02"
"organization-defined frequency","annually","ac-01_odp.03"
"organization-defined personnel or roles","CISO, Security Team","ac-01_odp.04"
"organization-defined frequency","annually","ac-01_odp.05"
"organization-defined events","policy violations, audit findings","ac-01_odp.06"
"organization-defined frequency","annually","ac-01_odp.07"
"organization-defined events","procedure changes, system updates","ac-01_odp.08"
```

### Step 2: Confirm with User
Display CSV content and ask for confirmation before proceeding.

### Step 3: Set the values in the markdown header
Edit the `x-trestle-set-params` header of `md_profile/ac/ac-1.md` — not the prose. The moustache
in the statement stays as generated; `profile-assemble --set-parameters` reads the header.
```yaml
x-trestle-set-params:
  ac-01_odp.01:
    profile-values:
      - annually
    profile-param-value-origin: Organization Security Policy v1.0
```

### Step 4: Regenerate Profile and Catalog
```
MCP tool: trestle_author_profile_assemble
markdown_dir: md_profile
output_profile: nist_low
set_parameters: true

MCP tool: trestle_author_profile_resolve
name: nist_low
output: catalog_resolved
show_values: true
bracket_format: "[.]"
value_not_assigned_prefix: "ORGANISATION TO DEFINE —"

MCP tool: trestle_author_catalog_generate
name: catalog_resolved
output: md_catalog_resolved
```

## Example 3: Local Custom Catalog

### Step 1: Import Local Catalog
```
MCP tool: trestle_import
file: ./resources/catalogs/custom_catalog.json
output: custom_catalog
```

### Step 2: Import Local Profile
```
MCP tool: trestle_import
file: ./resources/profiles/custom_profile.json
output: custom_profile
```

### Step 3: Edit Profile href
Edit `profiles/custom_profile/profile.json`:
```json
"imports": [
  {
    "href": "catalogs/custom_catalog/catalog.json"
  }
]
```

### Step 4: Generate Markdown
```
MCP tool: trestle_author_catalog_generate
name: custom_catalog
output: md_custom_catalog

MCP tool: trestle_author_profile_generate
name: custom_profile
output: md_custom_profile
```

## Common Patterns

### Parameter Value Guidelines

**Good - Minimal and Natural:**
- "annually" for frequency
- "CISO" for personnel
- "30 days" for time periods

**Bad - Redundant:**
- "access control policy" when context already mentions policy
- "organization-defined frequency annually" (too verbose)

### CSV Column Format

Always use 3 columns:
1. `What's required` - Human-readable description
2. `Value` - The actual parameter value
3. `Id` - OSCAL parameter ID (e.g., ac-01_odp.01)

### Escape Characters

Maintain escape characters in markdown:
- Keep `\[` and `\]` as-is
- Keep `\{` and `\}` as-is
- Do not convert to plain brackets
