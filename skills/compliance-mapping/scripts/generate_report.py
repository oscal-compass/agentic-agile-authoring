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

"""Generate a self-contained HTML report from an OSCAL Mapping Collection.

The report is a single .html file with all data inlined as JSON. Users open
it in a browser and can:
  - Browse the links table with filters
  - See target-side gaps and source-side low-coverage entries
  - Add / delete / modify links (non-LLM operations only) via a
    Stage → Approve/Discard workflow that mirrors the authoring skill's
    Staging Protocol
  - Copy the edited JSON to the clipboard, or download it
  - See a changelog of every applied edit

The report has zero server dependencies once written. Edits persist across
browser refreshes via LocalStorage (keyed by the mapping's fingerprint).

Usage:
    python generate_report.py <mapping_collection.json> \
        [--work-dir <dir>] \
        [--source-catalog <path>] [--target-catalog <path>] \
        [--output <report.html>]

If --output is omitted, the report is written to <mapping_collection>.report.html
alongside the input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


TEMPLATE = Path(__file__).resolve().parent / "template.html"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_latest_working_catalog(work_dir: Path, side: str) -> Path | None:
    """Match either `<side>_wc_genN.json` or the legacy `left/right` naming."""
    candidates: list[Path] = []
    for name in (side, "left" if side == "source" else "right"):
        candidates.extend(sorted(work_dir.glob(f"{name}_wc_gen*.json")))
    return candidates[-1] if candidates else None


def _extract_target_gaps(mapping: dict) -> list[str]:
    ids: list[str] = []
    for m in mapping.get("mapping-collection", {}).get("mappings", []):
        gap = m.get("target-gap-summary", {})
        for entry in gap.get("unmapped-controls", []):
            ids.extend(entry.get("with-ids", []))
    return ids


def _extract_low_coverage(work_dir: Path | None) -> list[dict]:
    """aggregate.json (if present) has a `low_coverage_controls` list."""
    if not work_dir:
        return []
    agg_path = work_dir / "aggregated.json"
    if not agg_path.is_file():
        return []
    try:
        return _read_json(agg_path).get("low_coverage_controls", [])
    except Exception:
        return []


def _extract_control_texts(working_catalog_path: Path | None) -> dict[str, str]:
    """Return a dict of {control_or_atom_id: text} from a working catalog.
    Empty dict if the file is missing — the report just shows a placeholder.
    """
    out: dict[str, str] = {}
    if not working_catalog_path or not working_catalog_path.is_file():
        return out
    try:
        wc = _read_json(working_catalog_path)
    except Exception:
        return out
    for c in wc.get("controls", []):
        out[c["id"]] = _compose_text(c)
    for a in wc.get("atoms", []):
        out[a["id"]] = a.get("text", "")
    return out


def _compose_text(control: dict) -> str:
    parts: list[str] = []
    title = control.get("title")
    if title:
        parts.append(title)
    body = control.get("text") or control.get("statement") or ""
    if body:
        parts.append(body)
    return "\n\n".join(parts)


def _fingerprint(mapping: dict) -> str:
    """Stable fingerprint for LocalStorage key — a hash of the mapping uuid
    plus map count, so edits stay attached to this specific mapping and don't
    bleed across unrelated reports opened on the same machine."""
    mc = mapping.get("mapping-collection", {})
    mc_uuid = mc.get("uuid", "")
    map_count = sum(len(m.get("maps", [])) for m in mc.get("mappings", []))
    h = hashlib.sha256(f"{mc_uuid}:{map_count}".encode("utf-8")).hexdigest()[:16]
    return h


def _build_report_data(
    mapping: dict,
    work_dir: Path | None,
    source_wc_path: Path | None,
    target_wc_path: Path | None,
) -> dict:
    title = mapping.get("mapping-collection", {}).get("metadata", {}).get("title", "Compliance Mapping")
    version = mapping.get("mapping-collection", {}).get("metadata", {}).get("version", "")
    last_mod = mapping.get("mapping-collection", {}).get("metadata", {}).get("last-modified", "")

    return {
        "title": title,
        "subtitle": f"v{version} · {last_mod}" if version or last_mod else "",
        "sourceFingerprint": _fingerprint(mapping),
        "mapping": mapping,
        "targetGaps": _extract_target_gaps(mapping),
        "lowCoverage": _extract_low_coverage(work_dir),
        "controlTexts": {
            "source": _extract_control_texts(source_wc_path),
            "target": _extract_control_texts(target_wc_path),
        },
    }


def generate(
    mapping_path: Path,
    work_dir: Path | None,
    source_catalog: Path | None,
    target_catalog: Path | None,
    output_path: Path,
) -> Path:
    mapping = _read_json(mapping_path)

    # Prefer working catalogs (they carry decomposed atom texts too);
    # fall back to raw OSCAL Catalogs if not available.
    source_wc = _find_latest_working_catalog(work_dir, "source") if work_dir else None
    target_wc = _find_latest_working_catalog(work_dir, "target") if work_dir else None
    if not source_wc and source_catalog:
        source_wc = source_catalog if source_catalog.is_file() else None
    if not target_wc and target_catalog:
        target_wc = target_catalog if target_catalog.is_file() else None

    report_data = _build_report_data(mapping, work_dir, source_wc, target_wc)
    template = TEMPLATE.read_text(encoding="utf-8")

    # Serialize as compact JSON to keep the HTML small; the browser will
    # re-parse it once on load. Escape any `</script>` sequences that could
    # otherwise break out of the <script> tag we're embedding into.
    data_json = json.dumps(report_data, ensure_ascii=False, separators=(",", ":"))
    data_json = data_json.replace("</", "<\\/")

    html = template.replace("__TITLE__", report_data["title"]).replace("__REPORT_DATA__", data_json)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mapping_collection", type=Path)
    p.add_argument("--work-dir", type=Path, default=None,
                   help="Directory containing working catalogs and aggregated.json. Optional.")
    p.add_argument("--source-catalog", type=Path, default=None,
                   help="Fallback source OSCAL Catalog (used only when --work-dir has no working catalog).")
    p.add_argument("--target-catalog", type=Path, default=None,
                   help="Fallback target OSCAL Catalog.")
    p.add_argument("--output", type=Path, default=None,
                   help="Output HTML path. Default: <mapping_collection>.report.html")
    args = p.parse_args()

    if not args.mapping_collection.is_file():
        print(f"ERROR: mapping_collection not found: {args.mapping_collection}", file=sys.stderr)
        return 1

    output = args.output or args.mapping_collection.with_suffix(".report.html")
    result = generate(
        mapping_path=args.mapping_collection,
        work_dir=args.work_dir,
        source_catalog=args.source_catalog,
        target_catalog=args.target_catalog,
        output_path=output,
    )
    print(f"Wrote report to: {result}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
