# Phase 1: Setup

Asset acquisition and structure organization using trestle MCP.

## ⚠️ CRITICAL: Do NOT Use trestle_root Parameter

**All trestle MCP operations in this phase MUST omit the `trestle_root` parameter.**

trestle automatically detects and uses the workspace in the current directory. Do not pass `trestle_root` parameter to any MCP tool call.

## Step 1: Initialize Workspace

Initialize trestle in current directory:
- MCP tool: `trestle_init`
- mode: `local`
- trestle_root: (omit this parameter)

## Step 2: Asset Identification

Identify required assets:
- catalog (`catalogs/*`)
- profile (`profiles/*`)
- md_profile, csv

## Step 3: Acquisition (using trestle MCP)

### Catalog Acquisition

**[A] NIST Official URL**
- MCP tool: `trestle_import`
- file: `https://raw.githubusercontent.com/usnistgov/oscal-content/refs/heads/main/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json`
- output: `mycatalog`

**[B] Local File**
- MCP tool: `trestle_import`
- file: `./resources/catalogs/your_catalog.json`
- output: `mycatalog`

### Profile Acquisition

**[A] NIST Baseline (low/moderate/high/privacy)**
- MCP tool: `trestle_import`
- file: `https://raw.githubusercontent.com/usnistgov/oscal-content/refs/heads/main/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_LOW-baseline_profile.json`
- output: `myprofile_low`

**[B] Local Custom**
- MCP tool: `trestle_import`
- file: `./resources/profiles/custom_profile.json`
- output: `myprofile_custom`

## Step 4: Profile Editing (Required)

### 3a. Modify `imports[].href` to project-relative path

Edit `imports[].href` in profile.json to set a relative path pointing to the catalog within the project:

```json
"imports": [
  {
    "href": "catalogs/mycatalog/catalog.json"
  }
]
```

### 3b. Select Controls via Profile (Recommended Approach)

**To focus on specific controls (e.g., CM-2 only):**

Edit the `include-controls` section in profile.json to specify only desired control IDs:

```json
"include-controls": [
  {
    "with-ids": [
      "cm-2"
    ]
  }
]
```

**Benefits:**
- Follows NIST OSCAL framework standards
- Profile becomes the authoritative source for control selection
- Enables proper control inheritance and parameter management
- Supports profile resolution and assembly workflows

**Do NOT create custom control markdown files** - use profile-based selection instead.

## Step 5: Markdown Deployment (Required)

### Catalog→md
- MCP tool: `trestle_author_catalog_generate`
- name: `<catalog>`
- output: `<md_catalog>`

### Profile→md (Recommended for control selection)
- MCP tool: `trestle_author_profile_generate`
- name: `<profile>`
- output: `<md_profile>`
- **Result**: Generates markdown only for controls specified in profile's `include-controls`

### Profile resolved catalog→md (for change tracking)
- MCP tool: `trestle_author_profile_resolve`
- name: `myprofile`
- output: `catalog_resolved`
- show_values: true
- bracket_format: `"."`

Then:
- MCP tool: `trestle_author_catalog_generate`
- name: `catalog_resolved`
- output: `md_catalog_resolved`

**Important**: After converting to md, do not read catalog.json directly. Use only the md directory.

## Troubleshooting: trestle_root Parameter Issues

**Problem**: Path resolution errors when using `trestle_root` parameter
```
Error: Cache get failure for catalogs/...: [Errno 2] No such file or directory
```

**Solution**: Do NOT use `trestle_root` parameter. Instead:
1. Initialize trestle workspace in `./workspace/` directory
2. Run trestle MCP commands without `trestle_root` parameter
3. trestle will automatically use the workspace in current directory

**Robust Approach**:
- Initialize trestle workspace: `trestle_init` with mode `local` (no trestle_root)
- Run all trestle MCP operations without `trestle_root` parameter
- trestle automatically detects and uses the workspace structure

## Completion Criteria

- [ ] catalog/profile/md deployment complete (using trestle MCP)
- [ ] href in profile is project-relative path
- [ ] Profile's `include-controls` specifies desired controls only
- [ ] Confirmed md operations without reading catalog.json directly
- [ ] All MCP calls executed without `trestle_root` parameter
- [ ] (Optional) `<id>-initial` branch created and committed (if using Git workflow)
