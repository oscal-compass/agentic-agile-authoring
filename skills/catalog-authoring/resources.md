# NIST OSCAL Resources

Quick reference for common NIST OSCAL catalog and profile URLs.

## NIST SP 800-53 Rev 5 Catalog

**Full Catalog:**
```
https://raw.githubusercontent.com/usnistgov/oscal-content/refs/heads/main/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json
```

## NIST SP 800-53 Rev 5 Baselines

**Base URL:**
```
https://raw.githubusercontent.com/usnistgov/oscal-content/refs/heads/main/nist.gov/SP800-53/rev5/json/
```

**LOW Baseline:**
```
NIST_SP-800-53_rev5_LOW-baseline_profile.json
```

**MODERATE Baseline:**
```
NIST_SP-800-53_rev5_MODERATE-baseline_profile.json
```

**HIGH Baseline:**
```
NIST_SP-800-53_rev5_HIGH-baseline_profile.json
```

**PRIVACY Baseline:**
```
NIST_SP-800-53_rev5_privacy-baseline_profile.json
```

## Usage with trestle_import

**Example: Import NIST SP 800-53 Rev 5 Catalog**
```
MCP tool: trestle_import
file: https://raw.githubusercontent.com/usnistgov/oscal-content/refs/heads/main/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json
output: nist_sp800_53_rev5
```

**Example: Import LOW Baseline Profile**
```
MCP tool: trestle_import
file: https://raw.githubusercontent.com/usnistgov/oscal-content/refs/heads/main/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_LOW-baseline_profile.json
output: nist_low_baseline
```

## Other NIST Resources

For additional OSCAL content, visit:
- NIST OSCAL Content Repository: https://github.com/usnistgov/oscal-content
- NIST OSCAL Documentation: https://pages.nist.gov/OSCAL/
