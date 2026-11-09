# Phase 2: Editing & Embedding

Execute from parameter editing to profile/catalog deployment using trestle MCP.

## Step 1: Control Selection

Confirm target control(s) for editing with user. Present with brief descriptions.

## Step 2: CSV Template Generation

3-column format: `What's required`, `Value`, `Id`

**Example**: `tmp/ac-1_params.csv`
```csv
"What's required","Value","Id"
"How often the policy be reviewed or updated?","annually","ac-01_odp.05"
```

## Step 3: CSV Completion & Confirmation

- When agent completes: **Must display content to user → confirm (ask_followup_question) → proceed to next step only after OK**
- Prohibited: Automatic reflection/commit
- Allowed: Reflection/commit after confirmation

## Step 4: Parameter Reflection

- Update md files (maintain escape characters like `\[`)
- Replace with minimal phrases to create natural sentences

**Example**:
```
Original: "Develop an {{ insert: param, ac-01_odp.03 }} access control policy."
Appropriate: ac-01_odp.03 = "organizational" → "organizational access control policy"
Inappropriate: ac-01_odp.03 = "access control policy" → Redundant and unnatural
```

## Step 5: Profile/Catalog Regeneration

### Profile Regeneration (Required)
- MCP tool: `trestle_author_profile_assemble`
- markdown_dir: `md_profile`
- output_profile: `myprofile`
- set_parameters: true

The two required parameters are `markdown_dir` and `output_profile`. There is also a `name`
parameter, but it is optional and it is not the output. `set_parameters: true` is what reads the
`x-trestle-set-params` header back out of the markdown into the profile.

### Catalog Regeneration (Required - must execute both commands)

**Command 1: Resolve Profile**
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


**Command 2: Generate Markdown**
- MCP tool: `trestle_author_catalog_generate`
- name: `catalog_resolved`
- output: `md_catalog_resolved`

**Important**: Both Step 1 and Step 2 must be completed for proper deployment.

## Completion Criteria

- [ ] CSV template generated and edited
- [ ] Profile regenerated (trestle_author_profile_assemble)
- [ ] Catalog resolved (trestle_author_profile_resolve)
- [ ] Markdown catalog generated (trestle_author_catalog_generate)
- [ ] (Optional) PR created with `<id>-review` branch (if using Git workflow)
