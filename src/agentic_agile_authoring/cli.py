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

import argparse
import io
import json
import shutil
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString

PACKAGE_NAME = "agentic-agile-authoring"
SLUGS = ["agentic-agile-authoring"]
DATA_DIR = Path(__file__).parent / "data"
MODE_SKILLS_DIR_NAME = f"skills-{PACKAGE_NAME}"
COMMON_SKILLS_DIR_NAME = "skills"


# ---------------------------------------------------------------------------
# YAML helpers
# ---------------------------------------------------------------------------

def _yaml() -> YAML:
    y = YAML()
    y.default_flow_style = False
    y.allow_unicode = True
    y.width = 4096
    y.best_sequence_indent = 2
    return y


def _literal(s: str) -> LiteralScalarString:
    return LiteralScalarString(s.rstrip() + "\n")


def _scalar(s: str):
    return _literal(s) if "\n" in s else s


def _dump_yaml(data: dict) -> str:
    buf = io.StringIO()
    _yaml().dump(data, buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# .roomodes read / write (YAML)
# ---------------------------------------------------------------------------

def _read_roomodes(cwd: Path) -> dict:
    path = cwd / ".roomodes"
    if path.exists():
        return _yaml().load(path.read_text(encoding="utf-8")) or {"customModes": []}
    return {"customModes": []}


def _write_roomodes(cwd: Path, data: dict) -> None:
    (cwd / ".roomodes").write_text(_dump_yaml(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# Build Roo mode dict from bundled data
# ---------------------------------------------------------------------------

def _build_mode(slug: str, include_rules: bool = False) -> dict:
    roo_dir = DATA_DIR / "roo" / slug
    roo = _yaml().load((roo_dir / "roo.yaml").read_text(encoding="utf-8"))

    mode = {
        "slug": roo["slug"],
        "name": roo["name"],
        **{k: _scalar(v) if isinstance(v, str) else v
           for k, v in roo.items() if k not in ("slug", "name")},
    }

    if include_rules:
        rules_files = []
        rules_dir = roo_dir / "rules"
        if rules_dir.exists():
            for f in sorted(rules_dir.iterdir()):
                rules_files.append({
                    "relativePath": f.name,
                    "content": _literal(f.read_text(encoding="utf-8")),
                })
        mode["rulesFiles"] = rules_files

    return mode


# ---------------------------------------------------------------------------
# Skills helpers
# ---------------------------------------------------------------------------

def _skills_dir_name(scope: str) -> str:
    return COMMON_SKILLS_DIR_NAME if scope == "common" else MODE_SKILLS_DIR_NAME


def _copy_skills(skills_src: Path, skills_dst: Path, scope: str) -> None:
    """Copy skills to destination directory.

    common scope: merge individual skill dirs into skills_dst (preserve others).
    mode scope:   replace the whole skills_dst directory.
    """
    if scope == "common":
        skills_dst.mkdir(parents=True, exist_ok=True)
        for skill_dir in sorted(skills_src.iterdir()):
            dst = skills_dst / skill_dir.name
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(skill_dir, dst)
    else:
        if skills_dst.exists():
            shutil.rmtree(skills_dst)
        shutil.copytree(skills_src, skills_dst)


def _remove_skills(skills_dst: Path, scope: str, skills_src: Path) -> None:
    """Remove installed skills from destination directory.

    common scope: remove only the skill dirs this package installed.
    mode scope:   remove the whole package skills directory.
    """
    if not skills_dst.exists():
        return
    if scope == "common":
        for skill_dir in skills_src.iterdir():
            target = skills_dst / skill_dir.name
            if target.exists():
                shutil.rmtree(target)
                print(f"✓ .roo/{COMMON_SKILLS_DIR_NAME}/{skill_dir.name}/ removed")
    else:
        shutil.rmtree(skills_dst)
        print(f"✓ .roo/{MODE_SKILLS_DIR_NAME}/ removed")


# ---------------------------------------------------------------------------
# MCP helpers
# ---------------------------------------------------------------------------

def _merge_mcp(roo_dir: Path) -> None:
    src = DATA_DIR / "mcp.json"
    if not src.exists():
        return
    incoming = json.loads(src.read_text(encoding="utf-8")).get("mcpServers", {})
    if not incoming:
        return
    dst = roo_dir / "mcp.json"
    existing = json.loads(dst.read_text(encoding="utf-8")) if dst.exists() else {}
    existing.setdefault("mcpServers", {}).update(incoming)
    dst.write_text(json.dumps(existing, indent="\t"), encoding="utf-8")
    print(f"✓ .roo/mcp.json updated — added: {', '.join(incoming)}")


def _remove_mcp(roo_dir: Path) -> None:
    src = DATA_DIR / "mcp.json"
    if not src.exists():
        return
    keys = set(json.loads(src.read_text(encoding="utf-8")).get("mcpServers", {}))
    if not keys:
        return
    dst = roo_dir / "mcp.json"
    if not dst.exists():
        return
    data = json.loads(dst.read_text(encoding="utf-8"))
    servers = data.get("mcpServers", {})
    removed = [k for k in keys if k in servers]
    for k in removed:
        del servers[k]
    if not servers:
        dst.unlink()
        print("✓ .roo/mcp.json removed (empty)")
    else:
        dst.write_text(json.dumps(data, indent="\t"), encoding="utf-8")
        print(f"✓ .roo/mcp.json updated — removed: {', '.join(removed)}")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def install(cwd: Path, skills_scope: str) -> None:
    # 1. Merge modes into .roomodes
    roomodes = _read_roomodes(cwd)
    existing = [m for m in roomodes.get("customModes", []) if m.get("slug") not in SLUGS]
    roomodes["customModes"] = existing + [_build_mode(s) for s in SLUGS]
    _write_roomodes(cwd, roomodes)
    print(f"✓ .roomodes updated — added: {', '.join(SLUGS)}")

    roo_dir = cwd / ".roo"
    roo_dir.mkdir(exist_ok=True)

    # 2. Write skills files
    skills_src = DATA_DIR / "skills"
    dir_name = _skills_dir_name(skills_scope)
    skills_dst = roo_dir / dir_name
    _copy_skills(skills_src, skills_dst, skills_scope)
    n = sum(1 for _ in skills_src.iterdir())
    print(f"✓ .roo/{dir_name}/ written ({n} skills)")

    # 3. Write rules files (only if rules/ directory exists for the mode)
    for slug in SLUGS:
        src = DATA_DIR / "roo" / slug / "rules"
        dst = roo_dir / f"rules-{slug}"
        if not src.exists():
            continue
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        print(f"✓ .roo/rules-{slug}/ written ({len(list(dst.iterdir()))} files)")

    # 4. Merge MCP servers into .roo/mcp.json
    _merge_mcp(roo_dir)

    print(f"\n{PACKAGE_NAME} installed successfully.")


def uninstall(cwd: Path, skills_scope: str) -> None:
    # 1. Remove modes from .roomodes
    roomodes = _read_roomodes(cwd)
    before = len(roomodes.get("customModes", []))
    roomodes["customModes"] = [m for m in roomodes.get("customModes", []) if m.get("slug") not in SLUGS]
    if len(roomodes["customModes"]) < before:
        _write_roomodes(cwd, roomodes)
        print(f"✓ .roomodes updated — removed: {', '.join(SLUGS)}")
    else:
        print("No matching modes found in .roomodes.")

    roo_dir = cwd / ".roo"
    skills_src = DATA_DIR / "skills"
    dir_name = _skills_dir_name(skills_scope)
    skills_dst = roo_dir / dir_name

    # 2. Remove skills
    _remove_skills(skills_dst, skills_scope, skills_src)

    # 3. Remove rules directories
    for slug in SLUGS:
        rules_dir = roo_dir / f"rules-{slug}"
        if rules_dir.exists():
            shutil.rmtree(rules_dir)
            print(f"✓ .roo/rules-{slug}/ removed")

    # 4. Remove MCP servers from .roo/mcp.json
    _remove_mcp(roo_dir)

    print(f"\n{PACKAGE_NAME} uninstalled successfully.")


def download(output: Path, skills_scope: str) -> None:
    output.mkdir(parents=True, exist_ok=True)

    # 1. Copy skills files
    skills_src = DATA_DIR / "skills"
    dir_name = _skills_dir_name(skills_scope)
    skills_dst = output / dir_name
    _copy_skills(skills_src, skills_dst, skills_scope)
    n = sum(1 for _ in skills_src.iterdir())
    print(f"✓ Skills → {skills_dst}/ ({n} skills)")

    # 2. Generate mode export YAMLs on-the-fly
    modes_dst = output / "modes"
    modes_dst.mkdir(exist_ok=True)
    for slug in SLUGS:
        mode = _build_mode(slug, include_rules=True)
        yaml_text = _dump_yaml({"customModes": [mode]})
        (modes_dst / f"{slug}.yaml").write_text(yaml_text, encoding="utf-8")
    print(f"✓ Mode YAMLs → {modes_dst}/ ({', '.join(s + '.yaml' for s in SLUGS)})")

    mode_yaml_list = "\n".join(f"     {modes_dst}/{s}.yaml" for s in SLUGS)
    print(f"""
Resources saved to: {output}

Next steps
----------
1. Copy skills to your project:
   cp -r {skills_dst} <your-project>/.roo/

2. Import modes into Roo Code:
   Settings → Modes → Import (repeat for each YAML)
{mode_yaml_list}
""")


def _add_skills_scope_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--skills-scope",
        choices=["common", "mode"],
        default="mode",
        help=(
            "Where to install skills: "
            "'common' → .roo/skills/ (shared across all modes), "
            "'mode' → .roo/skills-agentic-agile-authoring/ (default)"
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog=PACKAGE_NAME,
        description="Install or uninstall agentic-agile-authoring Roo Code modes and skills.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    inst = sub.add_parser("install", help="Install modes and skills into the current project.")
    _add_skills_scope_arg(inst)

    uninst = sub.add_parser("uninstall", help="Remove modes and skills from the current project.")
    _add_skills_scope_arg(uninst)

    dl = sub.add_parser(
        "download",
        help="Download resources for manual installation without modifying project files.",
    )
    dl.add_argument(
        "-o", "--output",
        metavar="DIR",
        default="agentic-agile-authoring-resources",
        help="Directory to save resources (default: ./agentic-agile-authoring-resources)",
    )
    _add_skills_scope_arg(dl)

    args = parser.parse_args()
    cwd = Path.cwd()

    if args.command == "install":
        install(cwd, args.skills_scope)
    elif args.command == "uninstall":
        uninstall(cwd, args.skills_scope)
    elif args.command == "download":
        download(cwd / args.output, args.skills_scope)
