# Best Practices & Lessons Learned

## trestle_root Parameter Bug

### Problem
The `trestle_root` parameter in trestle MCP tools has path resolution bugs that cause failures:

```
Error: Cache get failure for catalogs/...: [Errno 2] No such file or directory
```

This occurs because trestle resolves relative paths from the workspace root, not from the specified `trestle_root` directory.

### Solution
**Do NOT use the `trestle_root` parameter.** Instead:

1. Initialize trestle workspace in current directory:
   ```
   MCP tool: trestle_init
   mode: local
   (omit trestle_root parameter)
   ```

2. Run all trestle MCP commands without `trestle_root`:
   ```
   MCP tool: trestle_import
   file: https://...
   output: mycatalog
   (omit trestle_root parameter)
   ```

3. trestle will automatically use the workspace in current directory

### Why This Works
- trestle searches for `.trestle/` directory in current working directory
- All relative paths are resolved from the workspace root
- No ambiguity in path resolution
- More robust and predictable behavior

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
(omit trestle_root parameter)
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
   └─ trestle_import (no trestle_root)

3. Import profile
   └─ trestle_import (no trestle_root)

4. Edit profile's include-controls
   └─ Specify desired control IDs only

5. Generate markdown from profile
   └─ trestle_author_profile_generate (no trestle_root)
   └─ Result: Only selected controls in markdown
```

### Phase 2: Customization
```
1. Edit generated markdown files
   └─ Set organization-specific parameters
   └─ Add implementation guidance

2. Assemble profile back to JSON
   └─ trestle_author_profile_assemble (no trestle_root)
   └─ Use --set-parameters flag
```

### Phase 3: Deployment
```
1. Resolve profile to catalog
   └─ trestle_author_profile_resolve (no trestle_root)

2. Generate resolved catalog markdown
   └─ trestle_author_catalog_generate (no trestle_root)

3. Deploy to organization
   └─ Use markdown or JSON as needed
```

## Common Mistakes to Avoid

### ❌ Mistake 1: Using trestle_root Parameter
```
MCP tool: trestle_import
file: https://...
output: mycatalog
trestle_root: /path/to/workspace  # ❌ Don't do this
```

### ✅ Correct Approach
```
MCP tool: trestle_import
file: https://...
output: mycatalog
(omit trestle_root parameter)  # ✅ Do NOT specify trestle_root
```

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

**Solution**:
1. Do NOT use `trestle_root` parameter in any MCP calls
2. Ensure `.trestle/` directory exists in current directory
3. Initialize trestle with: `trestle_init` mode `local` (no trestle_root)
4. All MCP operations work from workspace context automatically

### Issue: Profile Generation Fails
**Symptom**: `Error generating the profile markdown failed`

**Solution**:
1. Verify profile's `imports[].href` points to correct catalog path
2. Ensure catalog is in correct location relative to profile
3. Check that `include-controls` specifies valid control IDs
4. Do NOT use `trestle_root` parameter

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

**Last Updated**: 2026-03-17  
**Version**: 1.0  
**Status**: Active Best Practices
