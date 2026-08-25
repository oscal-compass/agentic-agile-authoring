# Link an assessment result to a pre-defined POA&M (path C, phase 2)

Prerequisite: a **pre-defined POA&M** built from a component-definition
([from-component-definition.md](from-component-definition.md)) and an OSCAL
`assessment-results.json`.

This step layers the assessment onto the pre-defined POA&M: each result becomes a top-level
`Finding` (with its `Observation`, and any `Risk`) and is **cross-linked to the existing pre-defined
poam-item** for the same rule/check. **No new poam-items are created** — the weakness catalog was
already defined in phase 1; assessment only records *which* weaknesses are currently open.

The builder handles **two shapes** of assessment result:

### A) Results with explicit `findings[]`

For each finding: read its linked observation(s)
(`finding.related-observations[].observation-uuid` → `results[].observations[]`), take the
observation's rule key, carry the observation + emit a top-level `Finding` (objective-id target,
`not-satisfied`/`satisfied`) + any linked `Risk`, and cross-link the matched item.

### B) Observation-only results (real PVP output — Auditree / Kyverno / OCM)

Real policy-validation output often has **observations but no findings**, with per-subject
pass/fail. The builder **derives** a finding per observation:

- **rule key** ← the observation's `check-id`, else `assessment-rule-id`, else `rule-id` prop.
- **state** ← from the observation's **subject-level `result` props**: if *any* evaluated subject is
  `failure`/`fail`/`error` (etc.) the rule is **`not-satisfied`**; if subjects were evaluated and
  none failed, **`satisfied`**. (An observation with no per-subject result at all is treated as
  `not-satisfied`, conservatively.)
- The full observation — including every evaluated subject and its `result`/`reason` — is carried
  into the POA&M as evidence, and a derived `Finding` (target = the item's `control-id`) is linked.

## The linking key

In both shapes the item is matched by the observation's rule identifier —
**`check-id` → `assessment-rule-id` → `rule-id`** (first present) — against the pre-defined item's
`check-id` prop, falling back to the finding's control `target-id` vs the item's `control-id`. So an
assessment need only name each observation's rule via any of those props (the demo's real assessment
uses `assessment-rule-id`).

## Keep-all semantics

The pre-defined POA&M is a **catalog of potential weaknesses**. Linking keeps *every* item:

- A **not-satisfied** finding marks its item as a currently-open weakness.
- A **satisfied** finding is still recorded and linked — the item stays as a pre-declared weakness
  that currently passes (useful provenance: "this was checked and passed").
- An item whose rule the assessment **did not cover** keeps its pre-defined entry with **no
  finding** (a known potential weakness that simply wasn't assessed this run).

This is deliberate (the component-definition-driven interpretation): the item set is fixed by the
component-definition; the assessment only toggles open/closed (or leaves untouched) via findings.

## Run it

```bash
# uv:
uv run --with 'compliance-trestle>=3.0' python "$SKILL_DIR/build_poam.py" link-assessment \
  --poam poam/plan-of-action-and-milestones.json \
  --assessment assessment-results.json --output-dir linked/
# venv:
.venv-poam/bin/python "$SKILL_DIR/build_poam.py" link-assessment \
  --poam poam/plan-of-action-and-milestones.json \
  --assessment assessment-results.json --output-dir linked/
```

The result (`linked/plan-of-action-and-milestones.json`) is valid OSCAL, round-tripped through
`oscal_read`. The tool prints how many findings are open vs satisfied and how many linked to a
pre-defined item (`unmatched` findings are still recorded, with a warning — usually a rule-id ⇄
check-id mismatch to investigate).

## Next

- Validate authoritatively with `trestle validate -t plan-of-action-and-milestones`
  ([build-poam.md](build-poam.md)).
- Preview as markdown ([poam-preview.md](poam-preview.md)) — open vs satisfied items are
  distinguished from the linked findings.
