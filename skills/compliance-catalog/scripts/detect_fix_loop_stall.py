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

"""Detect a stalled Phase 4 fix loop.

Compares two consecutive `validate.py` outputs (iter N-1 and iter N) and
tells the orchestrator whether the fix subagent produced ANY measurable
progress. If the total ERROR count is identical AND the per-rule error
breakdown is byte-identical, the iteration is a no-op — a "stall".

This exists because prompt-level warnings ("if the failure signature is
byte-identical, the previous edit didn't take effect") demonstrably do
NOT stop bob from printing "DONE" on a stalled iteration. Observed
2026-07-27 (ADGM-DPR-2021-Guidance): iter 2 and iter 3 both reported 27
errors with identical per-rule breakdown (Rule 1: 12, Rule 6a: 7, Rule
11: 1, Rule 12: 8, Rule 16: 1). The fix subagent saw the stall warning
in its prompt and shipped DONE anyway — every iteration burns ~5-10 min
of bob time, so the orchestrator needs a machine-level check.

Usage:

    python3 detect_fix_loop_stall.py <prev_validate_output> <cur_validate_output>

Exit codes:
    0  — progress detected (error count changed OR at least one rule's
         count changed). The orchestrator should continue looping.
    2  — STALL detected. Prev and cur have identical error count AND
         identical per-rule breakdown. The orchestrator should retry
         this iteration ONCE, then abort the fix loop if still stalled
         (per SKILL.md Phase 4 discipline).
    1  — cannot compare (one file missing / unreadable / malformed).
         Treat as "unknown, continue looping" rather than aborting.

The comparison reuses `_extract_error_stats` from build_fix_prompt so
we do not drift from the same-module definition of "error signature".
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _load_stats(path: Path) -> dict | None:
    """Read a validate.py output file and pull out its error stats.

    Returns None if the file is missing, empty, or cannot be parsed
    into a shape with an error_count.
    """
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        return None
    # Reuse the exact stat extractor build_fix_prompt uses so the
    # definition of "signature" stays in one place.
    here = Path(__file__).resolve().parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    from build_fix_prompt import _extract_error_stats  # type: ignore
    stats = _extract_error_stats(text)
    if "error_count" not in stats:
        return None
    return stats


def compare(prev: dict, cur: dict) -> tuple[bool, str]:
    """Return (is_stall, human_readable_reason)."""
    if prev.get("error_count") != cur.get("error_count"):
        return False, (
            f"error_count changed: {prev.get('error_count')} → "
            f"{cur.get('error_count')}"
        )
    prev_rules = prev.get("per_rule") or {}
    cur_rules = cur.get("per_rule") or {}
    if prev_rules != cur_rules:
        # Same total but a rule moved — that IS progress (a rule was
        # fixed at the cost of introducing a new one, which is normal
        # mid-iteration).
        return False, (
            f"per-rule breakdown changed: {prev_rules} → {cur_rules}"
        )
    return True, (
        f"STALL: error_count={cur.get('error_count')} and per-rule "
        f"breakdown identical to previous iteration: {cur_rules}"
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("prev", type=Path, help="Previous iteration's validate output")
    p.add_argument("cur", type=Path, help="Current iteration's validate output")
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the human-readable reason on stdout",
    )
    args = p.parse_args()

    prev_stats = _load_stats(args.prev)
    cur_stats = _load_stats(args.cur)
    if prev_stats is None:
        if not args.quiet:
            print(
                f"cannot compare: previous validate output missing or "
                f"malformed: {args.prev}",
                file=sys.stderr,
            )
        return 1
    if cur_stats is None:
        if not args.quiet:
            print(
                f"cannot compare: current validate output missing or "
                f"malformed: {args.cur}",
                file=sys.stderr,
            )
        return 1

    is_stall, reason = compare(prev_stats, cur_stats)
    if not args.quiet:
        print(reason)
    return 2 if is_stall else 0


if __name__ == "__main__":
    sys.exit(main())
