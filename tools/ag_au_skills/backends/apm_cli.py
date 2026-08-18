# Copyright OSCAL Compass Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Backend for APM-supported targets (claude, opencode, …): delegate to the pinned ``apm`` CLI.

This is the canonical, maintainer-tested path (design-spec §3.1). The wrapper does **not**
re-implement resolution, MCP normalization, the lockfile, or prune — ``apm`` owns all of that.
The wrapper's whole job here is to turn a resolved skill selection into one ``apm`` invocation:

* **project scope** (default): the ``--project`` directory *is* the APM project. We run
  ``apm install <skill-dir>… --target <t>`` with cwd there; APM writes ``apm.yml`` / ``apm.lock``
  into it, giving us its lockfile + non-destructive uninstall/prune for free. (Verified @ 0.28.0:
  positional local paths install the skill into the target's native dir AND wire each skill's
  ``dependencies.mcp`` into the native MCP config in one pass; a direct-dep self-defined MCP is
  auto-trusted.)
* **global scope** (``-g``): user scope (``~/.apm`` → ``~/.claude/skills`` + ``~/.claude.json``,
  ``~/.agents/skills`` + …). No project context needed.

Standalone-install shaping (§8.3): we do **not** synthesize a throwaway temp project — that would
discard APM's lockfile/prune, which is the reason we adopted APM (D4). The target project is the
APM project.

Pre-create note: 0.28.0 auto-creates the target root whenever ``--target`` is explicit
(``install/phases/targets.py:_create_target_dirs`` fires on ``auto_create OR explicit``; and
``ResolvedTargets.auto_create`` is always True after resolution). The wrapper always passes
``--target``, so the historically-documented ``auto_create=False`` skill-skip gotcha does not
apply. We still ``mkdir`` the root as cheap belt-and-suspenders against future/auto-detect paths.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

# APM-known targets we officially support in the wrapper UX. APM knows more (§3.1); these are the
# two we've verified end-to-end. The wrapper's --target choicelist is the union of these +
# myharness (added by cli.py). Unknown-to-APM slugs never reach this backend.
SUPPORTED_TARGETS = ("claude", "opencode")

# Native skill-dir per target root, used only for the belt-and-suspenders pre-create.
_TARGET_ROOT = {
    "claude": ".claude",
    "opencode": ".agents",
}


class ApmError(RuntimeError):
    """The pinned ``apm`` CLI exited non-zero (its stderr is attached)."""


@dataclass
class ApmResult:
    """Outcome of an ``apm`` invocation."""

    returncode: int
    stdout: str
    stderr: str


def resolve_apm_bin(apm_bin: str | None = None) -> str:
    """Locate the pinned ``apm`` executable.

    Order: explicit arg → ``APM_BIN`` env → ``apm`` on PATH. Raises if none is found so the
    failure is a clear prerequisite error rather than an opaque ``FileNotFoundError`` mid-run.
    """
    cand = apm_bin or os.environ.get("APM_BIN") or shutil.which("apm")
    if not cand:
        raise ApmError(
            "the pinned `apm` CLI was not found (install apm-cli, or set APM_BIN / add it to PATH)"
        )
    return cand


def _run(argv: list[str], *, cwd: Path | None, env: dict | None) -> ApmResult:
    proc = subprocess.run(
        argv,
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise ApmError(
            f"`{' '.join(argv)}` failed (exit {proc.returncode})\n{proc.stderr.strip()}"
        )
    return ApmResult(proc.returncode, proc.stdout, proc.stderr)


def install(
    skill_dirs: list[Path],
    *,
    target: str,
    project: Path,
    global_scope: bool = False,
    dry_run: bool = False,
    apm_bin: str | None = None,
    env: dict | None = None,
) -> ApmResult | list[str]:
    """Install *skill_dirs* into *target* by delegating to ``apm install``.

    ``skill_dirs`` are absolute local skill-package paths (each a dir with ``SKILL.md`` +
    ``apm.yml``). In project scope APM's bookkeeping lands in *project*; ``-g`` switches to user
    scope. Returns the argv (as a list) when ``dry_run`` is set, else the :class:`ApmResult`.
    """
    binp = resolve_apm_bin(apm_bin)
    argv = [binp, "install", *[str(d) for d in skill_dirs], "--target", target]
    if global_scope:
        argv.append("-g")

    if dry_run:
        return argv

    if not global_scope:
        project.mkdir(parents=True, exist_ok=True)
        # belt-and-suspenders: ensure the native root exists (not load-bearing in 0.28.0).
        root = _TARGET_ROOT.get(target)
        if root:
            (project / root).mkdir(parents=True, exist_ok=True)

    return _run(argv, cwd=None if global_scope else project, env=env)


def uninstall(
    skill_names: list[str],
    *,
    target: str,
    project: Path,
    global_scope: bool = False,
    dry_run: bool = False,
    apm_bin: str | None = None,
    env: dict | None = None,
) -> ApmResult | list[str]:
    """Uninstall skills by delegating to ``apm uninstall`` (APM prunes now-unreferenced MCP).

    Local skills are keyed ``_local/<name>`` in APM's lockfile (verified @ 0.28.0). APM removes
    each skill from the native dir and drops a shared MCP server only when no surviving installed
    skill still declares it — user-authored skills / user MCP servers are never touched (§3.1).
    ``target`` is accepted for symmetry/logging; APM resolves scope from the lockfile.
    """
    binp = resolve_apm_bin(apm_bin)
    keys = [f"_local/{n}" for n in skill_names]
    argv = [binp, "uninstall", *keys]
    if global_scope:
        argv.append("-g")

    if dry_run:
        return argv
    return _run(argv, cwd=None if global_scope else project, env=env)
