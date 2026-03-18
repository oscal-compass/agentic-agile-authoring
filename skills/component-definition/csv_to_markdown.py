# Copyright 2026 IBM Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
    
    table = "## Service Component (Kubernetes)\n\n"
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
    
    table = "## Validation Component (Kyverno)\n\n"
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
    summary += f"- **Service Component**: Kubernetes ({service_count} rules)\n"
    summary += f"- **Validation Component**: Kyverno ({validation_count} checks)\n"
    summary += f"- **Total Controls Mapped**: {total_controls} AC controls\n"
    summary += f"- **Namespace**: https://kubernetes.io and https://kyverno.io\n"
    
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
    markdown = "# Kubernetes + Kyverno Component Definition\n\n"
    markdown += create_service_table(service_rows)
    markdown += "\n"
    markdown += create_validation_table(validation_rows)
    markdown += "\n"
    markdown += create_summary(service_rows, validation_rows)
    
    # Write to file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(markdown)
    
    print(f"✅ Markdown file created: {output_file}")
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
