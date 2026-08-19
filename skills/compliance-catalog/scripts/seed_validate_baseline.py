#!/usr/bin/env python3
"""Compute the *seed-baseline diff* of validate.py errors.

Motivation
==========

When we regenerate a framework's catalog from a new PDF while inheriting IDs
from a seed catalog, the fresh catalog will inevitably have some
``validate.py`` errors — but a large fraction of those errors also existed
in the *seed itself*.  Chasing those in the Phase 4 fix loop is a pure
waste of time: the seed was already accepted with those errors, so the
new catalog achieves nothing by "fixing" the same pattern.

This script computes the set of errors that are **new to the target** and
were NOT present in the seed.  Those are the only errors the fix loop
should attempt.

Output
======

Writes ``_seed_baseline_diff.json`` next to ``target_catalog`` with:

```json
{
  "seed_error_count": 21,
  "target_error_count": 25,
  "target_only_errors": [
    "[Rule 14] catalog/chapter-vii/article-48: Prose contamination: 'Decree 995/2000'"
  ],
  "shared_error_count": 24,
  "seed_only_error_count": 0
}
```

``target_only_errors`` is what the fix subagent should attempt to fix.
If this list is empty, Phase 4 can be skipped entirely — the target is
"as good as the seed" and any residual errors were already accepted.

Errors are compared by a normalised string (rule number + control/group
path + first ~200 chars of the message).  That is loose enough that
prose text differences don't fake a "new" error, and tight enough that
a genuinely new offending control gets flagged.

Usage
=====

  python3 seed_validate_baseline.py \\
      <target_catalog> <seed_catalog> <validate_py> \\
      [--merged <merged.txt>]

Exits 0 always (this is diagnostic; failure to compute the diff should
never break the pipeline — the fix loop can proceed with the full error
list as a safe fallback).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


ERROR_LINE_RE = re.compile(r"^\s*❌\s*(.+)$")


def _run_validate(validate_py: Path, catalog: Path,
                  merged: Path | None) -> list[str]:
    cmd = ["python3", str(validate_py), str(catalog), "--skip-trestle"]
    if merged is not None and merged.is_file():
        cmd += ["--merged", str(merged)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return []
    errors: list[str] = []
    for line in (proc.stdout or "").splitlines():
        m = ERROR_LINE_RE.match(line)
        if m:
            errors.append(m.group(1).strip())
    return errors


def _normalise_error(err: str) -> str:
    # Strip prose content after the last colon (that's usually the raw
    # excerpt from the PDF and it differs between seed and target even
    # when the *structural* problem is identical).
    #
    # Example:
    #   "[Rule 14] catalog/x/y: Prose contamination: 'Decree 995/2000'"
    #                          ^ keep this bit
    #                                              ^ drop this (differs)
    parts = err.split(":", 2)
    if len(parts) >= 3:
        return f"{parts[0]}:{parts[1]}"
    return err


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target_catalog", type=Path,
                        help="Freshly generated catalog.json to check")
    parser.add_argument("seed_catalog", type=Path,
                        help="Seed catalog.json (previous generation)")
    parser.add_argument("validate_py", type=Path,
                        help="validate.py to run against both catalogs")
    parser.add_argument("--merged", type=Path, default=None,
                        help="merged.txt to pass through (--merged flag)")
    parser.add_argument("--output", type=Path, default=None,
                        help="Where to write the diff JSON (default: "
                             "target_catalog's parent / "
                             "_seed_baseline_diff.json)")
    args = parser.parse_args()

    if not args.target_catalog.is_file():
        print(f"target catalog not found: {args.target_catalog}",
              file=sys.stderr)
        return 0  # non-fatal
    if not args.seed_catalog.is_file():
        print(f"seed catalog not found: {args.seed_catalog}",
              file=sys.stderr)
        return 0
    if not args.validate_py.is_file():
        print(f"validate.py not found: {args.validate_py}",
              file=sys.stderr)
        return 0

    seed_errors = _run_validate(args.validate_py, args.seed_catalog,
                                args.merged)
    target_errors = _run_validate(args.validate_py, args.target_catalog,
                                  args.merged)

    seed_set = {_normalise_error(e) for e in seed_errors}
    target_only: list[str] = []
    shared = 0
    for e in target_errors:
        if _normalise_error(e) in seed_set:
            shared += 1
        else:
            target_only.append(e)
    seed_only = len(seed_errors) - shared

    diff = {
        "seed_error_count": len(seed_errors),
        "target_error_count": len(target_errors),
        "target_only_errors": target_only,
        "target_only_error_count": len(target_only),
        "shared_error_count": shared,
        "seed_only_error_count": seed_only,
    }

    out_path = args.output or (
        args.target_catalog.parent / "_seed_baseline_diff.json"
    )
    out_path.write_text(json.dumps(diff, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")

    # Human-readable summary to stdout.
    print(f"seed_validate_baseline: seed={len(seed_errors)} errors, "
          f"target={len(target_errors)} errors, "
          f"target_only={len(target_only)}, shared={shared}, "
          f"seed_only={seed_only}")
    if target_only:
        print("target_only errors (these are what Phase 4 should fix):")
        for e in target_only[:20]:
            print(f"  - {e}")
        if len(target_only) > 20:
            print(f"  ... and {len(target_only) - 20} more")
    else:
        print("no target-only errors — Phase 4 can be skipped (target is at "
              "least as clean as the seed)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
