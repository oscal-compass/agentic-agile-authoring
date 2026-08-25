# Working inside a trestle workspace (optional)

A **trestle workspace** is a directory `trestle init` has stamped with a `.trestle/` marker and a
fixed set of per-model directories. When the cwd is a workspace, you **don't ask the user for input
paths** — the directory layout tells you deterministically where each OSCAL model lives, and where
the POA&M must be written. This is optional: if the cwd is not a workspace and the user doesn't want
one, ignore this file and take input paths the normal way (see
[from-assessment.md](from-assessment.md) / [from-component-definition.md](from-component-definition.md)).

Use this when **either**:

- the cwd (or an ancestor) is already a trestle workspace, or
- the user wants to author the POA&M inside a trestle workspace.

It is orthogonal to paths A/B/C: it changes only **where inputs come from and where output goes**,
not which authoring path you run.

## Step 1 — Detect the workspace

Look for a `.trestle/` directory in the cwd or any ancestor (same idea as git's `.git/`):

```bash
d="$PWD"; while [ "$d" != "/" ]; do [ -d "$d/.trestle" ] && { echo "workspace: $d"; break; }; d=$(dirname "$d"); done
```

If found, that directory is the **workspace root** — resolve every path below relative to it. If not
found, this file does not apply (unless the user asks to create one — Step 2).

## Step 2 — Initialize a workspace (optional)

Only if the user wants a workspace and there is none. Use the **isolated** trestle from
[setup-env.md](setup-env.md) — never a global install:

```bash
# uv:   uv run --with 'compliance-trestle>=3.0' trestle init
# venv: .venv-poam/bin/trestle init      # (or:  <PY> -m trestle init)
```

`trestle init` creates `.trestle/` plus one directory per OSCAL model (`catalogs/`, `profiles/`,
`component-definitions/`, `system-security-plans/`, `assessment-plans/`, `assessment-results/`,
`plan-of-action-and-milestones/`, `mapping-collections/`) and a `dist/` for assembled output. Place
the inputs you already have into their canonical directories (Step 3) before authoring.

## Step 3 — Locate inputs deterministically (don't ask for paths)

Each model sits at `<workspace>/<model-dir>/<name>/<model-type>.json`. Resolve inputs by globbing —
ask the user to choose **only** when a glob matches more than one:

| Input | Canonical path | Used by |
|---|---|---|
| component-definition | `component-definitions/*/component-definition.json` | path C (pre-define) |
| assessment result | `assessment-results/*/assessment-results.json` | path A · path C phase 2 |
| catalog / profile | `catalogs/*/catalog.json` · `profiles/*/profile.json` | control-id resolution |

Notes:

- **Split models.** trestle can `split` a model into several files under its `<name>/` directory. If
  the single `<model-type>.json` isn't there, read the split parts under that directory, or read the
  assembled copy under `dist/<model-dir>/` after `trestle assemble`.
- **remediations.json is not an OSCAL model** — it has no canonical trestle directory. Prefer
  consolidating remediation/risk onto the component-definition's validation props (see
  [from-component-definition.md](from-component-definition.md)); if you keep a separate file, put it
  at the workspace root and pass it with `--remediations`.

## Step 4 — Write the POA&M to its canonical path

Point the builder's `--output-dir` at the POA&M model directory:

```
plan-of-action-and-milestones/<name>/plan-of-action-and-milestones.json
```

This is exactly where `trestle validate -t plan-of-action-and-milestones` expects the file, so **no
copy step is needed** — build straight into place, then validate (see
[build-poam.md](build-poam.md)). Use the same `<name>` as the source system (e.g. the
component-definition's system-id) for a consistent layout.

```bash
# example, from the workspace root:
<PY> "$SKILL_DIR/build_poam.py" link-assessment \
  --poam predefined/plan-of-action-and-milestones.json \
  --assessment assessment-results/k8s-prod/assessment-results.json \
  --output-dir plan-of-action-and-milestones/k8s-prod/
<PY> -m trestle validate -t plan-of-action-and-milestones     # → VALID
```
