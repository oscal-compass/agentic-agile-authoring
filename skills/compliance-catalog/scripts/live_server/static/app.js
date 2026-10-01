/*
 * SPA glue for the ephemeral live server.
 *
 * Poll /api/state every 1000ms while the run is in flight, back off to
 * 3000ms once .catalog.done exists. There's no WebSocket / SSE because
 * the state we care about lives in files and only ticks a couple of
 * times per minute — polling is simpler and gives us a natural
 * timestamp header for the "last updated Xs ago" indicator.
 */

const els = {
  controls:    document.querySelector("#stat-controls .stat-num"),
  groups:      document.querySelector("#stat-groups .stat-num"),
  errors:      document.querySelector("#stat-errors .stat-num"),
  iteration:   document.querySelector("#stat-iteration .stat-num"),
  outputDir:   document.getElementById("output-dir"),
  phaseList:   document.getElementById("phase-list"),
  errChart:    document.getElementById("err-chart"),
  errEmpty:    document.getElementById("err-empty"),
  agentLog:    document.getElementById("agent-log"),
  followToggle: document.getElementById("follow-toggle"),
  donePanel:   document.getElementById("done-panel"),
  doneSummary: document.getElementById("done-summary"),
  approveBtn:  document.getElementById("approve-btn"),
  rejectBtn:   document.getElementById("reject-btn"),
  shutdownBtn: document.getElementById("shutdown-btn"),
  verdictStatus: document.getElementById("verdict-status"),
  reportMd:    document.getElementById("report-md"),
  lastUpdated: document.getElementById("last-updated"),
};

let lastSnapshot = null;
let currentPollDelay = 1000;

async function poll() {
  try {
    const r = await fetch("/api/state");
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const snap = await r.json();
    render(snap);
    lastSnapshot = snap;
    // Slow down polling once the run has settled — we're only watching
    // for a human to press Approve/Reject after that.
    currentPollDelay = snap.done ? 3000 : 1000;
  } catch (e) {
    els.lastUpdated.textContent = `poll failed: ${e.message}`;
  }
  setTimeout(poll, currentPollDelay);
}

function render(snap) {
  els.outputDir.textContent = snap.output_dir || "—";
  const c = snap.controls || {};
  els.controls.textContent = c.total != null ? c.total : "—";
  els.groups.textContent   = c.groups != null ? c.groups : "—";
  const v = snap.validate || {};
  els.errors.textContent = v.current_errors != null ? v.current_errors : "—";
  const iters = (v.iterations || []).length;
  els.iteration.textContent = iters > 0 ? iters : "—";

  renderPhases(snap.phases || []);
  renderErrChart(v.iterations || []);
  renderLog(snap.recent_log || []);

  if (snap.done) {
    els.donePanel.classList.remove("hidden");
    const code = snap.done_exit_code;
    els.doneSummary.textContent =
      code === 0
        ? `Pipeline exited cleanly. ${c.total || "?"} controls in ${c.groups || "?"} groups.`
        : `Pipeline finished with exit code ${code ?? "unknown"}. Check report.md.`;
    if (snap.report_md) els.reportMd.textContent = snap.report_md;
    refreshVerdict();
  }

  els.lastUpdated.textContent = `Last updated ${new Date().toLocaleTimeString()}`;
}

function renderPhases(phases) {
  const html = phases.map(p => {
    const icon = p.status === "done"    ? "✓"
               : p.status === "running" ? "…"
               : p.status === "error"   ? "!"
               :                          "○";
    const detail = p.detail ? `<span class="phase-detail">${escapeHtml(p.detail)}</span>` : "";
    return `<li>
      <div class="phase-icon ${p.status}">${icon}</div>
      <div class="phase-name">Phase ${p.id} · ${escapeHtml(p.name)}</div>
      ${detail}
    </li>`;
  }).join("");
  els.phaseList.innerHTML = html;
}

function renderErrChart(iterations) {
  if (!iterations.length) {
    els.errChart.innerHTML = "";
    els.errEmpty.classList.remove("hidden");
    return;
  }
  els.errEmpty.classList.add("hidden");
  const maxErr = Math.max(...iterations.map(i => i.errors ?? 0), 1);
  els.errChart.innerHTML = iterations.map(it => {
    const err = it.errors ?? 0;
    const heightPct = Math.max(6, Math.round(err / maxErr * 100));
    return `<div class="err-bar" style="height:${heightPct}%">
      <div class="err-num">${it.errors == null ? "?" : it.errors}</div>
      <div class="err-i">iter ${it.i}</div>
    </div>`;
  }).join("");
}

