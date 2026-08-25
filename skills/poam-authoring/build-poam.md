# Build + validate the OSCAL POA&M

Prerequisite: an isolated environment with `compliance-trestle` ([setup-env.md](setup-env.md)),
and a `poam_input.json` ([poam-model.md](poam-model.md)).

## Generate

Run `build_poam.py` with the mechanism you chose in setup-env.md. `$SKILL_DIR` is this skill's
directory.

```bash
# uv path:
uv run --with 'compliance-trestle>=3.0' python "$SKILL_DIR/build_poam.py" \
  --input poam_input.json --output-dir poam/

# venv path:
.venv-poam/bin/python "$SKILL_DIR/build_poam.py" \
  --input poam_input.json --output-dir poam/
```

This writes `poam/plan-of-action-and-milestones.json` and round-trips it through `oscal_read`
(pydantic schema validation). On success it prints `OK: wrote …; re-read validates.`

Optional overrides: `--title "…"`, `--version "…"`.

## Validate (authoritative)

Confirm with the trestle CLI inside a trestle workspace. The file must sit at
`<workspace>/plan-of-action-and-milestones/<name>/plan-of-action-and-milestones.json`:

```bash
# once, if you don't already have a trestle workspace:
<PY> -m trestle init            # or: trestle init   (use the isolated env's trestle)

mkdir -p plan-of-action-and-milestones/poam
cp poam/plan-of-action-and-milestones.json plan-of-action-and-milestones/poam/
trestle validate -t plan-of-action-and-milestones
```

Expect: `VALID: Model … passed the Validator`. (`<PY>`/`trestle` = the isolated env's interpreter
or CLI, e.g. `.venv-poam/bin/trestle` or `uv run --with 'compliance-trestle>=3.0' trestle`.)

## If validation fails

- **`… should be a valid dictionary or instance of SystemId`** — a field expects an OSCAL object,
  not a string (the builder already wraps `system_id`; if you edited the script, wrap it in
  `SystemId(id=…)`).
- **Missing required field** — every `poam-item` needs `title` and `description`; the document needs
  `uuid` + `metadata` + at least one `poam-item`.
- **datetime error on `last-modified`** — must be timezone-aware (the builder uses UTC).
- Re-read the error, fix `poam_input.json` (or the builder), and regenerate.

## No MCP needed

Building and validating happen entirely through the trestle library/CLI in the isolated env. If a
trestle **MCP** server happens to be wired into the harness and exposes a POA&M schema-validation
tool, you may optionally call it as an extra check — but it is not required and authoring does not
depend on it.
