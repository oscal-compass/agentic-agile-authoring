# Best Practices & Lessons Learned

## `trestle_root` and the server's working directory

### What this file used to say, and why it said it

`trestle_root` was documented here as unusable, on the strength of this failure:

```
Error: Cache get failure for catalogs/...: [Errno 2] No such file or directory
```

The cause was in the **MCP wrapper**, not in trestle. The wrapper handed `--trestle-root` to
trestle as a flag and nothing more, so every argument that is a *filesystem path* was still
resolved by the OS against the server process's working directory — wherever the client launched
it, which is almost never the workspace. Passing `trestle_root` therefore changed nothing, and
starting the server in the workspace and omitting it was the only thing that worked.

### Fixed in compliance-trestle-mcp 1.0.0

`run_trestle_command` now makes the `--trestle-root` value absolute and runs the subprocess
**inside** that directory (`absolute_trestle_root` and `_working_directory` in
`trestle_mcp/libs/trestle.py`, new in 1.0.0). The repo-root `.mcp.json` and this skill's `apm.yml`
both floor the dependency at `compliance-trestle-mcp>=1.0.0`, so this is the behaviour an install
gets. So:

- **Pass `trestle_root` — as an absolute path — when you cannot be sure the server is running in
  the workspace.** It is what makes a workspace-relative path argument mean what you meant, and
  the client decides the working directory, not you.
- **Omitting it is still correct when the server was started in the workspace**, which is what the
  examples below assume.
- A `trestle_root` that does not exist is rejected with `Given directory ... is not in a valid
  trestle root directory`, naming the path. It does not fall back silently.

Not every call was affected, which is why the old rule looked right in some places and not others:
an argument that is a model **name** is resolved by trestle against the root, so it never depended
on the working directory. Measured against trestle 5.2.0 — run from outside the workspace with the
flag alone, `author profile-generate --name miniprof --output md_prof` still writes into the
workspace, while `split -f catalogs/minicat/catalog.json -e catalog.groups --trestle-root <ws>` fails with
`File <cwd>/catalogs/minicat/catalog.json does not exist`.

## Profile-Based Control Selection

### Recommended Approach
**Use profile's `include-controls` to select specific controls, not custom markdown files.**

### Why This Matters
1. **NIST OSCAL Compliance**: Follows official OSCAL framework standards
2. **Proper Inheritance**: Controls inherit parameters and guidance from catalog
3. **Profile Authority**: Profile becomes the authoritative source for control selection
4. **Workflow Support**: Enables profile resolution, assembly, and parameter management
5. **Maintainability**: Single source of truth for control selection

### Implementation

#### Step 1: Edit Profile JSON
Modify `profiles/<profile_name>/profile.json` to specify only desired controls:

```json
{
  "profile": {
    "imports": [
      {
        "href": "catalogs/mycatalog/catalog.json",
        "include-controls": [
          {
            "with-ids": [
              "cm-2",
              "cm-3",
              "cm-5"
            ]
          }
        ]
      }
    ]
  }
}
```

#### Step 2: Generate Profile Markdown
```
MCP tool: trestle_author_profile_generate
name: myprofile
output: md_profile
```

**Result**: Generates markdown only for controls specified in `include-controls`

#### Step 3: Customize Parameters
Edit the generated markdown files to set organization-specific parameter values:

```yaml
x-trestle-set-params:
  cm-02_odp.01:
    profile-values:
      - "annually or when significant system changes occur"
    profile-param-value-origin: "Organization Security Policy v1.0"
```

### What NOT to Do
❌ **Do NOT create custom control markdown files** with `org_` prefix  
❌ **Do NOT manually define controls outside the NIST framework**  
❌ **Do NOT bypass profile-based selection**

### Benefits of Profile-Based Approach
- ✅ Maintains NIST framework integrity
- ✅ Enables proper control inheritance
- ✅ Supports parameter management
- ✅ Allows profile resolution and assembly
- ✅ Facilitates compliance tracking
- ✅ Enables version control of control selections

## Workflow Summary

### Phase 1: Setup (Correct Approach)
```
1. Initialize trestle workspace
   └─ trestle init --local

2. Import catalog
   └─ trestle_import

3. Import profile
   └─ trestle_import

4. Edit profile's include-controls
   └─ Specify desired control IDs only

5. Generate markdown from profile
   └─ trestle_author_profile_generate
   └─ Result: Only selected controls in markdown
```

