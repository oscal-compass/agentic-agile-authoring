# Installer Spec

This document describes the distribution and installation specification for the `agentic-agile-authoring` package.

---

## Roo Code

### Distribution

Distributed as a Python package, installable directly from GitHub via `uvx`.

Source files are managed in the repository root and bundled into the package at build time.

```
skills/                         Skill files (bundled as package data)
agents/roo/agentic-agile-authoring/
  roo.yaml                      Mode config
  rules/                        Workflow rules (bundled as package data)
src/agentic_agile_authoring/
  cli.py                        install / uninstall / download commands
```

### Install

Run in the root of the Roo Code project you want to install into.

```bash
# From a release wheel (recommended)
uvx --from "https://github.com/oscal-compass/agentic-agile-authoring/releases/download/v0.1.0/agentic_agile_authoring-0.1.0-py3-none-any.whl" agentic-agile-authoring install

# From source at main (latest)
uvx --from git+https://github.com/oscal-compass/agentic-agile-authoring@main agentic-agile-authoring install
```

### Install outputs

```
.roomodes                               agentic-agile-authoring mode merged in
.roo/
  skills-agentic-agile-authoring/       skill files (default)
  rules-agentic-agile-authoring/        workflow rules
```

With `--skills-scope common`, skills are placed in `.roo/skills/` (shared across all modes).

### Uninstall

```bash
uvx --from "https://..." agentic-agile-authoring uninstall
```

Removes the mode from `.roomodes` and deletes `.roo/skills-agentic-agile-authoring/` and `.roo/rules-agentic-agile-authoring/`.

### Manual install (GUI)

Use the `download` command to export resources without modifying project files.

```bash
uvx --from "https://..." agentic-agile-authoring download -o ./my-resources
```

Output:

```
my-resources/
  modes/
    agentic-agile-authoring.yaml    # Import via Roo Settings -> Modes -> Import
  skills-agentic-agile-authoring/   # Copy manually under .roo/
```

### Usage

Switch to the `📑 Agentic Agile Authoring` mode from the mode selector.

---

## Claude Code

### Distribution

This repository itself is a Claude Code Plugin.

```
.claude-plugin/
  plugin.json          plugin manifest
  marketplace.json     marketplace catalog
skills/                skills available as slash commands
agents/claude/         agent persona
```

### Install

```
/plugin marketplace add oscal-compass/agentic-agile-authoring
/plugin install agentic-agile-authoring@agentic-agile-authoring
```

### Usage

**Slash commands**

| Command | Purpose |
|---|---|
| `/catalog-authoring` | OSCAL catalog and profile operations |
| `/component-definition` | Component definition authoring, CSV -> JSON |
| `/assessment` | Compliance assessment result generation |
| `/git-workflow` | Git branch management for compliance documents |

**Agent** (multi-turn tasks)

The `agentic-agile-authoring` agent orchestrates all skills. Describe your task in natural language and Claude automatically invokes the appropriate skill.

### Local development testing (CLI only)

```bash
claude --plugin-dir ./
```

---

## Comparison

| | Roo Code | Claude Code |
|---|---|---|
| Distribution unit | Python package | Git repository (plugin) |
| Install | `uvx --from ... install` | `/plugin marketplace add` -> `/plugin install` |
| Uninstall | `uvx --from ... uninstall` | `/plugin uninstall` |
| Update | Re-run the same install command (idempotent) | Update via marketplace |
| Skill invocation | Switch mode, then natural language | Slash command or natural language |
