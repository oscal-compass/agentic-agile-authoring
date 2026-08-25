# Link an assessment result to a pre-defined POA&M (path C, phase 2)

Prerequisite: a **pre-defined POA&M** built from a component-definition
([from-component-definition.md](from-component-definition.md)) and an OSCAL
`assessment-results.json`.

This step layers the assessment onto the pre-defined POA&M: each finding becomes a top-level
`Finding` (with its `Observation`, and an optional `Risk`) and is **cross-linked to the existing
pre-defined poam-item** for the same check. **No new poam-items are created** — the weakness catalog
was already defined in phase 1; assessment only records *which* weaknesses are currently open.

## The linking key: `check-id` (fallback `control-id`)

For each finding in the assessment result:

1. Read the finding's linked observation(s) (`finding.related-observations[].observation-uuid` →
   `results[].observations[]`) and take the observation's **`check-id`** prop.
2. Find the pre-defined poam-item whose **`check-id`** prop matches. If the observation has no
   `check-id`, fall back to matching the finding's control **`target-id`** against the item's
   `control-id` prop.
3. Append the observation + a top-level `Finding` (objective-id target, state
   `not-satisfied`/`satisfied`) + any linked `Risk`, and cross-link the matched poam-item via
   `related-findings` / `related-observations` / `related-risks`.

For the linking to be unambiguous, the assessment's observations should carry a **`check-id`** prop
naming the rule/check that was evaluated (the demo assessment does this). If yours does not, add it,
or rely on the control-id fallback.

## Keep-all semantics

The pre-defined POA&M is a **catalog of potential weaknesses**. Linking keeps *every* item:

- A **not-satisfied** finding marks its item as a currently-open weakness.
- A **satisfied** finding is still recorded and linked — the item stays as a pre-declared weakness
  that currently passes (useful provenance: "this was checked and passed").

This is deliberate (the component-definition-driven interpretation): the item set is fixed by the
component-definition; the assessment only toggles open/closed via findings.

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
pre-defined item (`unmatched` findings are still recorded, with a warning — usually a `check-id`
mismatch to investigate).

## Next

- Validate authoritatively with `trestle validate -t plan-of-action-and-milestones`
  ([build-poam.md](build-poam.md)).
- Preview as markdown ([poam-preview.md](poam-preview.md)) — open vs satisfied items are
  distinguished from the linked findings.
