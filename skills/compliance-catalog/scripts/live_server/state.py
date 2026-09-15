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

"""Read-only introspection of a compliance-catalog output directory.

`state.snapshot(output_dir)` returns a JSON-friendly dict describing where
in the Phase 0-6 pipeline the run currently sits. The live server calls
this every second and streams the deltas to the browser.

The snapshotter is deliberately filesystem-driven: the agent is the source
of truth for the pipeline, and the only reliable observations from the
outside are the files it writes. We NEVER call into the agent's process.

Phase decoding matches SKILL.md:

    Phase 1 — analyze_pdf.py runs
    Phase 2 — generate.py authored + first extraction
    Phase 3 — validate.py authored
    Phase 4 — iterative fix loop (`_fix_agent_N.jsonl`, `_validate_N.txt`)
    Phase 5 — exclusion pass (usually rolled into Phase 4)
    Phase 6 — report.md authored, `.catalog.done` written
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def snapshot(output_dir: str | Path) -> dict:
    """Return a snapshot of the current pipeline state.

    Shape:
        {
          "output_dir": "...",
          "phases": [
            {"id": 1, "name": "PDF analysis", "status": "done"},
            ...
          ],
          "current_phase": 4,
          "controls": {"total": 74, "groups": 7},   # None if catalog.json missing
          "validate": {
            "iterations": [
              {"i": 1, "errors": 23, "timestamp": "..."},
              {"i": 2, "errors": 21, "timestamp": "..."},
            ],
            "current_errors": 21,
          },
          "recent_log": ["line", "line", ...],       # last 20 lines from agent.jsonl
          "done": false,
          "done_exit_code": null,
          "report_md": "...",                         # full text once phase 6 completes
        }
    """
    d = Path(output_dir)
    if not d.is_dir():
        return {
            "output_dir": str(d),
            "error": f"output_dir does not exist: {d}",
            "phases": [],
            "done": False,
        }
    phases = _phase_states(d)
    controls = _catalog_summary(d)
    validate = _validate_progress(d)
    log = _recent_agent_log(d)
    done_marker = d / ".catalog.done"
    marker_done, exit_code = _done_marker(done_marker)
    report_path = d / "report.md"
    # Two independent completion signals — the CLI wrapper's .catalog.done
    # marker (authoritative when present) OR report.md existing (which is
    # the last artefact the agent writes under plain opencode). Either
    # is enough for the UI to show the "Run complete" panel.
    done = marker_done or report_path.is_file()
    report_md = None
    if done and report_path.is_file():
        try:
            report_md = report_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            report_md = None
    current_phase = _current_phase(phases, done)
    return {
        "output_dir": str(d),
        "phases": [asdict(p) for p in phases],
        "current_phase": current_phase,
        "controls": controls,
        "validate": validate,
        "recent_log": log,
        "done": done,
        "done_exit_code": exit_code,
        "report_md": report_md,
    }


# ---------------------------------------------------------------------------
# Phase decoding
# ---------------------------------------------------------------------------


@dataclass
class PhaseState:
    id: int
    name: str
    status: str            # "pending" | "running" | "done" | "error"
    detail: str | None = None


def _phase_states(d: Path) -> list[PhaseState]:
    """Decide each phase's status from filesystem markers.

    Completion signals, in order of trust:
      * ``.catalog.done`` marker — only the Downstream CLI wrapper writes
        this; treat as ground truth when present.
      * ``report.md`` exists — the agent finished Phase 6, so everything
        upstream must have completed too. This is the signal we key on
        under plain opencode where no wrapper is running.
      * Latest ``_validate_N.txt`` says PASSED — fix loop converged.
    """
    generate_py = d / "generate.py"
    validate_py = d / "validate.py"
    catalog_json = d / "catalog.json"
    report_md = d / "report.md"
    done_marker = d / ".catalog.done"

    # Global "run finished" signal: prefer the explicit marker, fall back
    # to report.md existence (opencode path).
    run_finished = done_marker.is_file() or report_md.is_file()

    # merged.txt / pages/ mark Phase 1 completion.
    phase1_done = (d / "merged.txt").is_file() or (d / "pages").is_dir()

    fix_iterations = _fix_iteration_count(d)
    validate_iterations = _validate_iteration_count(d)
    latest_errors = None
    validate_prog = _validate_progress(d)
    if validate_prog["iterations"]:
        latest_errors = validate_prog["iterations"][-1]["errors"]

    p1 = PhaseState(1, "PDF analysis", "done" if phase1_done else "running")

    # Phase 2 covers BOTH generate.py authoring AND the two extraction
    # passes (initial extraction → excluded_units.json → re-extraction
    # with the exclusion filter applied). We report "done" as soon as
    # catalog.json exists; if excluded_units.json is also present we
    # note the number of excluded units in the detail line so the
    # operator can see the two-pass mechanism landed cleanly.
    p2_done = generate_py.is_file() and catalog_json.is_file()
    p2_running = generate_py.is_file() and not catalog_json.is_file()
    p2_status = "done" if p2_done else "running" if p2_running else "pending"
    p2_detail = None
    if catalog_json.is_file():
        summary = _catalog_summary(d)
        parts = []
        if summary:
            parts.append(f"{summary['total']} controls, {summary['groups']} groups")
        excluded_n = _excluded_unit_count(d)
        if excluded_n is not None:
            parts.append(f"{excluded_n} excluded")
        p2_detail = " · ".join(parts) if parts else None
    p2 = PhaseState(2, "Author generate.py", p2_status, p2_detail)

    p3_done = validate_py.is_file()
    p3 = PhaseState(3, "Author validate.py", "done" if p3_done else "pending")

    # Phase 4 is the fix loop. It's done once ANY of these hold:
    #   * the run-finished signal fired (report.md or .catalog.done)
    #   * the latest _validate_*.txt reports zero errors (loop converged)
    # Otherwise: running when at least one iteration exists, pending
    # before the first one.
    p4_status = "pending"
    p4_detail = None
    if fix_iterations > 0 or validate_iterations > 0:
        if run_finished or latest_errors == 0:
            p4_status = "done"
        else:
            p4_status = "running"
        p4_detail = f"iteration {max(fix_iterations, validate_iterations)}"
    p4 = PhaseState(4, "Validate / fix loop", p4_status, p4_detail)

    # Phase 5 — Final Verification: the late-write drift check that
    # snapshots hashes of catalog.json / generate.py / validate.py /
    # validate_config.py after Phase 4 passes and re-checks them before
    # Phase 6. The agent writes _phase5_hashes.txt when it takes the
    # snapshot and _phase5_hashes_final.txt after confirming no drift.
    phase5_snapshot = d / "_phase5_hashes.txt"
    phase5_final = d / "_phase5_hashes_final.txt"
    if phase5_final.is_file():
        p5_status = "done"
    elif phase5_snapshot.is_file():
        p5_status = "running"
    elif run_finished:
        # Some runs skip surfacing the phase-5 files (e.g. Downstream
        # wrapper), but if the pipeline finished at all Phase 5 must
        # have passed to get there.
        p5_status = "done"
    else:
        p5_status = "pending"
    p5 = PhaseState(5, "Final verification", p5_status)

    # Phase 6 is "done" whenever report.md exists — writing it is the
    # last thing the agent does before printing PHASE_2_DONE / exiting.
    p6_status = "done" if report_md.is_file() else "pending"
    p6 = PhaseState(6, "Write report.md", p6_status)

    return [p1, p2, p3, p4, p5, p6]


def _current_phase(phases: list[PhaseState], done: bool) -> int:
    if done:
        return 6
    running = [p for p in phases if p.status == "running"]
    if running:
        return running[0].id
    # No phase is "running" — pick the first pending one.
    for p in phases:
        if p.status == "pending":
            return p.id
    return 6


# ---------------------------------------------------------------------------
# Catalog / validate progress
# ---------------------------------------------------------------------------


def _catalog_summary(d: Path) -> dict | None:
    p = d / "catalog.json"
    if not p.is_file():
        return None
    try:
        cat = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    root = cat.get("catalog", cat)
    groups = root.get("groups") or []
    total = sum(len(g.get("controls") or []) for g in groups)
    return {"total": total, "groups": len(groups)}


def _excluded_unit_count(d: Path) -> int | None:
    """Return how many units were excluded, or None if the file is missing.

    ``excluded_units.json`` is written by the Phase 2 subagent between
    the first and second ``generate.py`` runs; each key is a control id
    that was flagged as non-requirement (definitions, administrative,
    etc.). We count keys — the value shape (``{"reason": "..."}``) is
    metadata for reviewers, not something the live view surfaces.
    """
    p = d / "excluded_units.json"
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(data, dict):
        return len(data)
    if isinstance(data, list):
        return len(data)
    return None


# The validator prints its outcome in one of these three shapes.
# We check them in order and pick the first match.
_VALIDATE_ERR_RE_HEADER = re.compile(r"^ERRORS\s*\((\d+)\)\s*:", re.MULTILINE)
_VALIDATE_ERR_RE_FAILED = re.compile(r"(\d+)\s+errors?\s+must be fixed", re.IGNORECASE)
_VALIDATE_PASSED_RE     = re.compile(r"VALIDATION\s+PASSED", re.IGNORECASE)


def _validate_progress(d: Path) -> dict:
    """Parse `_validate_N.txt` in order to build a per-iteration error series.

    The validator's actual output shape (as of skill v1.x):
        `ERRORS (N):`                        — always present when N > 0
        `❌ VALIDATION FAILED`               — accompanies non-zero errors
        `N errors must be fixed`             — trailing summary line
        `✅ VALIDATION PASSED (with warnings)` — the success case, zero errors

    Files with no matching header AND no PASSED line are recorded with
    errors=None so the ordinal in the UI stays honest — better than
    guessing.
    """
    files = sorted(d.glob("_validate_*.txt"), key=_iter_key)
    iterations: list[dict[str, Any]] = []
    for f in files:
        m = re.search(r"_validate_(\d+)\.txt$", f.name)
        if not m:
            continue
        i = int(m.group(1))
        try:
            body = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            body = ""
        errors: int | None
        header_match = _VALIDATE_ERR_RE_HEADER.search(body)
        failed_match = _VALIDATE_ERR_RE_FAILED.search(body)
        if header_match:
            errors = int(header_match.group(1))
        elif failed_match:
            errors = int(failed_match.group(1))
        elif _VALIDATE_PASSED_RE.search(body):
            errors = 0
        else:
            errors = None
        iterations.append({
            "i": i,
            "errors": errors,
            "modified_at": f.stat().st_mtime,
        })
    current = iterations[-1]["errors"] if iterations else None
    return {"iterations": iterations, "current_errors": current}


def _fix_iteration_count(d: Path) -> int:
    files = list(d.glob("_fix_agent_*.jsonl"))
    n = 0
    for f in files:
        m = re.search(r"_fix_agent_(\d+)\.jsonl$", f.name)
        if m:
            n = max(n, int(m.group(1)))
    return n


def _validate_iteration_count(d: Path) -> int:
    n = 0
    for f in d.glob("_validate_*.txt"):
        m = re.search(r"_validate_(\d+)\.txt$", f.name)
        if m:
            n = max(n, int(m.group(1)))
    return n


def _iter_key(p: Path) -> int:
    m = re.search(r"_(\d+)\.", p.name)
    return int(m.group(1)) if m else 0


# ---------------------------------------------------------------------------
# Agent log tail
# ---------------------------------------------------------------------------


def _recent_agent_log(d: Path, limit: int = 200) -> list[dict]:
    """Return a compact tail of the agent's own log for the UI.

    Each entry is ``{"kind": "tool" | "output" | "note" | "phase" | "raw",
    "text": str}`` so the SPA can colour lines by type. The intent is a
    real transcript — interleaved agent narration ("what I'm about to
    do") with the tools it invokes ("bash: python3 …") — not just tool
    calls in isolation.

    Sources, tried in order:
      1. ``opencode.db`` — the authoritative store when running under
         opencode. Yields TEXT parts (assistant narration) + TOOL parts
         (with commands and, when the agent bothered, a ``description``).
      2. ``$OUT/cli_output.log`` — the human-facing tail written by the
         Downstream CLI wrapper.
      3. ``opencode.log`` grep — coarse fallback if opencode.db access
         fails (permissions, alternative install location).
      4. Newest ``$OUT/agent.*.jsonl`` — raw agent trace.

    Returning early on the first source that has any lines avoids
    stitching two different provenances together in one view.
    """
    opencode_db_events = _opencode_db_events(d, limit=limit)
    if opencode_db_events:
        return opencode_db_events

    cli = d / "cli_output.log"
    if cli.is_file():
        try:
            lines = cli.read_text(encoding="utf-8", errors="replace").splitlines()
            if lines:
                tail = lines[-limit:]
                return [_classify_cli_line(l) for l in tail]
        except OSError:
            pass

    opencode_log_events = _opencode_log_events(d, limit=limit)
    if opencode_log_events:
        return opencode_log_events

    # Best-effort JSONL peek: newest file, last N lines, only summary fields.
    jsonls = sorted(d.glob("agent.*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not jsonls:
        return []
    try:
        lines = jsonls[0].read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out: list[dict] = []
    for raw in lines[-limit * 2:]:
        try:
            obj = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        summary = _summarise_event(obj)
        if summary:
            out.append(_classify_cli_line(summary))
    return out[-limit:]


# ---------------------------------------------------------------------------
# opencode.db tap (best-quality source)
# ---------------------------------------------------------------------------


_OPENCODE_DB_PATH = Path.home() / ".local" / "share" / "opencode" / "opencode.db"


def _opencode_db_events(output_dir: Path, *, limit: int) -> list[dict]:
    """Read a real transcript from opencode's message/part store.

    Strategy:
      1. Find the most recently active session that references our
         output_dir anywhere in its parts (path.cwd or a tool input).
      2. Fetch that session's newest ``limit`` non-boilerplate parts.
      3. Interleave TEXT (narration) and TOOL (invocation + description
         + command) into a single chronological list.

    If the sqlite file isn't there, or the session doesn't touch our
    output_dir, or any parse step fails, return [] and let the caller
    fall back to the log-file tap.
    """
    import sqlite3
    if not _OPENCODE_DB_PATH.is_file():
        return []

    # Compute both path variants (macOS /tmp ↔ /private/tmp).
    needles = _output_dir_variants(output_dir)

    # opencode locks the WAL — open read-only with URI mode so our
    # polling doesn't fight the running session.
    uri = f"file:{_OPENCODE_DB_PATH}?mode=ro&immutable=0"
    try:
        con = sqlite3.connect(uri, uri=True, timeout=0.5)
    except sqlite3.OperationalError:
        return []
    con.row_factory = sqlite3.Row

    try:
        session_id = _pick_session(con, needles)
        if not session_id:
            return []

        # Grab the newest window of parts on that session. 4× limit gives
        # us headroom to drop step-start / step-finish boilerplate.
        rows = con.execute(
            """
            SELECT p.time_created, p.data
            FROM part p JOIN message m ON p.message_id = m.id
            WHERE m.session_id = ?
            ORDER BY p.time_created DESC
            LIMIT ?
            """,
            (session_id, limit * 4),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        con.close()

    events: list[dict] = []
    for r in rows:
        try:
            data = json.loads(r["data"])
        except (TypeError, json.JSONDecodeError):
            continue
        ev = _opencode_part_to_event(data)
        if ev:
            events.append(ev)

    events.reverse()   # oldest first, matches the log-tail convention
    return events[-limit:]


def _pick_session(con, needles: set[str]) -> str | None:
    """Pick the parent (build-mode) opencode session that owns our run.

    When the catalog pipeline delegates Phase 2 / 3 / 4 / 6 to subagents
    via ``task``, each subagent gets its own opencode session with
    ``mode=general``. Those refresh most recently, so a naive "newest
    touching this output_dir" pick jumps to the subagent's view and
    hides the parent's narration.

    We fix that by preferring sessions whose newest assistant message
    reports ``mode=build`` (the parent TUI). Subagent (``general``)
    sessions are used only as a fallback for the rare case where the
    pipeline was kicked off via ``opencode run "…"`` and there is no
    interactive build session at all.

    No time-since-last-message filter — narration should stay visible
    in the sidebar even after the run completes so the operator can
    scroll through what happened.
    """
    rows = con.execute(
        """
        SELECT session_id, MAX(time_created) AS t
        FROM message
        GROUP BY session_id
        ORDER BY t DESC
        LIMIT 40
        """,
    ).fetchall()
    fallback: str | None = None
    for row in rows:
        session_id = row["session_id"]
        found = con.execute(
            """
            SELECT 1 FROM part p JOIN message m ON p.message_id = m.id
            WHERE m.session_id = ?
            AND (
                {clauses}
            )
            LIMIT 1
            """.format(clauses=" OR ".join(["p.data LIKE ?"] * len(needles))),
            (session_id, *[f"%{n}%" for n in needles]),
        ).fetchone()
        if not found:
            continue
        mode = _session_mode(con, session_id)
        if mode == "build":
            return session_id
        if fallback is None:
            fallback = session_id
    return fallback


def _session_mode(con, session_id: str) -> str | None:
    """Return the ``mode`` field ("build" / "general" / …) of the most
    recent assistant message in ``session_id``, or None if unavailable.
    """
    row = con.execute(
        """
        SELECT data FROM message
        WHERE session_id = ?
        ORDER BY time_created DESC
        LIMIT 1
        """,
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    try:
        data = json.loads(row["data"])
    except (TypeError, json.JSONDecodeError):
        return None
    return data.get("mode")


def _opencode_part_to_event(data: dict) -> dict | None:
    """Turn one opencode ``part.data`` payload into a UI event.

    Filters out boilerplate types (``step-start`` / ``step-finish``) and
    normalises TEXT vs TOOL into the same ``{kind, text, html?}`` shape
    as the rest of the log sources. TEXT parts carry a rendered ``html``
    field so the SPA can drop it into the panel without doing markdown
    parsing client-side.
    """
    t = data.get("type")
    if t == "text":
        text = (data.get("text") or "").strip()
        if not text:
            return None
        return {"kind": "note", "text": text, "html": _render_note_html(text)}
    if t == "tool":
        tool = data.get("tool") or "tool"
        state = data.get("state") or {}
        inp = state.get("input") or {}
        desc = (inp.get("description") or "").strip()
        # Pick the most useful "command" field per tool type.
        cmd = (
            inp.get("command")
            or inp.get("filePath") or inp.get("file_path") or inp.get("path")
            or inp.get("pattern") or ""
        )
        cmd = str(cmd)
        head = _tool_glyph(tool) + " " + tool
        if desc:
            head += " · " + desc
        line = head
        if cmd:
            line += "\n" + _indent(_truncate(cmd, 400), "    ")
        return {"kind": "tool", "text": line}
    return None


# ---------------------------------------------------------------------------
# Markdown → HTML rendering (narration only)
# ---------------------------------------------------------------------------
#
# Deliberately small: only the constructs opencode's assistant actually
# emits in short narration blocks. Doing this server-side gives us:
#   * a single source of escaping (html.escape before injecting into
#     any tag), which is easier to audit than jamming a JS markdown
#     parser into the SPA;
#   * a stable {kind, text, html} shape so future sources can either
#     opt in (fill html) or stay text-only (SPA renders text plain).
#
# Not supported (intentionally): tables, images, HTML passthrough,
# fenced code blocks with language tags, autolinks without <>. If the
# agent ever writes those, they'll fall back to reading fine as plain
# text — annoying, not broken.


_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_MD_BULLET_RE = re.compile(r"^\s*[-*]\s+(.+?)\s*$")
_MD_CODE_INLINE_RE = re.compile(r"`([^`]+)`")
_MD_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_MD_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def _render_note_html(text: str) -> str:
    """Render a narration block into safe HTML.

    Pipeline: split into lines → group consecutive bullets into ``<ul>`` →
    apply inline markdown (code, bold, italic, link) per line. Everything
    else stays as ``<div>``-per-line so vertical rhythm is preserved.
    """
    lines = text.splitlines()
    out: list[str] = []
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for raw_line in lines:
        line = raw_line.rstrip()
        if not line.strip():
            close_list()
            out.append('<div class="note-blank"></div>')
            continue

        # Bullet list line?
        m = _MD_BULLET_RE.match(line)
        if m:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_render_inline(m.group(1))}</li>")
            continue
        else:
            close_list()

        # Heading?
        m = _MD_HEADING_RE.match(line)
        if m:
            level = min(len(m.group(1)), 4)   # cap at h4 for sidebar sizing
            content = _render_inline(m.group(2))
            out.append(f"<h{level}>{content}</h{level}>")
            continue

        # Plain line — inline formatting only.
        out.append(f'<div class="note-line">{_render_inline(line)}</div>')

    close_list()
    return "".join(out)


def _render_inline(s: str) -> str:
    """Apply inline formatting (``code``, **bold**, *italic*, [link](url))
    to a fragment, escaping HTML metacharacters first.

    Order matters: escape → link → code → bold → italic. The link regex
    runs before code because a link's URL could contain characters that
    the code-span regex would otherwise chew up.
    """
    import html
    s = html.escape(s, quote=True)
    # Links: [text](url) — url is already HTML-escaped by the pass above
    # (& → &amp;, etc.), so we don't need a second escape here.
    def _link_sub(m: "re.Match[str]") -> str:
        text = m.group(1)
        href = m.group(2)
        return f'<a href="{href}" target="_blank" rel="noopener noreferrer">{text}</a>'
    s = _MD_LINK_RE.sub(_link_sub, s)
    s = _MD_CODE_INLINE_RE.sub(lambda m: f"<code>{m.group(1)}</code>", s)
    s = _MD_BOLD_RE.sub(lambda m: f"<strong>{m.group(1)}</strong>", s)
    s = _MD_ITALIC_RE.sub(lambda m: f"<em>{m.group(1)}</em>", s)
    return s


def _tool_glyph(tool: str) -> str:
    return {
        "bash": "🔧",
        "read": "📖",
        "write": "📝",
        "edit": "✏️",
        "grep": "🔎",
        "glob": "🔎",
        "list": "🗂",
        "webfetch": "🌐",
        "task": "🧭",
        "todowrite": "☑",
    }.get(tool, "·")


def _indent(s: str, prefix: str) -> str:
    return "\n".join(prefix + line for line in s.splitlines())


def _output_dir_variants(output_dir: Path) -> set[str]:
    """Return the set of path strings we'll match against opencode's records.

    macOS resolves /tmp to /private/tmp, and opencode logs the shape the
    caller passed in (usually the un-resolved form). Match both.
    """
    variants: set[str] = {str(output_dir)}
    try:
        variants.add(os.path.realpath(str(output_dir)))
    except OSError:
        pass
    try:
        variants.add(str(Path(output_dir).absolute()))
    except OSError:
        pass
    for n in list(variants):
        if n.startswith("/private/tmp/"):
            variants.add(n.replace("/private/tmp/", "/tmp/", 1))
        if n.startswith("/private/var/"):
            variants.add(n.replace("/private/var/", "/var/", 1))
    return variants


# ---------------------------------------------------------------------------
# opencode.log tap
# ---------------------------------------------------------------------------


_OPENCODE_LOG_PATH = Path.home() / ".local" / "share" / "opencode" / "log" / "opencode.log"

# Extract ``key=value`` or ``key="quoted value"`` from opencode's log lines.
_OC_KV_RE = re.compile(r'(\w[\w.]*)=("(?:[^"\\]|\\.)*"|\S+)')


def _opencode_log_events(output_dir: Path, *, limit: int) -> list[dict]:
    """Read the tail of opencode.log and turn it into UI events.

    We keep only lines that mention the current output_dir path (any tool
    call, permission decision, or file touch touching it), so a session
    that also runs unrelated work in the background doesn't leak into
    this view. Lines are classified into tool / output / note / phase
    kinds using the same colour scheme as the Downstream job transcript.
    """
    if not _OPENCODE_LOG_PATH.is_file():
        return []
    try:
        # Read a bounded suffix. opencode.log can be many MB; tailing
        # avoids paying for the whole file on every 1-second poll.
        size = _OPENCODE_LOG_PATH.stat().st_size
        offset = max(0, size - 512_000)   # ~500 KB tail
        with _OPENCODE_LOG_PATH.open("rb") as f:
            f.seek(offset)
            blob = f.read().decode("utf-8", errors="replace")
    except OSError:
        return []

    # On macOS ``/tmp`` resolves to ``/private/tmp``. opencode logs the
    # path the caller passed in (usually the un-resolved form), so we
    # match against both variants to catch either shape.
    needles = {str(output_dir)}
    try:
        needles.add(os.path.realpath(str(output_dir)))
    except OSError:
        pass
    try:
        needles.add(str(Path(output_dir).absolute()))
    except OSError:
        pass
    # Also add the /tmp/… variant when we resolved to /private/tmp/…
    for n in list(needles):
        if n.startswith("/private/tmp/"):
            needles.add(n.replace("/private/tmp/", "/tmp/", 1))
        if n.startswith("/private/var/"):
            needles.add(n.replace("/private/var/", "/var/", 1))

    out: list[dict] = []
    for raw in blob.splitlines():
        if not any(n in raw for n in needles):
            continue
        event = _parse_opencode_line(raw)
        if event:
            out.append(event)
    return out[-limit:]


def _parse_opencode_line(raw: str) -> dict | None:
    """Turn one opencode.log line into a UI event dict.

    We recognise a handful of shapes:
      * ``evaluated permission=bash pattern="..."`` → tool invocation
      * ``evaluated permission=read pattern="..."`` → tool invocation
      * ``evaluated permission=write pattern="..."`` → tool invocation
      * ``"touching file" file=...``                → file write
      * ``stream providerID=... modelID=...``       → LLM step (compact)
    Anything else that mentions the output dir is surfaced as raw so the
    reviewer can still see it.
    """
    kv = dict((k, _oc_unquote(v)) for k, v in _OC_KV_RE.findall(raw))
    perm = kv.get("permission")
    pattern = kv.get("pattern")
    action = kv.get("action.action")
    if action == "allow" and perm == "bash" and pattern:
        return {"kind": "tool", "text": f"🔧 bash · {_truncate(pattern, 200)}"}
    if action == "allow" and perm == "read" and pattern:
        return {"kind": "tool", "text": f"📖 read · {_truncate(pattern, 200)}"}
    if action == "allow" and perm == "write" and pattern:
        return {"kind": "tool", "text": f"📝 write · {_truncate(pattern, 200)}"}
    if action == "allow" and perm == "grep" and pattern:
        return {"kind": "tool", "text": f"🔎 grep · {_truncate(pattern, 200)}"}
    if "touching file" in raw:
        f = kv.get("file")
        if f:
            return {"kind": "output", "text": f"✓ wrote {f}"}
    if kv.get("message") == "stream" and kv.get("modelID"):
        return {"kind": "phase", "text": f"⋯ LLM step ({kv['modelID']})"}
    # Anything else that mentions the output dir: surface as raw so the
    # reviewer isn't left wondering what the agent was doing.
    return None


def _oc_unquote(s: str) -> str:
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return s


def _truncate(s: str, n: int) -> str:
    s = s.replace("\n", " ⏎ ")
    return s if len(s) <= n else s[: n - 1] + "…"


def _classify_cli_line(text: str) -> dict:
    """Bucket a single CLI-tail line into a colouring kind.

    Categories match the visual style of the Downstream job transcript:
      - tool   ← lines announcing a tool invocation (``🔧 …``)
      - output ← check marks / results (``✓ …``, ``✗ …``, EXIT: …)
      - note   ← the agent's own commentary (``💬 …`` / ``💭 …``)
      - phase  ← the wrapper's ``[catalog] …`` prefix without a tool marker,
                 covering "launching…" / "Phase N …" narration
      - raw    ← everything else (stack traces, blank lines, indented output)
    """
    stripped = text.strip()
    if "🔧" in text:
        kind = "tool"
    elif stripped.startswith(("✓", "✗", "✅", "❌")) or " EXIT:" in text or "elapsed" in text.lower():
        kind = "output"
    elif "💬" in text or "💭" in text:
        kind = "note"
    elif stripped.startswith("[catalog]") or stripped.startswith("[mapping]"):
        kind = "phase"
    else:
        kind = "raw"
    return {"kind": kind, "text": text}


def _summarise_event(obj: dict) -> str | None:
    # Try a handful of common shapes without over-committing to any harness.
    if obj.get("type") == "tool_use":
        name = obj.get("name") or "tool"
        return f"🔧 {name}"
    if obj.get("type") == "text":
        text = (obj.get("text") or "").strip()
        return text.splitlines()[0] if text else None
    msg = obj.get("message") or {}
    if isinstance(msg, dict):
        content = msg.get("content")
        if isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    text = (c.get("text") or "").strip()
                    if text:
                        return text.splitlines()[0]
    return None


# ---------------------------------------------------------------------------
# Done marker
# ---------------------------------------------------------------------------


def _done_marker(p: Path) -> tuple[bool, int | None]:
    if not p.is_file():
        return False, None
    try:
        body = p.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return True, None
    # `.catalog.done` conventionally contains an exit code string like "0"
    # or "0\n"; be tolerant of anything else.
    try:
        return True, int(body)
    except ValueError:
        return True, None
