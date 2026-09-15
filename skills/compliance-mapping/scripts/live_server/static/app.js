/*
 * SPA glue for the ephemeral live server (mapping variant).
 *
 * Poll /api/state every 1000ms while the run is in flight, back off to
 * 3000ms once report.html exists. There's no WebSocket / SSE because
 * the state we care about lives in files and only ticks a couple of
 * times per minute — polling is simpler and gives us a natural
 * timestamp header for the "last updated Xs ago" indicator.
 */

const els = {
  source:      document.querySelector("#stat-source .stat-num"),
  target:      document.querySelector("#stat-target .stat-num"),
  links:       document.querySelector("#stat-links .stat-num"),
  chunks:      document.querySelector("#stat-chunks .stat-num"),
  outputDir:   document.getElementById("output-dir"),
  phaseList:   document.getElementById("phase-list"),
  relCard:     document.getElementById("relationships-card"),
  relBars:     document.getElementById("rel-bars"),
  agentLog:    document.getElementById("agent-log"),
  followToggle: document.getElementById("follow-toggle"),
  donePanel:   document.getElementById("done-panel"),
  doneSummary: document.getElementById("done-summary"),
  approveBtn:  document.getElementById("approve-btn"),
  rejectBtn:   document.getElementById("reject-btn"),
  shutdownBtn: document.getElementById("shutdown-btn"),
  verdictStatus: document.getElementById("verdict-status"),
  reportLink:  document.getElementById("report-link"),
  lastUpdated: document.getElementById("last-updated"),
};

let currentPollDelay = 1000;

async function poll() {
  try {
    const r = await fetch("/api/state");
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const snap = await r.json();
    render(snap);
    currentPollDelay = snap.done ? 3000 : 1000;
  } catch (e) {
    els.lastUpdated.textContent = `poll failed: ${e.message}`;
  }
  setTimeout(poll, currentPollDelay);
}

function render(snap) {
  els.outputDir.textContent = snap.output_dir || "—";
  const m = snap.mapping || {};

  els.source.textContent = m.source_controls != null ? m.source_controls : "—";
  els.target.textContent = m.target_controls != null ? m.target_controls : "—";
  els.links.textContent  = m.links != null ? m.links : "—";
  if (m.chunks_total > 0) {
    els.chunks.textContent = `${m.chunks_done ?? 0}/${m.chunks_total}`;
  } else {
    els.chunks.textContent = "—";
  }

  renderPhases(snap.phases || []);
  renderRelationships(m.relationships || {}, m.links);
  renderLog(snap.recent_log || []);

  if (snap.done) {
    els.donePanel.classList.remove("hidden");
    els.doneSummary.textContent =
      `Emitted ${m.links ?? "?"} links between ${m.source_controls ?? "?"} source and ${m.target_controls ?? "?"} target controls.`;
    if (snap.report_html_path) updateReportLink(snap.report_html_path);
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
      <div class="phase-name">Stage ${p.id} · ${escapeHtml(p.name)}</div>
      ${detail}
    </li>`;
  }).join("");
  els.phaseList.innerHTML = html;
}

// Colour map for the four OSCAL mapping relationships. Kept in sync
// with the AskCompliance-style palette used in Downstream so the same
// mapping shown in both UIs looks like the same mapping.
const REL_COLORS = {
  "equivalent-to":   "#4a86e8",   // direct, blue
  "intersects-with": "#c4a02c",   // partial, mustard
  "superset-of":     "#8a5cf0",   // wider, purple
  "subset-of":       "#3a9ec7",   // narrower, teal
  "no-relationship": "#8b98ad",   // neutral
};

function renderRelationships(rels, total) {
  const entries = Object.entries(rels).filter(([, v]) => v > 0);
  if (!entries.length || !total) {
    els.relCard.classList.add("hidden");
    return;
  }
  els.relCard.classList.remove("hidden");
  entries.sort((a, b) => b[1] - a[1]);
  const maxCount = entries[0][1];
  els.relBars.innerHTML = entries.map(([rel, count]) => {
    const color = REL_COLORS[rel] || "#8b98ad";
    const pct = Math.round(count / total * 100);
    const widthPct = Math.max(4, Math.round(count / maxCount * 100));
    return `<div class="rel-row">
      <div class="rel-label">${escapeHtml(rel)}</div>
      <div class="rel-bar-track">
        <div class="rel-bar-fill" style="width:${widthPct}%; background:${color}"></div>
      </div>
      <div class="rel-count">${count} <span class="text-dim">(${pct}%)</span></div>
    </div>`;
  }).join("");
}

function renderLog(entries) {
  const norm = entries.map(e =>
    typeof e === "string" ? {kind: "raw", text: e} : e
  );
  els.agentLog.innerHTML = norm.map(e => {
    const kind = escapeHtml(e.kind || "raw");
    const body = (e.html && typeof e.html === "string")
      ? e.html
      : escapeHtml(e.text || "");
    return `<div class="log-line kind-${kind}">${body}</div>`;
  }).join("");
  if (els.followToggle && els.followToggle.checked) {
    els.agentLog.scrollTop = els.agentLog.scrollHeight;
  }
}

// Follow-tail auto-toggle. Identical to the catalog variant — user
// scrolls up = untick, back to bottom = re-tick. Programmatic scrolls
// (auto-tail after each render) are ignored via a MutationObserver
// window so they don't accidentally trip the "user scrolled" heuristic.
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
  if (!confirm("Stop the live server?\n\nThe browser tab will keep the current view but stop updating.")) return;
  try {
    await fetch("/api/shutdown", {method: "POST"});
  } catch (e) {
    // Socket may close mid-response — that's the success case here.
  }
  els.shutdownBtn.disabled = true;
  els.shutdownBtn.textContent = "⏻ Server stopping…";
  els.verdictStatus.textContent = "Live server shutdown requested. This tab is now static.";
}
if (els.shutdownBtn) {
  els.shutdownBtn.addEventListener("click", requestShutdown);
}

// The report.html link only makes sense once the file exists. We point
// it at /api/report rather than a file:// URL so the tab works even
// when the operator is viewing the live server via port-forward.
function updateReportLink(reportPath) {
  if (!reportPath || !els.reportLink) return;
  els.reportLink.href = "/api/report";
  els.reportLink.textContent = "Open report.html →";
}

function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

poll();
