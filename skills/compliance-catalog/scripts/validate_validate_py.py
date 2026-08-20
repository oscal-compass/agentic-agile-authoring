#!/usr/bin/env python3
# Copyright OSCAL Compass Authors
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

"""
Validate that a generated validate.py includes all required rules.

This script checks that the generated validate.py:
1. Defines all required check_rule_X functions
2. Calls all required rules in validate_catalog()
3. Has proper error/warning handling for each rule

Usage:
    python validate_validate_py.py <path/to/validate.py>

Exit codes:
    0 - All required rules are present
    1 - Missing rules detected
"""

import argparse
import ast
import sys
from pathlib import Path


# Required rules that MUST be present in validate.py.
# Function names must match those defined in validate_template.py exactly.
REQUIRED_RULES = {
    # (function_name, rule_id, type, description)
    ("check_rule_1_duplicate_ids", "Rule 1", "ERROR", "Duplicate IDs"),
    ("check_rule_2_empty_lists", "Rule 2", "ERROR", "Empty Lists"),
    ("check_rule_3_sequential_order", "Rule 3", "ERROR", "Out of Order Controls"),
    ("check_rule_4_duplicate_group_ids", "Rule 4", "ERROR", "Duplicate Group IDs"),
    ("check_rule_5_toc_contamination", "Rule 5", "ERROR", "Title Contamination"),
    ("check_rule_6_complete_extraction", "Rule 6", "ERROR", "Required Sections / Groups / Nested Controls"),
    ("check_rule_7_valid_content", "Rule 7", "ERROR", "Invalid Content"),
    ("check_rule_8_balanced_structure", "Rule 8", "ERROR", "Balanced Structure"),
    ("check_rule_9_oscal_compliance", "Rule 9", "ERROR", "OSCAL Compliance"),
    ("check_rule_10_sequential_gaps", "Rule 10", "ERROR", "Sequential Gaps"),
    ("check_rule_12_merged_text_comparison", "Rule 12", "ERROR", "Missing Groups from merged.txt"),
    ("check_rule_13_config_completeness", "Rule 13", "ERROR", "CONFIG Completeness"),
    ("check_rule_14_prose_contamination", "Rule 14", "ERROR", "Prose Contamination"),
    ("check_rule_15_trestle_compliance", "Rule 15", "ERROR", "NCName / Trestle Compliance"),
    ("run_trestle_validate", "Rule 16", "ERROR", "Trestle Validate Command"),
    ("check_rule_17_props_namespace", "Rule 17", "ERROR", "Props Namespace"),
}

# Optional rules (warnings, not blocking)
OPTIONAL_RULES = {
    ("check_rule_11_control_count", "Rule 11", "WARNING", "Control Count"),
}

# Minimum required rules (core validation — the ones that catch structural
# issues even for very simple documents).
MINIMUM_REQUIRED = {
    "check_rule_1_duplicate_ids",
    "check_rule_2_empty_lists",
    "check_rule_3_sequential_order",
    "check_rule_4_duplicate_group_ids",
    "check_rule_7_valid_content",
    "check_rule_9_oscal_compliance",
    "check_rule_10_sequential_gaps",
    "check_rule_13_config_completeness",
    "check_rule_15_trestle_compliance",
    "run_trestle_validate",
    "check_rule_17_props_namespace",
}


