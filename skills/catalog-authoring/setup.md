# Phase 1: Setup

Asset acquisition and structure organization using trestle MCP.

## The workspace every call runs in

trestle commands resolve a relative path against the working directory of the server process, and
the MCP client — not this skill — decides what that is. Two ways to make it the workspace:

- **Pass `trestle_root` as an absolute path.** On compliance-trestle-mcp 1.0.0+ the wrapper runs
  the command inside it, so a workspace-relative path resolves. Give it an absolute path because a
  relative one is made absolute against the *server's* directory — which the client chose and you
  do not know — so `./workspace` names somewhere unpredictable.
- **Omit it when the server is already running in the workspace.** The steps below are written
  that way, which is why they pass bare names like `mycatalog`.

Before 1.0.0, `trestle_root` was a flag and nothing more — it did not move the working directory,
so omitting it was the only thing that worked. `best-practices.md` has the history and the
measurements; if you are on an older server, keep omitting it.

## Step 1: Initialize Workspace

Initialize trestle in current directory:
- MCP tool: `trestle_init`
- mode: `local`
- trestle_root: omit it when the server runs in the workspace, otherwise its absolute path

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
- bracket_format: `"[.]"`
- value_not_assigned_prefix: `"ORGANISATION TO DEFINE —"`

`profile-resolve` has no `set_parameters` parameter — `show_values: true` is what substitutes
values into the prose. In `bracket_format` the dot stands for the value, so `"."` on its own
renders the value with nothing around it; `"[.]"` is what makes a filled parameter visible, and
more than one dot is an error. `value_not_assigned_prefix` requires `show_values` and marks every
ODP still unset, printing its label rather than a blank.

Do not combine `show_values` with `show_labels` or `label_prefix`: trestle rejects it with
`Use of show-values is not compatible with show-labels or label-prefix`.

Then:
- MCP tool: `trestle_author_catalog_generate`
- name: `catalog_resolved`
- output: `md_catalog_resolved`

**Important**: After converting to md, do not read catalog.json directly. Use only the md directory.

## Troubleshooting: a relative path that does not resolve

**Problem**
```
Error: Cache get failure for catalogs/...: [Errno 2] No such file or directory
```

The path was resolved against a working directory that is not the workspace.

**Solution**
1. Pass `trestle_root` as an **absolute** path, so the command runs in the workspace
   (compliance-trestle-mcp 1.0.0+)
2. Check `.trestle/` exists there — `trestle_init` mode `local` creates it
3. A `trestle_root` that does not exist is reported as
   `Given directory ... is not in a valid trestle root directory`, which names the path, so read
   that before suspecting the file
4. On a pre-1.0.0 server the parameter cannot help: start the server in the workspace and omit it

## Completion Criteria

- [ ] catalog/profile/md deployment complete (using trestle MCP)
- [ ] href in profile is project-relative path
- [ ] Profile's `include-controls` specifies desired controls only
- [ ] Confirmed md operations without reading catalog.json directly
- [ ] Every MCP call ran in the workspace — `trestle_root` absolute, or omitted with the server started there
- [ ] (Optional) `<id>-initial` branch created and committed (if using Git workflow)
