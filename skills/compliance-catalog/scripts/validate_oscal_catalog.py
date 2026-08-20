#!/usr/bin/env python3
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

"""Validate an OSCAL Catalog against the OSCAL schema.

Thin wrapper around `trestle validate`. Does not attempt to interpret or
fix errors itself — per the design's separation of concerns, that
judgment belongs to the Agent: read the trestle output, decide what in
generate.py needs to change, and re-run this after fixing.

`trestle validate -f` requires the target file to live inside an
initialized trestle workspace (a directory containing `.trestle/`), so
this script creates a throwaway workspace in a temp directory, copies the
catalog into it under `catalogs/candidate/catalog.json`, and validates it
there — the caller doesn't need to manage a trestle workspace themselves.

Usage:
    python validate_oscal_catalog.py --catalog <catalog.json>
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

        cat_dir = ws_path / "catalogs" / "candidate"
        cat_dir.mkdir(parents=True, exist_ok=True)
        target = cat_dir / "catalog.json"
        shutil.copy(filepath, target)

        try:
            result = subprocess.run(
                ["trestle", "validate", "-tr", str(ws_path), "-f", str(target)],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            return False, "trestle validate timed out after 120 seconds"

        return result.returncode == 0, result.stdout + result.stderr


def main():
    parser = argparse.ArgumentParser(description="Validate an OSCAL Catalog with trestle")
    parser.add_argument("--catalog", required=True, help="Path to the OSCAL Catalog JSON file")
    args = parser.parse_args()

    passed, output = run_trestle_validate(args.catalog)
    print(output.strip(), file=sys.stderr)

    if passed:
        print(f"validate_oscal_catalog: PASSED -> {args.catalog}", file=sys.stderr)
        sys.exit(0)
    else:
        print(f"validate_oscal_catalog: FAILED -> {args.catalog}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
