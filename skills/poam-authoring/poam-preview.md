# Preview: OSCAL POA&M → human-readable markdown

There is no reverse trestle task (OSCAL → xlsx / human view), so render the preview yourself. This
reads only the generated JSON — **no trestle, no isolated env needed** (plain stdlib Python).

## Purpose

Show the user a readable table of the POA&M before finalizing: each weakness, its controls, the
remediation plan, milestones, owner, due date, and risk rating.

## Script

Save as `poam_to_markdown.py` and run `python3 poam_to_markdown.py <poam.json> [out.md]`.

```python
#!/usr/bin/env python3
"""Render an OSCAL plan-of-action-and-milestones.json as a markdown table (stdlib only)."""
import json
import sys
from pathlib import Path


def props(item, name):
    return [p["value"] for p in item.get("props", []) if p["name"] == name]


def one(item, name, default=""):
    v = props(item, name)
    return v[0] if v else default


def render(poam_json: str) -> str:
    doc = json.loads(Path(poam_json).read_text(encoding="utf-8"))
    p = doc["plan-of-action-and-milestones"]
    md = [f"# {p['metadata']['title']}", ""]
    sysid = (p.get("system-id") or {}).get("id")
    if sysid:
        md.append(f"**System:** {sysid}  ")
    md.append(f"**Version:** {p['metadata']['version']} · **OSCAL:** {p['metadata']['oscal-version']}")
    md.append("")
    md.append("| POAM ID | Weakness | Controls | Risk | POC | Due | Remediation | Milestones |")
    md.append("|---|---|---|---|---|---|---|---|")
    for it in p.get("poam-items", []):
        controls = ", ".join(props(it, "control-id")) or "—"
        milestones = "<br>".join(props(it, "milestone")) or "—"
        remediation = (it.get("remarks") or "—").replace("|", "\\|")
        desc = it.get("description", "").replace("|", "\\|")
        row = [
            one(it, "poam-id", "—"),
            f"**{it['title']}**<br>{desc}".replace("|", "\\|"),
            controls,
            one(it, "risk-rating", "—"),
            one(it, "point-of-contact", "—"),
            one(it, "scheduled-completion-date", "—"),
            remediation,
            milestones.replace("|", "\\|"),
        ]
        md.append("| " + " | ".join(row) + " |")
    md.append("")
    md.append(f"**Total open items:** {len(p.get('poam-items', []))}")
    return "\n".join(md)


def main():
    if len(sys.argv) < 2:
        print("usage: python3 poam_to_markdown.py <poam.json> [out.md]")
        sys.exit(1)
    md = render(sys.argv[1])
    out = sys.argv[2] if len(sys.argv) > 2 else Path(sys.argv[1]).with_suffix(".md").name
    Path(out).write_text(md + "\n", encoding="utf-8")
    print(f"wrote {out} ({md.count(chr(10)) + 1} lines)")


if __name__ == "__main__":
    main()
```

## Use

1. After [build-poam.md](build-poam.md) produces `plan-of-action-and-milestones.json`, run the
   script to get a markdown table.
2. Show it to the user and confirm the weaknesses, plans, milestones, owners, and dates are right.
3. If anything is wrong, fix `poam_input.json` and regenerate — the OSCAL JSON stays the source of
   truth; the markdown is a view.
