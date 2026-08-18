# `ag-au-skills`

A thin installer CLI for this repo's skills. It is **not** a package manager — it wraps
[**Microsoft APM**](https://github.com/microsoft/apm) (`apm-cli`, exact-pinned), which owns
package resolution, per-harness deployment, the lockfile, non-destructive MCP merge, and
reachability-based prune. `ag-au-skills` adds only the parts APM doesn't cover.

See [../docs/design-spec.md](../docs/design-spec.md) for the full design and decision log (D4).

## What the wrapper adds

1. **Selection over this repo** — `--scenario <name>` (reads `scenarios/<name>/steps.md`),
   `--exclude`, or all skills. APM has no concept of our scenarios.
2. **Stable UX** — hides APM's project mechanics (resolves the selection to local skill paths and
   drives one `apm install <paths> --target <t>`; the `--project` dir *is* the APM project, so
   APM's `apm.lock.yaml` + prune land there — no throwaway temp project) and enforces the
   prerequisite policy. `--global` switches to APM user scope (`~/.claude/…`).
3. **MyHarness deployment** — APM's target set is closed, so for our custom harness the wrapper
   **reuses APM's target-agnostic resolve/normalize as a library** and does the small deployment
   diff itself (copy skill + merge `~/.myharness/mcp.json`). No fork of APM.

## What APM does (delegated, not re-implemented)

- Copy the whole skill package (`SKILL.md` + `scripts/`/`references/`/`assets/`) into the target's
  native skill dir (`.claude/skills/`, `.agents/skills/`, …).
- Resolve `dependencies.mcp` and wire each server into the target's native MCP config
  (`.mcp.json` / `opencode.json` / …), merging non-destructively.
- `apm.lock.yaml` ownership + prune a shared MCP server only when no remaining skill needs it.

## Usage

```bash
ag-au-skills install   [--scenario <name> | --exclude a,b | --skill a,b] --target {claude|opencode|myharness}
ag-au-skills uninstall [--skill a,b | --all] --target {claude|opencode|myharness}
```

## Prerequisites

- **`uv`** (baseline) — provides `uvx`, runs the pinned `apm-cli` and `uvx`-based MCP servers.
- Per-MCP runtimes (e.g. `docker`, `npx`) are the environment's responsibility — the wrapper
  checks presence and **warns** if one a selected skill needs is missing, but does not auto-install
  them. Only a missing `uv` baseline is a hard error.

## Develop

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[test]"     # pins apm-cli; pulls pyyaml + pytest
pytest                       # unit tests + pinned-apm integration spikes
ag-au-skills --help
```

The bespoke surface is small: selection/policy (unit-tested) and the MyHarness deployer. The
load-bearing behavior lives in APM, so the primary safety net is an **integration spike suite**
pinned to the `apm-cli` version (standalone install → skill+MCP present; shared-MCP prune;
OpenCode native-config merge; MyHarness deploy), re-run in CI and before any `apm-cli` bump.
