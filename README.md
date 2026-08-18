# Agentic Agile Authoring

An **ecosystem of portable authoring skills** for OSCAL-based compliance work — from NIST
catalog customization through component definition to assessment result generation — installable
into multiple agent harnesses (**Claude Code**, **OpenCode**, custom harnesses, …).

The OSCAL Compass project is hosted by the [Cloud Native Computing Foundation (CNCF)](https://cncf.io).

## What's here

- **Skills** (`skills/`) — the payload. Each is a portable `SKILL.md` plus an
  [`apm.yml`](docs/design-spec.md#23-mcp-dependency-declaration-dependenciesmcp) package manifest
  and optional `scripts/`/`references/`/`assets/`. A skill that needs an MCP server declares it in
  `apm.yml` (`dependencies.mcp`).
- **Scenarios** (`scenarios/`) — end-to-end use cases that exercise N skills and double as
  **conformance runs** (checkpoints that must hold on a given harness + model).
- **`tools/`** — `ag-au-skills`, a thin installer CLI. It is a small wrapper over
  [**Microsoft APM**](https://github.com/microsoft/apm) (`apm-cli`), which does the heavy lifting:
  copy the skill into each harness's native dir **and** wire its declared MCP servers into that
  harness's native MCP config, with a lockfile and non-destructive uninstall/prune. See
  [tools/README.md](tools/README.md) and [docs/design-spec.md](docs/design-spec.md).

## Install

Prerequisite: **[`uv`](https://docs.astral.sh/uv/)** (provides `uvx`, which also runs `uvx`-based
MCP servers like trestle). That is the only baseline runtime — no Node required.

```bash
# install a scenario's skills into Claude Code (skill files + MCP wiring, one step)
uvx ag-au-skills install --scenario catalog-to-assessment --target claude

# or into OpenCode
uvx ag-au-skills install --scenario catalog-to-assessment --target opencode

# subset selection
uvx ag-au-skills install --exclude git-workflow --target claude
uvx ag-au-skills install --skill catalog-authoring,assessment --target opencode
```

Each install copies the selected skills into the harness's native skill dir and wires the
`trestle` MCP server — declared by `catalog-authoring` / `component-definition` — into the
harness's native MCP config (`.mcp.json` for Claude, `opencode.json` for OpenCode). User-authored
skills and user-defined MCP servers are never touched.

Uninstall is non-destructive; a shared MCP server is pruned only once no remaining installed
skill needs it:

```bash
uvx ag-au-skills uninstall --skill assessment --target claude
```

> **Status:** the `ag-au-skills` wrapper is being built on top of `apm-cli` (see
> [docs/design-spec.md](docs/design-spec.md), §8). The underlying APM flow — skill placement +
> MCP wiring + prune, for Claude Code and OpenCode — is verified working.

## Demo → scenario

https://github.com/user-attachments/assets/628ebb15-f9cc-4cef-88de-86f026bce499

The demo — tailoring a NIST SP 800-53 catalog, mapping controls to a Kubernetes component, and
generating an assessment result, all in natural language — is captured as a runnable conformance
scenario: **[`scenarios/catalog-to-assessment/`](scenarios/catalog-to-assessment/steps.md)**.
Install those three skills, then give the agent each prompt in
[`steps.md`](scenarios/catalog-to-assessment/steps.md); the
[`expected.md`](scenarios/catalog-to-assessment/expected.md) checkpoints define a passing run
(e.g. the generated `catalog.json` passes `trestle validate`).

## Skills

| Skill | Description | MCP dep |
|-------|-------------|---------|
| `catalog-authoring` | Import NIST OSCAL assets, edit parameters, generate CSV templates, deploy Markdown catalogs | `trestle` |
| `component-definition` | Map abstract controls to component-specific rules and validation checks; generate `component-definition.json` | `trestle` |
| `assessment` | Evaluate control compliance from component definitions and validation scan results | — |
| `git-workflow` | Two-branch Git strategy for change tracking and PR review of compliance documents (opt-in) | — |

Skills are invoked directly by each harness — there is no orchestrator persona. A scenario
carries the orchestration.

## Contributing a skill

1. Add `skills/<name>/SKILL.md` (frontmatter: `name` = directory name, `description`).
2. Add `skills/<name>/apm.yml` with `name`/`version`, and — if the skill needs an MCP server —
   `dependencies.mcp` (see the existing manifests). Do **not** put `target:` in it.
3. Consider adding or extending a scenario in `scenarios/` that exercises the skill.

See [docs/development.md](docs/development.md) and [docs/design-spec.md](docs/design-spec.md).

## License

Unless otherwise noted, files in this repository are licensed under the root LICENSE. Some skill
directories include their own LICENSE.txt, which governs files in that directory.

---

We are a Cloud Native Computing Foundation sandbox project.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://www.cncf.io/wp-content/uploads/2022/07/cncf-white-logo.svg">
  <img src="https://www.cncf.io/wp-content/uploads/2022/07/cncf-color-bg.svg" width=300 />
</picture>

The Linux Foundation® (TLF) has registered trademarks and uses trademarks. For a list of TLF trademarks, see [Trademark Usage](https://www.linuxfoundation.org/legal/trademark-usage).
