# CSV to Markdown Preview

Generate a human-readable markdown preview of the component definition CSV before converting to OSCAL JSON.

**IMPORTANT**: This skill generates a markdown FILE, not just stdout output. The markdown file is written to disk and can be reviewed by users.

## Purpose

Markdown preview helps users review the mapping between:
- **Controls** (from catalog/profile)
- **Rules** (service component implementations)
- **Checks** (validation component verifications)

This visualization catches errors early and ensures the mapping is correct before OSCAL generation.

## When to Use

1. After authoring the CSV with service and validation components
2. Before invoking `trestle_task_csv_to_oscal_cd`
3. To show users a clear view of control → rule → check relationships
4. To generate a persistent markdown file for documentation and review

## Python Script

Use the following Python script to convert CSV to markdown:

```python
#!/usr/bin/env python3
"""
CSV to Markdown Table Converter for Component Definition

Converts a CSV file with service and validation components into a formatted markdown document
with separate tables for each component type.
"""

import csv
import sys
from pathlib import Path
from typing import List, Dict, Tuple


def read_csv(csv_file: str) -> List[Dict[str, str]]:
    """Read CSV file and return list of dictionaries."""
    rows = []
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def separate_components(rows: List[Dict[str, str]]) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """Separate rows into service and validation components."""
    service_rows = [row for row in rows if row.get('$$Component_Type') == 'service']
    validation_rows = [row for row in rows if row.get('$$Component_Type') == 'validation']
    return service_rows, validation_rows


def create_service_table(rows: List[Dict[str, str]]) -> str:
    """Create markdown table for service components."""
    if not rows:
        return ""
    
    table = "## Service Component\n\n"
    table += "| Component_Title | Component_Description | Component_Type | Control_Id_List | Rule_Id | Rule_Description |\n"
    table += "|---|---|---|---|---|---|\n"
    
    for row in rows:
        component_title = row.get('$$Component_Title', '')
        component_desc = row.get('$$Component_Description', '')
        component_type = row.get('$$Component_Type', '')
        control_id = row.get('$$Control_Id_List', '')
        rule_id = row.get('$$Rule_Id', '')
        rule_desc = row.get('$$Rule_Description', '')
        
        # Escape pipe characters in descriptions
        rule_desc = rule_desc.replace('|', '\\|')
        
        table += f"| {component_title} | {component_desc} | {component_type} | {control_id} | {rule_id} | {rule_desc} |\n"
    
    return table


def create_validation_table(rows: List[Dict[str, str]]) -> str:
    """Create markdown table for validation components."""
    if not rows:
        return ""
    
    table = "## Validation Component\n\n"
    table += "| Component_Title | Component_Description | Component_Type | Control_Id_List | Rule_Id | Check_Id | Check_Description |\n"
    table += "|---|---|---|---|---|---|---|\n"
    
    for row in rows:
        component_title = row.get('$$Component_Title', '')
        component_desc = row.get('$$Component_Description', '')
        component_type = row.get('$$Component_Type', '')
        control_id = row.get('$$Control_Id_List', '')
        rule_id = row.get('$$Rule_Id', '')
        check_id = row.get('$Check_Id', '')
        check_desc = row.get('$Check_Description', '')
        
        # Escape pipe characters in descriptions
        check_desc = check_desc.replace('|', '\\|')
        
        table += f"| {component_title} | {component_desc} | {component_type} | {control_id} | {rule_id} | {check_id} | {check_desc} |\n"
    
    return table


def create_summary(service_rows: List[Dict[str, str]], validation_rows: List[Dict[str, str]]) -> str:
    """Create summary section."""
    service_count = len(service_rows)
    validation_count = len(validation_rows)
    total_controls = len(set(row.get('$$Control_Id_List', '') for row in service_rows))
    
    summary = "## Summary\n\n"
    summary += f"- **Service Component**: {service_rows[0].get('$$Component_Title', 'Unknown') if service_rows else 'N/A'} ({service_count} rules)\n"
    summary += f"- **Validation Component**: {validation_rows[0].get('$$Component_Title', 'Unknown') if validation_rows else 'N/A'} ({validation_count} checks)\n"
    summary += f"- **Total Controls Mapped**: {total_controls} controls\n"
    
    return summary


def convert_csv_to_markdown(csv_file: str, output_file: str = None) -> str:
    """Convert CSV to markdown and optionally write to file."""
    if output_file is None:
        output_file = Path(csv_file).stem + '.md'
    
    # Read CSV
    rows = read_csv(csv_file)
    
    # Separate components
    service_rows, validation_rows = separate_components(rows)
    
    # Create markdown content
    markdown = "# Component Definition Mapping\n\n"
    markdown += create_service_table(service_rows)
    markdown += "\n"
    markdown += create_validation_table(validation_rows)
    markdown += "\n"
    markdown += create_summary(service_rows, validation_rows)
    
    # Write to file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(markdown)
    
    print(f"✅ Markdown file created: {output_file}")
    print(f"   File size: {len(markdown)} bytes")
    print(f"   Service components: {len(service_rows)} rules")
    print(f"   Validation components: {len(validation_rows)} checks")
    return markdown


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python csv_to_markdown.py <csv_file> [output_file]")
        sys.exit(1)
    
    csv_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not Path(csv_file).exists():
        print(f"❌ Error: CSV file not found: {csv_file}")
        sys.exit(1)
    
    convert_csv_to_markdown(csv_file, output_file)


if __name__ == '__main__':
    main()
```

## Usage

Save the script as `csv_to_markdown.py` and run:

```bash
python3 csv_to_markdown.py <csv_file> [output_file]
```

**Example:**
```bash
python3 csv_to_markdown.py kubernetes_ac_component.csv kubernetes_ac_component.md
```

**Output:**
```
✅ Markdown file created: kubernetes_ac_component.md
   File size: 5432 bytes
   Service components: 12 rules
   Validation components: 8 checks
```

The markdown file is now ready for review and can be committed to version control or shared with stakeholders.

## Output Format

The script generates markdown with separate tables for each component type:

### Service Component Table
Shows how the service component implements controls through rules.

### Validation Component Table
Shows how the validation component checks that service component rules are enforced.

### Summary Section
- Service component name and rule count
- Validation component name and check count
- Total controls mapped
- Namespaces used

## Integration with Workflow

1. **Author CSV** with service and validation components
2. **Generate markdown preview** using `csv_to_markdown.py` → **Creates persistent markdown file on disk**
3. **Review the markdown file** for accuracy and completeness
4. **Share the markdown file** with stakeholders for approval
5. **Fix any issues** in the CSV if needed, then regenerate markdown
6. **Invoke `trestle_task_csv_to_oscal_cd`** to generate OSCAL JSON from the validated CSV

**Key Point**: The markdown file is a tangible deliverable that enables human review before OSCAL generation. Always ensure the file is written to disk and verified before proceeding.

## Script Features

- Separates service and validation components automatically
- Escapes pipe characters in descriptions to prevent markdown table corruption
- Counts components and controls for summary
- Handles empty optional columns gracefully
- Generates human-readable output for user review
