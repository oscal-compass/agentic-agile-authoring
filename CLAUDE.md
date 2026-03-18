# Claude Code — Project Instructions

This repo is a **Claude Code plugin** and **Roo Code mode collection** for agile content authoring workflows.

## Architecture

```
skills/               Native Claude Code agent skills (source of truth for Claude plugin)
  outline/
    SKILL.md          name, description, argument-hint frontmatter + instructions
  task-breakdown/
    SKILL.md
  draft/
    SKILL.md
  revise/
    SKILL.md
  review/
    SKILL.md

agents/
  claude/             Claude Code persona agents (planner, author, reviewer)
    planner.md        Thin persona agent — delegates to skills
    author.md
    reviewer.md
  roo/                Roo Code modes
    <slug>/
      roo.yaml        Mode config (slug, name, groups, source, customInstructions)
      rules/          Thin workflow rules — reference skills by installed path

.claude-plugin/
  plugin.json         Claude Code plugin manifest (references ./skills/)
  marketplace.json    Claude Code marketplace catalog

src/
  agentic_agile_authoring/
    cli.py            install / uninstall / download commands
pyproject.toml        Python package config with force-include mappings
```

## Editing guide

| What to change | File to edit | Build needed? |
|---|---|---|
| Skill logic | `skills/<name>/SKILL.md` | No — edit directly |
| Claude agent persona | `agents/claude/<name>.md` | No |
| Roo mode config | `agents/roo/<slug>/roo.yaml` | No |
| Roo mode workflow rules | `agents/roo/<slug>/rules/01-workflow.md` | No |

### Validate skills

```bash
.venv/bin/python scripts/build.py
```

Checks that every `skills/<name>/SKILL.md` exists and has required frontmatter (`name`, `description`).

### SKILL.md frontmatter reference

```yaml
---
name: skill-name          # Used as /skill-name slash command (required)
description: ...          # When to use it — Claude auto-invokes based on this (required)
argument-hint: <hint>     # Shown in autocomplete (optional)
---
```

## Claude Code usage

Install as plugin (once published):
```
/plugin marketplace add yana1205/agentic-agile-authoring
/plugin install agentic-agile-authoring@agentic-agile-authoring
```

Local development testing (CLI only):
```
claude --plugin-dir ./
```

Skills are available as `/outline`, `/task-breakdown`, `/draft`, `/revise`, `/review`.

## Roo Code usage

**Auto install** (recommended):
```bash
uvx --from git+https://github.com/yana1205/agentic-agile-authoring agentic-agile-authoring install
```

Installs to:
- `.roo/skills-agentic-agile-authoring/` — skill files
- `.roo/rules-<slug>/` — mode workflow rules

**Manual install** (GUI):
```bash
uvx --from git+https://github.com/yana1205/agentic-agile-authoring agentic-agile-authoring download
```
Then follow the printed instructions to copy skills and import mode YAMLs.

## Install outputs (gitignored)

`.roo/skills-*/` and `.roo/rules-*/` are created by the installer and gitignored.
For local Roo development in this repo, run the installer in the repo root.
