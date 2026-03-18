# Development Guide

## Repo structure

```
skills/                     Agent skills (source of truth for both Claude and Roo)
  <skill-name>/
    SKILL.md                Skill definition — frontmatter + instructions
    *.md / *.py             Supporting resources referenced by the skill

agents/
  claude/
    agentic-agile-authoring.md   Claude Code agent persona
  roo/
    agentic-agile-authoring/
      roo.yaml              Roo Code mode config (slug, name, groups, roleDefinition, …)
      rules/                Workflow rules installed to .roo/rules-<slug>/

src/
  agentic_agile_authoring/
    cli.py                  CLI entry point (install / uninstall / download)
    data/                   Bundled at build time via pyproject.toml force-include
      skills/               → copy of skills/
      roo/                  → copy of agents/roo/

.github/
  workflows/
    publish.yml             Release workflow — builds, signs (Sigstore), publishes to GitHub Release

.claude-plugin/
  plugin.json               Claude Code plugin manifest
  marketplace.json          Marketplace catalog entry
```

## Adding a skill

1. Create `skills/<skill-name>/SKILL.md` with required frontmatter:

```yaml
---
name: skill-name        # slash command trigger: /skill-name
description: ...        # when Claude should auto-invoke this skill
argument-hint: <hint>   # shown in autocomplete (optional)
---
```

2. Add supporting `.md` or `.py` files under the same directory as needed.
3. Reference the new skill from the agent prompt (`agents/claude/agentic-agile-authoring.md`) and Roo mode (`agents/roo/agentic-agile-authoring/roo.yaml`) if applicable.

No build step is needed — skills are read directly from the filesystem.

## Agent prompts

### Claude Code agent — `agents/claude/agentic-agile-authoring.md`

Defines the persona and scope for the Claude Code agent. Frontmatter fields:
- `name` — agent identifier
- `description` — when Claude auto-invokes this agent

The body describes what the agent does and which skills it delegates to.

### Roo Code mode — `agents/roo/agentic-agile-authoring/roo.yaml`

Defines the Roo Code mode. Key fields:
- `slug` / `name` — mode identifier and display name
- `roleDefinition` — persona instructions embedded in the mode
- `whenToUse` — shown in mode selection
- `customInstructions` — which skill to use for each task type
- `groups` — tool permissions (`read`, `edit`, `command`, `mcp`)

Workflow rules in `rules/` are installed to `.roo/rules-<slug>/` and loaded automatically by Roo.

## `src/` — installer and future agent tools

### Current: installer CLI (`cli.py`)

Three subcommands:

| Command | What it does |
|---|---|
| `install` | Merges mode into `.roomodes`, copies skills and rules into `.roo/` |
| `uninstall` | Reverses install |
| `download` | Exports skills and mode YAMLs for manual GUI installation |

`--skills-scope` controls where skills land:
- `mode` (default) → `.roo/skills-agentic-agile-authoring/`
- `common` → `.roo/skills/` (shared across all modes)

### Future: agent tools

`src/agentic_agile_authoring/` is the home for Python-based agent tools (MCP servers, CLI tools, etc.) that skills may invoke.

## Release

Releases are managed via git tags. The `publish.yml` workflow fires on `v*` tags:

1. Builds the wheel with `hatch build`
2. Signs all artifacts with Sigstore (keyless OIDC)
3. Attaches wheel, sdist, and `.sigstore.json` files to the GitHub Release

To cut a release:

```bash
# 1. Bump version in pyproject.toml
# 2. Commit and tag
git tag v0.1.0
git push --tags
```

The GitHub Release is created automatically with a pre-built wheel attached.

```bash
# Install from a release wheel (recommended — no build step)
uvx --from "https://github.com/oscal-compass/agentic-agile-authoring/releases/download/v0.1.0/agentic_agile_authoring-0.1.0-py3-none-any.whl" agentic-agile-authoring install

# Install from source at a git ref (tag or branch)
uvx --from git+https://github.com/oscal-compass/agentic-agile-authoring@v0.1.0 agentic-agile-authoring install

# Install from local repo (development)
uvx --from /path/to/agentic-agile-authoring agentic-agile-authoring install
```
