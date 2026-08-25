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

## Step 3 — Draft one weakness per failed finding

**The unit of a POA&M is the weakness, not the control.** Draft one weakness per failed finding.
A weakness carries zero or more *anchors* for traceability; `control-id` is optional (the output
is valid without it), but fill an anchor whenever the source provides one.

| Field | Source |
|---|---|
| `poam_id` | assign `POAM-001`, `POAM-002`, … (or reuse an existing ID) |
| `weakness_name` | name the **deficiency**, i.e. what is wrong — NOT the rule/check text. Phrase it as the failure. |
| `weakness_description` | what is wrong + the evidence from the finding |
| `controls` | affected control ID(s), e.g. `["ac-2"]` — see resolution below (may be empty) |
| `check_id` | the scanner/rule id (e.g. `QGUARD-CHECK-...`) when the source is a scanner |
| `cve` | a CVE id, if the finding has one |
| `source_identifier` | the detector's own id for the weakness, if any |
| `affected_files` | files the finding touches (code-scanner findings) |

> **Name the failure, not the requirement.** The assessment's rule/check column states what
> *should* be true ("Admin accounts require MFA"); the weakness is what is *actually wrong*. Invert
> it. Example: rule "Admin accounts require MFA" + finding "3 admin accounts without MFA" →
> `weakness_name`: **"MFA not enforced on admin accounts"** (not "Admin accounts require MFA").

> **Every weakness should have ≥1 anchor** (`control-id` / `check-id` / `cve` /
> `source_identifier`). A weakness with none is still valid but not traceable — the builder warns.

### Resolving `control-id` — fill it when a source lets you (it is optional)

Try these in order; stop at the first that yields control id(s). If none do, leave `controls` empty
and rely on `check_id`/`cve` as the anchor (common for scanner findings).

1. **The assessment result itself** — `finding.target.target-id` (OSCAL), or the Control ID column
   (markdown). This is the direct case (the demo `assessment-results.json` has it).
2. **A control ↔ rule/check mapping file**, if the user provides one — map the finding's
   `check_id`/rule to the control id(s).
3. **A trestle-style `component-definition.json`**, if available — its control-implementations map
   each rule (`Rule_Id`) to the control id(s) it satisfies; match the finding's rule/check to a
   rule there and read off the control(s). (This is exactly what the `component-definition` skill
   produces, so it plugs straight in.)
4. **A `catalog`**, if available — use it to normalize / confirm the control ids resolved above.
5. Otherwise **ask the user**, or leave `controls` empty.

## Step 4 — Carry evidence + risk from the assessment (optional but recommended)

If the assessment result has observations/risks, carry them into each weakness so the POA&M keeps
the evidence and cross-links (this is what a hand-authored POA&M does):

- `observation`: `{description, methods, title}` — from the finding's linked observation
  (`results[].observations[]` matched via `related-observations[].observation-uuid`), or the
  finding description. The builder emits an OSCAL Observation and links it (`related-observations`).
- `risk`: `{statement, status, title, description}` — the risk the weakness poses. The builder
  emits an OSCAL Risk and links it (`related-risks`). Use `status: "open"` for an unremediated risk.

## Step 5 — Elicit the plan from the user (not in the assessment)

For each drafted weakness, ask the user for:

- `remediation_plan` — how they will fix it
- `milestones` — list of `{description, target_date}`
- `poc` — the responsible owner / team
- `scheduled_completion_date` — overall due date
- `risk_rating` (control-assessment style) or `severity` (scanner style), and `phase` if used

## Step 6 — Assemble `poam_input.json`

Combine the drafted weaknesses (anchors + evidence/risk) + the user's plan fields into the input
JSON described in [poam-model.md](poam-model.md), then proceed to [build-poam.md](build-poam.md).
