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

"""``compliance-authoring-skills`` CLI: a thin wrapper over OpenAPM (design-spec §3).

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

from . import __version__, policy
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
    # MyHarness MCP-entry shaping — reshape APM's normalized keys for a custom harness (e.g. bob,
    # which doesn't want `transport`/`registry`). Ignored by the APM-backed targets.
    p.add_argument(
        "--mcp-drop", action="append", default=[], metavar="KEY[,KEY…]",
        help="MyHarness: drop these keys from each MCP server entry (comma-ok, repeatable)",
    )
    p.add_argument(
        "--mcp-rename", action="append", default=[], metavar="OLD=NEW[,…]",
        help="MyHarness: rename MCP entry keys, applied after --mcp-drop (e.g. transport=type)",
    )
    p.add_argument(
        "--provenance-key", default=myharness.DEFAULT_PROVENANCE_KEY, metavar="KEY",
        help="MyHarness: top-level mcp.json key tracking the servers we wrote "
             f"(default: {myharness.DEFAULT_PROVENANCE_KEY})",
    )
    p.add_argument(
        "--no-provenance", action="store_true",
        help="MyHarness: write no provenance block (uninstall can then no longer prune wired MCP)",
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
        description="thin wrapper over OpenAPM: install portable skills + wire their MCP deps",
    )
    ap.add_argument(
        "-V", "--version", action="version",
        version=f"%(prog)s {__version__}",
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

    sub.add_parser("version", help="print the version and exit (same as -V/--version)")
    return ap


def _myharness_root(args: argparse.Namespace) -> Path:
    return Path(args.myharness_root).resolve() if args.myharness_root else myharness.DEFAULT_ROOT


def _parse_renames(values) -> dict[str, str]:
    """Parse repeatable ``old=new`` (comma-ok) rename pairs into a dict."""
    out: dict[str, str] = {}
    for item in _split_csv(values):
        old, sep, new = item.partition("=")
        old, new = old.strip(), new.strip()
        if not sep or not old or not new:
            raise policy.PolicyError(f"--mcp-rename expects OLD=NEW, got {item!r}")
        out[old] = new
    return out


def _mcp_shape(args: argparse.Namespace) -> myharness.McpShape:
    """Build the MyHarness MCP-entry shape from the shaping flags."""
    return myharness.McpShape(
        drop=frozenset(_split_csv(args.mcp_drop)),
        rename=_parse_renames(args.mcp_rename),
        provenance_key=None if args.no_provenance else args.provenance_key,
    )


def _warn_unused_shaping(args: argparse.Namespace) -> None:
    """The shaping flags only affect MyHarness; note it if they're passed to an APM target."""
    if args.target == MYHARNESS:
        return
    if args.mcp_drop or args.mcp_rename or args.no_provenance or args.provenance_key != myharness.DEFAULT_PROVENANCE_KEY:
        sys.stderr.write(
            f"warning: MCP-shaping flags (--mcp-drop/--mcp-rename/--provenance-key/--no-provenance) "
            f"have no effect for target '{args.target}' — APM owns MCP wiring there\n"
        )


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

    _warn_unused_shaping(args)
    sys.stdout.write(f"Installing {len(skills)} skill(s) → {args.target}: {', '.join(skills)}\n")

    if args.target == MYHARNESS:
        res = myharness.install(
            skill_dirs, root=_myharness_root(args), dry_run=args.dry_run, shape=_mcp_shape(args)
        )
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

    _warn_unused_shaping(args)
    if args.target == MYHARNESS:
        res = myharness.uninstall(
            picks, root=_myharness_root(args), dry_run=args.dry_run,
            provenance_key=None if args.no_provenance else args.provenance_key,
        )
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
    if args.cmd == "version":
        sys.stdout.write(f"compliance-authoring-skills {__version__}\n")
        return 0
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
