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

**Ask which delivery shape the user wants — it's a real difference to them — and default to the
simple one:**

- **(default) A standalone POA&M file** — no trestle workspace. This is what most users want: one
  `plan-of-action-and-milestones.json` they hand to another platform. Do **not** run `trestle init`.
- **A trestle workspace** — only if the user is already in one, or wants the trestle directory layout
  (many models managed together). See [trestle-workspace.md](trestle-workspace.md).

### Default — validate the standalone file (no workspace)

The builder already round-tripped the file through `oscal_read` (the `re-read validates` message), so
it is schema-valid. For an explicit authoritative check on the file **in place, no `trestle init`**,
use whichever is available — **both take a standalone file path, no workspace**:

1. **MCP (preferred if wired)** — `mcp__trestle__trestle_validate` with
   `{ "file": "poam/plan-of-action-and-milestones.json", "expected_model_type": "plan-of-action-and-milestones" }`.
   Returns `✅ Valid OSCAL plan-of-action-and-milestones (schema + semantic)`.
2. **Library/CLI (fallback)** — the isolated-env trestle, no init:

   ```bash
   <PY> -m trestle partial-object-validate -f poam/plan-of-action-and-milestones.json \
     -e plan-of-action-and-milestones
   ```

   Expect: `VALID: …/plan-of-action-and-milestones.json for plan-of-action-and-milestones`.

**Never run `trestle init` in the user's working directory just to validate** — it litters their
directory with `.trestle/` + eight model folders + `dist/`. `partial-object-validate` above needs
none of that. Only turn the user's own directory into a workspace when **(a)** it already is one, or
**(b)** the user explicitly wants a trestle-workspace deliverable.

### `trestle validate -t` without polluting (throwaway workspace)

If you specifically want the `trestle validate -t` command (it's workspace-only) but the user's dir
isn't a workspace and they didn't ask for one, run it in a **temporary** workspace and discard it —
leave the user's directory untouched:

```bash
tmp=$(mktemp -d)
<PY> -m trestle init --trestle-root "$tmp"
mkdir -p "$tmp/plan-of-action-and-milestones/poam"
cp poam/plan-of-action-and-milestones.json "$tmp/plan-of-action-and-milestones/poam/"
( cd "$tmp" && trestle validate -t plan-of-action-and-milestones )
rm -rf "$tmp"
```

### Workspace deliverable

When the user's directory **is** a workspace (or they want one), build straight into its canonical
`plan-of-action-and-milestones/<name>/` path and validate there — no temp dir, no copy. See
[trestle-workspace.md](trestle-workspace.md).

(`<PY>`/`trestle` = the isolated env's interpreter or CLI, e.g. `.venv-poam/bin/trestle` or
`uv run --with 'compliance-trestle>=3.0' trestle`.)

## If validation fails

- **`… should be a valid dictionary or instance of SystemId`** — a field expects an OSCAL object,
  not a string (the builder already wraps `system_id`; if you edited the script, wrap it in
  `SystemId(id=…)`).
- **Missing required field** — every `poam-item` needs `title` and `description`; the document needs
  `uuid` + `metadata` + at least one `poam-item`.
- **datetime error on `last-modified`** — must be timezone-aware (the builder uses UTC).
- Re-read the error, fix `poam_input.json` (or the builder), and regenerate.

## MCP is optional (preferred for validate when present)

Building always happens through the trestle library in the isolated env (no MCP, no workspace).
For the **validate** step, prefer the MCP `trestle_validate` tool **if it's wired** — it takes a
standalone file and needs no workspace — and otherwise fall back to the library
`partial-object-validate` (also no workspace). Either way authoring never depends on the MCP, and
neither default path requires `trestle init`.
