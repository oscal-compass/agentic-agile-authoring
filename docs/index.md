# Agentic Agile Authoring

An **ecosystem of portable authoring skills** for OSCAL-based compliance work — from NIST
catalog customization through component definition to assessment result generation — installable
into multiple agent harnesses (**Claude Code**, **OpenCode**, custom harnesses, …).

The OSCAL Compass project is hosted by the [Cloud Native Computing Foundation (CNCF)](https://cncf.io).

## Three first-class objects

- **Skill** — a unit of authoring know-how (`SKILL.md` + an `apm.yml` package manifest + optional
  scripts/references/assets), portable across harnesses. A skill that needs an MCP server declares
  it in `apm.yml` (`dependencies.mcp`).
- **Demo** — an end-to-end walkthrough exercising N skills, captured as a single
  `demos/<name>/README.md`. See [Architecture](architecture.md) and the
  [Design Spec](design-spec.md).
- **MCP dependency** — declared in `apm.yml`, resolved and wired into the target harness's native
  MCP config on install; not hardcoded anywhere.

## Install

Skills are installed by `compliance-authoring-skills`, a thin CLI (in `tools/`) that wraps
[Microsoft APM](https://github.com/microsoft/apm) (`apm-cli`). Prerequisite:
[`uv`](https://docs.astral.sh/uv/) (provides `uvx`) — no Node required.

```bash
uvx compliance-authoring-skills install --demo catalog-to-assessment --target claude
uvx compliance-authoring-skills install --demo catalog-to-assessment --target opencode
```

This copies the selected skills into the target's native skill dir (`.claude/skills/` for Claude,
`.agents/skills/` for OpenCode) and wires the
[trestle MCP server](https://github.com/oscal-compass/compliance-trestle-mcp) into the target's
native MCP config (`.mcp.json` / `opencode.json`) — non-destructively. See the
[Development guide](development.md) and the [Design Spec](design-spec.md) for the full model,
subset selection, uninstall/prune, and the custom-harness path.

## Demo

The full authoring lifecycle — tailoring a NIST SP 800-53 catalog, mapping controls to a
Kubernetes component, and generating an assessment result — is captured as a runnable walkthrough,
`catalog-to-assessment`. Its `demos/catalog-to-assessment/README.md` carries a demo video, the
install steps, the prompts to give the agent in order, and uninstall (e.g. the generated
`catalog.json` passes `trestle validate`).

## Skills

See the [Skills reference](skills.md).

| Skill | Description |
|-------|-------------|
| `catalog-authoring` | Import NIST OSCAL assets, edit parameters, generate CSV templates, deploy Markdown catalogs |
| `component-definition` | Map abstract controls to component-specific rules and validation checks; generate `component-definition.json` |
| `assessment` | Evaluate control compliance from component definitions and validation scan results |
| `git-workflow` | Two-branch Git strategy for change tracking and PR review of compliance documents (opt-in) |

## License

Unless otherwise noted, files in this repository are licensed under the Apache License 2.0.
Some skill directories include their own LICENSE.txt, which governs files in that directory.

---

We are a Cloud Native Computing Foundation sandbox project.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://www.cncf.io/wp-content/uploads/2022/07/cncf-white-logo.svg">
  <img src="https://www.cncf.io/wp-content/uploads/2022/07/cncf-color-bg.svg" width=300 />
</picture>

The Linux Foundation® (TLF) has registered trademarks and uses trademarks. For a list of TLF trademarks, see [Trademark Usage](https://www.linuxfoundation.org/legal/trademark-usage).
