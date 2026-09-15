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
"""
Compare the generated NIST SP 800-171 Rev.3 OSCAL catalog against the
official NIST OSCAL edition.

Prints a summary table to stdout.  Pass --markdown to (re)generate
README_COMPARE_REPORT.md and images/compare_chart.svg (and .png if cairosvg
is available).

Flags:
  --markdown                  Regenerate README_COMPARE_REPORT.md and SVG/PNG chart.
  --no-strip-related-controls Keep "Related Controls: …" blocks in the prose before
                              computing similarity (off by default; useful to measure
                              how much of the score difference is due to this artifact).

Prose similarity uses word-level Jaccard overlap on normalized tokens:
  - one side blank, the other non-blank  → 0.0  (completely dissimilar)
  - length ratio outside [0.4, 2.5]      → min(jaccard, 0.5)  (likely noise)
  - otherwise: |intersection| / |union| of word sets

This is a direct adaptation of the SP 800-53 catalog comparison script from
compliance-mapping-agents/demo/python/compare_catalogs.py. Structural
differences vs. that reference:

- Only one "baseline": the full 800-171 catalog (no low/moderate/high).
- The generator's control IDs (`nist-sp-800-171-r3-03-01-01`) and the
  official catalog's IDs (`SP_800_171_03.01.01`) are both normalized to the
  canonical requirement label (`03.01.01`).
- The generated catalog stores statement + inline discussion in one
  `statement` prose separated by NIST's `DISCUSSION` heading. We split on
  that so the recovered discussion prose lands next to the official
  `guidance` part during collection.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE      = Path(__file__).resolve().parent
REPORT    = HERE / "README_COMPARE_REPORT.md"
SVG_CHART = HERE / "images" / "compare_chart.svg"

CLEANED_CATALOG = HERE / "catalog.cleaned.json"

# The generator's raw output carries a few well-defined PDF-extraction
# artifacts (trailing `REFERENCES` blocks, soft-hyphen line breaks) that don't
# belong in requirement prose. `postprocess.py` strips them before this
# comparison runs, and we compare the cleaned catalog against the official
# NIST OSCAL edition — the same shape as the reference implementation for
# SP 800-53 (single generated catalog vs single official catalog).
PAIRS = {
    "sp-800-171-rev3": {
        "generated": CLEANED_CATALOG,
        "official":  HERE / "nist-sp-800-171-rev3-catalog-official.json",
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ID_TAIL_RE = re.compile(r"(\d{2})[-_.](\d{2})[-_.](\d{2})$")


def canonical_id(ctrl_id: str) -> str:
    """Turn either `nist-sp-800-171-r3-03-01-01` or `SP_800_171_03.01.01`
    into the canonical requirement label `03.01.01`. Non-matching IDs are
    returned unchanged (so we don't accidentally silently drop anything)."""
    m = _ID_TAIL_RE.search(ctrl_id)
    if m:
        return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
    return ctrl_id


def flatten_controls(catalog: dict) -> dict[str, dict]:
    """Return {canonical_control_id: control_dict} for every control in the catalog."""
    result: dict[str, dict] = {}

    def walk_controls(items):
        for item in items:
            cid = item.get("id", "")
            if cid:
                result[canonical_id(cid)] = item
            walk_controls(item.get("controls", []))

    def walk_groups(items):
        for item in items:
            walk_groups(item.get("groups", []))
            walk_controls(item.get("controls", []))

    root = catalog.get("catalog", catalog)
    walk_groups(root.get("groups", []))
    walk_controls(root.get("controls", []))
    return result


def get_title(ctrl: dict) -> str:
    return ctrl.get("title", "").strip()


_RC_RE = re.compile(r"(?i)\nrelated controls?\s*:")

# Set to False via --no-strip-related-controls to disable the truncation.
STRIP_RELATED_CONTROLS: bool = True


def _split_generated_statement(prose: str) -> tuple[str, str]:
    """The generated catalog embeds discussion inside the same `statement`
    prose as the requirement body, separated by the source document's
    `DISCUSSION` heading. Split on it. Returns (statement_body, discussion)."""
    for marker in ("\nDISCUSSION\n", "\nDISCUSSION", "DISCUSSION\n", "DISCUSSION"):
        idx = prose.find(marker)
        if idx != -1:
            return prose[:idx].strip(), prose[idx + len(marker):].strip()
    return prose.strip(), ""


def selected_prose(ctrl: dict, *, strip_related: bool | None = None) -> str:
    """Collect prose from statement and guidance parts only (recursively).

    Assessment objectives, assessment methods, and other non-normative parts
    are excluded so the comparison reflects only the requirement text.

    For the generated 800-171 catalog, the requirement statement and the
    inline discussion live in the same `statement` prose. We split on
    `DISCUSSION` so both halves are collected in a way that lines up with
    the official catalog's separate `statement` / `guidance` parts.

    Any trailing "Related Controls: …" block (a PDF extraction artifact) is
    removed by searching backwards from the end of the assembled prose and
    truncating at the last occurrence.
    """
    texts: list[str] = []

    def collect(parts, inside_target: bool):
        for part in parts:
            name = part.get("name", "")
            descend = inside_target or name in ("statement", "guidance")
            if descend:
                if t := part.get("prose", "").strip():
                    if name == "statement":
                        stmt_body, disc = _split_generated_statement(t)
                        if stmt_body:
                            texts.append(stmt_body)
                        if disc:
                            texts.append(disc)
                    else:
                        texts.append(t)
            collect(part.get("parts", []), inside_target=descend)

    collect(ctrl.get("parts", []), inside_target=False)
    prose = " ".join(texts)

    should_strip = STRIP_RELATED_CONTROLS if strip_related is None else strip_related
    if should_strip:
        m = _RC_RE.search(prose, pos=max(0, len(prose) - 2000))  # only search the tail
        if m is None:
            m = _RC_RE.search(prose)
        if m:
            prose = prose[: m.start()].rstrip()

    return prose


def _tokens(text: str) -> set[str]:
    """Lower-case word tokens, stripping punctuation and OSCAL param noise."""
    text = re.sub(r"\{\{[^}]*\}\}", " ", text)   # {{ insert: param, ... }}
    text = re.sub(r"\[[^\]]*\]", " ", text)        # [Assignment: ...]
    text = re.sub(r"(?i)^control\s*:", " ", text)  # "Control:" PDF prefix
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def prose_similarity(a: str, b: str) -> float:
    """Word-level Jaccard similarity with blank and length-ratio guards."""
    a, b = a.strip(), b.strip()
    if bool(a) != bool(b):
        return 0.0
    if not a and not b:
        return 1.0
    ratio    = len(a) / len(b) if len(b) else 0.0
    length_ok = 0.4 <= ratio <= 2.5
    ta, tb   = _tokens(a), _tokens(b)
    union    = ta | tb
    if not union:
        return 1.0
    jaccard  = len(ta & tb) / len(union)
    return jaccard if length_ok else min(jaccard, 0.5)


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def _is_withdrawn(ctrl: dict) -> bool:
    """A control is withdrawn if its OSCAL status prop says so (official side)
    or its title has been replaced with the literal "Withdrawn" (generated side)."""
    if get_title(ctrl).lower() == "withdrawn":
        return True
    for p in ctrl.get("props", []):
        if p.get("name") == "status" and p.get("value") == "withdrawn":
            return True
    return False


def compare(baseline: str, gen_path: Path, off_path: Path) -> dict:
    gen_cat = json.loads(gen_path.read_text())
    off_cat = json.loads(off_path.read_text())

    gen_ctrl = flatten_controls(gen_cat)
    off_ctrl = flatten_controls(off_cat)

    gen_ids = set(gen_ctrl)
    off_ids = set(off_ctrl)

    missing_from_gen = sorted(off_ids - gen_ids)
    extra_in_gen     = sorted(gen_ids - off_ids)
    common           = sorted(gen_ids & off_ids)

    # Withdrawn requirements have no prose in the official catalog, so they
    # can't meaningfully participate in prose similarity — they'd all pin to 0%
    # and swamp the "dissimilar" table with matched-but-empty entries. Exclude
    # them from prose scoring but report them separately.
    withdrawn = sorted(
        cid for cid in common
        if _is_withdrawn(gen_ctrl[cid]) or _is_withdrawn(off_ctrl[cid])
    )
    withdrawn_agree = [
        cid for cid in withdrawn
        if _is_withdrawn(gen_ctrl[cid]) and _is_withdrawn(off_ctrl[cid])
    ]
    withdrawn_disagree = [
        cid for cid in withdrawn if cid not in withdrawn_agree
    ]
    scored = [cid for cid in common if cid not in set(withdrawn)]

    title_mismatches = sum(
        1 for cid in scored
        if get_title(gen_ctrl[cid]).lower() != get_title(off_ctrl[cid]).lower()
    )

    sims_by_id: dict[str, float] = {}
    for cid in scored:
        gp = selected_prose(gen_ctrl[cid])
        op = selected_prose(off_ctrl[cid])
        sims_by_id[cid] = prose_similarity(gp, op)

    sims = list(sims_by_id.values())
    avg_prose_sim = sum(sims) / len(sims) if sims else 1.0

    # Dissimilar = worst 25% by prose similarity score
    threshold = sorted(sims)[max(0, int(len(sims) * 0.25) - 1)] if sims else 0.0
    dissimilar: list[tuple] = [
        (cid, sims_by_id[cid], selected_prose(gen_ctrl[cid]), selected_prose(off_ctrl[cid]))
        for cid in scored
        if sims_by_id[cid] <= threshold
    ]
    dissimilar.sort(key=lambda x: x[1])

    return {
        "baseline":         baseline,
        "gen_count":        len(gen_ids),
        "off_count":        len(off_ids),
        "missing_from_gen": missing_from_gen,
        "extra_in_gen":     extra_in_gen,
        "common":           scored,
        "withdrawn":        withdrawn,
        "withdrawn_agree":  withdrawn_agree,
        "withdrawn_disagree": withdrawn_disagree,
        "title_mismatches": title_mismatches,
        "avg_prose_sim":    avg_prose_sim,
        "dissimilar_threshold": threshold,
        "sims_by_id":       sims_by_id,
        "dissimilar":       dissimilar,
    }


# ---------------------------------------------------------------------------
# Terminal output
# ---------------------------------------------------------------------------

def _wrap(text: str, width: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for w in words:
        if len(line) + len(w) + (1 if line else 0) > width:
            lines.append(line)
            line = w
        else:
            line = (line + " " + w) if line else w
    if line:
        lines.append(line)
    return lines or [""]


def print_detail(r: dict):
    sep = "=" * 72
    print(sep)
    print(f"  BASELINE: {r['baseline'].upper()}")
    print(sep)
    delta = r['gen_count'] - r['off_count']
    sign  = "+" if delta >= 0 else ""
    print(f"\n  Generated : {r['gen_count']:>4} controls")
    print(f"  Official  : {r['off_count']:>4} controls")
    print(f"  Delta     : {sign}{delta}")
    if r["missing_from_gen"]:
        print(f"\n  Missing from generated ({len(r['missing_from_gen'])}):")
        for cid in r["missing_from_gen"]:
            print(f"    - {cid}")
    if r["extra_in_gen"]:
        print(f"\n  Extra in generated ({len(r['extra_in_gen'])}):")
        for cid in r["extra_in_gen"]:
            print(f"    + {cid}")
    print()


# ---------------------------------------------------------------------------
# SVG bar chart
# ---------------------------------------------------------------------------

def _color(s: float) -> str:
    if s >= 0.75: return "#16a34a"
    if s >= 0.50: return "#ca8a04"
    return "#dc2626"


LEGEND_H = 32


def _svg_column(r: dict, col_w: int, x_off: int, y_off: int = 0, *,
                bar_h: int = 8, gap: int = 2, font_scale: float = 1.0) -> list[str]:
    """Render one baseline's horizontal-bar column.

    Sizing knobs (bar_h/gap/font_scale) let the caller scale up when there's
    only one column to draw; the reference implementation runs 3 columns
    across 1500px which naturally keeps bars readable, but at 500px wide with
    ~100 rows a single column feels cramped.
    """
    ids_sims = sorted(r["sims_by_id"].items(), key=lambda x: x[1], reverse=True)
    ids, sims = zip(*ids_sims) if ids_sims else ([], [])
    n         = len(ids)

    def sz(px: float) -> str:
        return f"{max(1, int(round(px * font_scale)))}"

    label_w   = int(90 * font_scale)
    pct_w     = int(50 * font_scale)
    bar_area  = col_w - label_w - pct_w
    row_h     = bar_h + gap
    col_h     = n * row_h
    title_y   = y_off + int(20 * font_scale)
    pct_top_y = y_off + int(40 * font_scale)
    axis_y0   = y_off + int(54 * font_scale)
    axis_y1   = axis_y0 + col_h

    elems: list[str] = []
    elems.append(
        f'<text x="{x_off + col_w // 2}" y="{title_y}" '
        f'text-anchor="middle" font-weight="bold" font-size="{sz(15)}" fill="#1f2328">'
        f'{r["baseline"].upper()} ({len(ids)})</text>'
    )

    ax = x_off + label_w
    elems.append(
        f'<line x1="{ax}" y1="{axis_y0}" x2="{ax}" y2="{axis_y1}" '
        f'stroke="#ccc" stroke-width="1"/>'
    )
    for pct in (25, 50, 75, 100):
        gx = ax + int(bar_area * pct / 100)
        elems.append(
            f'<line x1="{gx}" y1="{axis_y0}" x2="{gx}" y2="{axis_y1}" '
            f'stroke="#e5e7eb" stroke-width="1" stroke-dasharray="3,2"/>'
        )
        elems.append(
            f'<text x="{gx}" y="{pct_top_y}" text-anchor="middle" '
            f'fill="#9ca3af" font-size="{sz(11)}">{pct}%</text>'
        )
        elems.append(
            f'<text x="{gx}" y="{axis_y1 + int(16 * font_scale)}" text-anchor="middle" '
            f'fill="#9ca3af" font-size="{sz(11)}">{pct}%</text>'
        )

    for i, (cid, sim) in enumerate(zip(ids, sims)):
        y    = axis_y0 + i * row_h
        bw   = int(bar_area * sim)
        fill = _color(sim)
        elems += [
            f'<text x="{ax - 4}" y="{y + bar_h - 1}" '
            f'text-anchor="end" fill="#374151" font-size="{sz(10)}">{cid}</text>',
            f'<rect x="{ax}" y="{y}" width="{bw}" height="{bar_h}" '
            f'fill="{fill}" rx="1"/>',
        ]

    return elems


def _svg_three_column(all_results: list[dict], total_w: int | None = None) -> str:
    """Render all baselines side by side.

    The reference implementation renders 3 baselines across 1500px. Here we
    typically have only one baseline, so we use the same 1500px canvas but
    thicken the bars and scale the type so the chart doesn't feel cramped
    compared to the reference's per-column density.
    """
    n_cols   = len(all_results)
    if total_w is None:
        total_w = 1500
    col_w    = total_w // n_cols
    # One column at 1500px is a lot of horizontal room for ~100 bars — bump the
    # bar thickness and type size so the chart reads at the same scale as the
    # reference report. When more columns exist, revert to the tighter reference
    # spacing so nothing overflows horizontally.
    if n_cols == 1:
        bar_h, gap, font_scale = 18, 6, 1.5
    else:
        bar_h, gap, font_scale = 8, 2, 1.0
    max_rows = max(len(r["common"]) for r in all_results)
    row_h    = bar_h + gap
    y_off    = int(LEGEND_H * font_scale)
    col_y0   = y_off + int(54 * font_scale)
    svg_h    = col_y0 + max_rows * row_h + int(28 * font_scale)

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="{svg_h}" '
        f'font-family="monospace" font-size="{max(9, int(9 * font_scale))}">',
    ]

    # Legend swatch + label sizes scale with the chart so it doesn't shrink to
    # illegibility on the single-column layout.
    sw_w = int(14 * font_scale)
    sw_h = int(12 * font_scale)
    gap_swatch_text = int(6 * font_scale)
    legend_entry_w  = int(110 * font_scale)
    legend_font     = max(10, int(11 * font_scale))
    ly = int(18 * font_scale)
    lx = total_w // 2 - int(legend_entry_w * 1.5)
    for color, label in [("#16a34a", ">=75%"), ("#ca8a04", "50-74%"), ("#dc2626", "&lt;50%")]:
        lines.append(
            f'<rect x="{lx}" y="{ly - sw_h}" width="{sw_w}" height="{sw_h}" '
            f'fill="{color}" rx="1"/>'
        )
        lines.append(
            f'<text x="{lx + sw_w + gap_swatch_text}" y="{ly - 1}" '
            f'fill="#6b7280" font-size="{legend_font}">{label}</text>'
        )
        lx += legend_entry_w

    for i, r in enumerate(all_results):
        lines += _svg_column(
            r, col_w, x_off=i * col_w, y_off=y_off,
            bar_h=bar_h, gap=gap, font_scale=font_scale,
        )

    lines.append("</svg>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def _md_escape(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def _html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _word_diff_html(a: str, b: str) -> tuple[str, str]:
    """Return (a_html, b_html) with differing runs wrapped in <mark>."""
    import html as _html
    from difflib import SequenceMatcher

    def prep(text: str) -> str:
        return text.replace("\n", " ").replace("[", r"\[")

    def tokenise(text: str) -> list[str]:
        return re.split(r"(\s+)", text)

    def normalise(tok: str) -> str:
        return tok.lower().strip()

    ta = tokenise(prep(a))
    tb = tokenise(prep(b))

    na = [normalise(t) for t in ta]
    nb = [normalise(t) for t in tb]

    sm = SequenceMatcher(None, na, nb, autojunk=False)

    def render(tokens: list[str], opcodes, side: str) -> str:
        parts: list[str] = []
        for tag, i1, i2, j1, j2 in opcodes:
            idx1, idx2 = (i1, i2) if side == "a" else (j1, j2)
            chunk = _html.escape("".join(tokens[idx1:idx2]))
            if tag == "equal":
                parts.append(chunk)
            else:
                parts.append(f"<mark>{chunk}</mark>" if chunk.strip() else chunk)
        return "".join(parts)

    opcodes = sm.get_opcodes()
    return render(ta, opcodes, "a"), render(tb, opcodes, "b")


def _dissimilar_html_table(r: dict) -> str:
    """Render dissimilar controls as expandable <details> blocks with <mark> highlights."""
    b   = r["baseline"]
    thr = r["dissimilar_threshold"]
    ndis = len(r["dissimilar"])

    inner_rows: list[str] = []
    for cid, sim, gp, op in r["dissimilar"]:
        gen_html, off_html = _word_diff_html(gp, op)
        inner_rows += [
            f"<details open>",
            f"<summary><strong>[{cid}] — similarity {sim*100:.0f}%</strong></summary>",
            "",
            "| PDF (generated) | NIST OSCAL (official) |",
            "|---|---|",
            f"| {gen_html} | {off_html} |",
            "",
            "</details>",
            "",
        ]

    rows = [
        f"<details>",
        f"<summary><strong>Baseline: {b.upper()} — dissimilar controls "
        f"(worst 25%, at or below {thr*100:.0f}%, {ndis} controls)</strong></summary>",
        "",
        *inner_rows,
        "</details>",
        "",
    ]
    return "\n".join(rows)


def write_markdown(all_results: list[dict], path: Path, png_path: Path | None = None, svg_path: Path | None = None):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    # A single-baseline hero panel: the whole point of this report is one number
    # ("how faithful is the generated catalog?"), so lead with it.
    hero = all_results[0] if len(all_results) == 1 else None
    if hero is not None:
        sim_pct     = round(hero["avg_prose_sim"] * 100)
        n_active    = len(hero["common"])
        n_gen       = hero["gen_count"]
        n_official  = hero["off_count"]
        n_missing   = len(hero["missing_from_gen"])
        n_extra     = len(hero["extra_in_gen"])
        title_delta = hero["title_mismatches"]
        # 4-tile KPI banner, laid out as a borderless HTML table so it renders
        # in both GitHub-flavored markdown and our local server's converter.
        lines += [
            "# Catalog Comparison Report",
            "",
            "Compares the AI-generated NIST SP 800-171 Rev.3 OSCAL catalog "
            "(produced from the source PDF by the `compliance-catalog` skill) against the "
            "[official NIST OSCAL content](https://github.com/usnistgov/oscal-content).",
            "",
            '<div class="hero">',
            '  <div class="hero-main">',
            f'    <div class="hero-value">{sim_pct}%</div>',
            '    <div class="hero-label">Average prose similarity vs. NIST</div>',
            f'    <div class="hero-sub">across {n_active} active controls</div>',
            '  </div>',
            '  <div class="hero-stats">',
            f'    <div class="hero-stat"><span class="v">{n_gen}/{n_official}</span><span class="l">Controls reproduced</span></div>',
            f'    <div class="hero-stat"><span class="v">{n_missing}</span><span class="l">Missing</span></div>',
            f'    <div class="hero-stat"><span class="v">{n_extra}</span><span class="l">Extra</span></div>',
            f'    <div class="hero-stat"><span class="v">{title_delta}</span><span class="l">Title delta</span></div>',
            '  </div>',
            '</div>',
            "",
            "> **Prose similarity** is computed with word-level Jaccard overlap after "
            "stripping OSCAL parameter references (`{{ insert: param, … }}`), PDF "
            "assignment placeholders (`[Assignment: …]`), and `Related Control(s): …` "
            "lines (PDF artifact).  "
            "The worst-scoring 25% of controls are listed in the dissimilar-controls table.",
            "",
        ]
    else:
        lines += [
            "# Catalog Comparison Report",
            "",
            "Compares the AI-generated NIST SP 800-171 Rev.3 OSCAL catalog "
            "(produced from the source PDF by the `compliance-catalog` skill) against the "
            "[official NIST OSCAL content](https://github.com/usnistgov/oscal-content).",
            "",
            "> **Prose similarity** is computed with word-level Jaccard overlap after "
            "stripping OSCAL parameter references (`{{ insert: param, … }}`), PDF "
            "assignment placeholders (`[Assignment: …]`), and `Related Control(s): …` "
            "lines (PDF artifact).  "
            "The worst-scoring 25% of controls are listed in the dissimilar-controls table.",
            "",
        ]

    # ── Summary table ────────────────────────────────────────────────────────
    lines += [
        "## Summary",
        "",
        "| Baseline | Generated | Official | Delta | Missing | Extra | Title Delta | Avg prose sim | Dissimilar |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in all_results:
        delta = r['gen_count'] - r['off_count']
        sign  = "+" if delta >= 0 else ""
        sim   = f"{r['avg_prose_sim']*100:.0f}%"
        ndis  = len(r['dissimilar'])
        lines.append(
            f"| {r['baseline']} "
            f"| {r['gen_count']} | {r['off_count']} | {sign}{delta} "
            f"| {len(r['missing_from_gen'])} | {len(r['extra_in_gen'])} "
            f"| {r['title_mismatches']} | {sim} | {ndis} |"
        )
    lines.append("")

    # ── Prose similarity chart ─────────────────────────────────────────────
    lines += [
        "## Prose similarity per control",
        "",
        "Each bar is one control — green >= 75%, yellow 50-74%, red < 50%.",
        "",
    ]
    if png_path and png_path.exists():
        rel = png_path.relative_to(path.parent)
        lines += [f"![Prose similarity chart]({rel})", ""]
    elif svg_path and svg_path.exists():
        rel = svg_path.relative_to(path.parent)
        lines += [f"![Prose similarity chart]({rel})", ""]
    else:
        lines += [_svg_three_column(all_results), ""]

    # ── Per-baseline dissimilar sections ─────────────────────────────────
    for r in all_results:
        b = r["baseline"]

        if r["missing_from_gen"] or r["extra_in_gen"]:
            lines += [f"---", f"", f"## Baseline: {b.upper()} — structural issues", ""]
            if r["missing_from_gen"]:
                lines.append(f"**Missing from generated ({len(r['missing_from_gen'])}):** "
                              + ", ".join(f"`{c}`" for c in r["missing_from_gen"]))
                lines.append("")
            if r["extra_in_gen"]:
                lines.append(f"**Extra in generated ({len(r['extra_in_gen'])}):** "
                              + ", ".join(f"`{c}`" for c in r["extra_in_gen"]))
                lines.append("")

        if r["dissimilar"]:
            lines += ["---", "", _dissimilar_html_table(r)]

    path.write_text("\n".join(lines))
    print(f"  Report written to {path.name}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    global STRIP_RELATED_CONTROLS
    write_md = "--markdown" in sys.argv
    STRIP_RELATED_CONTROLS = "--no-strip-related-controls" not in sys.argv
    if not STRIP_RELATED_CONTROLS:
        print("  NOTE: --no-strip-related-controls — Related Controls blocks included in prose similarity")

    # Always regenerate the cleaned catalog from the raw generator output so
    # this comparison stays in sync with the current generator state. The
    # post-process is fast (a couple of regex substitutions per control).
    import subprocess
    subprocess.run([sys.executable, str(HERE / "postprocess.py")], check=True)

    all_results = []
    for baseline, paths in PAIRS.items():
        gp = paths["generated"]
        op = paths["official"]
        if not gp.exists():
            print(f"  ERROR: {baseline}: generated catalog not found at {gp}", file=sys.stderr)
            return 1
        if not op.exists():
            print(f"  ERROR: {baseline}: official catalog not found at {op}", file=sys.stderr)
            return 1
        all_results.append(compare(baseline, gp, op))

    # ── Terminal summary table ───────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("  SUMMARY")
    print("=" * 72)
    print(f"  {'Baseline':<20} {'Gen':>6} {'Official':>8} {'Delta':>6}  "
          f"{'Missing':>7}  {'Extra':>5}  {'TitleΔ':>6}  {'ProseSim':>8}  {'Dissimilar':>10}")
    print(f"  {'-'*20} {'-'*6} {'-'*8} {'-'*6}  "
          f"{'-'*7}  {'-'*5}  {'-'*6}  {'-'*8}  {'-'*10}")
    for r in all_results:
        delta = r['gen_count'] - r['off_count']
        sign  = "+" if delta >= 0 else ""
        sim   = f"{r['avg_prose_sim']*100:.0f}%"
        ndis  = len(r['dissimilar'])
        print(f"  {r['baseline']:<20} {r['gen_count']:>6} {r['off_count']:>8} {sign+str(delta):>6}  "
              f"{len(r['missing_from_gen']):>7}  {len(r['extra_in_gen']):>5}  "
              f"{r['title_mismatches']:>6}  {sim:>8}  {ndis:>10}")
    print()

    failures = [
        r for r in all_results
        if r['gen_count'] != r['off_count']
        or r['missing_from_gen']
        or r['extra_in_gen']
    ]
    if failures:
        for r in failures:
            print_detail(r)

    if write_md:
        SVG_CHART.parent.mkdir(parents=True, exist_ok=True)
        SVG_CHART.write_text(_svg_three_column(all_results))
        try:
            import cairosvg
            png_path = SVG_CHART.with_suffix(".png")
            cairosvg.svg2png(url=str(SVG_CHART), write_to=str(png_path), scale=1)
        except Exception:
            png_path = None
        write_markdown(all_results, REPORT, png_path=png_path, svg_path=SVG_CHART)

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
