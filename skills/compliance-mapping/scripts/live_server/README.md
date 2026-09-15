# live_server (compliance-mapping)

Ephemeral local server that the `compliance-mapping` skill spins up at
the start of each run so the operator can watch the mapping build itself
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

- Stage 1 → 8 progress with running / done / error icons
- source_wc / target_wc control counts (once Stage 1 lands them)
- judge-chunk fan-out progress (chunks done / total)
- link count and relationship mix once `mapping_collection.json` exists
- tail of the agent log (`opencode.db` events, then `cli_output.log`
  fallback, then `agent.*.jsonl` fallback)
- `report.html` link once emitted
- an "Approve / Reject" verdict recorded to `<output_dir>/.reviewed.json`

There is **no state on the server**. Kill it, re-run it, point it at an
already-completed dir — you always get the same view derived from disk.

## Lifecycle

- **TUI mode** (interactive `opencode` / `claude` / `bob`): pass
  `--die-with-parent --parent-pid $$` from the shell launching us. When
  the TUI is Ctrl-C'd, the launcher notices its parent gone within
  ~5 seconds and shuts itself down.
- **One-shot mode** (`opencode run "…"`): omit `--die-with-parent`. The
  caller exits when the pipeline finishes, but we stay alive so the
  operator can open the browser and inspect the result. A 3-hour
  loitering guard (`--max-lifetime`) makes sure we don't linger forever.
- Either way the operator can hit the `⏻ Shutdown server` button on the
  browser's "Run complete" panel, or run `kill "$(cat $OUT/.live_server.pid)"`.

## Usage — manually against an existing run

Handy for debugging the UI or replaying a past run:

```bash
python3 scripts/live_server/launcher.py \
    --output-dir /path/to/some/finished/mapping
```

Add `--no-browser` when running via SSH or CI.

## Dependencies

- `fastapi` and `uvicorn` (both listed in `scripts/requirements.txt`)

The server bundles a self-contained SPA (`static/`); it does not fetch
anything from a CDN.
