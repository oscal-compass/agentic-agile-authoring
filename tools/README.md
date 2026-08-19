# `compliance-authoring-skills`

A thin installer CLI for this repo's skills. It is **not** a package manager — it wraps
[**OpenAPM**](https://github.com/microsoft/apm) (`apm-cli`, exact-pinned), which owns
package resolution, per-harness deployment, the lockfile, non-destructive MCP merge, and
reachability-based prune. `compliance-authoring-skills` adds only the parts APM doesn't cover.

See [../docs/design-spec.md](../docs/design-spec.md) for the full design and decision log (D4).

## What the wrapper adds

1. **Selection over a skills source** — `--demo <name>` (reads `demos/<name>/README.md`),
   `--exclude`, `--skill a,b`, or all skills. APM has no concept of our demos. The source is
   the **skills bundled inside this package** by default (so the CLI works from any directory
   without a checkout); `--source <repo>` installs from an external skills repo instead.
2. **Stable UX** — hides APM's project mechanics (resolves the selection to local skill paths and
   drives one `apm install <paths> --target <t>`; the `--project` dir *is* the APM project — no
   throwaway temp project) and enforces the prerequisite policy. `--global` switches to APM user
   scope (`~/.claude/…`). After a project-scope install the wrapper **tidies**: the project keeps
   only the deployed products (`.claude/skills/`, `.mcp.json`), while APM's ledger (`apm.yml` +
   `apm.lock.yaml`) is consolidated into a hidden `.compliance-authoring-skills/` dir and the `apm_modules/` cache
   + APM's `.gitignore` edit are dropped. `uninstall` restores the ledger transparently so APM's
   prune still runs, then re-tidies. `--keep-apm-files` disables tidying (debugging / direct `apm`).
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
# Skills come from the copy bundled in this package — run from ANY directory, no checkout needed:
compliance-authoring-skills install   [--demo <name> | --exclude a,b | --skill a,b] --target {claude|opencode|myharness}
compliance-authoring-skills uninstall [--skill a,b | --all] --target {claude|opencode|myharness}

#   --project <dir>   where to install (default: cwd); --global for user scope (~/.claude/…)
#   --source  <repo>  install from an external skills repo instead of the bundled skills
```

The skills + demos are packaged into the wheel (`compliance_authoring_skills/_bundled/`) at build time from
the repo's top-level `skills/`/`demos/` — those stay the single source of truth (no committed
duplicate; an editable/dev install falls back to the repo checkout).

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
compliance-authoring-skills --help
```

The bespoke surface is small: selection/policy (unit-tested) and the MyHarness deployer. The
load-bearing behavior lives in APM, so the primary safety net is an **integration spike suite**
pinned to the `apm-cli` version (standalone install → skill+MCP present; shared-MCP prune;
OpenCode native-config merge; MyHarness deploy), re-run in CI and before any `apm-cli` bump.
