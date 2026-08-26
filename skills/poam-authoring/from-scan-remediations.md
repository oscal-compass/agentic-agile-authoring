# From a scan tool's remediation data → POA&M (path D, reference-driven)

Use this when a **scanner / security tool** emits its own **remediation data** (per weakness: what's
wrong + how to fix it, often with severity, affected assets, owners, due dates, steps) and you want
it held as an OSCAL POA&M — typically to load into another platform.

The point of this path: **you don't hand-code each tool.** The tool's export format, and the exact
shape the destination wants the remediation in, are **data** — you learn them from a *sample /
reference* the user provides and fill the POA&M accordingly. OSCAL `props` and the `risk.remediations`
(`response`) object are extension points, so almost any shape maps cleanly.

## Inputs

1. **The scanner's remediation export** (any format — JSON/CSV/xlsx/…).
2. **A reference for how to represent it** — one of:
   - a *sample* of the desired output remediation (an example POA&M `risk`/`remediation` the user
     shows you), or
   - a *field legend / mapping note* ("`fix` → the remediation text, `sev` → severity, `due` → the
     deadline, put our finding id in a `vendor-finding-id` prop under ns `…`"), or
   - nothing explicit — then propose a sensible default mapping and confirm it.

## Where remediation goes in OSCAL (so you map to the right place)

- **what's wrong** → the `poam-item` (`weakness_name`/`weakness_description`) and any `observation`.
- **how to fix it** → the item's **`risk.remediations[]`** — an OSCAL *response*:
  `lifecycle` (`recommendation` | `planned` | `completed`), `title`, `description`, `props`,
  `origins` (attribute it to the tool — `actor-type: tool`, an id only), `required-assets`, and
  **`tasks[]`** for steps/milestones (`type: "milestone"`, `timing`, `responsible-roles`).
- **when** → `risk.deadline` (overall) and per-step `task.timing`.
- **anything tool-specific** → free-form `props` (on the item via `extra_props`, or on the
  risk/response/task) under whatever namespace the reference names. Never invent a control mapping the
  tool didn't provide.

## Workflow

1. **Set up the isolated env** ([setup-env.md](setup-env.md)).
2. **Read the export + the reference.** Derive a **field mapping** (tool field → POA&M target). Show
   it to the user as a short table and **confirm** before building — do not fabricate remediation.
3. **Emit `poam_input.json`** ([poam-model.md](poam-model.md)): one item per finding, with the
   remediation expressed through the **pass-through** `risk` object (and `extra_props`) *exactly as
   the reference dictates*. Example item:

   ```json
   {
     "weakness_name": "MFA not enforced on admin accounts",
     "weakness_description": "3 cluster-admin accounts can authenticate without MFA.",
     "controls": ["ia-2"],
     "source_identifier": "SCN-F-42",
     "extra_props": [{"name": "scanner-severity", "ns": "https://<vendor>/ns", "value": "critical"}],
     "risk": {
       "status": "open",
       "deadline": "2026-12-31T00:00:00+00:00",
       "props": [{"name": "vendor-finding-id", "ns": "https://<vendor>/ns", "value": "F-42"}],
       "remediations": [
         {"lifecycle": "planned", "title": "Enforce MFA", "description": "Enable the IdP MFA policy …",
          "tasks": [{"type": "milestone", "title": "Enable MFA policy",
                     "timing": {"within-date-range": {"end": "2026-10-15T00:00:00+00:00"}}}]}
       ]
     }
   }
   ```

   You may omit `uuid`s — the builder backfills deterministic ones for the risk / remediations /
   tasks. Any valid OSCAL shape inside `risk` is written through and validated by trestle; no builder
   change is needed for a new format.
4. **Build + validate** ([build-poam.md](build-poam.md)): `build_poam.py build --input poam_input.json`.
   Confirm `trestle validate` says **VALID**.
5. **Preview** ([poam-preview.md](poam-preview.md)) and confirm with the user.

## Notes

- **Reference-driven, not tool-coded.** A different scanner (or the same one, changed) just means a
  different sample/mapping — re-map and rebuild; the skill and builder don't change. Keep any
  proprietary tool/platform name in the *data and the user's reference*, never hard-coded here.
- **Multiple remediations per risk** are fine — e.g. the tool's `recommendation` plus your
  organization's committed `planned` response, both under one `risk`.
- If the destination platform requires a specific namespace or prop names, put them in the mapping
  (the reference), not in code.
