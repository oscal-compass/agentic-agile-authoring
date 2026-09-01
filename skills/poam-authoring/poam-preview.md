# Preview: OSCAL POA&M → human-readable markdown

There is no reverse trestle task (OSCAL → xlsx / human view), so render the preview yourself. This
reads only the generated JSON — **no trestle, no isolated env needed** (plain stdlib Python).

## Purpose

Show the user a readable table of the POA&M before finalizing: each weakness, its controls, the
remediation plan, milestones, owner, due date, and risk rating. When the POA&M carries top-level
`findings` (path C, after `link-assessment`), a **Status** column is added showing each item as
**open** (a linked `not-satisfied` finding) or **satisfied** — so a pre-defined catalog reads as
which weaknesses are currently open. If there are no findings (path A, or a phase-1 pre-defined
POA&M), the Status column is omitted.

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


def _localdef_static(p):
    """Map rule-id -> its consolidated static props from local-definitions (path C).

    Poam-items don't duplicate the weakness/risk/remediation content — they reference their rule
    group by a `rule-id` prop, and the content lives on the local-definitions validation
    component's props (grouped by the CD's `remarks` token, verbatim CD names). We re-key that
    grouping by the group's own `rule-id` prop, so items dereference by `rule-id` (the `remarks`
    token is trestle-internal grouping and never leaves local-definitions). Returns
    {rule_id: {"Risk_Rating": .., "POC": .., "Scheduled_Completion_Date": .., "Remediation_Plan": ..,
             "Milestone": [..]}}."""
    by_token = {}
    ld = p.get("local-definitions") or {}
    for comp in ld.get("components", []):
        for pr in comp.get("props") or []:
            tok = pr.get("remarks")
            if not tok:
                continue
            g = by_token.setdefault(tok, {})
            if pr["name"] == "Milestone":
                g.setdefault("Milestone", []).append(pr["value"])
            else:
                g[pr["name"]] = pr["value"]
    # re-key each rule-set group by its own `rule-id` prop (the join key items reference)
    return {g["rule-id"]: g for g in by_token.values() if g.get("rule-id")}


def _risk_by_uuid(p):
    return {r["uuid"]: r for r in p.get("risks", [])}


def _item_remediation(it, ld_static, risks):
    """Remediation text for an item: its own `remarks` if inlined (fallback items), else the
    local-def group's `Remediation_Plan`, else the linked risk's first remediation description."""
    if it.get("remarks"):
        return it["remarks"]
    grp = ld_static.get(one(it, "rule-id"), {})
    if grp.get("Remediation_Plan"):
        return grp["Remediation_Plan"]
    for rr in it.get("related-risks", []):
        risk = risks.get(rr.get("risk-uuid"))
        for resp in (risk or {}).get("remediations", []):
            if resp.get("description"):
                return resp["description"]
    return "—"


def _item_field(it, ld_static, cd_name, prop_name):
    """A descriptive field for an item: the inlined item prop if present (fallback items), else the
    local-def rule-set group's verbatim CD prop."""
    v = one(it, prop_name)
    if v:
        return v
    return ld_static.get(one(it, "rule-id"), {}).get(cd_name, "—")


def _item_milestones(it, ld_static):
    ms = props(it, "milestone")
    if ms:
        return ms
    return ld_static.get(one(it, "rule-id"), {}).get("Milestone", [])


def _status_by_item(p):
    """Map poam-item uuid -> "open"/"satisfied"/"" using linked top-level findings (path C)."""
    fstate = {}
    for f in p.get("findings", []):
        st = (((f.get("target") or {}).get("status")) or {}).get("state")
        fstate[f["uuid"]] = st
    out = {}
    for it in p.get("poam-items", []):
        states = [fstate.get(rf.get("finding-uuid")) for rf in it.get("related-findings", [])]
        if "not-satisfied" in states:
            out[it.get("uuid")] = "open"
        elif "satisfied" in states:
            out[it.get("uuid")] = "satisfied"
        else:
            out[it.get("uuid")] = ""  # no linked finding (e.g. a pre-defined, not-yet-assessed item)
    return out


def render(poam_json: str) -> str:
    doc = json.loads(Path(poam_json).read_text(encoding="utf-8"))
    p = doc["plan-of-action-and-milestones"]
    md = [f"# {p['metadata']['title']}", ""]
    sysid = (p.get("system-id") or {}).get("id")
    if sysid:
        md.append(f"**System:** {sysid}  ")
    md.append(f"**Version:** {p['metadata']['version']} · **OSCAL:** {p['metadata']['oscal-version']}")
    md.append("")
    status = _status_by_item(p)
    ld_static = _localdef_static(p)   # rule-set token -> consolidated static props (path C)
    risks = _risk_by_uuid(p)
    has_status = any(status.values())
    header = "| POAM ID | Weakness | Controls |"
    sep = "|---|---|---|"
    if has_status:
        header += " Status |"
        sep += "---|"
    header += " Risk | POC | Due | Remediation | Milestones |"
    sep += "---|---|---|---|---|"
    md.append(header)
    md.append(sep)
    n_open = 0
    for it in p.get("poam-items", []):
        controls = ", ".join(props(it, "control-id")) or "—"
        milestones = "<br>".join(_item_milestones(it, ld_static)) or "—"
        remediation = _item_remediation(it, ld_static, risks).replace("|", "\\|")
        desc = it.get("description", "").replace("|", "\\|")
        row = [
            one(it, "poam-id", "—"),
            f"**{it['title']}**<br>{desc}".replace("|", "\\|"),
            controls,
        ]
        if has_status:
            st = status.get(it.get("uuid")) or "—"
            if st == "open":
                n_open += 1
            row.append(st)
        row += [
            _item_field(it, ld_static, "Risk_Rating", "risk-rating"),
            _item_field(it, ld_static, "POC", "point-of-contact"),
            _item_field(it, ld_static, "Scheduled_Completion_Date", "scheduled-completion-date"),
            remediation,
            milestones.replace("|", "\\|"),
        ]
        md.append("| " + " | ".join(row) + " |")
    md.append("")
    total = len(p.get("poam-items", []))
    if has_status:
        md.append(f"**Total items:** {total} ({n_open} open · {total - n_open} satisfied/other)")
    else:
        md.append(f"**Total open items:** {total}")
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

> **Where the columns come from (path C).** Path-C poam-items do **not** duplicate the static
> weakness/risk/remediation content — they reference their rule group via a `rule-id` prop,
> and the content lives once in `local-definitions` (grouped by the CD's `remarks` token, re-keyed
> by `rule-id`) plus the top-level `risk`. The renderer dereferences it: for each item it reads
> Risk/POC/Due/Remediation/Milestones from the `rule-id` → local-definitions group (remediation also
> falls back to the linked risk's `remediations[]`). For path-A POA&Ms (no `local-definitions`) the
> same columns are read from the item's own props/`remarks` — so both shapes render full detail.

1. After [build-poam.md](build-poam.md) produces `plan-of-action-and-milestones.json`, run the
   script to get a markdown table.
2. Show it to the user and confirm the weaknesses, plans, milestones, owners, and dates are right.
3. If anything is wrong, fix `poam_input.json` and regenerate — the OSCAL JSON stays the source of
   truth; the markdown is a view.
