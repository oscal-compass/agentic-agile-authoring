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

"""Read-only introspection of a compliance-mapping output directory.

``state.snapshot(output_dir)`` returns a JSON-friendly dict describing
where in the Stage 1-8 pipeline the run currently sits. The live server
calls this every second and streams the deltas to the browser.

The snapshotter is deliberately filesystem-driven: the agent is the source
of truth for the pipeline, and the only reliable observations from the
outside are the files it writes. We NEVER call into the agent's process.

Stage decoding matches SKILL.md:

    Stage 1 — ingest_normalize.py → work/source_wc_gen0.json + target_wc_gen0.json
    Stage 3 — blocking.py         → work/candidates.json
    Stage 4a-c — judge_prep      → work/judge_tasks.json + judge_chunk_*_prompt.txt
    Stage 4d   — judge subagents → work/agent_verdicts_<N>.jsonl (one per chunk)
    Stage 4e-8 — run_judge_pipeline.sh → judgments.json, scored.json,
                 aggregated.json, mapping_collection.json, report.html

(Stage 2 is intentionally empty in the OSS variant — reserved for the
downstream Granularity Align stage.)
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, asdict
from pathlib import Path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def snapshot(output_dir: str | Path) -> dict:
    """Return a snapshot of the current pipeline state.

    Shape:
        {
          "output_dir": "...",
          "phases": [
            {"id": 1, "name": "Ingest / Normalize", "status": "done"},
            ...
          ],
          "current_phase": 4,
          "mapping": {
            "source_controls": 287,
            "target_controls": 177,
            "links": 69,
            "relationships": {"intersects-with": 67, ...},
            "chunks_total": 13,
            "chunks_done": 13,
          },
          "recent_log": [{"kind": "note"|"tool"|..., "text": "..."}, ...],
          "done": true,
          "done_exit_code": null,
          "report_html_path": ".../report.html",
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
    mapping = _mapping_summary(d)
    log = _recent_agent_log(d)

    mapping_collection = d / "mapping_collection.json"
    report_html = d / "report.html"
    # Completion signal — SKILL.md's own criterion: both artefacts non-empty.
    done = (
        mapping_collection.is_file() and mapping_collection.stat().st_size > 0
        and report_html.is_file() and report_html.stat().st_size > 0
    )

    current_phase = _current_phase(phases, done)
    return {
        "output_dir": str(d),
        "phases": [asdict(p) for p in phases],
        "current_phase": current_phase,
        "mapping": mapping,
        "recent_log": log,
        "done": done,
        "done_exit_code": None,   # mapping SKILL has no wrapper writing a done marker
        "report_html_path": str(report_html) if done else None,
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


# Stage numbers below match SKILL.md so the SPA and the mapping SKILL
# use the same vocabulary. Stage 2 is intentionally skipped in OSS (see
# the SKILL.md notes on Granularity Align).
def _phase_states(d: Path) -> list[PhaseState]:
    """Decide each Stage's status from filesystem markers.

    Completion signals, in order of trust:
      * mapping_collection.json + report.html both non-empty → the whole
        pipeline finished (SKILL.md's own completion criterion)
      * judge_pipeline.log exists and contains "exit 0" → Stage 4e-8 fine
      * per-Stage artefacts exist → that Stage completed
    """
    work = d / "work"

    # Convenience predicates
    def _f(p: Path) -> bool:
        return p.is_file() and p.stat().st_size > 0

    src_wc = work / "source_wc_gen0.json"
    tgt_wc = work / "target_wc_gen0.json"
    candidates = work / "candidates.json"
    judge_tasks = work / "judge_tasks.json"
    judgments = work / "judgments.json"
    scored = work / "scored.json"
    aggregated = work / "aggregated.json"
    mapping_json = d / "mapping_collection.json"
    report_html = d / "report.html"
    # `judge_pipeline.log` is written by run_judge_pipeline.sh but we don't
    # currently key any phase decision on it — mapping_collection.json +
    # report.html non-empty is a stronger completion signal (SKILL.md's own
    # criterion). Leaving the file discovery to the future in case we want
    # to surface exit codes.

    # Stage 4d chunk accounting
    chunk_prompts = sorted(work.glob("judge_chunk_*_prompt.txt")) if work.is_dir() else []
    verdicts = sorted(work.glob("agent_verdicts_*.jsonl")) if work.is_dir() else []
    total_chunks = len(chunk_prompts)
    done_verdicts = sum(
        1 for v in verdicts
        if re.search(r"agent_verdicts_(\d+)\.jsonl$", v.name) and v.stat().st_size > 0
    )

    # Stage 1
    s1_done = _f(src_wc) and _f(tgt_wc)
    p1 = PhaseState(1, "Ingest / Normalize", "done" if s1_done else "running",
                    None if not s1_done else _stage1_detail(src_wc, tgt_wc))

    # Stage 3 (Stage 2 reserved / skipped)
    s3_done = _f(candidates)
    s3_status = "done" if s3_done else ("running" if s1_done else "pending")
    p3 = PhaseState(3, "Blocking (top-K candidates)", s3_status)

    # Stage 4 prep (4a-c)
    s4prep_done = _f(judge_tasks) and total_chunks > 0
    s4prep_status = "done" if s4prep_done else ("running" if s3_done else "pending")
    p4prep = PhaseState(
        4, "Judge prep (chunk & prompt)", s4prep_status,
        None if not s4prep_done else f"{total_chunks} chunks",
    )

    # Stage 4d — fan-out to subagents.
    s4d_status = "pending"
    s4d_detail = None
    if total_chunks > 0:
        if done_verdicts >= total_chunks:
            s4d_status = "done"
        elif done_verdicts > 0:
            s4d_status = "running"
        else:
            s4d_status = "running" if s4prep_done else "pending"
        s4d_detail = f"{done_verdicts}/{total_chunks} chunks judged"
    p4d = PhaseState(5, "Judge fan-out (subagents)", s4d_status, s4d_detail)

    # Stage 4e-8 packaged (bash scripts/run_judge_pipeline.sh)
    # We surface Score/Aggregate/Emit as one row so the SPA doesn't get
    # too tall — matches the SKILL.md "packaged downstream script" framing.
    s5_done = (
        _f(judgments) and _f(scored) and _f(aggregated)
        and _f(mapping_json) and _f(report_html)
    )
    if s5_done:
        s5_status = "done"
    elif _f(judgments) or _f(scored) or _f(aggregated):
        s5_status = "running"
    elif s4d_status == "done":
        s5_status = "running"
    else:
        s5_status = "pending"
    p5 = PhaseState(
        6, "Score / Aggregate / Emit / Report", s5_status,
        None if not s5_done else "mapping_collection.json + report.html",
    )

    return [p1, p3, p4prep, p4d, p5]


def _stage1_detail(src_wc: Path, tgt_wc: Path) -> str | None:
    try:
        s = json.load(open(src_wc, encoding="utf-8"))
        t = json.load(open(tgt_wc, encoding="utf-8"))
        sn = len(s.get("controls") or []) if isinstance(s, dict) else len(s or [])
        tn = len(t.get("controls") or []) if isinstance(t, dict) else len(t or [])
        return f"source {sn} · target {tn}"
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def _current_phase(phases: list[PhaseState], done: bool) -> int:
    if done and phases:
        return phases[-1].id
    running = [p for p in phases if p.status == "running"]
    if running:
        return running[0].id
    for p in phases:
        if p.status == "pending":
            return p.id
    return phases[-1].id if phases else 1


# ---------------------------------------------------------------------------
# Mapping summary
# ---------------------------------------------------------------------------


def _mapping_summary(d: Path) -> dict:
    """Extract the numbers the KPI tiles display.

    Preferred source: ``mapping_collection.json`` once emitted; fallback to
    intermediate artefacts so the tiles show meaningful numbers during
    the run. Missing values are returned as ``None`` — the SPA renders
    them as ``—``.
    """
    work = d / "work"
    mapping_json = d / "mapping_collection.json"
    src_wc = work / "source_wc_gen0.json"
    tgt_wc = work / "target_wc_gen0.json"

    source_controls = _count_controls(src_wc)
    target_controls = _count_controls(tgt_wc)

    links = None
    relationships: dict[str, int] = {}
    if mapping_json.is_file() and mapping_json.stat().st_size > 0:
        try:
            data = json.load(open(mapping_json, encoding="utf-8"))
            mc = data.get("mapping-collection") or {}
            all_maps: list[dict] = []
            for m in mc.get("mappings") or []:
                all_maps.extend(m.get("maps") or [])
            links = len(all_maps)
            for m in all_maps:
                r = m.get("relationship") or "?"
                relationships[r] = relationships.get(r, 0) + 1
        except (OSError, json.JSONDecodeError):
            pass

    # Chunk progress lives in work/. We surface it as its own field
    # rather than shoehorning into "links" so the SPA can render it
    # as a distinct tile during Stage 4d.
    chunk_prompts = sorted(work.glob("judge_chunk_*_prompt.txt")) if work.is_dir() else []
    verdicts = sorted(work.glob("agent_verdicts_*.jsonl")) if work.is_dir() else []
    chunks_total = len(chunk_prompts)
    chunks_done = sum(1 for v in verdicts if v.stat().st_size > 0)

    return {
        "source_controls": source_controls,
        "target_controls": target_controls,
        "links": links,
        "relationships": relationships,
        "chunks_total": chunks_total,
        "chunks_done": chunks_done,
    }


def _count_controls(wc_path: Path) -> int | None:
    """Read a ``work/{source,target}_wc_gen0.json`` and count entries.

    The internal working-catalog format is an object with a ``controls``
    array (see internal_model.py). Fall back to counting a top-level
    array shape if the file is somehow flat.
    """
    if not wc_path.is_file():
        return None
    try:
        d = json.load(open(wc_path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(d, dict) and isinstance(d.get("controls"), list):
        return len(d["controls"])
    if isinstance(d, list):
        return len(d)
    return None


# ---------------------------------------------------------------------------
# Agent log tail  (identical to the catalog live_server module)
# ---------------------------------------------------------------------------
#
# We tap the same three sources in the same order:
#   1. opencode.db (best-quality: interleaved TEXT + TOOL parts)
#   2. cli_output.log inside the output dir (only present when a
#      wrapper is running the pipeline, e.g. Downstream tools/cli)
#   3. opencode.log grep as a coarse fallback
#   4. any agent.*.jsonl the user might have piped into the output dir
#
# Duplicating the code across the two skills is intentional — SKILLs are
# meant to stand alone as self-contained packages, so we accept the copy
# rather than force a shared library that would break the "each skill is
# a portable directory" invariant.


def _recent_agent_log(d: Path, limit: int = 200) -> list[dict]:
    """Return a compact tail of the agent's own log for the UI.

    Each entry is ``{"kind": ..., "text": ..., "html"?: ...}`` so the SPA
    can colour tool invocations differently from their output and render
    narrative markdown as safe HTML.
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


def _classify_cli_line(text: str) -> dict:
    stripped = text.strip()
    if "🔧" in text:
        kind = "tool"
    elif stripped.startswith(("✓", "✗", "✅", "❌")) or " EXIT:" in text or "elapsed" in text.lower():
        kind = "output"
    elif "💬" in text or "💭" in text:
        kind = "note"
    elif stripped.startswith("[mapping]") or stripped.startswith("[catalog]"):
        kind = "phase"
    else:
        kind = "raw"
    return {"kind": kind, "text": text}


# ---------------------------------------------------------------------------
# opencode.db tap (best-quality source)
# ---------------------------------------------------------------------------


_OPENCODE_DB_PATH = Path.home() / ".local" / "share" / "opencode" / "opencode.db"


def _opencode_db_events(output_dir: Path, *, limit: int) -> list[dict]:
    """Read a real transcript from opencode's message/part store."""
    import sqlite3
    if not _OPENCODE_DB_PATH.is_file():
        return []

    needles = _output_dir_variants(output_dir)

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

    events.reverse()
    return events[-limit:]


def _pick_session(con, needles: set[str]) -> str | None:
    """Pick the parent (build-mode) opencode session that owns our run.

    When Stage 4d fans out judge chunks via ``task`` subagents, each
    subagent gets its own opencode session with ``mode=general``. Those
    sessions are what refresh most recently, so a naive "newest
    touching this output_dir" pick jumps to a subagent view and hides
    the parent's narration.

    We fix that by preferring sessions whose newest assistant message
    reports ``mode=build`` (the parent TUI). Subagent (``general``)
    sessions are only used as a fallback when no build session touches
    the output_dir.

    No time-since-last-message filter — narration should stay visible in
    the sidebar even after the run has completed so the operator can
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
            # First (= most recent) build session that touches our output
            # dir. That's the parent TUI — the answer.
            return session_id
        if fallback is None:
            # Remember the newest non-build hit as a fallback in case
            # no build session ever mentions this output_dir. This
            # happens when the operator kicked off the pipeline directly
            # via `opencode run "…"` — there is no interactive build
            # session at all, only the one-shot run's session (which
            # itself has mode=general).
            fallback = session_id
    return fallback


def _session_mode(con, session_id: str) -> str | None:
    """Return the ``mode`` field ("build" / "general" / …) of the most
    recent assistant message in ``session_id``, or None if unavailable.

    We check the newest assistant message rather than the very first
    because opencode's session shape stays stable across a session's
    lifetime — a build session's assistant messages are always
    ``mode=build``, a subagent's are always ``mode=general``.
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
# Markdown → HTML rendering (narration only)
# ---------------------------------------------------------------------------


_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_MD_BULLET_RE = re.compile(r"^\s*[-*]\s+(.+?)\s*$")
_MD_CODE_INLINE_RE = re.compile(r"`([^`]+)`")
_MD_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_MD_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def _render_note_html(text: str) -> str:
    """Render a narration block into safe HTML."""
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

        m = _MD_BULLET_RE.match(line)
        if m:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_render_inline(m.group(1))}</li>")
            continue
        else:
            close_list()

        m = _MD_HEADING_RE.match(line)
        if m:
            level = min(len(m.group(1)), 4)
            content = _render_inline(m.group(2))
            out.append(f"<h{level}>{content}</h{level}>")
            continue

        out.append(f'<div class="note-line">{_render_inline(line)}</div>')

    close_list()
    return "".join(out)


def _render_inline(s: str) -> str:
    import html
    s = html.escape(s, quote=True)

    def _link_sub(m: "re.Match[str]") -> str:
        return f'<a href="{m.group(2)}" target="_blank" rel="noopener noreferrer">{m.group(1)}</a>'
    s = _MD_LINK_RE.sub(_link_sub, s)
    s = _MD_CODE_INLINE_RE.sub(lambda m: f"<code>{m.group(1)}</code>", s)
    s = _MD_BOLD_RE.sub(lambda m: f"<strong>{m.group(1)}</strong>", s)
    s = _MD_ITALIC_RE.sub(lambda m: f"<em>{m.group(1)}</em>", s)
    return s


# ---------------------------------------------------------------------------
# opencode.log grep (fallback)
# ---------------------------------------------------------------------------


_OPENCODE_LOG_PATH = Path.home() / ".local" / "share" / "opencode" / "log" / "opencode.log"
_OC_KV_RE = re.compile(r'(\w[\w.]*)=("(?:[^"\\]|\\.)*"|\S+)')


def _opencode_log_events(output_dir: Path, *, limit: int) -> list[dict]:
    if not _OPENCODE_LOG_PATH.is_file():
        return []
    try:
        size = _OPENCODE_LOG_PATH.stat().st_size
        offset = max(0, size - 512_000)
        with _OPENCODE_LOG_PATH.open("rb") as f:
            f.seek(offset)
            blob = f.read().decode("utf-8", errors="replace")
    except OSError:
        return []

    needles = _output_dir_variants(output_dir)
    out: list[dict] = []
    for raw in blob.splitlines():
        if not any(n in raw for n in needles):
            continue
        event = _parse_opencode_line(raw)
        if event:
            out.append(event)
    return out[-limit:]


def _parse_opencode_line(raw: str) -> dict | None:
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
    return None


def _oc_unquote(s: str) -> str:
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return s


def _truncate(s: str, n: int) -> str:
    s = s.replace("\n", " ⏎ ")
    return s if len(s) <= n else s[: n - 1] + "…"


def _summarise_event(obj: dict) -> str | None:
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
