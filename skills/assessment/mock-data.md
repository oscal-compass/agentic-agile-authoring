# Mock Assessment Data

## Overview

For demo purposes, generate realistic mock assessment data without requiring actual component implementations or validation checks.

## Mock Data Structure

### Controls (NIST SP 800-53)

```json
{
  "controls": [
    {
      "id": "AC-2",
      "title": "Account Management",
      "description": "The organization manages information system accounts including establishing, activating, modifying, disabling, and removing accounts."
    },
    {
      "id": "AC-3",
      "title": "Access Enforcement",
      "description": "The information system enforces approved authorizations for logical access to information and system resources."
    },
    {
      "id": "AU-2",
      "title": "Audit Events",
      "description": "The information system is configured to generate audit records for the events defined in AU-2a."
    },
    {
      "id": "SC-7",
      "title": "Boundary Protection",
      "description": "The information system monitors and controls communications at external boundaries and key internal boundaries."
    }
  ]
}
```

### Rules (Service Component)

```json
{
  "rules": [
    {
      "control_id": "AC-2",
      "description": "All user accounts must have MFA enabled",
      "component": "Identity Management System"
    },
    {
      "control_id": "AC-3",
      "description": "All access decisions must be logged",
      "component": "Access Control System"
    },
    {
      "control_id": "AU-2",
      "description": "All security events must be logged to central repository",
      "component": "Logging System"
    },
    {
      "control_id": "SC-7",
      "description": "Firewall rules must restrict traffic to approved ports",
      "component": "Network Firewall"
    }
  ]
}
```

### Checks (Validation Component)

```json
{
  "checks": [
    {
      "rule_id": "AC-2",
      "method": "Automated scan",
      "description": "Scan for user accounts without MFA enabled",
      "tool": "Identity Scanner"
    },
    {
      "rule_id": "AC-3",
      "method": "Log analysis",
      "description": "Verify access logs contain all access decisions",
      "tool": "Log Analyzer"
    },
    {
      "rule_id": "AU-2",
      "method": "Log analysis",
      "description": "Verify security events are logged to central repository",
      "tool": "Log Analyzer"
    },
    {
      "rule_id": "SC-7",
      "method": "Network scan",
      "description": "Verify firewall rules restrict traffic to approved ports",
      "tool": "Network Scanner"
    }
  ]
}
```

### Assessment Results (Mock)

```json
{
  "results": [
    {
      "control_id": "AC-2",
      "status": "Compliant",
      "findings": "0 accounts without MFA found",
      "evidence": "Scanned 250 user accounts, all have MFA enabled"
    },
    {
      "control_id": "AC-3",
      "status": "Compliant",
      "findings": "100% of access decisions logged",
      "evidence": "Verified 10,000 access log entries in last 24 hours"
    },
    {
      "control_id": "AU-2",
      "status": "Compliant",
      "findings": "All security events logged",
      "evidence": "Central log repository contains 5,234 security events"
    },
    {
      "control_id": "SC-7",
      "status": "Non-Compliant",
      "findings": "3 firewall rules allow non-approved ports",
      "evidence": "Rules allow traffic on ports 8080, 8443, 9000 (not in approved list)"
    }
  ]
}
```

## Mock Data Generation Patterns

### Compliant Results

- **Automated Checks**: "0 vulnerabilities found", "100% compliant", "All X configured"
- **Manual Checks**: "Personnel confirmed awareness", "Documentation reviewed and current"
- **Log Analysis**: "All events logged", "No gaps detected"

### Non-Compliant Results

- **Missing Implementation**: "Feature not configured", "Tool not installed"
- **Partial Implementation**: "80% of systems compliant", "5 of 100 accounts non-compliant"
- **Expired Controls**: "Last review: 18 months ago", "Policy outdated"
- **Configuration Issues**: "3 rules allow non-approved ports", "Encryption not enabled"

### Check Methods

- **Automated scan**: Network scanner, vulnerability scanner, configuration scanner
- **Log analysis**: Central log repository, audit logs, security event logs
- **Manual review**: Document review, policy review, configuration review
- **Interview**: Personnel interview, management interview
- **Observation**: Physical inspection, system observation

## Example Assessment Table (Mock Data)

```markdown
| Control ID | Control Description | Rule Description | Check Method | Check Description | Findings | Status |
|------------|-------------------|------------------|---------------|-------------------|----------|--------|
| AC-2 | Account Management | All user accounts must have MFA enabled | Automated scan | Scan for accounts without MFA | 0 accounts without MFA found | Compliant |
| AC-3 | Access Enforcement | All access decisions must be logged | Log analysis | Verify access logs contain all decisions | 100% of access decisions logged | Compliant |
| AU-2 | Audit Events | All security events must be logged | Log analysis | Verify security events logged to central repository | 5,234 security events logged | Compliant |
| SC-7 | Boundary Protection | Firewall rules restrict traffic to approved ports | Network scan | Verify firewall rules in place | 3 non-approved ports found | Non-Compliant |
```

## Implementation

### Python Script for Mock Data Generation

```python
import json
import random

def generate_mock_assessment():
    controls = [
        {"id": "AC-2", "title": "Account Management"},
        {"id": "AC-3", "title": "Access Enforcement"},
        {"id": "AU-2", "title": "Audit Events"},
        {"id": "SC-7", "title": "Boundary Protection"}
    ]
    
    rules = {
        "AC-2": "All user accounts must have MFA enabled",
        "AC-3": "All access decisions must be logged",
        "AU-2": "All security events must be logged",
        "SC-7": "Firewall rules restrict traffic to approved ports"
    }
    
    checks = {
        "AC-2": {"method": "Automated scan", "desc": "Scan for accounts without MFA"},
        "AC-3": {"method": "Log analysis", "desc": "Verify access logs"},
        "AU-2": {"method": "Log analysis", "desc": "Verify security events logged"},
        "SC-7": {"method": "Network scan", "desc": "Verify firewall rules"}
    }
    
    results = []
    for control in controls:
        cid = control["id"]
        status = random.choice(["Compliant", "Non-Compliant"])
        
        if status == "Compliant":
            findings = f"0 issues found for {cid}"
        else:
            findings = f"3 issues found for {cid}"
        
        results.append({
            "control_id": cid,
            "control_title": control["title"],
            "rule": rules[cid],
            "check_method": checks[cid]["method"],
            "check_desc": checks[cid]["desc"],
            "findings": findings,
            "status": status
        })
    
    return results
```

## Usage

1. Call `generate_mock_assessment()` to create mock data
2. Format results as markdown table
3. Display to user for review
4. Later, replace mock data with actual component definition and validation results
