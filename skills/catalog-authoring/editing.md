# Phase 2: Editing & Embedding

Execute from parameter editing to profile/catalog deployment using trestle MCP.

## Step 1: Control Selection

Confirm target control(s) for editing with the user, presented with brief descriptions. When no
human is in the loop, take the selection from the profile's `include-controls` — it is already
the authoritative list — and do not ask.

## Step 2: CSV Template Generation

3-column format: `What's required`, `Value`, `Id`

**Example**: `tmp/ac-1_params.csv`
```csv
"What's required","Value","Id"
"How often the policy be reviewed or updated?","annually","ac-01_odp.05"
```

## Step 3: CSV Completion & Confirmation

- When the agent completes: **display the content to the user → ask for confirmation using
  whatever ask/confirm affordance the harness provides → proceed only after OK**
- Prohibited: Automatic reflection/commit
- Allowed: Reflection/commit after confirmation
- **With no human in the loop**, leave the CSV in the workspace as the record and proceed. See
  SKILL.md, *Running with no human in the loop*.

## Step 4: Parameter Reflection

Set values in the **`x-trestle-set-params` header** of each control markdown file. That header is
the only thing `trestle_author_profile_assemble` reads values from (`set_parameters: true` →
`ControlReader`, key `x-trestle-set-params`), and trestle's own generated comment in the header
says it: *only the `profile-values` and `display-name` properties are editable*.

```yaml
x-trestle-set-params:
  ac-01_odp.03:
    profile-values:
      - organizational
    profile-param-value-origin: SYSTEM.md — single-tenant service, one owning team
```

Leave the `{{ insert: param, ... }}` moustache in the prose exactly as generated. Rewriting the
prose does not create a set-parameter: the assembled profile takes nothing from the statement
text, so an edit there is lost and the parameter stays unset while the markdown looks finished.
Maintain escape characters like `\[` while editing.

Two cases worth getting right:

- **A parameter deliberately left unset.** Give it a `profile-param-value-origin` saying why and
  no `profile-values`. The decision is then recorded in the artefact instead of looking like an
  oversight, and `profile-resolve`'s `value_not_assigned_prefix` (Step 5) marks it in the prose.
- **An aggregating parameter** — one whose header shows an `aggregates` property. Its value comes
  from the parameters it aggregates, and trestle states `profile-values` is not applicable to it.
  Do not set one.

Choose values as minimal phrases that read naturally in the control sentence:

```
Prose:         "Develop an {{ insert: param, ac-01_odp.03 }} access control policy."
Appropriate:   ac-01_odp.03 = "organizational" → "organizational access control policy"
Inappropriate: ac-01_odp.03 = "access control policy" → redundant and unnatural
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
