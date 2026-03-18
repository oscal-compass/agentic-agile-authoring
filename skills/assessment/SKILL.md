---
name: assessment
description: Generate OSCAL assessment results by mapping component-definition rules to validation checks and evaluating control compliance. Use when user wants to assess whether controls are satisfied based on component implementations and validation checks, or generate assessment tables with compliance status.
argument-hint: Optional component name or assessment scope (e.g., "firewall", "kubernetes-cluster")
license: Complete terms in LICENSE.txt
---

# Assessment

## Purpose

Given a component definition with service component rules and validation component checks, generate an OSCAL assessment that evaluates whether controls are satisfied based on the control-rule-check mappings.

This skill bridges the gap between **what a component implements** and **whether those implementations actually satisfy the control requirements**.

## Concepts

- **service component**: implements controls directly (firewall, OS, middleware, application)
- **validation component**: verifies that service component rules are actually enforced (scanner, audit tool, monitoring agent)
- **control-rule-check mapping**: derived from component definition to show which checks validate which rules for which controls
- **assessment result**: compliance status (compliant/non-compliant) with evidence from validation checks

## Main Tasks

1. Load component definition (service and validation components)
2. Extract control-rule mappings from service component
3. Extract rule-check mappings from validation component
4. Derive control-rule-check mappings
5. Generate assessment table with mock data (for demo)
6. Output assessment results in markdown or OSCAL format

## Sub-skills

- [assessment-table.md](assessment-table.md) — Generate human-readable assessment table showing control compliance status
- [mock-data.md](mock-data.md) — Create mock assessment data for demo purposes

## Workflow

1. Confirm the component definition source (file path or trestle workspace)
2. Load component definition JSON or markdown
3. Extract service component rules and their control mappings
4. Extract validation component checks and their rule mappings
5. Build control-rule-check mapping matrix
6. For each control, evaluate compliance based on validation check results
7. Generate assessment table with:
   - Control ID and description
   - Rule description
   - Check method and description
   - Compliance status (compliant/non-compliant)
   - Evidence/findings
8. Output in markdown table format

## Key Learnings

### Control-Rule-Check Mapping

The mapping chain is:
```
Control ID → Service Component Rule → Validation Component Check → Compliance Status
```

Example:
- Control: AC-2 (Account Management)
- Rule: "All user accounts must have MFA enabled"
- Check: "Scan for accounts without MFA"
- Status: Compliant (0 accounts without MFA found)

### Assessment Table Structure

Generate markdown table with columns:
- **Control ID**: e.g., AC-2
- **Control Description**: e.g., "Account Management"
- **Rule Description**: e.g., "All user accounts must have MFA enabled"
- **Check Method**: e.g., "Automated scan"
- **Check Description**: e.g., "Scan for accounts without MFA"
- **Findings**: e.g., "0 accounts without MFA"
- **Status**: e.g., "Compliant" or "Non-Compliant"

### Mock Data for Demo

For demo purposes, generate mock assessment data:
- Use realistic control IDs from NIST SP 800-53
- Create plausible rule descriptions
- Define check methods (automated, manual, interview, etc.)
- Generate compliance findings with evidence
- Mix compliant and non-compliant results for variety

### Common Patterns

**Automated Checks:**
- Scan results with counts (e.g., "5 vulnerabilities found")
- Configuration verification (e.g., "TLS 1.2+ enabled on all endpoints")
- Log analysis (e.g., "All access attempts logged")

**Manual Checks:**
- Interview results (e.g., "Personnel confirmed policy awareness")
- Document review (e.g., "Incident response plan reviewed and current")
- Observation (e.g., "Physical security controls observed in place")

**Non-Compliant Examples:**
- Missing implementation (e.g., "MFA not configured")
- Partial implementation (e.g., "MFA enabled for 80% of accounts")
- Expired controls (e.g., "Last security training: 18 months ago")
