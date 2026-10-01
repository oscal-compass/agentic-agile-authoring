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

"""Compare generated NIST 800-53 → 800-171 mapping against the authoritative NIST CUI Overlay.

Reference (ground truth):  reference/mapping_collection.json
                            (derived from sp800-171r3-cui-overlay.xlsx, Tailoring
                             Decision = CUI only; 97 requirement-level entries)
Generated:                  ../expected-output/mapping_collection.json
                            (produced by the compliance-mapping skill in this demo)

Normalization:
- Source ids (800-53) already look like `ac-2`, `ac-2.3`. No transform.
- Target ids differ: reference uses `03.01.01`, generated uses
  `nist-sp-800-171-r3-03-01-01`. Normalize both to `03.01.01`.
- Compare at (source, target) pair level.
"""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REF_PATH = HERE / "reference" / "mapping_collection.json"
GEN_PATH = HERE.parent / "expected-output" / "mapping_collection.json"
OUT = HERE
OUT.mkdir(parents=True, exist_ok=True)


def normalize_target(tid: str) -> str | None:
    # generated: nist-sp-800-171-r3-03-01-01 -> 03.01.01
    m = re.search(r"(\d{2})-(\d{2})-(\d{2})$", tid)
    if m:
        return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
    # reference: 03.01.01
    if re.fullmatch(r"\d{2}\.\d{2}\.\d{2}", tid):
        return tid
    return None


def normalize_source(sid: str) -> str:
    return sid.lower().strip()


def load_pairs(path: Path) -> tuple[dict[tuple[str, str], str], dict[str, str], dict[tuple[str, str], list[str]]]:
    """Return:
    - pair_relationships: (source, target) -> relationship label
    - target_titles: target -> requirement title (best effort)
    - pair_extra: (source, target) -> [prop strings], for debugging
    """
    data = json.loads(path.read_text())
    coll = data["mapping-collection"]
    pair_rel: dict[tuple[str, str], str] = {}
    target_titles: dict[str, str] = {}
    pair_extra: dict[tuple[str, str], list[str]] = defaultdict(list)

    for mapping in coll["mappings"]:
        for m in mapping.get("maps", []):
            rel = m.get("relationship", "?")
            sources = [normalize_source(s["id-ref"]) for s in m.get("sources", [])]
            targets_raw = [t["id-ref"] for t in m.get("targets", [])]
            targets = [normalize_target(t) for t in targets_raw]
            title = ""
            for p in m.get("props", []):
                if p.get("name") == "requirement-title":
                    title = p.get("value", "")
                    break
            for t in targets:
                if not t:
                    continue
                if title and t not in target_titles:
                    target_titles[t] = title
                for s in sources:
                    key = (s, t)
                    pair_rel[key] = rel
    return pair_rel, target_titles, pair_extra


REL_COMPATIBLE = {
    ("subset-of", "subset-of"),
    ("subset-of", "equivalent-to"),
    ("subset-of", "intersects-with"),  # weaker but still asserts overlap
}


