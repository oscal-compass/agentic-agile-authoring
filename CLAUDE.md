# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

An ecosystem of portable authoring **skills** for OSCAL-based compliance authoring — from NIST
catalog customization through component definition to assessment result generation — usable
across multiple agent harnesses (Claude Code, Roo Code, opencode, …). Skills are the single
source of truth in `skills/`; **scenarios** in `scenarios/` are end-to-end conformance runs;
`tools/` holds the only bespoke code (the `ag-au-skills` CLI). See `docs/design-spec.md` for the design.

## Build & Development Commands

The bespoke code is the `ag-au-skills` CLI in `tools/` (Python) — a thin wrapper over Microsoft
APM (`apm-cli`, exact-pinned).

```bash
cd tools
python -m venv .venv && . .venv/bin/activate
pip install -e ".[test]"     # pins apm-cli; pulls pyyaml + pytest
pytest                       # unit tests + pinned-apm integration spikes

# Run the CLI (prereq: uv):
ag-au-skills install --scenario catalog-to-assessment --target claude
ag-au-skills --help

# Add license headers to source files
python scripts/add_license_headers.py

# Pre-commit (uses detect-secrets)
pre-commit run --all-files

# Documentation site
make install   # Install docs dependencies
make serve     # Serve docs locally at http://localhost:8000
make build     # Build docs with strict mode
```

## Architecture

### Portable skills + a thin installer over Microsoft APM

Skills in `skills/` are portable hybrid packages (`SKILL.md` + `apm.yml`) shared by every
harness. Installation is delegated to **Microsoft APM** (`apm-cli`, exact-pinned): APM copies the
skill package into each harness's native dir **and** wires the skill's declared MCP servers into
that harness's native MCP config, with `apm.lock.yaml` ownership + non-destructive uninstall/prune.
`ag-au-skills` (`tools/`, Python) is a thin wrapper adding only: selection over our scenarios, a
stable UX + prereq policy, and a custom-harness ("MyHarness") deployer that reuses APM's
target-agnostic resolve/normalize as a library. See `docs/design-spec.md` (decision **D4**).

### Key directories

- **`skills/<name>/`** — hybrid skill packages: `SKILL.md` (frontmatter: `name` = dir name,
  `description`, optional `license`/`argument-hint`) + `apm.yml` + supporting files. Four skills:
  `catalog-authoring`, `component-definition`, `assessment`, `git-workflow`.
- **`skills/<name>/apm.yml`** — the APM package manifest (`name`, `version`, and `dependencies.mcp`
  where the skill needs an MCP server — `catalog-authoring`/`component-definition` declare
  `trestle`). Do NOT add a `target:` field (APM rejects unknown target tokens at parse time).
- **`scenarios/<name>/`** — `steps.md` (prompts + frontmatter `skills:` / `verified:`) and
  `expected.md` (`[exact]`/`[approx]` checkpoints). A scenario is a conformance run over N skills.
- **`tools/`** — the `ag-au-skills` wrapper (Python). Modules: `cli.py`, `policy.py` (selection +
  prereq checks), `backends/apm_cli.py` (subprocess to pinned `apm` for supported targets),
  `targets/myharness.py` (library reuse of APM + our deployer). This is the code with tests.
- **`.mcp.json`** — the canonical `trestle` server definition (reference for the skill manifests).

### Installation flow (no build-time bundling)

`ag-au-skills install --target <t>` resolves a skill selection, then for each skill: if `<t>` is
an APM-known target (claude, opencode, …) it delegates to the pinned `apm` (which copies the skill
+ wires MCP + updates `apm.lock.yaml`); if `<t>` is MyHarness it uses APM as a library to get the
resolved skill + normalized MCP, then deploys itself. `uninstall`/prune go through APM for
supported targets (a shared MCP server is dropped only when no remaining skill needs it). No wheel,
no plugin — skills are installed from a local checkout of this repo.

### Adding a new skill

1. Create `skills/<skill-name>/SKILL.md` (frontmatter: `name` = directory name, `description`;
   optional `argument-hint`, `license`).
2. Add supporting `.md`/`.py`/`references/`/`assets/` files in the same directory.
3. Add `skills/<skill-name>/apm.yml` (APM package manifest): `name`, `version`, and — if the skill
   needs an MCP server — `dependencies.mcp` in APM's shape (`registry: false` for self-defined
   stdio; mirror the server def in root `.mcp.json`). Do NOT add a `target:` field.
4. Optionally add/extend a scenario in `scenarios/` that exercises it.
5. Run `python scripts/add_license_headers.py` to add license headers.

Skills are invoked directly per harness — there is no orchestrator agent/mode to update.

## Important: Do not use the trestle MCP server

This repo develops the MCP server infrastructure itself. Do not invoke or depend on the trestle
MCP server (compliance-trestle-mcp) when working in this repository.

## Conventions

- **License headers**: `.py` and `.yaml`/`.yml` files get Apache 2.0 comment headers; SKILL.md
  files get a `license` frontmatter field and a `LICENSE.txt` in their directory. Use
  `scripts/add_license_headers.py` (it also covers the Python sources under `tools/`).
- **`ag-au-skills` CLI**: Python ≥ 3.10, thin wrapper over exact-pinned `apm-cli`; tested with
  `pytest` (unit) + a pinned-apm integration spike suite. Baseline runtime prerequisite is `uv`
  (no Node). Per-MCP runtimes (docker/npx) are the environment's responsibility.
- **Skill placement / MCP wiring / lockfile / prune are APM's**, not ours — don't re-implement
  them. The only place we deploy directly is the custom "MyHarness" target (reusing APM's
  target-agnostic resolve/normalize).
- **No native skill versioning**: identity is the directory name; "has it changed?" is APM's
  `apm.lock.yaml` content hash, not semver.
