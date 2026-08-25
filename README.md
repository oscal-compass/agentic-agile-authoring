# Agentic Agile Authoring

An **ecosystem of portable authoring skills** for OSCAL-based compliance work — from framework
onboarding (compliance PDF → catalog, catalog ↔ catalog mapping) through catalog customization,
component definition, and assessment to POA&M generation — installable into multiple agent
harnesses (**Claude Code**, **OpenCode**, custom harnesses, …).

The OSCAL Compass project is hosted by the [Cloud Native Computing Foundation (CNCF)](https://cncf.io).

## What's here

- **Skills** (`skills/`) — the payload. Each is a portable `SKILL.md` plus an
  [`apm.yml`](docs/design-spec.md#23-mcp-dependency-declaration-dependenciesmcp) package manifest
  and optional `scripts/`/`references/`/`assets/`. A skill that needs an MCP server declares it in
  `apm.yml` (`dependencies.mcp`).
- **Demos** (`demos/`) — end-to-end walkthroughs that exercise N skills, each a single
  `demos/<name>/README.md` (prompts + install/uninstall + a demo video).
- **`tools/`** — `compliance-authoring-skills`, a thin installer CLI. It is a small wrapper over
  [**OpenAPM**](https://github.com/microsoft/apm) (`apm-cli`), which does the heavy lifting:
  copy the skill into each harness's native dir **and** wire its declared MCP servers into that
  harness's native MCP config, with a lockfile and non-destructive uninstall/prune. See
  [tools/README.md](tools/README.md) and [docs/design-spec.md](docs/design-spec.md).

## Skills

Seven portable skills. The **authoring lifecycle** composes left-to-right
(`catalog-authoring → component-definition → assessment → poam-authoring`); the
**framework-onboarding** skills sit upstream, turning source documents into the OSCAL Catalogs the
lifecycle consumes. Each is invoked directly by the harness — there is no orchestrator persona; a
demo carries any ordering.

### Authoring lifecycle

| Skill | Description | MCP dep |
|-------|-------------|---------|
| `catalog-authoring` | Import NIST OSCAL assets, edit parameters, generate CSV templates, deploy Markdown catalogs | `trestle` |
| `component-definition` | Map abstract controls to component-specific rules and validation checks; generate `component-definition.json` | `trestle` |
| `assessment` | Evaluate control compliance from component definitions and validation scan results | — |
| `poam-authoring` | Author an OSCAL POA&M from an assessment's failed findings — remediation plan, milestones, POC, due date | — |

### Framework onboarding

| Skill | Description | MCP dep |
|-------|-------------|---------|
| `compliance-catalog` | Convert a compliance-document PDF (law, regulation, standard) into a validated OSCAL Catalog | — |
| `compliance-mapping` | Map controls between two OSCAL Catalogs into an OSCAL Mapping Collection + browsable HTML report | — |

### Cross-cutting

| Skill | Description | MCP dep |
|-------|-------------|---------|
| `git-workflow` | Two-branch Git strategy for change tracking and PR review of compliance documents (opt-in) | — |

`compliance-catalog` / `compliance-mapping` use `trestle` as a local CLI/library for validation
rather than the MCP server, so they wire no MCP dependency. See the [Skills reference](docs/skills.md)
for per-skill detail.

## Install

Prerequisite: **[`uv`](https://docs.astral.sh/uv/)** (provides `uvx`, which also runs `uvx`-based
MCP servers like trestle). That is the only baseline runtime — no Node required.

Not published to a package index yet — install **git-direct** with `uvx --from`. The
`--from` points at the `tools/` subdirectory of a release tag (`@v0.1.0`); use any newer
release tag, or `@main` to track the latest:

```bash
# install a demo's skills into Claude Code (skill files + MCP wiring, one step)
uvx \
  --from "git+https://github.com/oscal-compass/agentic-agile-authoring.git@v0.1.0#subdirectory=tools" \
  compliance-authoring-skills install --demo catalog-to-assessment --target claude

# or into OpenCode
uvx \
  --from "git+https://github.com/oscal-compass/agentic-agile-authoring.git@v0.1.0#subdirectory=tools" \
  compliance-authoring-skills install --demo catalog-to-assessment --target opencode

# subset selection
uvx \
  --from "git+https://github.com/oscal-compass/agentic-agile-authoring.git@v0.1.0#subdirectory=tools" \
  compliance-authoring-skills install --exclude git-workflow --target claude
uvx \
  --from "git+https://github.com/oscal-compass/agentic-agile-authoring.git@v0.1.0#subdirectory=tools" \
  compliance-authoring-skills install --skill catalog-authoring,assessment --target opencode
```

Each install copies the selected skills into the harness's native skill dir and wires the
`trestle` MCP server — declared by `catalog-authoring` / `component-definition` — into the
harness's native MCP config (`.mcp.json` for Claude, `opencode.json` for OpenCode). User-authored
skills and user-defined MCP servers are never touched.

Uninstall is non-destructive; a shared MCP server is pruned only once no remaining installed
skill needs it:

```bash
uvx \
  --from "git+https://github.com/oscal-compass/agentic-agile-authoring.git@v0.1.0#subdirectory=tools" \
  compliance-authoring-skills uninstall --skill assessment --target claude
```

> **Status:** the `compliance-authoring-skills` wrapper is being built on top of `apm-cli` (see
> [docs/design-spec.md](docs/design-spec.md), §8). The underlying APM flow — skill placement +
> MCP wiring + prune, for Claude Code and OpenCode — is verified working.

## Demos

Each demo is a runnable walkthrough — install steps, the prompts to give the agent in order,
uninstall, and a demo video:

- **[`demos/catalog-to-assessment/`](demos/catalog-to-assessment/README.md)** — the full authoring
  lifecycle end-to-end: tailor a NIST SP 800-53 catalog, map its controls to a Kubernetes
  component, and generate an assessment result (`catalog-authoring → component-definition →
  assessment`).
- **[`demos/poam-authoring/`](demos/poam-authoring/README.md)** — author a valid OSCAL Plan of
  Action and Milestones, via both input paths (assessment result → POA&M, and FedRAMP xlsx →
  POA&M).

## Contributing a skill

1. Add `skills/<name>/SKILL.md` (frontmatter: `name` = directory name, `description`).
2. Add `skills/<name>/apm.yml` with `name`/`version`, and — if the skill needs an MCP server —
   `dependencies.mcp` (see the existing manifests). Do **not** put `target:` in it.
3. Consider adding or extending a demo in `demos/` that exercises the skill.

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

*OSCAL Compass is an independent open source project. It is not affiliated with, endorsed by, or sponsored by the National Institute of Standards and Technology (NIST) or any other government agency.*
