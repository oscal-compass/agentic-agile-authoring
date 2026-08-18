# Design Spec — Skills, Scenarios, and Installation

> **Status:** Approved; implementation in progress (rev.4, 2026-08-18). Supersedes the removed
> `docs/installer-spec.md`. This restructure covers **structure + the first scenario
> (`catalog-to-assessment`) + the `ag-au-skills` installer**; POA&M authoring is the next task.
>
> **Strategy (decided):** *Adopt, don't invent.* We are **not** building a package manager or a
> second dependency/ownership system. We stand on **Microsoft APM** (`apm-cli`,
> [`microsoft/apm`](https://github.com/microsoft/apm), MIT) — a real, actively-developed OSS
> Agent Package Manager whose model (`apm.yml` package + `dependencies.mcp` + per-harness
> deployment + `apm.lock.yaml` + non-destructive MCP merge + prune) is exactly our problem. Our
> `ag-au-skills` CLI is a **thin wrapper** that adds only what APM can't do for us. See
> `.insights/installer-node-vs-python.md` and the decision log (§9, **D4**).
>
> **Runtime (decided):** Python. Baseline prerequisite is **`uv`** (provides `uvx`, which also
> runs the pinned installer and `uvx`-based MCP servers like trestle). **No Node/npx.** The
> installer exact-pins `apm-cli` (verified against **0.28.0**).

## 1. Goal

Turn `agentic-agile-authoring` into an **ecosystem** where many contributors add authoring
skills, usable across multiple agent harnesses (**Claude Code**, **OpenCode**, a custom/minor
harness we call **MyHarness**, …). Three first-class objects:

- **Skill** — a unit of authoring know-how: `SKILL.md` + an `apm.yml` package manifest +
  optional `scripts/`/`references/`/`assets/`. Single source of truth in `skills/`, harness-independent.
- **Scenario** — an end-to-end use case exercising **N skills**, doubling as a **conformance
  run** (§4). Lives in `scenarios/`.
- **MCP dependency** — a skill declares (in `apm.yml`) that it needs an MCP server (e.g.
  `trestle`); the installer resolves it and wires it into the selected harness's native MCP
  config (§3).

## 2. Skills and their metadata

### 2.1 Portable `SKILL.md`

Keep `SKILL.md` portable across harnesses (Anthropic Agent-Skill format). Universally-required
frontmatter: `name` (== directory name) and `description`; optional `license`/`argument-hint`
are read by Claude and ignored elsewhere. The same package deploys to every target — there are
**no** per-harness skill packages (`trestle-skill-claude/…` is an anti-pattern).

### 2.2 `apm.yml` package manifest (hybrid layout)

Each skill is a **hybrid APM package**: `SKILL.md` (agent-consumed content) + `apm.yml`
(installer-consumed package/dependency metadata) in the same directory. Verified: APM copies the
**whole** skill folder (`SKILL.md`, `scripts/`, `references/`, `assets/`, …) on install.

```
skills/trestle-skill/
  SKILL.md
  apm.yml            # APM package manifest (name, version, dependencies.mcp)
  scripts/ …         # optional; ride along on install
```

Identity is the directory name; "has it changed?" is answered by APM's `apm.lock.yaml` (resolved
SHA + content hash), **not** a bespoke `version` scheme. We do not invent skill versioning.

### 2.3 MCP dependency declaration (`dependencies.mcp`)

A skill needing an MCP server declares it in its `apm.yml` under `dependencies.mcp`, in APM's
shape. Self-defined stdio servers (our `trestle` case) use `registry: false`:

```yaml
name: trestle-skill
version: "1.0.0"

dependencies:
  mcp:
    - name: trestle
      registry: false          # self-defined (not resolved from a registry)
      transport: stdio          # stdio | http | sse | streamable-http
      command: uvx
      args:
        - --from
        - git+https://github.com/oscal-compass/compliance-trestle-mcp.git
        - trestle-mcp
```

APM's `MCPDependency` supports `name, transport, command, args, env, url, headers, tools,
version, registry, package` — so both local stdio and remote http servers are expressible.
Skills with no MCP need simply omit `dependencies.mcp`.

> **Do NOT hardcode `target:`/`targets:` in a skill's `apm.yml`.** An unknown target token there
> is the one thing APM rejects at parse time — which would break MyHarness reuse (§3.3). Targets
> are chosen at install time, not baked into the package.

## 3. Installation — thin wrapper over Microsoft APM

`ag-au-skills` is the only bespoke code. It does **not** re-implement package resolution,
dependency graphs, lockfiles, MCP normalization, or ownership — APM owns all of that. It adds
three things APM alone doesn't give us:

1. **Selection** over *this repo* (`--scenario`, `--exclude`, all-skills) — APM has no concept of
   our scenarios; the wrapper resolves a selection to a set of local skill packages.
2. **A stable UX** that hides APM's project mechanics (a standalone skill install needs an APM
   project context; the wrapper synthesizes it) and enforces our prerequisite policy (§3.5).
3. **MyHarness deployment** — APM's target set is closed (§3.3), so the wrapper deploys to
   MyHarness itself, **reusing APM's resolver/normalizer** so it's a deployment diff only.

```
                    ag-au-skills
                         │
                         ▼
              APM manifest + resolution + MCP normalization   (always via apm-cli, pinned)
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
     APM-supported target        MyHarness (unknown to APM)
     (claude, opencode, …)               │
             │                    our deployer over APM's
        apm deploys               resolved/normalized objects
     skill + MCP + lockfile       (skill copy + native MCP merge)
```

### 3.1 Supported targets — delegate to `apm` (claude, opencode, …)

For any target APM knows, the wrapper shells out to the pinned `apm` CLI — the canonical,
maintainer-tested path. **Verified (spikes, §5):**

- `apm install <skill> --target claude` (or `opencode`, …) in a synthesized project **copies the
  skill into the target's native skill dir AND wires the MCP server into the target's native MCP
  config in one pass.** Direct-dependency self-defined MCP is auto-trusted (no extra flag).
  - Claude → skill in `.claude/skills/<name>/`, MCP in `.mcp.json` (`mcpServers`).
  - OpenCode → skill in `.agents/skills/<name>/`, MCP in `opencode.json` (`mcp.<name> = {type:
    local, command:[…], enabled}`). APM does the per-harness format translation.
- `apm uninstall <key>` + APM's reachability prune removes a skill and drops an MCP server
  **only when no remaining installed skill still declares it** — user-authored skills and
  user-defined MCP servers are never touched. (Verified with a diamond dep + a hand-injected user
  server that survived.)

The wrapper's job for supported targets is just: resolve the selection → for each skill, ensure a
project context (synthetic temp project depending on the local skill, or user scope `-g`) →
`apm install --target <t>` → surface results. Ownership/lockfile/prune all live in APM.

Gotcha handled by the wrapper: APM's Claude skill deploy is gated `auto_create=False`, so the
target root (`.claude/` or `~/.claude/`) must be pre-created or the skill silently isn't placed.

### 3.2 Selection (default: all skills in this repo)

| Intent | Resolves to |
|---|---|
| default (no selector) | all skill packages under `skills/` |
| `--skill a,b` | explicit pick |
| `--exclude x,y` | (all) − {x,y} |
| `--scenario name` | the `skills:` set declared in `scenarios/name/steps.md` |

The resolved set is validated against the repo (typos error out), then each skill is handed to
the appropriate backend (§3.1 for APM targets, §3.3 for MyHarness).

### 3.3 MyHarness — reuse APM's core, own only deployment

APM's deployment targets are a **closed, hardcoded registry** (`apm_cli/factory.py:
_MCP_CLIENT_REGISTRY`); unknown target slugs are rejected, and there is **no entry-point/plugin
mechanism** to register an external target. We do **not** fork APM. Instead — verified by source
trace — APM's **manifest load → dependency resolution → MCP normalization are fully
target-agnostic**:

- `apm_cli.models.apm_package:APMPackage.from_apm_yml(Path)` → parsed package
- `apm_cli.deps.apm_resolver:APMDependencyResolver.resolve_dependencies(project_root)` → graph
- `apm_cli.integration.mcp_config_view:CurrentMcpConfigView.derive(...)` (or
  `APMPackage.get_all_mcp_dependencies()`) → normalized `MCPDependency` objects / `{name:
  to_dict()}` — **none of these take a target.**

So the MyHarness adapter imports the pinned APM as a **library** to get resolved skills +
normalized MCP, then does the small deployment diff itself:

```
resolved skill package + normalized MCP  (from APM library)
        │
        ├── copy skill bundle → ~/.myharness/skills/<name>/
        └── merge normalized MCP → ~/.myharness/mcp.json   (non-destructive; preserve user entries)
```

MyHarness prune reuses the **same reachability idea** APM uses: recompute the required MCP set
from the currently-installed skills' manifests and drop only servers no surviving skill needs.
The only MyHarness-local state is "which entries we wrote" — not a second dependency manager.

### 3.4 Library vs CLI boundary (decided)

Split by need, not dogma (exact-pinned `apm-cli`, so private APIs are acceptable when we've read
the pinned source):

- **Supported targets → CLI** (`apm install/uninstall/prune`). We don't need APM's internal
  objects here; APM owns the whole lifecycle. Least code. (The Click-free entry
  `apm_cli.install.service:InstallService.run(InstallRequest(...))` exists if we ever want
  in-process, but the CLI does the project/lockfile bookkeeping for free.)
- **MyHarness → library** (`APMPackage.from_apm_yml` → `APMDependencyResolver` →
  `CurrentMcpConfigView.derive`), because we need the normalized objects in-process to drive our
  own deployer.

Version bumps of `apm-cli` are gated behind the §5 integration spikes.

### 3.5 Prerequisites (deliberately simple)

- **Guaranteed baseline: `uv`** (→ `uvx`). `uvx` runs the pinned `ag-au-skills`/`apm-cli` and the
  `uvx`-based trestle MCP. This is the only runtime we promise.
- **Other MCP-specific prerequisites are the environment's responsibility.** If a skill's MCP
  needs `npx` or `docker`, those must already be installed; the wrapper validates presence and
  emits a useful error but does **not** auto-install system dependencies.

## 4. Scenario

A scenario is a **conformance run**: a walkthrough exercising N skills, with checkpoints that
assert the run produced the right kind of result on a given (harness, model).

### 4.1 Layout

```
scenarios/<scenario-name>/
  steps.md        walkthrough: prompts to give the agent, in order (+ frontmatter)
  expected.md     checkpoints: what must be true at key points
```

- **1 scenario : N skills** (not 1:1). `steps.md` frontmatter declares the skill set (also used
  by `--scenario` install, §3.2):

```yaml
---
name: catalog-to-assessment
skills: [catalog-authoring, component-definition, assessment]
verified:
  - harness: claude-code
    model: claude-opus-4-8
    date: 2026-08-18
---
```

### 4.2 Checkpoints (`expected.md`)

Each checkpoint names a location in the run and a match mode:

- **exact** — must hold precisely (e.g. `trestle validate` prints `VALID`; file P exists).
- **approx** — "roughly this kind of output", judged by a reader/agent, not word-for-word.

Because LLMs are non-deterministic, scenarios are **acceptance-style** (validate
artifacts/behavior), not byte-snapshot. `verified` records which (harness, model) combos have
passed — one combo is acceptable now; the full matrix is a future goal.

## 5. Verification & Validation

### 5.1 Verification — "did we build it right?" (tests)

The bespoke code is small: the selection wrapper and the MyHarness deployer. Test those directly
(unit). But the load-bearing behavior lives in APM, so the primary safety net is an
**integration spike suite** pinned to the `apm-cli` version — the same checks proven by hand
during design (see `.insights/installer-node-vs-python.md`), run in CI and re-run before any
`apm-cli` bump:

- **standalone install (supported target):** install a local skill `--target claude` → skill
  appears in `.claude/skills/<name>/` **and** its stdio MCP appears in `.mcp.json`.
- **OpenCode:** same, into `.agents/skills/` + `opencode.json` (native `mcp` shape), preserving a
  pre-existing user `provider`/`model` config.
- **shared-MCP prune:** two skills declare the same server → uninstall one keeps it, uninstall the
  last removes it; a hand-planted user MCP server survives throughout.
- **selection:** `--exclude` / `--scenario` resolve to the correct skill set.
- **MyHarness:** library reuse yields normalized MCP objects for an unknown target; our deployer
  writes `~/.myharness/skills/` + merges `~/.myharness/mcp.json` non-destructively; prune drops
  only unreferenced servers.

### 5.2 Validation — "did we build the right thing?" (acceptance)

Two instruments, both acceptance-style (§4.2):

1. **Scenario conformance runs (§4)** validate the *authoring capability* — a real (harness,
   model) drives an N-skill scenario and the `expected.md` checkpoints must hold (e.g. produced
   OSCAL passes `trestle validate`). Recorded per scenario in `verified:`.
2. **Installer acceptance** = the §5.1 spikes at requirement level: skills land in each harness's
   native dir; MCP servers appear in native config; non-destructive uninstall; prune-when-unreferenced.

## 6. Target repo layout

```
skills/<name>/               skill package: SKILL.md + apm.yml [+ scripts/refs/assets]
scenarios/<name>/            steps.md + expected.md (conformance runs)
tools/                       `ag-au-skills` — thin wrapper over apm-cli (Python)
  pyproject.toml             deps: apm-cli==<pin>, pyyaml
  ag_au_skills/
    cli.py                   install / uninstall  --target {claude|opencode|myharness|…}
    policy.py                selection + apm.yml validation + prereq checks (uv; npx/docker existence)
    backends/apm_cli.py      subprocess to pinned `apm` for supported targets (canonical path)
    targets/myharness.py     library reuse (APM resolve/normalize) + our deployer
  tests/ag_au_skills/        unit + pinned-apm integration spikes (§5.1)
docs/
```

Notes:
- Skill *placement* into a user project is done by APM (supported targets) or the MyHarness
  deployer — producing `.claude/skills/`, `.agents/skills/`, `~/.myharness/skills/`, and the
  matching native MCP config, plus APM's `apm.lock.yaml` for supported targets.
- The old Python installer (`installer/agentic_agile_authoring/cli.py`), wheel, Claude plugin, and
  publish workflow are **retired/removed**.

## 7. Requirements traceability

| Requirement | Where satisfied |
|---|---|
| Install per each harness's convention | §3.1 APM native-dir deploy (claude/opencode verified); §3.3 MyHarness deployer |
| Same package to all harnesses (no per-harness pkg) | §2.1 hybrid `SKILL.md`+`apm.yml`, target chosen at install |
| Selectable which skills (default all) | §3.2 (`--skill`/`--exclude`/`--scenario`) |
| Provided as a CLI (uvx-runnable) | §3 (`ag-au-skills`, Python, pins `apm-cli`) |
| Skill declares MCP dep; installer wires it | §2.3 + §3.1 (`apm`) / §3.3 (MyHarness) |
| MCP merged into native config, non-destructive | §3.1 verified (Claude `.mcp.json`, OpenCode `opencode.json`) |
| Uninstall non-destructive + prune unused MCP | §3.1 APM reachability prune (verified); §3.3 for MyHarness |
| One source of truth for lifecycle/ownership | APM `apm.lock.yaml` for supported targets; minimal MyHarness-scoped record only |
| Scenario = conformance run over N skills | §4 |
| Prerequisite policy (uv baseline) | §3.5 |

## 8. Phasing / open items

1. **Wrapper build** — `ag-au-skills` (cli/policy/backends.apm_cli/targets.myharness). *In progress.*
2. **apm-cli pin** — exact-pin the verified version (0.28.0) in `pyproject.toml`; CI gate on §5.1.
3. **Standalone-install shaping** — finalize synthetic-project vs `-g` user-scope vs `--root` for
   supported targets (spikes used a temp project with a local-path dep; both work).
4. **MyHarness spec** — pin `~/.myharness/{skills/,mcp.json}` paths + the minimal ownership record.
5. **Remote source shorthand** — `--source oscal-compass/agentic-agile-authoring` would `git clone`
   first (git then an optional prereq); deferred.
6. **trestle MCP runtime bug (external)** — `compliance-trestle-mcp` currently crashes on import
   (`No module named 'mcp.server.fastmcp'`, stale FastMCP pin). Wiring is correct in every harness,
   but the server yields no tools until that repo's dependency is fixed. Tracked separately.
7. **OpenAPM tracking** — APM/OpenAPM is pre-1.0 and fast-moving; the `dependencies.mcp` shape and
   library entry points may shift. Mitigated by the version pin + §5.1 gate.

## 9. Decision log

Short ADR-style records of load-bearing choices. Most recent first.

### D4 — Adopt Microsoft APM (`apm-cli`) as the installer backend

- **Status:** Accepted (2026-08-18). **Supersedes D3** (and restores D1's "adopt, don't invent").
- **Context:** After D3 chose to self-implement placement + a bespoke MCP bridge/lockfile, research
  surfaced **Microsoft APM** (`microsoft/apm`, `apm-cli`) — a real, maintained OSS package manager
  that already models exactly our problem: `apm.yml` packages, `dependencies.mcp` (incl. self-defined
  stdio `command`/`args`), per-harness deployment (Claude, OpenCode, +9), `apm.lock.yaml`,
  non-destructive native-MCP merge, and reachability-based prune. Re-implementing that ourselves
  would be a second dependency/ownership system — the thing we explicitly want to avoid.
- **Evidence (source trace + spikes against `apm-cli==0.28.0`):**
  - `apm install <local-skill> --target claude` → skill in `.claude/skills/` + trestle stdio in
    `.mcp.json`, one pass, direct-dep MCP auto-trusted.
  - `--target opencode` → skill in `.agents/skills/` + `opencode.json` `mcp` (native shape),
    **user `litellm` provider config preserved**; a real OpenCode agent (litellm haiku) then loaded
    and listed the installed skill.
  - shared-MCP: two skills → uninstall one keeps trestle, uninstall the last prunes it; a
    hand-injected user MCP server survived throughout.
  - target-agnostic library layer (`APMPackage.from_apm_yml` → `APMDependencyResolver` →
    `CurrentMcpConfigView.derive`) yields normalized MCP for an **unknown** target — enabling
    MyHarness without forking APM.
- **Decision:** `ag-au-skills` becomes a **thin wrapper**: delegate supported targets to the pinned
  `apm` CLI; add only selection (our scenarios), UX, prereq policy, and a **MyHarness deployer** that
  reuses APM's target-agnostic resolve/normalize (library) and writes MyHarness's own skill dir +
  MCP config. Exact-pin `apm-cli`; gate bumps on the §5.1 spikes.
- **Consequences:** (+) drastically less bespoke code; APM owns resolution/lockfile/ownership/prune;
  correct per-harness MCP translation for free; broad target coverage. (−) a real dependency on a
  pre-1.0, fast-moving project (mitigated by pin + spikes); baseline prereq is now **`uv`** (not
  zero); MyHarness is the one place we still write a deployer + a small ownership record.
- **Not chosen:** forking APM to add MyHarness to `_MCP_CLIENT_REGISTRY` (maintenance burden;
  library reuse of the target-agnostic layers avoids it). Full write-up:
  `.insights/installer-node-vs-python.md`.

### D3 — Self-implement placement in Python (SUPERSEDED by D4)

- **Status:** Superseded by D4. Was: reverse D1 and self-implement placement + MCP bridge in Python
  (no Node) because Vercel `skills` has no library API and forces Node on users.
- **Why superseded:** the anti-Node reasoning still holds (we do not use Vercel `skills`), but MS
  APM provides the placement/ownership/prune we were about to hand-write — in Python, reusable as a
  library — so hand-writing it is no longer justified. The Vercel `skills` findings (no library API;
  closed harness set) remain recorded in `.insights/prior-art-skill-dependency-managers.md`.

### D2 — Implement `ag-au-skills` in Python (still holds)

- **Status:** Accepted. Reinforced by D4: APM itself is Python, so library reuse of its
  resolve/normalize layer for MyHarness is natural. Tested with `pytest`.

### D1 — Adopt, don't invent (restored by D4)

- **Status:** Accepted; the "reuse existing tooling for placement/MCP" intent is fulfilled by D4
  (adopt MS APM). Declaring MCP deps in `apm.yml` (§2.3) is APM's own shape.
