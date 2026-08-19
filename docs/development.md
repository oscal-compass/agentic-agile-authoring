# Development Guide

## Repo structure

```
skills/                     Skill packages (single source of truth for every harness)
  <skill-name>/
    SKILL.md                Skill definition — frontmatter (name, description) + instructions
    apm.yml                 APM package manifest (name, version, dependencies.mcp)
    *.md / *.py             Supporting resources referenced by the skill

demos/                  End-to-end walkthroughs
  <demo-name>/
    README.md               Frontmatter (skills:) + demo video + install → prompts → uninstall
    …                       Any referenced assets

tools/                      `compliance-authoring-skills` — thin installer CLI over Microsoft APM (Python)
  pyproject.toml            deps: apm-cli==<pin>, pyyaml
  compliance_authoring_skills/             cli / policy / backends.apm_cli / targets.myharness
  tests/compliance_authoring_skills/       unit tests + pinned-apm integration spikes

.mcp.json                   Canonical trestle MCP server definition
docs/                       This documentation site
scripts/add_license_headers.py
```

There is no wheel, plugin manifest, or build-time bundling. Skill placement and MCP wiring are
delegated to [Microsoft APM](https://github.com/microsoft/apm) (`apm-cli`); `compliance-authoring-skills` is a
thin wrapper that adds selection, UX, and custom-harness deployment (see
[Architecture](architecture.md) and the [Design Spec](design-spec.md)).

## Adding a skill

1. Create `skills/<skill-name>/SKILL.md` with the required frontmatter:

```yaml
---
name: skill-name        # MUST equal the directory name (Roo enforces this)
description: ...        # when a harness should activate this skill
argument-hint: <hint>   # optional
license: Complete terms in LICENSE.txt   # optional; added by scripts/add_license_headers.py
---
```

2. Add supporting `.md` / `.py` / `references/` / `assets/` files in the same directory.
3. Add `skills/<skill-name>/apm.yml` — the APM package manifest. Include `name`/`version`, and,
   if the skill needs an MCP server, `dependencies.mcp` (APM's shape; `registry: false` for a
   self-defined stdio server):

```yaml
name: skill-name
version: "1.0.0"
dependencies:
  mcp:
    - name: trestle
      registry: false
      transport: stdio
      command: uvx
      args: ["--from", "git+https://github.com/oscal-compass/compliance-trestle-mcp.git", "trestle-mcp"]
```

Do **not** add a `target:` field to a skill's `apm.yml` (an unknown target token is the one thing
APM rejects at parse time, which would break custom-harness reuse).

4. Optionally add or extend a demo in `demos/` that exercises the skill.
5. Run `python scripts/add_license_headers.py`.

No build step is needed for skills. They are invoked directly; there is no orchestrator to update.

## The `compliance-authoring-skills` CLI (`tools/`)

A thin wrapper over [Microsoft APM](https://github.com/microsoft/apm) (`apm-cli`, exact-pinned).
Python ≥ 3.10.

```bash
cd tools
python -m venv .venv && . .venv/bin/activate
pip install -e ".[test]"     # pins apm-cli; pulls pyyaml + pytest
pytest                       # unit tests + pinned-apm integration spikes
compliance-authoring-skills --help
```

What the wrapper owns (everything else is APM's — resolution, deployment, lockfile, prune):

- **Selection** — `--skill`, `--exclude a,b`, `--demo <name>` (reads the demo `README.md` `skills:`).
- **UX + prereq policy** — synthesize the APM project context for a standalone skill install;
  check the baseline `uv`.
- **MyHarness deployer** — reuse APM's target-agnostic `APMPackage.from_apm_yml` →
  `APMDependencyResolver` → `CurrentMcpConfigView.derive` (library), then copy the skill +
  merge `~/.myharness/mcp.json`.

```bash
compliance-authoring-skills install --demo catalog-to-assessment --target claude
compliance-authoring-skills install --exclude git-workflow --target opencode
compliance-authoring-skills uninstall --skill assessment --target claude
```

Testing strategy: the bespoke surface (selection/policy, MyHarness deployer) is unit-tested; the
delegated behavior is covered by an **integration spike suite pinned to the `apm-cli` version**
(standalone install → skill+MCP present; shared-MCP prune; OpenCode native-config merge), re-run
before any pin bump. See [tools/README.md](https://github.com/oscal-compass/agentic-agile-authoring/blob/main/tools/README.md).

## Prerequisites

- **`uv`** — baseline runtime (provides `uvx`, which runs the pinned tooling and `uvx`-based MCP
  servers). No Node required.
- **Python ≥ 3.10** — to develop/run `compliance-authoring-skills`.
- Per-MCP runtimes (`docker`, `npx`, …) are the environment's responsibility.

## Documentation site

```bash
make install   # install docs dependencies
make serve     # serve locally at http://localhost:8000
make build     # build with strict mode
```
