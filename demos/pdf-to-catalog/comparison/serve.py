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

"""Render README_COMPARE_REPORT.md into an HTML page, GitHub-style, and serve
it locally so it can be viewed / screen-recorded in the browser. The markdown
file is re-read on every request so a browser refresh picks up edits (rerun
`compare_catalogs.py --markdown` and hit reload).
"""

from __future__ import annotations

import argparse
import http.server
import re
import socketserver
import webbrowser
from pathlib import Path

HERE   = Path(__file__).resolve().parent
REPORT = HERE / "README_COMPARE_REPORT.md"


def markdown_to_html(md: str) -> str:
    """Small, purpose-built markdown → HTML converter.

    The report is authored by our own `compare_catalogs.py` so we only need to
    handle the exact features it emits: headings, blockquotes, pipe tables,
    inline code, bold, images, and raw HTML blocks (<details>/<summary>/<mark>)
    which are passed through unchanged.
    """
    lines = md.split("\n")
    out: list[str] = []
    i = 0

    def _inline(s: str) -> str:
        # Preserve inline HTML tags already written by the report (<mark>, <br>).
        # Only rewrite markdown inline syntax.
        # 1. Images: ![alt](url)
        s = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r'<img alt="\1" src="\2">', s)
        # 2. Links: [text](url)  (only if not already an image)
        s = re.sub(r"(?<!\!)\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
        # 3. Bold: **text**
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        # 4. Inline code: `text`
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        return s

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Raw HTML block (details/summary/etc.) — pass through, but still
        # transform inline markdown inside a summary text.
        if stripped.startswith("<") and not stripped.startswith("<img"):
            out.append(_inline(line))
            i += 1
            continue

        # Horizontal rule
        if stripped == "---":
            out.append("<hr>")
            i += 1
            continue

        # Headings
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            out.append(f"<h{level}>{_inline(m.group(2))}</h{level}>")
            i += 1
            continue

        # Blockquote
        if stripped.startswith(">"):
            block = []
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                block.append(lines[i].lstrip()[1:].strip())
                i += 1
            out.append("<blockquote>" + _inline(" ".join(block)) + "</blockquote>")
            continue

        # Table (pipe syntax with a header separator on the next line)
        if "|" in stripped and i + 1 < len(lines) and re.match(r"^\|?[\s\-:|]+\|?\s*$", lines[i + 1].strip()):
            header_cells = [c.strip() for c in stripped.strip("|").split("|")]
            sep_cells    = [c.strip() for c in lines[i + 1].strip().strip("|").split("|")]
            aligns       = []
            for c in sep_cells:
                if c.startswith(":") and c.endswith(":"):
                    aligns.append("center")
                elif c.endswith(":"):
                    aligns.append("right")
                elif c.startswith(":"):
                    aligns.append("left")
                else:
                    aligns.append(None)
            i += 2
            body_rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                row = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                body_rows.append(row)
                i += 1
            out.append('<table class="grid">')
            out.append("<thead><tr>" + "".join(
                f'<th{f" style=\"text-align:{a}\"" if a else ""}>{_inline(h)}</th>'
                for h, a in zip(header_cells, aligns)
            ) + "</tr></thead>")
            out.append("<tbody>")
            for row in body_rows:
                cells = "".join(
                    f'<td{f" style=\"text-align:{a}\"" if a else ""}>{_inline(cell)}</td>'
                    for cell, a in zip(row, aligns + [None] * len(row))
                )
                out.append(f"<tr>{cells}</tr>")
            out.append("</tbody></table>")
            continue

        # Blank line
        if stripped == "":
            out.append("")
            i += 1
            continue

        # Paragraph — collect until blank line or a structural marker
        para: list[str] = [line]
        i += 1
        while i < len(lines):
            nxt = lines[i]
            ns  = nxt.strip()
            if not ns or ns.startswith("#") or ns.startswith(">") or ns.startswith("---") or ns.startswith("<") or "|" in ns:
                break
            para.append(nxt)
            i += 1
        out.append("<p>" + _inline(" ".join(x.strip() for x in para)) + "</p>")

    return "\n".join(out)


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>NIST SP 800-171 Rev.3 — Catalog Comparison Report</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {
    --bg:              #ffffff;
    --text:            #1f2328;
    --text-muted:      #59636e;
    --border:          #d1d9e0;
    --border-muted:    #d8dee4;
    --code-bg:         #eff1f3;
    --blockquote-fg:   #59636e;
    --blockquote-bar:  #d1d9e0;
    --link:            #0969da;
    --table-alt:       #f6f8fa;
    --mark-bg:         #fff8c5;
    --mark-fg:         #1f2328;
    --summary-bg:      #f6f8fa;
    --summary-bg-hov:  #eaeef2;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg:              #0d1117;
      --text:            #e6edf3;
      --text-muted:      #9198a1;
      --border:          #3d444d;
      --border-muted:    #2a313c;
      --code-bg:         #151b23;
      --blockquote-fg:   #9198a1;
      --blockquote-bar:  #3d444d;
      --link:            #4493f8;
      --table-alt:       #151b23;
      --mark-bg:         #3b2e00;
      --mark-fg:         #ffdf5d;
      --summary-bg:      #151b23;
      --summary-bg-hov:  #1e252e;
    }
  }
  html { color-scheme: light dark; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 16px;
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
  }
  main {
    max-width: 1012px;
    margin: 0 auto;
    padding: 40px 32px 80px;
  }
  h1, h2, h3, h4 {
    margin-top: 24px;
    margin-bottom: 16px;
    line-height: 1.25;
    font-weight: 600;
  }
  h1 { font-size: 2em;   padding-bottom: .3em; border-bottom: 1px solid var(--border-muted); }
  h2 { font-size: 1.5em; padding-bottom: .3em; border-bottom: 1px solid var(--border-muted); }
  h3 { font-size: 1.25em; }
  p  { margin: 0 0 16px; }
  hr {
    height: 1px;
    border: 0;
    background: var(--border-muted);
    margin: 24px 0;
  }
  a { color: var(--link); text-decoration: none; }
  a:hover { text-decoration: underline; }
  blockquote {
    padding: 0 1em;
    color: var(--blockquote-fg);
    border-left: .25em solid var(--blockquote-bar);
    margin: 0 0 16px;
  }
  code {
    padding: .2em .4em;
    margin: 0;
    font-size: 85%;
    background: var(--code-bg);
    border-radius: 6px;
    font-family: ui-monospace, "SF Mono", "Menlo", "Consolas", monospace;
  }
  img {
    max-width: 100%;
    height: auto;
    background: var(--bg);
  }

  /* Hero KPI banner emitted by compare_catalogs.py for single-baseline runs.
     The main value is the overall similarity number; the tile row on the right
     carries the structural counts (reproduced/missing/extra/title-delta). */
  .hero {
    display: flex;
    align-items: stretch;
    gap: 24px;
    margin: 24px 0 32px;
    padding: 28px 32px;
    background: linear-gradient(135deg, rgba(22,163,74,0.10), rgba(22,163,74,0.03));
    border: 1px solid rgba(22,163,74,0.35);
    border-radius: 12px;
    flex-wrap: wrap;
  }
  .hero-main {
    flex: 1 1 260px;
    min-width: 260px;
    display: flex;
    flex-direction: column;
    justify-content: center;
  }
  .hero-value {
    font-size: 96px;
    font-weight: 700;
    line-height: 1;
    color: #16a34a;
    letter-spacing: -0.03em;
    font-variant-numeric: tabular-nums;
  }
  .hero-label {
    font-size: 18px;
    font-weight: 600;
    color: var(--text);
    margin-top: 12px;
    letter-spacing: -0.005em;
  }
  .hero-sub {
    font-size: 14px;
    color: var(--text-muted);
    margin-top: 4px;
  }
  .hero-stats {
    display: grid;
    grid-template-columns: repeat(2, minmax(120px, 1fr));
    gap: 12px 24px;
    align-content: center;
    flex: 1 1 320px;
  }
  .hero-stat {
    display: flex;
    flex-direction: column;
    padding: 12px 16px;
    background: var(--bg);
    border: 1px solid var(--border-muted);
    border-radius: 8px;
  }
  .hero-stat .v {
    font-size: 26px;
    font-weight: 700;
    line-height: 1.15;
    color: var(--text);
    font-variant-numeric: tabular-nums;
  }
  .hero-stat .l {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-muted);
    margin-top: 2px;
  }
  @media (max-width: 720px) {
    .hero-value { font-size: 72px; }
    .hero-stats { grid-template-columns: 1fr 1fr; }
  }
  table.grid {
    border-collapse: collapse;
    margin: 0 0 16px;
    display: block;
    width: max-content;
    max-width: 100%;
    overflow: auto;
  }
  table.grid th, table.grid td {
    padding: 6px 13px;
    border: 1px solid var(--border);
  }
  table.grid th { background: var(--table-alt); font-weight: 600; }
  table.grid tr:nth-child(2n) td { background: var(--table-alt); }

  /* Diff tables (the ones inside <details>) have two wide prose columns. */
  details table.grid {
    display: table;
    table-layout: fixed;
    width: 100%;
  }
  details table.grid td {
    vertical-align: top;
    word-wrap: break-word;
    font-size: 14px;
    line-height: 1.55;
  }

  details {
    margin: 8px 0;
    padding: 0 12px;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--bg);
  }
  details > summary {
    cursor: pointer;
    padding: 10px 4px;
    margin: 0 -12px;
    padding-left: 16px;
    padding-right: 16px;
    background: var(--summary-bg);
    border-radius: 6px 6px 0 0;
    list-style-position: inside;
  }
  details[open] > summary {
    border-bottom: 1px solid var(--border);
    margin-bottom: 12px;
  }
  details > summary:hover { background: var(--summary-bg-hov); }
  details details {
    background: transparent;
    margin: 12px 0;
  }
  details details > summary { background: transparent; }

  mark {
    background: var(--mark-bg);
    color: var(--mark-fg);
    padding: 1px 2px;
    border-radius: 3px;
  }

  /* Footer refresh hint */
  .refresh-hint {
    color: var(--text-muted);
    font-size: 12px;
    margin-top: 40px;
    text-align: center;
    border-top: 1px solid var(--border-muted);
    padding-top: 16px;
  }
