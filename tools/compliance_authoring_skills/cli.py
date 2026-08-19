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

"""``compliance-authoring-skills`` CLI: a thin wrapper over Microsoft APM (design-spec §3).

    compliance-authoring-skills install   --target {claude|opencode|myharness} [--demo|--skill|--exclude] …
    compliance-authoring-skills uninstall --target {claude|opencode|myharness}  --skill a,b | --all

Flow: resolve a skill selection over *this repo* (policy) → hand it to the right backend
(``apm`` for supported targets; the MyHarness deployer for the custom harness). APM owns
placement / MCP wiring / lockfile / prune; we own only selection, UX, prereqs, and MyHarness.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import policy
from .backends import apm_cli
from .targets import myharness

MYHARNESS = "myharness"
_TARGETS = (*apm_cli.SUPPORTED_TARGETS, MYHARNESS)


def _split_csv(values) -> list[str]:
    """Flatten repeatable, comma-separated option values into a clean list."""
    out: list[str] = []
    for v in values or []:
        out.extend(p.strip() for p in v.split(",") if p.strip())
    return out


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "-t", "--target", required=True, choices=_TARGETS,
        help="harness to deploy to",
    )
    p.add_argument(
        "-g", "--global", dest="global_scope", action="store_true",
        help="user scope instead of the project (APM -g; MyHarness ~/.myharness)",
    )
    p.add_argument(
        "--project", default=".",
        help="project dir to install into / uninstall from (default: .; ignored with -g)",
    )
    p.add_argument(
        "--myharness-root", default=None,
        help=f"MyHarness root (default: {myharness.DEFAULT_ROOT})",
    )
    p.add_argument(
        "--keep-apm-files", action="store_true",
        help="leave APM's project files (apm.yml/apm.lock.yaml/apm_modules) in place instead of "
             "consolidating them into the hidden .compliance-authoring-skills/ stash (project scope only)",
    )
    p.add_argument("--dry-run", action="store_true", help="print what would happen; change nothing")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="compliance-authoring-skills",
        description="thin wrapper over Microsoft APM: install portable skills + wire their MCP deps",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    inst = sub.add_parser("install", help="install a skill selection into a harness (+ wire MCP)")
    inst.add_argument("--source", default=None, help="skills repo to install from (default: the skills bundled in this package)")
    inst.add_argument("--skill", "-s", action="append", default=[], help="explicit skills (comma-ok, repeatable)")
    inst.add_argument("--demo", help="skill set declared by demos/<name>/README.md")
    inst.add_argument("--exclude", action="append", default=[], help="all skills minus these (comma-ok, repeatable)")
    _add_common(inst)

    unin = sub.add_parser("uninstall", help="remove skills from a harness (+ prune unused MCP)")
    unin.add_argument("--skill", "-s", action="append", default=[], help="skills to remove (comma-ok, repeatable)")
    unin.add_argument("--all", action="store_true", help="remove the whole selectable skill set")
    unin.add_argument("--source", default=None, help="skills repo the selection is drawn from for --all (default: the bundled skills)")
    _add_common(unin)
    return ap


def _myharness_root(args: argparse.Namespace) -> Path:
    return Path(args.myharness_root).resolve() if args.myharness_root else myharness.DEFAULT_ROOT


def _emit_prereqs(report: policy.PrereqReport) -> None:
    for cmd in report.missing_optional:
        sys.stderr.write(
            f"warning: '{cmd}' not found — a selected skill's MCP server needs it "
            "(per-MCP runtimes are the environment's responsibility)\n"
        )


def _resolve_source(args: argparse.Namespace) -> Path:
    """The skills source: an explicit ``--source`` if given, else the bundled/dev default."""
    return Path(args.source).resolve() if args.source else policy.default_source_root()


def _install(args: argparse.Namespace) -> int:
    source = _resolve_source(args)
    skills = policy.resolve_selection(
        source,
        picks=_split_csv(args.skill),
        demo=args.demo,
        exclude=_split_csv(args.exclude),
    )
    skill_dirs = [policy.skill_dir(source, n) for n in skills]
    manifests = [policy.validate_skill_manifest(d) for d in skill_dirs]

    report = policy.check_prerequisites(manifests)
    if not report.ok:
        raise policy.PolicyError(
            f"missing baseline prerequisite(s): {', '.join(report.missing_baseline)} "
            "(uv is required; see design-spec §3.5)"
        )
    _emit_prereqs(report)

    sys.stdout.write(f"Installing {len(skills)} skill(s) → {args.target}: {', '.join(skills)}\n")

    if args.target == MYHARNESS:
        res = myharness.install(skill_dirs, root=_myharness_root(args), dry_run=args.dry_run)
        if args.dry_run:
            sys.stdout.write(f"[dry-run] would deploy skills: {', '.join(res.skills_deployed)}\n")
            if res.mcp_added:
                sys.stdout.write(f"[dry-run] would wire MCP: {', '.join(res.mcp_added)}\n")
        else:
            sys.stdout.write(f"  deployed: {', '.join(res.skills_deployed)}\n")
            if res.mcp_added:
                sys.stdout.write(f"  wired MCP: {', '.join(res.mcp_added)}\n")
        return 0

    out = apm_cli.install(
        skill_dirs,
        target=args.target,
        project=Path(args.project).resolve(),
        global_scope=args.global_scope,
        dry_run=args.dry_run,
        tidy=not args.keep_apm_files,
    )
    if args.dry_run:
        sys.stdout.write(f"[dry-run] {' '.join(out)}\n")
    else:
        sys.stdout.write(out.stdout)
    return 0


def _uninstall(args: argparse.Namespace) -> int:
    picks = _split_csv(args.skill)
    if not args.all and not picks:
        raise policy.PolicyError("uninstall needs --skill <a,b> or --all")

    if args.all:
        picks = policy.resolve_selection(_resolve_source(args))

    if args.target == MYHARNESS:
        res = myharness.uninstall(picks, root=_myharness_root(args), dry_run=args.dry_run)
        prefix = "[dry-run] would remove" if args.dry_run else "  removed"
        sys.stdout.write(f"{prefix}: {', '.join(res.skills_removed) or '(none)'}\n")
        if res.mcp_pruned:
            verb = "would prune" if args.dry_run else "pruned"
            sys.stdout.write(f"  {verb} MCP: {', '.join(res.mcp_pruned)}\n")
        return 0

    out = apm_cli.uninstall(
        picks,
        target=args.target,
        project=Path(args.project).resolve(),
        global_scope=args.global_scope,
        dry_run=args.dry_run,
        tidy=not args.keep_apm_files,
    )
    if args.dry_run:
        sys.stdout.write(f"[dry-run] {' '.join(out)}\n")
    else:
        sys.stdout.write(out.stdout)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "install":
            return _install(args)
        if args.cmd == "uninstall":
            return _uninstall(args)
    except (policy.PolicyError, apm_cli.ApmError, myharness.MyHarnessError, OSError) as e:
        sys.stderr.write(f"error: {e}\n")
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