function renderLog(entries) {
  // state.py sends [{kind, text, html?}, ...]. Older builds sent
  // [string, ...]; keep tolerant of both so a mid-run server restart
  // doesn't break the panel while a stale cached SPA is talking to a
  // newer server.
  const norm = entries.map(e =>
    typeof e === "string" ? {kind: "raw", text: e} : e
  );
  els.agentLog.innerHTML = norm.map(e => {
    const kind = escapeHtml(e.kind || "raw");
    // Server-rendered HTML (currently only narration notes) is trusted
    // because it comes from our own _render_note_html() — the only
    // untrusted content, agent text, has already been html.escape'd
    // before any tag was added. Fall back to plain text otherwise.
    const body = (e.html && typeof e.html === "string")
      ? e.html
      : escapeHtml(e.text || "");
    return `<div class="log-line kind-${kind}">${body}</div>`;
  }).join("");
  // Scroll to the tail only when Follow tail is on. That flag is
  // maintained by the user-scroll listener below: an intentional
  // scroll-up flips it off, a scroll-back-to-bottom flips it on.
  if (els.followToggle && els.followToggle.checked) {
    els.agentLog.scrollTop = els.agentLog.scrollHeight;
  }
}

// Follow-tail auto-toggle. Two signals:
//   * user scrolls up → treat as "I want to read old entries",
//     untick Follow tail
//   * user scrolls back down to within a small threshold of the bottom
//     → treat as "keep me on the tail", re-tick Follow tail
// We distinguish user-driven scrolls from programmatic ones by ignoring
// scroll events that fire within a short window after each render.
// Without that guard, our own auto-tail scroll would immediately untick
// the box on the next poll.
const NEAR_BOTTOM_PX = 30;
let _programmaticScrollUntil = 0;
if (els.agentLog && els.followToggle) {
  els.agentLog.addEventListener("scroll", () => {
    if (Date.now() < _programmaticScrollUntil) return;
    const panel = els.agentLog;
    const distanceFromBottom = panel.scrollHeight - panel.scrollTop - panel.clientHeight;
    const nearBottom = distanceFromBottom <= NEAR_BOTTOM_PX;
    if (els.followToggle.checked !== nearBottom) {
      els.followToggle.checked = nearBottom;
    }
  });
  // Any DOM update inside the log panel counts as a programmatic scroll
  // opportunity — arm the guard so the trailing scrollTop assignment
  // in renderLog doesn't trip the user-scroll heuristic.
  new MutationObserver(() => {
    _programmaticScrollUntil = Date.now() + 80;
  }).observe(els.agentLog, {childList: true, subtree: false});
}

async function refreshVerdict() {
  try {
    const r = await fetch("/api/verdict");
    if (!r.ok) return;
    const data = await r.json();
    const rec = data.recorded;
    if (rec) {
      els.verdictStatus.textContent = `Recorded ${rec.verdict.toUpperCase()} at ${rec.recorded_at}${rec.note ? " — " + rec.note : ""}`;
    } else {
      els.verdictStatus.textContent = "No verdict yet.";
    }
  } catch (e) { /* silent */ }
}

async function submitVerdict(verdict) {
  const note = prompt(`Optional note for ${verdict}:`, "") || "";
  try {
    const r = await fetch("/api/verdict", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({verdict, note}),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    await refreshVerdict();
  } catch (e) {
    alert(`verdict failed: ${e.message}`);
  }
}
els.approveBtn.addEventListener("click", () => submitVerdict("approve"));
els.rejectBtn .addEventListener("click", () => submitVerdict("reject"));

async function requestShutdown() {
  // Two-step UX: confirm, then swap the panel out for a static "server
  // stopped" message so the user gets closure even though the SSE-like
  // polling is about to start failing. We deliberately don't try to
  // detect the server actually going down — the very next poll will
  // fail and els.lastUpdated already surfaces that.
  if (!confirm("Stop the live server?\n\nThe browser tab will keep the current view but stop updating.")) return;
  try {
    await fetch("/api/shutdown", {method: "POST"});
  } catch (e) {
    // The POST may error out because the socket closes mid-response —
    // that's actually the success case for a shutdown, so we swallow.
  }
  els.shutdownBtn.disabled = true;
  els.shutdownBtn.textContent = "⏻ Server stopping…";
  els.verdictStatus.textContent = "Live server shutdown requested. This tab is now static.";
}
if (els.shutdownBtn) {
  els.shutdownBtn.addEventListener("click", requestShutdown);
}

function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

poll();
