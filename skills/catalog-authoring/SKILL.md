---
name: catalog-authoring
description: OSCAL catalog and profile authoring workflow from asset import to parameter editing and markdown deployment using trestle MCP. Use when user requests OSCAL catalog operations, NIST SP800-53 deployment, parameter editing, CSV template generation, or compliance control customization.
argument-hint: Optional catalog/profile name or NIST baseline (e.g., "nist-800-53-low")
license: Complete terms in LICENSE.txt
---

# OSCAL Agile Authoring

## Purpose
Support custom catalog operations using NIST OSCAL catalogs and profiles, from parameter editing to Markdown deployment using trestle MCP tools.

## Default Workspace
- **Auto-initialized**: trestle workspace is automatically set up in current directory
- **No user input required**: Users do not need to specify workspace directory

## Main Tasks
1. Research and import OSCAL assets (catalogs, profiles)
2. Parameter editing and CSV template generation
3. Markdown deployment and assembly
4. Organizational distribution and data preparation

## Key Principles
- Must reference actual files (no guessing)
- Do not read catalog.json directly → operate after splitting into md
- **Must use trestle MCP** (do not use trestle CLI)
- **Do NOT use `trestle_root` parameter** - omit it from all MCP calls
- **Use profile-based control selection** - edit profile's `include-controls` to specify desired controls, not custom markdown files
- Output in English (other languages allowed when specified by user)
- When completing CSV, confirm with the user before proceeding to the next step — when a human is
  in the loop; otherwise see [Running with no human in the loop](#running-with-no-human-in-the-loop)
- Git operations are NOT performed by default → Only use git-workflow skill when user explicitly requests it

## Default Workflow

### Phase 1: Setup
Asset acquisition and structure organization.
See [setup.md](setup.md) for detailed instructions.

### Phase 2: Editing & Embedding
Parameter editing to profile/catalog deployment.
See [editing.md](editing.md) for detailed instructions.
## Rules

- Always use trestle MCP tools, never CLI commands
- **Never use `trestle_root` parameter** - omit it from all MCP tool calls
- **Use profile-based control selection** - edit profile's `include-controls` to specify desired controls instead of creating custom markdown files
- Confirm CSV content with user before parameter reflection
- Maintain escape characters in markdown files
- Use minimal, natural phrases for parameter values
- Complete both profile and catalog regeneration steps
- Reference actual files only, no assumptions
- After md conversion, never read catalog.json directly

## Running with no human in the loop

The confirmation steps above assume someone is watching. Settle that question once, at the
start: the run is unattended when the request already fixes the decisions it would otherwise
ask about (the prompt, or an instructions file in the workspace that it points at, pins them),
when it is a recorded or batch run, or when the user has said to go ahead without asking.

When the run is unattended:

- **Do not stop at the approval gate.** Still generate the markdown preview — it is the record of
  what was converted — then run the conversion in the same pass.
- **Let the conversion be the review.** `validate_controls="on"` and the required-column checks
  reject exactly the rows a reviewer would have caught. Fix the row it names and run it again.
- **Where a question would have supplied a missing fact**, take it from the pinned instructions,
  and name the choice you made in your summary. Do not invent one silently.
- **Never ask a question that cannot be answered.** With no human present a question does not
  slow the run down, it ends it.

## Related Skills

- For Git version control and PR workflow: Use `git-workflow` skill (only when user explicitly requests)

## Quick Reference

- NIST Resources: [resources.md](resources.md)
- Examples: [examples.md](examples.md)
- Best Practices & Lessons Learned: [best-practices.md](best-practices.md)
