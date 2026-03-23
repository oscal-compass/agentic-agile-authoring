# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI agent skills and modes for OSCAL-based compliance authoring — from NIST catalog customization through component definition to assessment result generation. Supports both Claude Code (as a plugin) and Roo Code (via Python installer CLI).

## Build & Development Commands

```bash
# Build the package
hatch build

# Install locally for development
pip install -e .

# Run the CLI (install/uninstall/download subcommands)
python -m agentic_agile_authoring.cli install
python -m agentic_agile_authoring.cli uninstall
python -m agentic_agile_authoring.cli download

# Run via uvx from local repo
uvx --from . agentic-agile-authoring install

# Test as Claude Code plugin locally
claude --plugin-dir ./

# Add license headers to new files
python scripts/add_license_headers.py

# Pre-commit (uses detect-secrets)
pre-commit run --all-files

# Documentation site
make install   # Install docs dependencies
make serve     # Serve docs locally at http://localhost:8000
make build     # Build docs with strict mode
```

## Architecture

### Dual-platform distribution

The repo serves as both a **Claude Code plugin** (via `.claude-plugin/`) and a **Roo Code installer** (via the Python package in `src/`). Skills in `skills/` are the single source of truth for both platforms.

### Key directories

- **`skills/<name>/`** — Agent skills. Each has a `SKILL.md` with YAML frontmatter (`name`, `description`, `argument-hint`) plus supporting `.md`/`.py` files. Four skills: `catalog-authoring`, `component-definition`, `assessment`, `git-workflow`.
- **`agents/agentic-agile-authoring.md`** — Claude Code agent persona definition (frontmatter + body).
- **`agents-roo/agentic-agile-authoring/roo.yaml`** — Roo Code mode config (slug, roleDefinition, customInstructions, groups).
- **`src/agentic_agile_authoring/cli.py`** — Installer CLI with three commands: `install` (merges mode into `.roomodes`, copies skills/rules to `.roo/`), `uninstall`, `download`. Uses `ruamel.yaml` for round-trip YAML handling.
- **`.claude-plugin/`** — Plugin manifest (`plugin.json`) and marketplace entry (`marketplace.json`).
- **`.mcp.json`** — Configures the trestle MCP server dependency (compliance-trestle-mcp).

### Data flow at build time

`pyproject.toml` uses `hatch` with `force-include` to bundle `skills/`, `agents-roo/`, and `.mcp.json` into `agentic_agile_authoring/data/` inside the wheel. The CLI reads from this bundled `data/` directory at runtime.

### Adding a new skill

1. Create `skills/<skill-name>/SKILL.md` with required frontmatter fields: `name`, `description`, optional `argument-hint`.
2. Add supporting `.md` or `.py` files in the same directory.
3. Reference the skill from `agents/agentic-agile-authoring.md` and `agents-roo/agentic-agile-authoring/roo.yaml`.
4. Run `python scripts/add_license_headers.py` to add license headers.

## Important: Do not use the trestle MCP server

This repo develops the MCP server infrastructure itself. Do not invoke or depend on the trestle MCP server (compliance-trestle-mcp) when working in this repository.

## Conventions

- **License headers required**: All `.py` and `.yaml` files need Apache 2.0 headers. SKILL.md files need a `license` frontmatter field and `LICENSE.txt` in their directory. Use `scripts/add_license_headers.py`.
- **Python 3.10+**, built with `hatchling`.
- **Single runtime dependency**: `ruamel.yaml`.
- **Releases**: Tag with `v*` pattern, `publish.yml` workflow builds, signs with Sigstore, and publishes to GitHub Releases.
- **`--skills-scope`**: Controls install location — `mode` (default, `.roo/skills-agentic-agile-authoring/`) or `common` (`.roo/skills/`).
