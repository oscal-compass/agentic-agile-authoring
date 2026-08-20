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

"""Stream-style file-watcher: block until files exist / update, emitting
one heartbeat line per second so orchestrating agent harnesses don't
mistake this process for hung and background it.

Design note (very important). Some agent harnesses — notably bob's
`execute_command` — auto-background any subprocess that stays silent for
more than a few seconds, returning a PID immediately and forcing the
orchestrator to poll for the outcome. That polling (`while ps -p …; do
sleep …; done` or `sleep 30; check; sleep 60; check`) then trips the
harness's own loop-detector and kills the orchestrating session.

The fix is to keep stdout streaming: bob (and every other harness with
similar heuristics) treats "process is emitting lines" as "process is
alive" and does NOT background it. So this script emits one line per
second — either a `[heartbeat]` line describing what it's waiting for,
or an event line when a file appears / becomes stale / becomes ready.
Every line is flushed immediately.

If the caller doesn't want the heartbeat noise (e.g., a claude harness
that runs synchronously anyway), pass `--quiet` to suppress heartbeats;
event lines still print.

## The bob shell tool's 180 s cap and how this script cooperates with it

Bob's `execute_command` tool has a hard, client-side cap: no matter what
the caller passes for `timeout`, bob clamps it to 180 seconds:

    let r = Math.min(this.params.timeout || 180, 180);   // in bobshell/bundle/bob.js

That means a single `python3 wait_for.py --timeout 900` tool call ALWAYS
aborts at the 180 s mark from bob's side. The wait_for.py process itself
gets killed with SIGTERM by bob when the abort fires, and every child in
its process group goes with it. The result is exactly the pathology we
were trying to prevent: bob "sees" wait_for.py fail, decides to relaunch
it, kills the (now-orphaned) PID it remembers, and repeats. Meanwhile
the actual subagent whose completion we were waiting for was never in
that process group and keeps running fine — but bob has now lost track
of it, kills random other PIDs looking for it, and the whole run
collapses. This was the failure mode observed on South-Africa-POPIA and
Australia-Privacy-Act on 2026-07-28.

The safe pattern under bob is therefore:

  * Call wait_for.py with `--timeout <=150` so it returns naturally
    inside bob's 180 s window (30 s of margin absorbs Python startup
    plus flush latency).
  * If wait_for.py returns exit code 3 (POLL_INCOMPLETE — see the
    exit-code table below), the file isn't ready yet — call wait_for.py
    AGAIN with a different `--attempt N` value.
  * `--attempt N` is a no-op flag whose sole job is to change the
    tool-call args so bob's loop-detector does not consider two
    consecutive wait_for.py calls "identical". Bob's detector hashes
    `sha256(tool_name + JSON.stringify(args))` and fires at 5
    consecutive identical hashes; incrementing `--attempt` from 1..5..N
    is enough to keep every call unique without changing behaviour.

Concretely, from a bob main agent's point of view:

    python3 wait_for.py $LOG --timeout 150 --attempt 1
    # if exit 3, still pending — call again:
    python3 wait_for.py $LOG --timeout 150 --attempt 2
    # ... up to the caller's own patience (60 attempts = ~2.5 hours)

Harnesses without the 180 s cap (claude, opencode) can pass a large
`--timeout` and skip `--attempt` entirely; the script's behaviour is
identical either way.

## Subagent-completion detection (--stable-for / --completion-marker)

By default this script returns as soon as each watched file EXISTS and
meets the size / mtime constraints. That is NOT enough when the file
being watched is a subagent log (e.g., `_fix_agent_${N}.jsonl`) that
the subagent is still appending to: the log exists from the first
tool call but the subagent may keep writing for another minute or
more, and if the orchestrator moves on it will race with a partially-
finished subagent whose delayed writes overwrite files (generate.py,
catalog.json, validate_config.py). We saw this in production — four
fix subagents running in parallel because wait_for returned too early.

Two ways to require "subagent really finished":

  --stable-for N       Wait for the file's size to remain unchanged for
                       N consecutive seconds. Cheap and harness-agnostic.
                       Recommended value: 5–10 seconds. This alone is
                       usually sufficient because bob emits tool_use
                       events in bursts, and 5s of silence reliably
                       indicates end-of-session.

  --completion-marker STRING
                       Additionally require the file's last few KB to
                       contain STRING somewhere. Use "attempt_completion"
                       for bob and Roo-style harnesses whose subagent
                       terminates by emitting an attempt_completion
                       tool_use. If STRING never appears the wait will
                       time out — combine with a generous --timeout.

These options are ANDed with the base existence / size / mtime checks.
All conditions must hold on the same tick.

Usage:
    python3 wait_for.py <path>... [--timeout N] [--attempt N] [--poll N]
                       [--updated-after ISO_OR_EPOCH | 'now']
                       [--min-size N] [--stable-for N]
                       [--completion-marker STRING] [--quiet]

Exit codes:
    0 — all conditions satisfied
    3 — POLL_INCOMPLETE: the timeout window closed without failure but
        the file is still pending; re-invoke with a different --attempt
        value to continue waiting under bob's tool-call cap. Non-bob
        callers can treat this identically to code 1 (both mean "did
        not finish within the requested budget").
    1 — legacy timeout code, kept as an alias for exit 3 when
        `--legacy-timeout-exit` is set; some existing callers already
        interpret 1 as "timed out, retry" and don't need to change.
    2 — argument error
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Harness-specific "session ended" markers.
#
# Both Bob and Claude Code stream stream-json where the FINAL line is
# always an event with `"type":"result"` (with a status/subtype indicating
# success or error). Detecting this string in the log tail is a positive
# signal that the subagent has finished — much stronger than waiting for
# file-size stability, which false-positives whenever the subagent pauses
# to "think" between tool_use calls.
#
# The marker is auto-selected from AGENT_HARNESS (set by run_agent.sh
# before it launches the subagent, and honoured by the parent orchestrator's
# environment). An explicit `--completion-marker` on the CLI still overrides.
_HARNESS_MARKERS: dict[str, str] = {
    "bob": '"type":"result"',
    "claude": '"type":"result"',
    # opencode's `--format json` stream doesn't emit a reliable session-
    # end event in the general case: short sessions terminate with
    # `step_finish reason="stop"`, but long sessions often just end on
    # a `step_finish reason="tool-calls"` with no follow-up. We can't
    # match on "stop" alone because it never fires for long turns.
    # Instead we rely on the stability fallback: run_agent.sh runs
    # opencode in foreground with output redirected to LOG_FILE, so
    # once opencode's process exits the file stops growing. Under
    # AGENT_HARNESS=opencode we automatically shorten --stable-for
    # (see _stable_for_default_for_harness below) so the wait
    # completes promptly instead of the 180 s bob-tuned default.
}


_OPENCODE_STABLE_FOR = 15.0  # seconds — under opencode the log stops


def _stable_for_default_for_harness(current_default: float) -> float:
    """Return the effective --stable-for default given the harness.

    Opencode has no reliable stream-side end-of-session marker, so we
    lean on the stability fallback — but the bob-tuned 180 s default
    is far longer than needed since opencode writes its full stream
    to LOG_FILE synchronously. 15 s is more than enough for the OS
    filesystem event to settle after the child process exits.
    """
    harness = (os.environ.get("AGENT_HARNESS") or "").strip().lower()
    if harness == "opencode":
        return _OPENCODE_STABLE_FOR
    return current_default


def _default_completion_marker() -> str:
    """Pick a completion marker from the AGENT_HARNESS env var.

    Returns "" if the harness is unknown / unset — the caller falls back
    to --stable-for alone in that case, which is the pre-existing
    behaviour. Case-insensitive.
    """
    harness = (os.environ.get("AGENT_HARNESS") or "").strip().lower()
    return _HARNESS_MARKERS.get(harness, "")


def _emit(line: str) -> None:
    """Write one event line to stdout and flush immediately.

    Immediate flush is what convinces the surrounding harness that this
    process is actively producing output, so it won't be auto-backgrounded.
    Do not batch, do not use print's default buffering.
    """
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def _parse_timestamp(s: str) -> float:
    s = s.strip()
    if s == "now":
        return time.time()
    try:
        return float(s)
    except ValueError:
        pass
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            f"cannot parse timestamp {s!r} "
            f"(expect ISO-8601, epoch seconds, or 'now'): {e}"
        )
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _file_status(path: Path, min_size: int, updated_after: float | None) -> tuple[bool, str]:
    """Return (satisfied, reason_if_not)."""
    if not path.exists():
        return False, "missing"
    if not path.is_file():
        return False, "not a regular file"
    try:
        st = path.stat()
    except OSError as e:
        return False, f"stat failed: {e}"
    if st.st_size < min_size:
        return False, f"size {st.st_size} < min {min_size}"
    if updated_after is not None and st.st_mtime <= updated_after:
        return False, f"mtime {st.st_mtime:.0f} not after {updated_after:.0f}"
    return True, f"ok ({st.st_size} bytes)"


# Per-path memory of the last observed (size, first_seen_at_size) tuple, used
# to determine whether a file's size has been stable for the required
# duration. Keyed by absolute path string.
_stable_seen: dict[str, tuple[int, float]] = {}


def _stability_status(
    path: Path, stable_for: float, now: float
) -> tuple[bool, str]:
    """Return (stable, reason) — is this file's size unchanged long enough?

    Uses the module-level `_stable_seen` dict to remember the first tick
    on which a given size was observed. As soon as we see a NEW size
    (larger — meaning the writer is still growing the file), we reset the
    clock. The file is considered stable once the current size has been
    held for at least `stable_for` seconds.
    """
    if stable_for <= 0:
        return True, "stability disabled"
    try:
        current_size = path.stat().st_size
    except OSError as e:
        # Base _file_status already flagged this; be defensive anyway.
        return False, f"stat failed during stability check: {e}"
    key = str(path)
    prev = _stable_seen.get(key)
    if prev is None or prev[0] != current_size:
        _stable_seen[key] = (current_size, now)
        return False, f"size {current_size} just observed; waiting {stable_for:.0f}s of no-change"
    first_seen_at = prev[1]
    held = now - first_seen_at
    if held < stable_for:
        return False, f"size {current_size} stable for {held:.1f}s / {stable_for:.0f}s"
    return True, f"size {current_size} stable for {held:.1f}s"


def _marker_present(path: Path, marker: str, tail_bytes: int = 65_536) -> tuple[bool, str]:
    """Return (found, reason) — does the last ~tail_bytes of file contain marker?

    We only scan the tail to avoid re-reading multi-MB subagent logs on
    every poll. 64 KB is enough to catch the closing tool_use of even
    verbose bob sessions.
    """
    if not marker:
        return True, "no marker configured"
    try:
        with path.open("rb") as f:
            size = path.stat().st_size
            start = max(0, size - tail_bytes)
            f.seek(start)
            chunk = f.read()
    except OSError as e:
        return False, f"read failed: {e}"
    if marker.encode("utf-8", errors="replace") in chunk:
        return True, f"marker {marker!r} present in tail"
    return False, f"marker {marker!r} not in tail ({len(chunk)} bytes scanned)"


def wait_for(
    paths: list[Path],
    timeout: float,
    poll: float,
    updated_after: float | None,
    min_size: int,
    quiet: bool,
    stable_for: float = 0.0,
    completion_marker: str = "",
) -> int:
    start = time.monotonic()
    deadline = start + timeout

    # Track which files have transitioned to ready so we emit an event
    # exactly once per file (not on every poll). "Ready" here means all
    # active conditions (existence, size, mtime, stability, marker) hold.
    was_ready: dict[str, bool] = {str(p): False for p in paths}

    extra = []
    if updated_after is not None:
        extra.append(f"updated_after={updated_after:.0f}")
    if stable_for > 0:
        extra.append(f"stable_for={stable_for:.0f}s")
    if completion_marker:
        extra.append(f"marker={completion_marker!r}")
    extra_str = (" " + " ".join(extra)) if extra else ""
    _emit(
        f"[wait_for] start "
        f"timeout={timeout:.0f}s "
        f"poll={poll:.1f}s "
        f"files={len(paths)}"
        f"{extra_str}"
    )

    while True:
        now = time.monotonic()
        elapsed = now - start

        # Assess all paths this tick. A path counts as ready when the
        # base conditions (existence, size, mtime) hold AND at least one
        # completion signal is present:
        #   - the completion marker is in the file's tail, OR
        #   - the file's size has been stable for `stable_for` seconds.
        # The marker is the PRIMARY signal (it's a positive end-of-session
        # event from the harness itself); stable-for is a FALLBACK for
        # sessions that were killed before emitting the marker, or for
        # harnesses that don't have one. Either being satisfied is enough.
        all_ready = True
        for p in paths:
            base_ok, base_reason = _file_status(p, min_size, updated_after)
            if not base_ok:
                all_ready = False
                continue

            # Evaluate both completion signals every tick so we can track
            # progress reasons for the timeout report even when the
            # OTHER signal ends up being the one that trips.
            stab_ok, stab_reason = _stability_status(p, stable_for, now)
            mark_ok, mark_reason = _marker_present(p, completion_marker)

            marker_enabled = bool(completion_marker)
            stable_enabled = stable_for > 0
            # If both signals are disabled, base conditions alone declare
            # ready — that's the original "file exists" semantic.
            if not marker_enabled and not stable_enabled:
                completion_ok = True
                completion_reason = "no completion signal configured"
            else:
                completion_ok = (marker_enabled and mark_ok) or (stable_enabled and stab_ok)
                # Build a reason describing WHICH signal fired (or why none did).
                if completion_ok:
                    if marker_enabled and mark_ok:
                        completion_reason = f"marker fired: {mark_reason}"
                    else:
                        completion_reason = f"stable-for fired: {stab_reason}"
                else:
                    parts = []
                    if marker_enabled:
                        parts.append(f"marker pending: {mark_reason}")
                    if stable_enabled:
                        parts.append(f"stable-for pending: {stab_reason}")
                    completion_reason = " | ".join(parts)

            if not completion_ok:
                all_ready = False
                # Reset ready state if we previously marked ready and the
                # file has grown again (subagent kept writing after we
                # thought we were done — rare, but harmless to re-arm).
                if was_ready[str(p)]:
                    _emit(
                        f"[wait_for] NOT-READY   t={elapsed:.0f}s  {p}  "
                        f"{completion_reason}"
                    )
                    was_ready[str(p)] = False
                continue

            if not was_ready[str(p)]:
                # State transition — emit once.
                _emit(
                    f"[wait_for] READY  t={elapsed:.0f}s  {p}  "
                    f"{base_reason}  ({completion_reason})"
                )
                was_ready[str(p)] = True

        if all_ready:
            _emit(
                f"[wait_for] done   t={elapsed:.0f}s  "
                f"all {len(paths)} file{'s' if len(paths) != 1 else ''} ready"
            )
            return 0

        if now >= deadline:
            _emit(f"[wait_for] TIMEOUT t={elapsed:.0f}s")
            for p in paths:
                if not was_ready[str(p)]:
                    reasons: list[str] = []
                    base_ok, base_reason = _file_status(p, min_size, updated_after)
                    reasons.append(base_reason)
                    if base_ok and stable_for > 0:
                        _, stab_reason = _stability_status(p, stable_for, time.monotonic())
                        reasons.append(stab_reason)
                    if base_ok and completion_marker:
                        _, mark_reason = _marker_present(p, completion_marker)
                        reasons.append(mark_reason)
                    _emit(f"[wait_for]   pending: {p}  " + " | ".join(reasons))
            return 1

        if not quiet:
            # Heartbeat every second regardless of poll interval, so the
            # surrounding harness sees continuous output. When poll > 1s
            # we still tick once per second but only check files every
            # `poll` seconds (checks are cheap; skipping is only for
            # aesthetics of the output).
            remaining = deadline - now
            n_pending = sum(1 for r in was_ready.values() if not r)
            _emit(
                f"[wait_for] hb     t={elapsed:.0f}s  "
                f"remaining={remaining:.0f}s  pending={n_pending}/{len(paths)}"
            )

        # Sleep the smaller of `poll` and 1s so heartbeats stay per-second.
        time.sleep(min(poll, 1.0))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="Files to wait for.")
    parser.add_argument(
        "--timeout",
        type=float,
        default=150.0,
        help=(
            "Maximum seconds to wait (default: 150). Chosen to fit inside "
            "bob's 180 s execute_command cap with 30 s of margin for "
            "Python startup and flushes. Non-bob harnesses can pass a "
            "larger value; wait_for.py's behaviour is otherwise unchanged."
        ),
    )
    parser.add_argument(
        "--attempt",
        type=int,
        default=None,
        help=(
            "Optional attempt counter, purely for defeating bob's "
            "loop-detector: it is logged and echoed but not otherwise "
            "acted upon. Increment across successive invocations so each "
            "tool call has unique args (bob's detector hashes name + "
            "args JSON and fires at 5 identical hashes in a row)."
        ),
    )
    parser.add_argument(
        "--poll",
        type=float,
        default=2.0,
        help="File-check interval in seconds (default: 2). Heartbeats still emit per second.",
    )
    parser.add_argument(
        "--updated-after",
        type=str,
        default=None,
        help=(
            "Require each file's mtime to be strictly after this reference "
            "point. Accepts ISO-8601, Unix epoch, or the literal 'now'. "
            "Useful when a file already exists but the caller wants to "
            "wait for it to be REGENERATED."
        ),
    )
    parser.add_argument(
        "--min-size",
        type=int,
        default=1,
        help="Minimum acceptable file size in bytes (default: 1).",
    )
    parser.add_argument(
        "--stable-for",
        type=float,
        default=_stable_for_default_for_harness(180.0),
        help=(
            "Fallback completion signal: declare the file ready if its "
            "size has been unchanged for this many consecutive seconds. "
            "Used as a safety net when the harness's own end-of-session "
            "marker never appears (killed session, harness with no "
            "marker like opencode). Default 180 seconds (3 minutes) — "
            "shortened to 15 seconds automatically under "
            "AGENT_HARNESS=opencode, whose stream has no reliable "
            "session-end marker and where the file stops growing "
            "immediately after the opencode process exits. Set to 0 "
            "to disable."
        ),
    )
    parser.add_argument(
        "--completion-marker",
        type=str,
        default=None,  # sentinel: None means "auto-detect from AGENT_HARNESS"
        help=(
            "Primary completion signal: consider the file ready once its "
            "tail contains this substring. Default: auto-selected from "
            "the AGENT_HARNESS env var — bob and claude both emit "
            '{\"type\":\"result\"} as their final stream-json event, '
            "so that string is used automatically. Pass an empty string "
            "to disable auto-detection and fall back to --stable-for only."
        ),
    )
    parser.add_argument(
        "--exists-is-enough",
        action="store_true",
        help=(
            "Skip the marker/stability check and return as soon as the "
            "file simply exists (with min-size / updated-after still "
            "honored). Use for completion-signal files like `.done` "
            "markers written atomically by a detached pipeline — the "
            "file's presence is the whole point, further checks would "
            "just add unnecessary delay."
        ),
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help=(
            "Suppress heartbeat lines. State-transition lines (READY / "
            "TIMEOUT / done / start) still print."
        ),
    )
    parser.add_argument(
        "--legacy-timeout-exit",
        action="store_true",
        help=(
            "Return exit code 1 on timeout instead of the new default 3 "
            "(POLL_INCOMPLETE). Preserved so existing wrappers that "
            "explicitly branch on exit 1 (e.g. an external orchestrator's "
            "wait for `.catalog.done`) don't change semantics until they "
            "are updated. New bob-facing callers should NOT set this; "
            "they benefit from the 1 / 3 split because 1 stays available "
            "for real failures once the semantics are separated."
        ),
    )
    args = parser.parse_args()

    if args.attempt is not None:
        _emit(f"[wait_for] attempt={args.attempt}")

    if args.timeout <= 0 or args.poll <= 0:
        _emit("[wait_for] ERROR --timeout and --poll must be positive")
        return 2
    if args.stable_for < 0:
        _emit("[wait_for] ERROR --stable-for must be non-negative")
        return 2

    updated_after: float | None = None
    if args.updated_after is not None:
        try:
            updated_after = _parse_timestamp(args.updated_after)
        except argparse.ArgumentTypeError as e:
            _emit(f"[wait_for] ERROR {e}")
            return 2

    # Resolve completion marker: None sentinel means "auto-detect from
    # AGENT_HARNESS"; explicit "" (empty string) means "user asked for
    # marker-less mode"; any other string is used verbatim.
    if args.completion_marker is None:
        completion_marker = _default_completion_marker()
        if completion_marker:
            _emit(
                f"[wait_for] auto-selected completion marker for "
                f"AGENT_HARNESS={os.environ.get('AGENT_HARNESS','')!r}: "
                f"{completion_marker!r}"
            )
    else:
        completion_marker = args.completion_marker

    # --exists-is-enough disables the marker and stability checks —
    # the file's mere existence (with min-size / updated-after still
    # applied) is the completion signal. Used for .done marker files
    # written by --detach mode.
    stable_for = args.stable_for
    if args.exists_is_enough:
        stable_for = 0.0
        completion_marker = ""
        _emit("[wait_for] --exists-is-enough: file existence alone signals ready")

    rc = wait_for(
        paths=args.paths,
        timeout=args.timeout,
        poll=args.poll,
        updated_after=updated_after,
        min_size=args.min_size,
        quiet=args.quiet,
        stable_for=stable_for,
        completion_marker=completion_marker,
    )
    # Split the historical "timeout means failed" (exit 1) into a new
    # POLL_INCOMPLETE code (exit 3) that only means "the timeout window
    # closed with the file still pending — poll again". This lets bob
    # main agents distinguish between "wait_for.py hit a real error"
    # (still exit 1 in the future) and "we're just inside the 180 s
    # tool-call cap and need another attempt". `--legacy-timeout-exit`
    # preserves the old return code for callers that already branch on
    # exit 1 as "not ready".
    if rc == 1 and not args.legacy_timeout_exit:
        return 3
    return rc


if __name__ == "__main__":
    sys.exit(main())
