# Assessment Table Generation

## Overview

Generate a human-readable markdown table showing control compliance assessment results derived from component-definition mappings.

## Input Requirements

1. **Component Definition Source**
   - Path to `component-definition.json` or markdown files
   - Or trestle workspace path with component definition

2. **Assessment Scope**
   - Which controls to assess (all or filtered list)
   - Which components to include (service, validation, or both)

## Output Format

Markdown table with the following columns:

| Column | Description | Example |
|--------|-------------|---------|
| Control ID | NIST control identifier | AC-2 |
| Control Description | Human-readable control name | Account Management |
| Rule Description | Service component rule | All user accounts must have MFA enabled |
| Check Method | Type of validation | Automated scan |
| Check Description | Specific check performed | Scan for accounts without MFA |
| Findings | Assessment results with evidence | 0 accounts without MFA found |
| Status | Compliance result | Compliant |

## Example Output

```markdown
| Control ID | Control Description | Rule Description | Check Method | Check Description | Findings | Status |
|------------|-------------------|------------------|---------------|-------------------|----------|--------|
| AC-2 | Account Management | All user accounts must have MFA enabled | Automated scan | Scan for accounts without MFA | 0 accounts without MFA found | Compliant |
| AC-3 | Access Enforcement | All access decisions logged | Log analysis | Verify access logs contain all decisions | 100% of access decisions logged | Compliant |
| AU-2 | Audit Events | All security events logged | Log analysis | Verify security event logging enabled | 5 events logged in last 24h | Compliant |
| SC-7 | Boundary Protection | Firewall rules restrict traffic | Network scan | Verify firewall rules in place | 3 non-compliant rules found | Non-Compliant |
```

## Workflow

### Step 1: Load Component Definition

```python
import json

# Load from file
with open('component-definition.json', 'r') as f:
    cd = json.load(f)
```

### Step 2: Extract Service Component Rules

```python
# Get service component
service_comp = next(
    (c for c in cd['components'] if c['component-type'] == 'service'),
    None
)

# Extract control-rule mappings
control_rules = {}
for control_impl in service_comp.get('control-implementations', []):
    for control in control_impl.get('implemented-requirements', []):
        control_id = control['control-id']
        for statement in control.get('statements', []):
            rule_desc = statement.get('description', '')
            if control_id not in control_rules:
                control_rules[control_id] = []
            control_rules[control_id].append(rule_desc)
```

### Step 3: Extract Validation Component Checks

```python
# Get validation component
validation_comp = next(
    (c for c in cd['components'] if c['component-type'] == 'validation'),
    None
)

# Extract rule-check mappings
rule_checks = {}
for control_impl in validation_comp.get('control-implementations', []):
    for control in control_impl.get('implemented-requirements', []):
        for statement in control.get('statements', []):
            rule_ref = statement.get('description', '')
            check_desc = statement.get('remarks', '')
            if rule_ref not in rule_checks:
                rule_checks[rule_ref] = []
            rule_checks[rule_ref].append(check_desc)
```

### Step 4: Build Assessment Table

```python
# Build rows
rows = []
for control_id, rules in control_rules.items():
    for rule_desc in rules:
        checks = rule_checks.get(rule_desc, ['No validation check defined'])
        for check_desc in checks:
            rows.append({
                'control_id': control_id,
                'rule_desc': rule_desc,
                'check_desc': check_desc,
                'status': 'Compliant'  # or from mock data
            })
```

### Step 5: Generate Markdown

```python
# Generate markdown table
md = "| Control ID | Rule Description | Check Description | Status |\n"
md += "|------------|------------------|-------------------|--------|\n"
for row in rows:
    md += f"| {row['control_id']} | {row['rule_desc']} | {row['check_desc']} | {row['status']} |\n"
```

## Implementation Notes

- Use Python to parse component definition JSON
- Extract control IDs from service component
- Map rules to checks via validation component
- Generate markdown table for easy viewing
- For demo, use mock compliance status (mix of Compliant/Non-Compliant)
