#!/usr/bin/env python3
"""
Assessment Generator

Generate OSCAL assessment results by mapping component-definition rules to 
validation checks and evaluating control compliance.

Usage:
    python assessment-generator.py [--component-def <path>] [--output <path>]
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple


class AssessmentGenerator:
    """Generate assessment tables from component definitions."""
    
    def __init__(self, component_def_path: str = None):
        """Initialize with optional component definition path."""
        self.component_def = None
        if component_def_path:
            self.load_component_definition(component_def_path)
    
    def load_component_definition(self, path: str) -> None:
        """Load component definition from JSON file."""
        try:
            with open(path, 'r') as f:
                self.component_def = json.load(f)
            print(f"✓ Loaded component definition from {path}")
        except FileNotFoundError:
            print(f"✗ Component definition not found: {path}")
            sys.exit(1)
        except json.JSONDecodeError:
            print(f"✗ Invalid JSON in component definition: {path}")
            sys.exit(1)
    
    def extract_service_rules(self) -> Dict[str, List[str]]:
        """Extract control-rule mappings from service component."""
        if not self.component_def:
            return {}
        
        control_rules = {}
        components = self.component_def.get('components', [])
        
        for component in components:
            if component.get('component-type') != 'service':
                continue
            
            for control_impl in component.get('control-implementations', []):
                for control in control_impl.get('implemented-requirements', []):
                    control_id = control.get('control-id', '')
                    
                    for statement in control.get('statements', []):
                        rule_desc = statement.get('description', '')
                        if rule_desc:
                            if control_id not in control_rules:
                                control_rules[control_id] = []
                            control_rules[control_id].append(rule_desc)
        
        return control_rules
    
    def extract_validation_checks(self) -> Dict[str, List[Tuple[str, str]]]:
        """Extract rule-check mappings from validation component."""
        if not self.component_def:
            return {}
        
        rule_checks = {}
        components = self.component_def.get('components', [])
        
        for component in components:
            if component.get('component-type') != 'validation':
                continue
            
            for control_impl in component.get('control-implementations', []):
                for control in control_impl.get('implemented-requirements', []):
                    for statement in control.get('statements', []):
                        rule_ref = statement.get('description', '')
                        check_method = statement.get('remarks', '')
                        
                        if rule_ref:
                            if rule_ref not in rule_checks:
                                rule_checks[rule_ref] = []
                            rule_checks[rule_ref].append((check_method, ''))
        
        return rule_checks
    
    def generate_mock_assessment(self) -> List[Dict]:
        """Generate mock assessment data for demo."""
        mock_controls = [
            {
                "id": "AC-2",
                "title": "Account Management",
                "rule": "All user accounts must have MFA enabled",
                "check_method": "Automated scan",
                "check_desc": "Scan for accounts without MFA",
                "findings": "0 accounts without MFA found",
                "status": "Compliant"
            },
            {
                "id": "AC-3",
                "title": "Access Enforcement",
                "rule": "All access decisions must be logged",
                "check_method": "Log analysis",
                "check_desc": "Verify access logs contain all decisions",
                "findings": "100% of access decisions logged",
                "status": "Compliant"
            },
            {
                "id": "AU-2",
                "title": "Audit Events",
                "rule": "All security events must be logged to central repository",
                "check_method": "Log analysis",
                "check_desc": "Verify security events logged to central repository",
                "findings": "5,234 security events logged in last 24 hours",
                "status": "Compliant"
            },
            {
                "id": "SC-7",
                "title": "Boundary Protection",
                "rule": "Firewall rules must restrict traffic to approved ports",
                "check_method": "Network scan",
                "check_desc": "Verify firewall rules restrict traffic",
                "findings": "3 firewall rules allow non-approved ports (8080, 8443, 9000)",
                "status": "Non-Compliant"
            },
            {
                "id": "SC-13",
                "title": "Cryptographic Protection",
                "rule": "All data in transit must be encrypted with TLS 1.2+",
                "check_method": "Configuration review",
                "check_desc": "Verify TLS 1.2+ enabled on all endpoints",
                "findings": "TLS 1.2+ enabled on 95% of endpoints (2 endpoints use TLS 1.1)",
                "status": "Non-Compliant"
            },
            {
                "id": "SI-4",
                "title": "Information System Monitoring",
                "rule": "All security events must be monitored and alerted",
                "check_method": "Log analysis",
                "check_desc": "Verify monitoring and alerting configured",
                "findings": "Monitoring and alerting configured for all critical events",
                "status": "Compliant"
            }
        ]
        
        return mock_controls
    
    def generate_markdown_table(self, assessment_data: List[Dict]) -> str:
        """Generate markdown table from assessment data."""
        md = "| Control ID | Control Title | Rule Description | Check Method | Check Description | Findings | Status |\n"
        md += "|------------|---------------|------------------|---------------|-------------------|----------|--------|\n"
        
        for row in assessment_data:
            control_id = row.get('id', '')
            title = row.get('title', '')
            rule = row.get('rule', '')
            method = row.get('check_method', '')
            check_desc = row.get('check_desc', '')
            findings = row.get('findings', '')
            status = row.get('status', '')
            
            # Escape pipe characters in content
            rule = rule.replace('|', '\\|')
            check_desc = check_desc.replace('|', '\\|')
            findings = findings.replace('|', '\\|')
            
            md += f"| {control_id} | {title} | {rule} | {method} | {check_desc} | {findings} | {status} |\n"
        
        return md
    
    def generate_assessment(self, use_mock: bool = True) -> str:
        """Generate complete assessment output."""
        if use_mock:
            assessment_data = self.generate_mock_assessment()
        else:
            # TODO: Implement real assessment from component definition
            assessment_data = self.generate_mock_assessment()
        
        markdown = self.generate_markdown_table(assessment_data)
        return markdown


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Generate OSCAL assessment results'
    )
    parser.add_argument(
        '--component-def',
        help='Path to component-definition.json'
    )
    parser.add_argument(
        '--output',
        help='Output file path (default: assessment.md)'
    )
    parser.add_argument(
        '--mock',
        action='store_true',
        default=True,
        help='Use mock data for demo (default: True)'
    )
    
    args = parser.parse_args()
    
    # Create generator
    generator = AssessmentGenerator(args.component_def)
    
    # Generate assessment
    markdown = generator.generate_assessment(use_mock=args.mock)
    
    # Output
    output_path = args.output or 'assessment.md'
    with open(output_path, 'w') as f:
        f.write("# Assessment Results\n\n")
        f.write(markdown)
    
    print(f"✓ Assessment generated: {output_path}")


if __name__ == '__main__':
    main()
