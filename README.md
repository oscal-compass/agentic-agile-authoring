# Agentic Agile Authoring

Agent skills and modes for OSCAL-based compliance authoring workflows — from NIST catalog customization through component definition to assessment result generation.

## Overview

This repo defines reusable **skills** (prompts + instructions) that run on two platforms:

| Platform | Agent definition | Skill location |
|----------|-----------------|----------------|
| **Claude Code** | `agents/claude/agentic-agile-authoring.md` | `skills/` |
| **Roo Code** | `agents/roo/agentic-agile-authoring/roo.yaml` | `.roo/skills[-agentic-agile-authoring]/` |

## Skills

| Skill | Description |
|-------|-------------|
| `catalog-authoring` | Import NIST OSCAL assets, edit parameters, generate CSV templates, deploy Markdown catalogs |
| `component-definition` | Map abstract controls to component-specific rules and validation checks; generate `component-definition.json` |
| `assessment` | Evaluate control compliance from component definitions and validation scan results |
| `git-workflow` | Two-branch Git strategy for change tracking and PR review of compliance documents (opt-in) |

## Agent / Mode

A single agent **`agentic-agile-authoring`** covers the full OSCAL authoring lifecycle and delegates to the skills above.

## Roo Code

### Auto install (recommended)

```bash
uvx --from git+https://github.com/oscal-compass/agentic-agile-authoring.git agentic-agile-authoring install
```

Skills are installed to `.roo/skills-agentic-agile-authoring/` by default.
To install into the shared `.roo/skills/` directory instead (accessible to all modes):

```bash
uvx --from git+https://github.com/oscal-compass/agentic-agile-authoring.git agentic-agile-authoring install --skills-scope common
```

### Uninstall

```bash
uvx --from git+https://github.com/oscal-compass/agentic-agile-authoring.git agentic-agile-authoring uninstall

# If installed with --skills-scope common:
uvx --from git+https://github.com/oscal-compass/agentic-agile-authoring.git agentic-agile-authoring uninstall --skills-scope common
```

### Manual install

```bash
uvx --from git+https://github.com/oscal-compass/agentic-agile-authoring.git agentic-agile-authoring download
```

Then follow the printed instructions to copy skills and import mode YAMLs into Roo Code.

### Install outputs

`.roo/skills-agentic-agile-authoring/` (or `.roo/skills/`) and `.roo/rules-*/` are created by the installer and gitignored.

## Claude Code

### Plugin install (once published)

```
/plugin marketplace add oscal-compass/agentic-agile-authoring
/plugin install agentic-agile-authoring@agentic-agile-authoring
```

### Local development

```bash
claude --plugin-dir ./
```

## Help

```bash
uvx --from git+https://github.com/oscal-compass/agentic-agile-authoring.git agentic-agile-authoring -h
uvx --from git+https://github.com/oscal-compass/agentic-agile-authoring.git agentic-agile-authoring install -h
```