class ValidatePyChecker:
    def __init__(self, filepath: Path):
        self.filepath = filepath
        self.content = filepath.read_text()
        self.tree = ast.parse(self.content)

        self.defined_functions: set[str] = set()
        self.called_functions: set[str] = set()
        self.rule_references: set[str] = set()

    def analyze(self):
        """Analyze the validate.py file."""
        for node in ast.walk(self.tree):
            # Find function definitions
            if isinstance(node, ast.FunctionDef):
                self.defined_functions.add(node.name)

            # Find function calls
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    self.called_functions.add(node.func.id)

            # Find string literals containing "Rule X"
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if "Rule " in node.value:
                    self.rule_references.add(node.value)

    def check_required_rules(self) -> tuple[list[str], list[str], list[str]]:
        """
        Check if all required rules are present.

        Returns:
            (missing_definitions, missing_calls, warnings)
        """
        missing_definitions = []
        missing_calls = []
        warnings = []

        for func_name, rule_id, rule_type, desc in REQUIRED_RULES:
            # Check if function is defined
            if func_name not in self.defined_functions:
                # Check for similar names (partial match)
                similar = [f for f in self.defined_functions if rule_id.lower().replace(" ", "_") in f.lower()]
                if similar:
                    warnings.append(f"{rule_id} ({desc}): Function '{func_name}' not found, but similar: {similar}")
                else:
                    missing_definitions.append(f"{rule_id} ({desc}): Missing function '{func_name}'")

            # Check if function is called in validate_catalog
            if func_name not in self.called_functions:
                # Also check if it's called by a different name
                if func_name in self.defined_functions:
                    missing_calls.append(f"{rule_id} ({desc}): Function defined but not called")

        return missing_definitions, missing_calls, warnings

    def check_minimum_required(self) -> list[str]:
        """Check if minimum required rules are present."""
        missing = []
        for func_name in MINIMUM_REQUIRED:
            if func_name not in self.defined_functions:
                missing.append(func_name)
            elif func_name not in self.called_functions:
                missing.append(f"{func_name} (defined but not called)")
        return missing

    def get_summary(self) -> dict:
        """Get summary of what's in the validate.py."""
        return {
            "total_functions": len(self.defined_functions),
            "check_rule_functions": [f for f in self.defined_functions if f.startswith("check_rule")],
            "rule_references": sorted(self.rule_references),
        }


def main():
    parser = argparse.ArgumentParser(
        description="Validate that a generated validate.py includes all required rules"
    )
    parser.add_argument("validate_py", type=Path, help="Path to validate.py to check")
    parser.add_argument("--strict", action="store_true", help="Fail on any missing rule")
    parser.add_argument("--summary", action="store_true", help="Show summary only")

    args = parser.parse_args()

    if not args.validate_py.exists():
        print(f"Error: File not found: {args.validate_py}")
        sys.exit(1)

    try:
        checker = ValidatePyChecker(args.validate_py)
        checker.analyze()
    except SyntaxError as e:
        print(f"Error: Invalid Python syntax in {args.validate_py}: {e}")
        sys.exit(1)

    summary = checker.get_summary()

    if args.summary:
        print(f"File: {args.validate_py}")
        print(f"Total functions: {summary['total_functions']}")
        print(f"Check rule functions: {len(summary['check_rule_functions'])}")
        for func in sorted(summary['check_rule_functions']):
            print(f"  - {func}")
        print(f"Rule references found: {summary['rule_references']}")
        sys.exit(0)

    print(f"Validating: {args.validate_py}")
    print("=" * 60)

    # Check minimum required
    missing_minimum = checker.check_minimum_required()

    # Check all required
    missing_defs, missing_calls, warnings = checker.check_required_rules()

    # Report results
    has_errors = False

    if missing_minimum:
        print("\n❌ MISSING MINIMUM REQUIRED RULES:")
        for item in missing_minimum:
            print(f"   - {item}")
        has_errors = True
    else:
        print("\n✅ All minimum required rules present")

    if missing_defs:
        print("\n❌ MISSING RULE DEFINITIONS:")
        for item in missing_defs:
            print(f"   - {item}")
        if args.strict:
            has_errors = True

    if missing_calls:
        print("\n⚠️  RULES DEFINED BUT NOT CALLED:")
        for item in missing_calls:
            print(f"   - {item}")
        if args.strict:
            has_errors = True

    if warnings:
        print("\n⚠️  WARNINGS:")
        for item in warnings:
            print(f"   - {item}")

    # Summary
    print("\n" + "=" * 60)
    print(f"Functions found: {len(summary['check_rule_functions'])}")
    print(f"  Defined: {', '.join(sorted(summary['check_rule_functions']))}")

    if has_errors:
        print("\n❌ VALIDATION FAILED")
        print("\nTo fix: Ensure validate.py includes all rules from validate_template.py")
        print("Run: diff validate.py <skill_scripts_dir>/validate_template.py")
        sys.exit(1)
    else:
        print("\n✅ VALIDATION PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