</style>
</head>
<body>
<main>
{BODY}
<div class="refresh-hint">
  Re-run <code>python compare_catalogs.py --markdown</code> and refresh to update.
</div>
</main>
</body>
</html>
"""


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            md = REPORT.read_text()
            body = markdown_to_html(md)
            html = PAGE.replace("{BODY}", body).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(html)
        elif self.path == "/README_COMPARE_REPORT.md":
            self._send_file(REPORT, "text/markdown; charset=utf-8")
        elif self.path.startswith("/images/"):
            rel = self.path.lstrip("/").split("?", 1)[0]
            asset = (HERE / rel).resolve()
            if HERE not in asset.parents or not asset.exists():
                self.send_error(404); return
            ct = "image/svg+xml" if asset.suffix == ".svg" else "image/png" if asset.suffix == ".png" else "application/octet-stream"
            self._send_file(asset, ct)
        else:
            self.send_error(404)

    def _send_file(self, path: Path, content_type: str):
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8879)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()

    if not REPORT.exists():
        print(f"{REPORT.name} missing. Run: python compare_catalogs.py --markdown")
        return

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((args.host, args.port), Handler) as httpd:
        url = f"http://{args.host}:{args.port}/"
        print(f"Serving catalog comparison report at {url}")
        print("Press Ctrl+C to stop.")
        if not args.no_open:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
