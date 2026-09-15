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

"""Render outputs/nist-171-53-comparison/comparison.json into a focused HTML
report — a single family-level recall bar chart — and serve it locally for
screen recording. Reads comparison.json on every request so refresh picks up
edits.
"""

from __future__ import annotations

import argparse
import json
import http.server
import socketserver
import webbrowser
from html import escape
from pathlib import Path

HERE = Path(__file__).parent
COMPARISON = HERE / "comparison.json"

FAMILY_TITLES = {
    "03.01": "Access Control",
    "03.02": "Awareness & Training",
    "03.03": "Audit & Accountability",
    "03.04": "Configuration Management",
    "03.05": "Identification & Authentication",
    "03.06": "Incident Response",
    "03.07": "Maintenance",
    "03.08": "Media Protection",
    "03.09": "Personnel Security",
    "03.10": "Physical Protection",
    "03.11": "Risk Assessment",
    "03.12": "Security Assessment",
    "03.13": "System & Comms Protection",
    "03.14": "System & Info Integrity",
    "03.15": "Planning",
    "03.16": "System & Services Acquisition",
    "03.17": "Supply Chain Risk Mgmt",
}


def render_family_rows(family_stats: dict) -> str:
    rows = []
    # Sort by recall descending, then by family code as a stable tiebreaker,
    # so the 100% block reads first and the below-100% rows stand out at the bottom.
    items = sorted(
        family_stats.items(),
        key=lambda x: (-(x[1]["recall"] or 0), x[0]),
    )
    for fam, s in items:
        recall_pct = s["recall"] * 100 if s["recall"] is not None else 0
        # Green for full recall, warning-orange for anything below.
        # This visually distinguishes "100%" from "<100%" without over-alarming
        # a genuinely-high number like 90%.
        below = recall_pct < 99.5
        klass = "below" if below else "full"
        title = FAMILY_TITLES.get(fam, "")
        # Bar always renders left-anchored; the fill width IS the recall %.
        # Zero-recall families would show a bare 0% label to keep the row visible.
        rows.append(f"""
        <tr>
          <td class="fam-id">
            <span class="fam-code">{escape(fam)}</span>
            <span class="fam-name">{escape(title)}</span>
          </td>
          <td class="bar-cell">
            <div class="bar-track">
              <div class="bar {klass}" style="width:{recall_pct:.1f}%">
                <span class="bar-label">{recall_pct:.0f}%</span>
              </div>
            </div>
          </td>
          <td class="ratio-cell">
            <span class="ratio">{s['hit']} / {s['ref']}</span>
          </td>
        </tr>
        """)
    return "\n".join(rows)


HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>NIST 800-53 → 800-171 Mapping — Recall by Family</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {
    --surface-1:      #fcfcfb;
    --page-plane:     #f9f9f7;
    --text-primary:   #0b0b0b;
    --text-secondary: #52514e;
    --text-muted:     #898781;
    --hairline:       #e1e0d9;
    --axis:           #c3c2b7;
    --border-ring:    rgba(11,11,11,0.10);
    --track:          #ececec;

    --bar-full:       #0ca30c;   /* good — 100% recall */
    --bar-below:      #eb6834;   /* orange — anything short of 100% */
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --surface-1:      #1a1a19;
      --page-plane:     #0d0d0d;
      --text-primary:   #ffffff;
      --text-secondary: #c3c2b7;
      --text-muted:     #898781;
      --hairline:       #2c2c2a;
      --axis:           #383835;
      --border-ring:    rgba(255,255,255,0.10);
      --track:          #262624;

      --bar-full:       #0ca30c;
      --bar-below:      #d95926;
    }
  }

  * { box-sizing: border-box; }
  html { color-scheme: light dark; }
  body {
    margin: 0;
    background: var(--page-plane);
    color: var(--text-primary);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    font-size: 15px;
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
  }
  .page { max-width: 1080px; margin: 0 auto; padding: 48px 32px 56px; }

  header .eyebrow {
    font-size: 12px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-muted);
    font-weight: 500;
    margin: 0;
  }
  header h1 {
    font-size: 26px;
    font-weight: 600;
    margin: 6px 0 8px;
    letter-spacing: -0.01em;
  }
  header .subtitle {
    color: var(--text-secondary);
    max-width: 780px;
    margin: 0;
  }
  .overall {
    margin-top: 26px;
    display: flex;
    align-items: baseline;
    gap: 18px;
    flex-wrap: wrap;
  }
  .overall .value {
    font-size: 64px;
    font-weight: 600;
    line-height: 1;
    letter-spacing: -0.03em;
    color: var(--bar-full);
    font-variant-numeric: tabular-nums;
  }
  .overall .value-caption {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .overall .headline {
    font-size: 14px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--text-muted);
    font-weight: 500;
  }
  .overall .detail {
    font-size: 14.5px;
    color: var(--text-secondary);
  }
  .overall .detail strong {
    color: var(--text-primary);
    font-weight: 600;
  }

  .chart {
    margin-top: 28px;
    background: var(--surface-1);
    border: 1px solid var(--border-ring);
    border-radius: 12px;
    padding: 20px 28px;
  }
  .chart table {
    width: 100%;
    border-collapse: collapse;
    font-variant-numeric: tabular-nums;
  }
  .chart thead th {
    text-align: left;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-muted);
    padding: 12px 8px 10px;
    border-bottom: 1px solid var(--hairline);
    font-weight: 500;
  }
  .chart thead th.ratio-h { text-align: right; padding-right: 8px; }
  .chart td {
    padding: 10px 8px;
    border-bottom: 1px solid var(--hairline);
    vertical-align: middle;
  }
  .chart tr:last-child td { border-bottom: none; }

  .fam-id { white-space: nowrap; width: 260px; }
  .fam-code {
    font-weight: 600;
    color: var(--text-primary);
    margin-right: 10px;
    font-variant-numeric: tabular-nums;
  }
  .fam-name { color: var(--text-secondary); font-size: 13.5px; }

  .bar-cell { padding-right: 24px; }
  .bar-track {
    position: relative;
    height: 22px;
    background: var(--track);
    border-radius: 5px;
    overflow: hidden;
  }
  .bar {
    height: 100%;
    display: flex;
    align-items: center;
    padding: 0 10px;
    border-radius: 5px;
    color: #fff;
    font-size: 12.5px;
    font-weight: 600;
    min-width: 44px;
  }
  .bar.full  { background: var(--bar-full); }
  .bar.below { background: var(--bar-below); }
  .bar-label { position: relative; z-index: 1; }

  .ratio-cell { text-align: right; padding-right: 8px; width: 90px; }
  .ratio {
    color: var(--text-secondary);
    font-size: 13px;
    font-variant-numeric: tabular-nums;
  }

  footer {
    margin-top: 22px;
    font-size: 12px;
    color: var(--text-muted);
  }
  footer code {
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
    font-size: 11.5px;
    background: rgba(11,11,11,0.05);
    padding: 1px 5px;
    border-radius: 3px;
  }
  @media (prefers-color-scheme: dark) {
    footer code { background: rgba(255,255,255,0.06); }
  }

  @media (max-width: 720px) {
    .fam-id { width: 170px; }
    .fam-name { display: none; }
  }
</style>
</head>
<body>
  <div class="page">
    <header>
      <p class="eyebrow">Mapping Quality — Recall by 800-171 Family</p>
      <h1>NIST SP 800-53 → 800-171: How much of NIST's own mapping did we reproduce?</h1>
      <p class="subtitle">
        Each row is one 800-171 Rev.3 requirement family. The bar shows the share of
        NIST-authoritative <code>(800-53, 800-171)</code> pairs, from the NIST CUI Overlay,
        that the generated mapping also produced.
      </p>
      <div class="overall">
        <div class="value">{RECALL_PCT}%</div>
        <div class="value-caption">
          <div class="headline">Overall recall vs. NIST</div>
          <div class="detail"><strong>{EXACT} of {REF_TOTAL}</strong> NIST-retained pairs recovered across all 17 families</div>
        </div>
      </div>
    </header>

    <div class="chart">
      <table>
        <thead>
          <tr>
            <th>Family</th>
            <th>Recall</th>
            <th class="ratio-h">Matched / NIST</th>
          </tr>
        </thead>
        <tbody>
          {FAMILY_ROWS}
        </tbody>
      </table>
    </div>

    <footer>
      Reference: NIST SP 800-171 Rev.3 CUI Overlay (<code>sp800-171r3-cui-overlay.xlsx</code>),
      rows with <code>Tailoring Decision = CUI</code>. Recall = matched pairs ÷ NIST-retained pairs in that family.
    </footer>
  </div>
</body>
</html>
"""


def render(data: dict) -> str:
    ref = data["reference_pairs"]
    exact = data["exact_agreement"]
    recall = data["recall"] * 100
    html = HTML
    html = html.replace("{REF_TOTAL}", str(ref))
    html = html.replace("{EXACT}", str(exact))
    html = html.replace("{RECALL_PCT}", f"{recall:.1f}")
    html = html.replace("{FAMILY_ROWS}", render_family_rows(data["family_stats"]))
    return html


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            data = json.loads(COMPARISON.read_text())
            html = render(data)
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/comparison.json":
            body = COMPARISON.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8878)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((args.host, args.port), Handler) as httpd:
        url = f"http://{args.host}:{args.port}/"
        print(f"Serving comparison report at {url}")
        print("Press Ctrl+C to stop.")
        if not args.no_open:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