### Phase 2: Customization
```
1. Edit generated markdown files
   └─ Set organization-specific parameters
   └─ Add implementation guidance

2. Assemble profile back to JSON
   └─ trestle_author_profile_assemble
   └─ Use --set-parameters flag
```

### Phase 3: Deployment
```
1. Resolve profile to catalog
   └─ trestle_author_profile_resolve

2. Generate resolved catalog markdown
   └─ trestle_author_catalog_generate

3. Deploy to organization
   └─ Use markdown or JSON as needed
```

## Common Mistakes to Avoid

### ❌ Mistake 1: Passing a relative `trestle_root`
```
MCP tool: trestle_import
file: https://...
output: mycatalog
trestle_root: ./workspace  # ❌ relative to the server's directory, which you do not know
```

A relative value is not doubled — `absolute_trestle_root` calls `os.path.abspath()` before the
path is used as the working directory, which is exactly what stops `ws/ws`. The problem is what it
is absolute *against*: the server process's directory, chosen by the client. So `./workspace`
names a place you cannot predict, and usually one that is not a workspace at all.

### ✅ Correct Approach
```
MCP tool: trestle_import
file: https://...
output: mycatalog
trestle_root: /abs/path/to/workspace  # ✅ absolute, or omit it when the server runs in the workspace
```

This file used to say never to pass `trestle_root` at all. That was a workaround for a wrapper bug
fixed in compliance-trestle-mcp 1.0.0 — see the first section.

### ❌ Mistake 2: Creating Custom Control Files
```
org-regulatory-controls/
├── org_cm-2_regulatory_control.md  # ❌ Don't create custom files
└── org_cm-3_regulatory_control.md  # ❌ Not NIST compliant
```

### ✅ Correct Approach
```
org-regulatory-controls/
├── profiles/
│   └── nist_low_baseline/
│       └── profile.json  # ✅ Edit include-controls here
└── md_profile/
    └── cm/
        ├── cm-2.md  # ✅ Generated from profile
        └── cm-3.md  # ✅ Generated from profile
```

### ❌ Mistake 3: Reading catalog.json Directly
```python
# WRONG - Performance degradation and unnecessary
with open("catalogs/catalog.json") as f:
    catalog = json.load(f)  # ❌ Don't do this
```

### ✅ Correct Approach
```python
# RIGHT - Use markdown files after generation
with open("md_catalog/cm/cm-2.md") as f:
    control = f.read()  # ✅ Use markdown instead
```

## Troubleshooting Guide

### Issue: Path Resolution Errors
**Symptom**: `Cache get failure for catalogs/...: [Errno 2] No such file or directory`

A relative path was resolved against a working directory that is not the workspace.

**Solution**:
1. Pass `trestle_root` as an **absolute** path. On compliance-trestle-mcp 1.0.0+ the command then
   runs in that directory, which is what makes the relative path resolve
2. Ensure `.trestle/` exists there — `trestle_init` mode `local` creates it
3. On a pre-1.0.0 server the parameter cannot help: start the server in the workspace instead

### Issue: Profile Generation Fails
**Symptom**: `Error generating the profile markdown failed`

**Solution**:
1. Verify profile's `imports[].href` points to correct catalog path
2. Ensure catalog is in correct location relative to profile
3. Check that `include-controls` specifies valid control IDs
4. Check the workspace the command actually ran in — `trestle_root` if you passed one, the
   server's working directory if you did not

### Issue: Missing Controls in Generated Markdown
**Symptom**: Only some controls appear in `md_profile/`

**Solution**:
1. This is expected behavior - profile's `include-controls` filters controls
2. To include more controls, edit profile's `include-controls` section
3. Regenerate markdown with `force_overwrite: true`

## References

- [NIST OSCAL Documentation](https://pages.nist.gov/OSCAL/)
- [Compliance Trestle GitHub](https://github.com/IBM/compliance-trestle)
- [NIST SP 800-53 Revision 5](https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final)

---

**Last Updated**: 2026-11-11  
**Version**: 1.1  
**Status**: Active Best Practices
