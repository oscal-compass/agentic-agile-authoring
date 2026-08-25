# From assessment result → draft weakness rows

The POA&M is seeded from the **failed / non-compliant findings** of an assessment result. This
step turns those findings into draft weakness rows; the user fills in the remediation plan later
(see the SKILL.md workflow).

## Step 1 — Locate and read the assessment result

The assessment result may be:

- The **`assessment` skill's markdown table** (columns include Control ID, Rule/Check, Findings,
  **Status**). This is the common case today.
- An OSCAL **`assessment-results.json`** (findings with `target` status, observations, risks).

Ask the user for the path if it is not obvious.

## Step 2 — Keep only the FAILED findings

Select only rows/findings whose status is **non-compliant / not-satisfied / failed**. Compliant
controls are not weaknesses and must NOT become POA&M items.

- Markdown table: keep rows where Status is "Non-Compliant" (or equivalent).
- OSCAL `assessment-results.json`: iterate `assessment-results.results[].findings[]` and keep a
  finding when `finding.target.status.state == "not-satisfied"`. For each kept finding:
  - **control id** ← `finding.target.target-id` (e.g. `ac-2`) → goes into `controls`
  - **evidence** ← `finding.description` (and, if richer, the linked
    `results[].observations[]` whose `uuid` matches `finding.related-observations[].observation-uuid`)
  - A `satisfied` finding is compliant — skip it.

  Read the JSON with a tool (or `python -c`/`jq`); do not eyeball a large file.

**If there are zero failed findings:** there is nothing to remediate. Tell the user the system
appears compliant and no POA&M is needed — or ask whether they want to enter weaknesses manually.
Do not fabricate weaknesses.

## Step 3 — Draft one weakness row per failed finding

For each failed finding, draft:

| Field | Source |
|---|---|
| `poam_id` | assign `POAM-001`, `POAM-002`, … (or reuse an existing ID) |
| `weakness_name` | name the **deficiency**, i.e. what is wrong — NOT the rule/check text. Phrase it as the failure. |
| `weakness_description` | what is wrong + the evidence from the finding |
| `controls` | the affected control ID(s), e.g. `["ac-2"]` |

> **Name the failure, not the requirement.** The assessment's rule/check column states what
> *should* be true ("Admin accounts require MFA"); the weakness is what is *actually wrong*. Invert
> it. Example: rule "Admin accounts require MFA" + finding "3 admin accounts without MFA" →
> `weakness_name`: **"MFA not enforced on admin accounts"** (not "Admin accounts require MFA").

### Filling missing control / component context — tiered fallback

If a failed finding does **not** carry the control ID (or which component it applies to), the
POA&M is still valid but its linkage is empty. Fill the gap in this order:

1. **Use what's embedded** in the finding (control ID / component named in the row).
2. **Ask the user**: "Which control(s) does this weakness relate to? Which component?"
3. **Recover from upstream** if available: match the finding text against the `catalog` /
   `component-definition` (or SSP) the user has on hand.

## Step 4 — Elicit the plan from the user (not in the assessment)

For each drafted weakness, ask the user for:

- `remediation_plan` — how they will fix it
- `milestones` — list of `{description, target_date}`
- `poc` — the responsible owner / team
- `scheduled_completion_date` — overall due date
- `risk_rating` — e.g. High / Moderate / Low

## Step 5 — Assemble `poam_input.json`

Combine the drafted rows + the user's plan fields into the input JSON described in
[poam-model.md](poam-model.md), then proceed to [build-poam.md](build-poam.md).
