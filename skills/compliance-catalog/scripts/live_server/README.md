# live_server

Ephemeral local server that the `compliance-catalog` skill spins up at
the start of each run so the operator can watch the catalog build itself
in the browser instead of tailing a jsonl.

**This is part of the skill.** It is intentionally stripped down — no
auth, no database, no GitHub integration, no multi-user roles. Persistent
team workflow lives in `compliance-mapping-agents` (Downstream), and
keeping this side single-session is what preserves the boundary.

## Usage — from an agent

At the start of a run, invoke:

```bash
python3 scripts/live_server/launcher.py --output-dir <output_dir> &
```

The launcher picks a free port in the 8850-8899 range, starts uvicorn,
opens the operator's default browser at `http://127.0.0.1:<port>/`, and
prints the URL so the CLI has it too.

The server watches `<output_dir>` and reflects state changes on the page:

- Phase 1 → 6 progress with running / done / error icons
- catalog.json control + group counts (once emitted)
- validate error series across `_validate_*.txt` iterations
- tail of the agent log (`cli_output.log` or newest `agent.*.jsonl`)
- `report.md` once written
- an "Approve / Reject" verdict recorded to `<output_dir>/.reviewed.json`

There is **no state on the server**. Kill it, re-run it, point it at an
already-completed dir — you always get the same view derived from disk.

## Usage — manually against an existing run

Handy for debugging the UI or replaying a past run:

```bash
python3 scripts/live_server/launcher.py \
    --output-dir /path/to/some/finished/catalog
```

Add `--no-browser` when running via SSH or CI.

## Dependencies

- `fastapi` and `uvicorn` (both listed in `scripts/requirements.txt`)

The server bundles a self-contained SPA (`static/`); it does not fetch
anything from a CDN.
