#!/usr/bin/env python3
"""Validate an emitted OSCAL Mapping Collection against the OSCAL schema.

Thin wrapper around `trestle validate`. Does not attempt to interpret or
fix errors itself — per the design's separation of concerns, that
judgment belongs to the Agent: read the trestle output, decide what in
the pipeline or its inputs needs to change, and re-run this after fixing.

`trestle validate -f` requires the target file to live inside an
initialized trestle workspace (a directory containing `.trestle/`), so
this script creates a throwaway workspace in a temp directory, copies the
mapping collection into it, and validates it there — the caller doesn't
need to manage a trestle workspace themselves.

Usage:
    python validate_oscal.py --mapping <mapping_collection.json>
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run_trestle_validate(filepath):
    with tempfile.TemporaryDirectory(prefix="trestle_ws_") as ws:
        ws_path = Path(ws)
        try:
            init = subprocess.run(
                ["trestle", "init", "-tr", str(ws_path)],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except FileNotFoundError:
            return False, "trestle command not found. Install with: pip install compliance-trestle"
        except subprocess.TimeoutExpired:
            return False, "trestle init timed out after 60 seconds"

        if init.returncode != 0:
            return False, "trestle init failed:\n" + init.stdout + init.stderr

        mc_dir = ws_path / "mapping-collections" / "candidate"
        mc_dir.mkdir(parents=True, exist_ok=True)
        target = mc_dir / "mapping-collection.json"
        shutil.copy(filepath, target)

        try:
            result = subprocess.run(
                ["trestle", "validate", "-tr", str(ws_path), "-f", str(target)],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            return False, "trestle validate timed out after 60 seconds"

        return result.returncode == 0, result.stdout + result.stderr


def main():
    parser = argparse.ArgumentParser(description="Validate an OSCAL Mapping Collection with trestle")
    parser.add_argument("--mapping", required=True, help="Path to the mapping collection JSON file")
    args = parser.parse_args()

    passed, output = run_trestle_validate(args.mapping)
    print(output.strip(), file=sys.stderr)

    if passed:
        print(f"validate_oscal: PASSED -> {args.mapping}", file=sys.stderr)
        sys.exit(0)
    else:
        print(f"validate_oscal: FAILED -> {args.mapping}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
