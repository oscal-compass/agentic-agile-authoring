---
name: git-workflow
description: OSCAL compliance document versioning with Git branching strategy for change tracking and pull request reviews. Use when user explicitly requests Git version control, PR creation, or change tracking for compliance documents.
argument-hint: Optional project identifier for branch naming (e.g., "nist-800-53")
---

# Git Workflow for OSCAL Compliance Documents

## Purpose
Provide version control and change tracking for OSCAL compliance documents using a two-branch strategy: baseline (`<id>-initial`) and review (`<id>-review`) branches.

## Important: Opt-in Only
**This workflow is NOT executed by default.** Only use when user explicitly requests:
- "Use Git for version control"
- "Create a PR at the end"
- "I want to track changes with Git"
- Or similar explicit requests

**Default behavior**: Skip all Git operations unless specifically requested.

## Default Workflow

### Phase 1: Setup (After Markdown Deployment)
Create baseline branch to establish change tracking foundation:

```sh
git checkout -b "<id>-initial"
git add -A && git commit -m "<message>"
```

**Purpose**: Establish a baseline for tracking changes.

### Phase 2: Review (After Editing Completion)
Create review branch and pull request for change review:

**Note**: Direct commits to `<id>-initial` are prohibited (protected branch)

```sh
git checkout <id>-initial
git checkout -b <id>-review
git add -A && git commit -m "<message>"
git push origin <id>-initial <id>-review
gh pr create --base <id>-initial --head <id>-review
```

**Best Practice**: Squash multiple commits into one before creating the PR.

## Branch Naming Convention

- `<id>-initial`: Baseline branch containing the initial state
- `<id>-review`: Review branch containing your changes

Replace `<id>` with a meaningful identifier for the compliance document or project (e.g., "nist-800-53-low", "fedramp-moderate").

## Rules

- Never execute Git operations unless user explicitly requests
- Always confirm branch identifier `<id>` with user before creating branches
- Protect `<id>-initial` branch from direct commits
- Use descriptive commit messages referencing control IDs when possible
- Squash commits before PR creation for clean history

## When to Recommend This Workflow

Suggest this workflow when:
- User mentions formal change tracking or review processes
- Multiple people are collaborating on compliance documents
- User needs clear audit trail of changes
- Organization requires pull request reviews

## Alternative Approaches

If this workflow doesn't fit user needs:
- Use custom Git branching strategy
- Commit directly to a single branch
- Use different version control system
- Skip version control entirely for simple projects

## Integration Points

This workflow integrates with:
- Phase 1 Setup: Execute after [`trestle_author_catalog_generate`](../../rules-agentic-agile-authoring/02-setup.md) and [`trestle_author_profile_generate`](../../rules-agentic-agile-authoring/02-setup.md)
- Phase 2 Edit: Execute after [`trestle_author_profile_assemble`](../../rules-agentic-agile-authoring/03-edit.md) and catalog regeneration
