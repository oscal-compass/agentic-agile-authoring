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

"""One-shot launcher the agent invokes at the start of a run.

Behavioural summary:

  1. Find a free port (default range 8850-8899).
  2. Start uvicorn in a background thread on that port.
  3. Open the user's default browser at the URL.
  4. Print the URL so the agent can also surface it in the CLI.
  5. Block until Ctrl-C, then exit.

Design constraint: the agent's harness (opencode / claude / bob) invokes
this script as a subprocess in the same terminal session. So we must NOT
daemonise — the agent needs the subprocess to stay attached until the
demo is over, and Ctrl-C in the shared terminal must tear us down.
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Allow `python3 skills/compliance-catalog/scripts/live_server/launcher.py`
# without the package import machinery kicking in — we import server.py
# directly by path if we're not being run as a package.
if __package__ in (None, ""):
    # Add the parent dir to sys.path and import as top-level.
    sys.path.insert(0, str(Path(__file__).parent))
    import server as _server_module        # type: ignore
else:
    from . import server as _server_module


def _find_free_port(start: int = 8850, end: int = 8899) -> int:
    """Scan a small port window and return the first one we can bind to.

    We prefer a range near 8850 (out of the way of most dev servers) so
    the URL the user sees is stable across runs on the same machine.
    """
    for p in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise RuntimeError(f"no free port between {start} and {end}")


_server_instance = None    # set at startup so shutdown hooks can flip should_exit


def _serve(app, host: str, port: int) -> None:
    import uvicorn
    global _server_instance
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    _server_instance = uvicorn.Server(config)
    _server_instance.run()


def _request_shutdown(reason: str) -> None:
    """Ask the uvicorn server thread to exit gracefully.

    Called from the parent-watchdog thread, the loitering-guard thread,
    and the /api/shutdown HTTP handler. All three share the same
    should_exit flag so we don't fight ourselves.
    """
    print(f"[live_server] shutting down ({reason})", flush=True)
    if _server_instance is not None:
        _server_instance.should_exit = True


def _parent_alive(pid: int) -> bool:
    """Return True while the process with ``pid`` is still around.

    ``os.kill(pid, 0)`` is a portable liveness probe: sending signal 0
    performs the permission / existence check without actually delivering
    anything. ESRCH means the process is gone; EPERM means it exists but
    isn't ours to signal (still alive → we treat it as alive).
    """
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


# ---------------------------------------------------------------------------
# Ancestor discovery
# ---------------------------------------------------------------------------
#
# Under opencode, our immediate parent is a short-lived `sh -c "…"` that
# opencode's Bash tool spawns to run the launcher's start command. That
# shell exits the moment its command returns, so `os.getppid()` would give
# us a PID that is already gone by the time our watchdog thread runs.
# Under claude / bob the story is similar — the harness spawns each tool
# invocation in a fresh process.
#
# The reliable ancestor to watch is the harness process itself. We find it
# by walking `ps -o ppid,args` up the chain until we hit a process whose
# command line contains one of a small set of well-known harness tokens.


# Basenames of processes we accept as "this is the agent harness". We
# check the leaf name of argv[0] (not a substring of the whole line) so
# a shell whose *arguments* mention e.g. `~/.claude/shell-snapshots/…`
# doesn't get mistaken for the harness itself.
_HARNESS_EXES = ("opencode", "claude", "bob-agent", "bob")

# How far up the PPID chain we're willing to walk before giving up.
_ANCESTOR_MAX_DEPTH = 12


def _proc_ppid_and_argv(pid: int) -> tuple[int, str] | None:
    """Return ``(ppid, argv)`` for ``pid`` using ``ps``, or None on error.

    We shell out to ``ps`` rather than reading /proc because macOS has
    no procfs. ``ps -o ppid=,args= -p <pid>`` prints exactly one line:
    the parent PID (left-padded) followed by the full argv. If ``pid``
    is gone or unreadable, ``ps`` exits non-zero and we return None.
    """
    import subprocess
    try:
        out = subprocess.check_output(
            ["ps", "-o", "ppid=,args=", "-p", str(pid)],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None
    if not out:
        return None
    # Split off the leading integer ppid; the rest is the argv line.
    parts = out.split(None, 1)
    try:
        ppid = int(parts[0])
    except (ValueError, IndexError):
        return None
    argv = parts[1] if len(parts) > 1 else ""
    return ppid, argv


def _find_agent_ancestor(start_pid: int) -> tuple[int, str] | None:
    """Walk up from ``start_pid`` and return the first ancestor whose
    argv basename is a known harness (opencode / claude / bob).

    Returns ``(pid, argv)`` on success, ``None`` if the walk reached
    launchd / init or ``_ANCESTOR_MAX_DEPTH`` without finding one.

    Robustness note: under opencode's Bash tool our immediate parent is
    a short-lived ``sh -c "…"`` that dies the moment the launcher goes
    into the background. That means ``ps`` on our PPID can already fail
    before we get to the first walk step. When that happens we fall
    back to ``os.getppid()`` (which macOS silently rewrites to 1 once
    the sh is gone — but 1 is not a harness, so we keep walking from
    there via the /proc-equivalent ``ps -A`` scan below).
    """
    # Step 1: figure out where to start walking from.
    #
    # The naive path — ps -o ppid -p <us> — fails if our parent shell
    # already exited. Fall back to os.getppid() in that case; on macOS
    # it will report launchd (PID 1) but that's fine because Step 2
    # below has a system-wide fallback that searches for a harness by
    # process listing rather than by chain walking.
    info = _proc_ppid_and_argv(start_pid)
    if info is not None:
        pid = info[0]
    else:
        pid = os.getppid()

    for _ in range(_ANCESTOR_MAX_DEPTH):
        step = _proc_ppid_and_argv(pid)
        if step is None or pid <= 1:
            # Chain broken (dead parent) or reached init — try the
            # system-wide fallback before giving up.
            return _system_wide_harness_scan()
        ppid, argv = step
        if _looks_like_harness(argv):
            return pid, argv
        pid = ppid
    return _system_wide_harness_scan()


def _system_wide_harness_scan() -> tuple[int, str] | None:
    """Best-effort: scan every process on the system for a harness.

    Used when the PPID chain broke before we could find a harness
    ancestor by walking. Not perfect — with multiple harness processes
    running side-by-side we can't tell which one launched us — so we
    prefer the youngest, on the assumption that if the operator just
    started an ``opencode`` session that produced *us*, its PID will
    be higher than any older one. Same argument as pgrep -n.
    """
    import subprocess
    try:
        out = subprocess.check_output(
            ["ps", "-A", "-o", "pid=,args="],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None
    matches: list[tuple[int, str]] = []
    for line in out.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        if _looks_like_harness(parts[1]):
            matches.append((pid, parts[1]))
    if not matches:
        return None
    matches.sort(key=lambda x: x[0], reverse=True)
    return matches[0]


def _looks_like_harness(argv: str) -> bool:
    """Return True iff argv's executable basename is a known harness.

    We look at the *leaf name of argv[0]* rather than a substring of the
    whole line so a shell whose arguments happen to mention e.g.
    ``~/.claude/shell-snapshots/…`` isn't mistaken for the harness. We
    accept both `opencode` (the CLI) and `opencode run …` here — the
    "TUI vs one-shot" distinction is orthogonal, made in SKILL.md by
    whether ``--die-with-parent`` is passed at all.
    """
    if not argv:
        return False
    first = argv.split(None, 1)[0]
    exe = os.path.basename(first)
    return exe in _HARNESS_EXES


def _first_argv_token(argv: str) -> str:
    """Take the leaf basename of the first argv token — used for a
    human-readable label in the "die-with-parent enabled" log line.

    "/Users/hiro/.opencode/bin/opencode --foo" → "opencode". Falls
    back to the raw argv when parsing fails so we never crash the
    startup path over a cosmetic label.
    """
    if not argv:
        return "?"
    first = argv.split(None, 1)[0]
    return os.path.basename(first) or first


def _watch_parent(initial_ppid: int, interval_seconds: float = 5.0) -> None:
    """Background thread: exit the server once the initial parent dies.

    We snapshot the parent PID at startup rather than re-reading it every
    tick because on macOS the PPID silently changes to 1 (launchd) once
    the real parent exits — os.kill(1, 0) always succeeds, so a naïve
    "is my current PPID alive?" check would loop forever.
    """
    while True:
        time.sleep(interval_seconds)
        if not _parent_alive(initial_ppid):
            _request_shutdown(f"parent PID {initial_ppid} exited")
            return


def _watch_max_lifetime(max_seconds: int) -> None:
    """Background thread: hard-cap the server's lifetime.

    Only used in persistent mode as a loitering guard so a forgotten
    ``opencode run`` never leaves a python process alive for days.
    """
    time.sleep(max_seconds)
    _request_shutdown(f"max lifetime {max_seconds}s reached")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True,
                        help="the catalog output dir the agent is writing to")
    parser.add_argument("--port", type=int, default=None,
                        help="explicit port; if omitted a free port in 8850-8899 is used")
    parser.add_argument("--no-browser", action="store_true",
                        help="do not auto-open the browser (useful when running via SSH / CI)")
    parser.add_argument("--die-with-parent", action="store_true",
                        help=("exit as soon as the parent process (recorded at startup) "
                              "goes away. Set this when the caller has a lifetime — an "
                              "interactive opencode / claude / bob TUI. Leave off for "
                              "`opencode run …`, where the caller exits the moment the "
                              "pipeline completes and we want to keep serving the result."))
    parser.add_argument("--parent-pid", type=int, default=None,
                        help=("PID to watch when --die-with-parent is set. Pass this from "
                              "the calling shell (e.g. `--parent-pid $$`) when the shell "
                              "will exit immediately after backgrounding us; otherwise "
                              "os.getppid() reports 1 (launchd on macOS) and the watchdog "
                              "never fires."))
    parser.add_argument("--max-lifetime", type=int, default=3 * 60 * 60,
                        help=("hard shutdown after N seconds regardless of parent state. "
                              "Loitering guard for persistent mode; defaults to 3 hours."))
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    port = args.port if args.port else _find_free_port()
    url = f"http://127.0.0.1:{port}/"

    # Determine the parent to watch. Priority:
    #   1. --parent-pid was passed explicitly → trust it.
    #   2. Walk our PPID chain looking for a harness process
    #      (opencode / claude / bob). Under opencode our immediate
    #      parent is a short-lived `sh -c "…"` that opencode spawns
    #      per tool call and reaps immediately, so `os.getppid()`
    #      would already point at a dead process by the time our
    #      watchdog runs — we need the harness itself, further up.
    #   3. Fall back to os.getppid(). Suits interactive Python
    #      invocations (`python3 launcher.py …` at a shell prompt).
    watchdog_label = "explicit"
    if args.parent_pid:
        initial_ppid = args.parent_pid
    else:
        ancestor = _find_agent_ancestor(os.getpid())
        if ancestor is not None:
            initial_ppid = ancestor[0]
            watchdog_label = f"agent ancestor ({_first_argv_token(ancestor[1])})"
        else:
            initial_ppid = os.getppid()
            watchdog_label = "immediate parent"

    app = _server_module.build_app(output_dir, on_shutdown=lambda: _request_shutdown("api /shutdown"))
    t = threading.Thread(target=_serve, args=(app, "127.0.0.1", port), daemon=True)
    t.start()

    if args.die_with_parent:
        if initial_ppid <= 1:
            # Watching launchd / init would never exit — refuse to start
            # a doomed watchdog and warn the caller so they know why.
            print(
                f"[live_server] warning: refusing to watch PID {initial_ppid} "
                "(launchd/init never exits). Skipping --die-with-parent; "
                "no harness ancestor was found on the PPID chain either.",
                flush=True,
            )
        else:
            threading.Thread(
                target=_watch_parent, args=(initial_ppid,), daemon=True,
            ).start()
            print(
                f"[live_server] die-with-parent enabled "
                f"(watching PID {initial_ppid} · {watchdog_label})",
                flush=True,
            )
    if args.max_lifetime and args.max_lifetime > 0:
        threading.Thread(
            target=_watch_max_lifetime, args=(args.max_lifetime,), daemon=True,
        ).start()

    # Small settling delay so the browser doesn't hit a not-yet-listening
    # port. 400ms is enough on macOS without noticeably slowing startup.
    time.sleep(0.4)
    print(f"[live_server] serving {output_dir} at {url}", flush=True)
    if not args.no_browser and os.environ.get("BROWSER") != "none":
        try:
            webbrowser.open(url)
        except Exception:
            pass    # non-fatal — the URL is still in the CLI

    # Block on the server thread. Ctrl-C reaches the main thread first
    # (KeyboardInterrupt) and lets us shut down cleanly.
    try:
        while t.is_alive():
            t.join(timeout=1.0)
    except KeyboardInterrupt:
        print("\n[live_server] stopped by Ctrl-C. output dir preserved:", output_dir)


if __name__ == "__main__":
    main()