def main() -> None:
    ref_pairs, ref_titles, _ = load_pairs(REF_PATH)
    gen_pairs, gen_titles, _ = load_pairs(GEN_PATH)

    ref_set = set(ref_pairs.keys())
    gen_set = set(gen_pairs.keys())
    exact = ref_set & gen_set
    ref_only = ref_set - gen_set
    gen_only = gen_set - ref_set

    disagreements = []
    for pair in exact:
        r_rel = ref_pairs[pair]
        g_rel = gen_pairs[pair]
        if r_rel != g_rel:
            disagreements.append((pair, r_rel, g_rel))

    precision = len(exact) / (len(exact) + len(gen_only)) if (exact or gen_only) else 0.0
    recall = len(exact) / (len(exact) + len(ref_only)) if (exact or ref_only) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    # family-level recall
    family_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"ref": 0, "hit": 0, "gen": 0})
    for s, t in ref_set:
        fam = t.rsplit(".", 1)[0]  # 03.01.01 -> 03.01
        family_stats[fam]["ref"] += 1
        if (s, t) in exact:
            family_stats[fam]["hit"] += 1
    for s, t in gen_set:
        fam = t.rsplit(".", 1)[0]
        family_stats[fam]["gen"] += 1

    # per-requirement misses (ref-only) — top 10
    req_misses: dict[str, int] = defaultdict(int)
    req_extras: dict[str, int] = defaultdict(int)
    for s, t in ref_only:
        req_misses[t] += 1
    for s, t in gen_only:
        req_extras[t] += 1
    top_misses = sorted(req_misses.items(), key=lambda x: -x[1])[:10]
    top_extras = sorted(req_extras.items(), key=lambda x: -x[1])[:10]

    titles = {**gen_titles, **ref_titles}

    # CSVs
    def write_csv(name: str, rows: set[tuple[str, str]], both_rel: bool = False):
        path = OUT / name
        with path.open("w", newline="") as f:
            w = csv.writer(f)
            if both_rel:
                w.writerow(["source_control_id", "target_requirement_id",
                            "relationship_ref", "relationship_gen", "requirement_title"])
            else:
                w.writerow(["source_control_id", "target_requirement_id",
                            "relationship", "requirement_title"])
            for s, t in sorted(rows):
                title = titles.get(t, "")
                if both_rel:
                    w.writerow([s, t, ref_pairs.get((s, t), ""), gen_pairs.get((s, t), ""), title])
                else:
                    rel = ref_pairs.get((s, t)) or gen_pairs.get((s, t)) or ""
                    w.writerow([s, t, rel, title])

    write_csv("shared-pairs.csv", exact, both_rel=True)
    write_csv("reference-only-pairs.csv", ref_only, both_rel=False)
    write_csv("generated-only-pairs.csv", gen_only, both_rel=False)

    # JSON summary
    summary = {
        "reference_pairs": len(ref_set),
        "generated_pairs": len(gen_set),
        "exact_agreement": len(exact),
        "reference_only": len(ref_only),
        "generated_only": len(gen_only),
        "relationship_disagreements": len(disagreements),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "family_stats": {
            fam: {
                **stats,
                "recall": round(stats["hit"] / stats["ref"], 4) if stats["ref"] else None,
            }
            for fam, stats in sorted(family_stats.items())
        },
        "top_missed_requirements": [
            {"req": t, "title": titles.get(t, ""), "missed_sources": n}
            for t, n in top_misses
        ],
        "top_extra_requirements": [
            {"req": t, "title": titles.get(t, ""), "extra_sources": n}
            for t, n in top_extras
        ],
        "relationship_disagreements_sample": [
            {"pair": list(p), "ref": r, "gen": g}
            for p, r, g in disagreements[:20]
        ],
    }
    (OUT / "comparison.json").write_text(json.dumps(summary, indent=2))

    # Markdown report
    lines = []
    lines.append("# NIST 800-53 → 800-171 Mapping: Generated vs. NIST CUI Overlay\n")
    lines.append(f"- Reference (NIST CUI Overlay): **{len(ref_set)} pairs** across {len({t for _, t in ref_set})} requirements")
    lines.append(f"- Generated: **{len(gen_set)} pairs** across {len({t for _, t in gen_set})} requirements")
    lines.append("")
    lines.append("## Overall")
    lines.append("")
    lines.append("| metric | value |")
    lines.append("|---|---|")
    lines.append(f"| Exact agreement | {len(exact)} |")
    lines.append(f"| Reference-only (missed by generator) | {len(ref_only)} |")
    lines.append(f"| Generated-only (extra vs. reference) | {len(gen_only)} |")
    lines.append(f"| Relationship disagreements on shared pairs | {len(disagreements)} |")
    lines.append(f"| **Precision** | {precision:.3f} |")
    lines.append(f"| **Recall** | {recall:.3f} |")
    lines.append(f"| **F1** | {f1:.3f} |")
    lines.append("")
    lines.append("Precision = |exact| / (|exact| + |generated-only|). Recall = |exact| / (|exact| + |reference-only|).")
    lines.append("")

    lines.append("## Coverage by 800-171 family")
    lines.append("")
    lines.append("| family | ref pairs | gen pairs | matched | recall |")
    lines.append("|---|---:|---:|---:|---:|")
    for fam, stats in sorted(family_stats.items()):
        rec = stats["hit"] / stats["ref"] if stats["ref"] else 0
        lines.append(f"| {fam} | {stats['ref']} | {stats['gen']} | {stats['hit']} | {rec:.2%} |")
    lines.append("")

    lines.append("## Top 10 requirements where the generator missed the most reference sources")
    lines.append("")
    lines.append("| requirement | title | missed sources |")
    lines.append("|---|---|---:|")
    for t, n in top_misses:
        lines.append(f"| {t} | {titles.get(t, '')} | {n} |")
    lines.append("")

    lines.append("## Top 10 requirements where the generator added the most extra sources")
    lines.append("")
    lines.append("| requirement | title | extra sources |")
    lines.append("|---|---|---:|")
    for t, n in top_extras:
        lines.append(f"| {t} | {titles.get(t, '')} | {n} |")
    lines.append("")

    lines.append("## Relationship distribution")
    lines.append("")
    lines.append("Reference is uniformly `subset-of` (NIST convention: 800-171 is a tailored subset of 800-53).")
    lines.append("Generator uses a mix:")
    gen_rel_counts: dict[str, int] = defaultdict(int)
    for rel in gen_pairs.values():
        gen_rel_counts[rel] += 1
    lines.append("")
    lines.append("| relationship | count |")
    lines.append("|---|---:|")
    for rel, n in sorted(gen_rel_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {rel} | {n} |")
    lines.append("")

    lines.append(f"On shared pairs, {len(disagreements)} have a different relationship label. Sample:")
    lines.append("")
    for (s, t), r, g in disagreements[:10]:
        lines.append(f"- `{s}` → `{t}`: reference `{r}`, generated `{g}` ({titles.get(t, '')})")
    lines.append("")

    lines.append("## Notes on interpretation")
    lines.append("")
    lines.append("- Reference-only pairs are pairs the NIST CUI Overlay asserts but the generator did not produce. These are false negatives against the authoritative baseline.")
    lines.append("- Generated-only pairs are pairs the generator produced without NIST asserting them. They are review candidates, not evidence of NIST omission — some may be legitimate related-control links that NIST tailored out.")
    lines.append("- Relationship disagreements: the reference labels every retained pair `subset-of`. The generator distinguishes `equivalent-to` / `intersects-with` / `superset-of`. On shared pairs, a generator label of `equivalent-to` is a stronger claim; `intersects-with` is weaker; `superset-of` inverts direction.")

    (OUT / "report.md").write_text("\n".join(lines) + "\n")
    print(f"Wrote {OUT}/comparison.json, report.md, and 3 CSVs.")
    print(f"  precision={precision:.3f}  recall={recall:.3f}  f1={f1:.3f}")
    print(f"  exact={len(exact)}  ref-only={len(ref_only)}  gen-only={len(gen_only)}  disagreements={len(disagreements)}")


if __name__ == "__main__":
    main()
