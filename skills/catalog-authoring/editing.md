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
- name: `myprofile`
- markdown: `md_profile`
- output: `myprofile`
- set-parameters: true

### Catalog Regeneration (Required - must execute both commands)

**Command 1: Resolve Profile**
- MCP tool: `trestle_author_profile_resolve`
- name: `myprofile`
- output: `catalog_resolved`
- set-parameters: true
- bracket-format: `"."`

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
