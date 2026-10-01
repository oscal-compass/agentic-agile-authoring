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

"""Ephemeral FastAPI server that visualises a compliance-catalog run.

Run via ``launcher.py`` — that helper handles port selection, browser
opening, and Ctrl-C teardown. This module only implements the endpoints:

    GET /              → SPA (index.html, app.js, styles.css)
    GET /api/state     → snapshot of the output dir as JSON
    GET /api/report    → report.md (raw text) once phase 6 completes
    POST /api/verdict  → record a lightweight review verdict

The server is single-user, single-session and holds NO state of its own:
everything comes from the output dir on disk. That means:

  * you can kill and re-run the server against the same output dir
    without losing anything
  * you can point the server at an already-completed run and get the
    same UI as if the run had just finished
  * closing the browser is enough to end the session — the agent's
    output dir stays intact
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

try:
    from fastapi import FastAPI, HTTPException, Body
    from fastapi.responses import HTMLResponse, PlainTextResponse
    from fastapi.staticfiles import StaticFiles
except ImportError as e:
    raise SystemExit(
        "live_server requires fastapi + uvicorn. Install with:\n"
        "  pip install fastapi uvicorn\n"
        f"(underlying error: {e})"
    )

# Support both "python -m skills.compliance_catalog.scripts.live_server.server"
# (package context, relative import works) and "python launcher.py" (which
# sys.path-inserts the parent dir and imports us as a top-level module).
try:
    from . import state as _state
except ImportError:
    import state as _state       # type: ignore[no-redef]


STATIC_DIR = Path(__file__).parent / "static"


def build_app(output_dir: Path, *, on_shutdown=None) -> FastAPI:
    """Wire up the FastAPI app against a specific output dir.

    We take the output_dir at build time (not per-request) because a live
    server session is bound to exactly one run's dir. Trying to swap
    output dirs mid-session would give the operator a confused view.

    ``on_shutdown`` is an optional callable invoked when the browser
    hits ``POST /api/shutdown``. The launcher wires this to its
    should_exit flag; if omitted, the shutdown endpoint is a no-op
    (useful when embedding the app in tests).
    """
    output_dir = output_dir.resolve()
    app = FastAPI(
        title="compliance-catalog live server",
        docs_url=None, redoc_url=None,   # keep the surface small
    )

    @app.get("/api/state")
    def api_state() -> dict:
        snap = _state.snapshot(output_dir)
        # Attach a server-side timestamp so the SPA can render "last
        # updated 2s ago" without trusting the client clock.
        snap["_server_now"] = time.time()
        return snap

    @app.get("/api/report", response_class=PlainTextResponse)
    def api_report() -> str:
        p = output_dir / "report.md"
        if not p.is_file():
            raise HTTPException(404, detail="report.md not written yet")
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            raise HTTPException(500, detail=str(e))

    @app.post("/api/verdict")
    def api_verdict(body: dict = Body(...)) -> dict:
        # A lightweight per-session verdict. Written to `.reviewed.json`
        # alongside the catalog. NOT a review workflow — no assignments,
        # no PR integration, no persistence beyond this file.
        verdict = (body.get("verdict") or "").strip().lower()
        if verdict not in ("approve", "reject"):
            raise HTTPException(400, detail="verdict must be 'approve' or 'reject'")
        note = (body.get("note") or "").strip() or None
        rec = {
            "verdict": verdict,
            "note": note,
            "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        (output_dir / ".reviewed.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8"
        )
        return {"ok": True, "recorded": rec}

    @app.get("/api/verdict")
    def api_verdict_get() -> dict:
        p = output_dir / ".reviewed.json"
        if not p.is_file():
            return {"recorded": None}
        try:
            return {"recorded": json.loads(p.read_text(encoding="utf-8"))}
        except (OSError, json.JSONDecodeError):
            return {"recorded": None}

    @app.post("/api/shutdown")
    def api_shutdown() -> dict:
        # Ask the launcher to flip uvicorn's should_exit. We deliberately
        # do NOT os.exit here — the caller wants a graceful shutdown so
        # the pending render finishes and the browser gets a clean 200
        # response before the socket closes.
        if callable(on_shutdown):
            on_shutdown()
            return {"ok": True, "shutdown": "requested"}
        return {"ok": False, "shutdown": "no shutdown hook wired"}

    # Static SPA. Path order matters: `/` catch-all must sit LAST so the
    # /api/* routes above win on prefix conflict.
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        p = STATIC_DIR / "index.html"
        return HTMLResponse(p.read_text(encoding="utf-8"))

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True,
                        help="the catalog output dir the agent is writing to")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8850)
    args = parser.parse_args()

    import uvicorn
    app = build_app(Path(args.output_dir))
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
