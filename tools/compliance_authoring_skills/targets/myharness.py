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

"""MyHarness deployer: reuse APM's core as a library, own only the deployment diff (§3.3).

APM's deployment targets are a closed, hardcoded registry with no plugin mechanism — an unknown
target slug is rejected. We do **not** fork APM. But APM's manifest-load and MCP-normalization are
target-agnostic, so for a custom harness ("MyHarness") we import the pinned APM as a *library* to
get the normalized MCP model, then do the small deployment ourselves:

    resolved skill package + normalized MCP   (APM library)
            │
            ├── copy skill bundle → <root>/skills/<name>/
            └── merge normalized MCP → <root>/mcp.json   (non-destructive)

Library entry points (verified @ apm-cli 0.28.0, see .insights/installer-node-vs-python.md):
``apm_cli.models.apm_package.APMPackage.from_apm_yml(Path)`` →
``.get_all_mcp_dependencies()`` → ``MCPDependency.to_dict()`` (a target-agnostic normalized dict).
Each local skill package is self-contained, so we normalize per-package directly and don't need
the full ``APMDependencyResolver`` graph (which is for transitive git/registry deps we don't use).

Ownership: the only MyHarness-local state is *which MCP servers we wrote*, tracked in an
``_compliance_authoring_skills`` provenance block inside ``mcp.json``. Prune reuses APM's reachability idea — recompute
the required MCP set from the currently-installed skills' manifests and drop only servers no
surviving skill needs, never touching user-authored servers.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

# Default MyHarness root. Overridable (tests point it at a temp dir).
DEFAULT_ROOT = Path.home() / ".myharness"

_PROVENANCE_KEY = "_compliance_authoring_skills"  # our ownership marker inside mcp.json (namespaced, non-colliding).
DEFAULT_PROVENANCE_KEY = _PROVENANCE_KEY  # public alias for callers (e.g. the CLI default).


class MyHarnessError(RuntimeError):
    """A MyHarness deployment problem (bad manifest, unreadable config, …)."""


@dataclass
class McpShape:
    """How to reshape a normalized MCP entry before writing it to a custom harness's mcp.json.

    APM's ``to_dict()`` is target-agnostic, so it emits keys some harnesses don't understand
    (e.g. ``transport``/``registry``). A harness that wants different keys passes an ``McpShape``:

    - ``drop`` — entry keys to remove (e.g. ``{"transport", "registry"}`` for bob).
    - ``rename`` — entry key renames applied after ``drop`` (e.g. ``{"transport": "type"}``).
    - ``provenance_key`` — top-level key used to track servers we wrote; ``None`` writes no
      provenance block (uninstall can then no longer prune the wired MCP — only skill dirs go).
    """

    drop: frozenset[str] = frozenset()
    rename: dict[str, str] = field(default_factory=dict)
    provenance_key: str | None = _PROVENANCE_KEY

    def apply(self, servers: dict[str, dict]) -> dict[str, dict]:
        """Return *servers* with each entry's keys dropped/renamed per this shape (server names kept)."""
        out: dict[str, dict] = {}
        for name, entry in servers.items():
            shaped: dict = {}
            for k, v in entry.items():
                if k in self.drop:
                    continue
                shaped[self.rename.get(k, k)] = v
            out[name] = shaped
        return out


@dataclass
class DeployResult:
    """Outcome of a MyHarness install/uninstall."""

    skills_deployed: list[str] = field(default_factory=list)
    mcp_added: list[str] = field(default_factory=list)
    skills_removed: list[str] = field(default_factory=list)
    mcp_pruned: list[str] = field(default_factory=list)


# --- APM library reuse (normalization) ---------------------------------------


def normalized_mcp(skill_dir: Path) -> dict[str, dict]:
    """Return ``{server_name: normalized_dict}`` for a skill package, via the pinned APM library.

    Uses ``APMPackage.from_apm_yml`` + ``MCPDependency.to_dict()`` so the shape is exactly what
    APM would wire — we inherit APM's parsing/validation instead of re-implementing it.
    """
    # Imported lazily so the module (and its unit tests for the pure deployer bits) don't hard-fail
    # if apm-cli isn't importable in some contexts; install callers always have it (pinned dep).
    from apm_cli.models.apm_package import APMPackage, clear_apm_yml_cache

    apm_yml = skill_dir / "apm.yml"
    if not apm_yml.is_file():
        raise MyHarnessError(f"{skill_dir}: missing apm.yml")
    clear_apm_yml_cache()  # avoid cross-call cache bleed (APM caches by path)
    pkg = APMPackage.from_apm_yml(apm_yml)
    out: dict[str, dict] = {}
    for dep in pkg.get_all_mcp_dependencies():
        d = dep.to_dict()
        out[d["name"]] = {k: v for k, v in d.items() if k != "name"}
    return out


# --- mcp.json read/merge (non-destructive) -----------------------------------


def _load_mcp_config(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise MyHarnessError(f"{path}: invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise MyHarnessError(f"{path}: expected a JSON object")
    return data


def _owned(config: dict, provenance_key: str | None = _PROVENANCE_KEY) -> set[str]:
    """Names of MCP servers we (compliance-authoring-skills) previously wrote, per the provenance block.

    With ``provenance_key=None`` we keep no provenance, so nothing is claimed as owned.
    """
    if not provenance_key:
        return set()
    prov = config.get(provenance_key) or {}
    owned = prov.get("owned_mcp") if isinstance(prov, dict) else None
    return set(owned) if isinstance(owned, list) else set()


def _write_mcp_config(path: Path, config: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def _merge_mcp(config: dict, servers: dict[str, dict], provenance_key: str | None = _PROVENANCE_KEY) -> list[str]:
    """Non-destructively merge *servers* into ``config['mcpServers']``; return names added/updated.

    User-authored servers (not in our provenance) are never overwritten; we only add new servers
    or refresh ones we already own. With ``provenance_key=None`` no provenance block is written
    (and, lacking one, an existing same-named server is treated as the user's and left untouched).
    """
    servers_block = config.setdefault("mcpServers", {})
    owned = _owned(config, provenance_key)
    added: list[str] = []
    for name, spec in servers.items():
        if name in servers_block and name not in owned:
            # a user (or another tool) owns this name — do not clobber it.
            continue
        servers_block[name] = spec
        owned.add(name)
        added.append(name)
    if provenance_key:
        config.setdefault(provenance_key, {})["owned_mcp"] = sorted(owned)
    return added


# --- deploy / undeploy -------------------------------------------------------


def install(
    skill_dirs: list[Path],
    *,
    root: Path = DEFAULT_ROOT,
    dry_run: bool = False,
    shape: McpShape | None = None,
) -> DeployResult:
    """Deploy skills to MyHarness: copy each bundle + merge its normalized MCP servers.

    *skill_dirs* are absolute local skill-package paths. Skill copy is idempotent (replaces our
    own prior copy). MCP merge is non-destructive (user servers preserved). *shape* reshapes each
    MCP entry (drop/rename keys, provenance-key) for harnesses that want a different key set than
    APM's normalized form; the default (``None`` → ``McpShape()``) keeps APM's shape verbatim.
    """
    shape = shape or McpShape()
    result = DeployResult()
    skills_root = root / "skills"
    mcp_path = root / "mcp.json"

    # gather normalized MCP across the selection first (fail fast on a bad manifest), then reshape
    # to the harness's preferred key set.
    all_servers: dict[str, dict] = {}
    for d in skill_dirs:
        all_servers.update(normalized_mcp(d))
    all_servers = shape.apply(all_servers)

    if dry_run:
        result.skills_deployed = [d.name for d in skill_dirs]
        result.mcp_added = sorted(all_servers)
        return result

    for d in skill_dirs:
        dest = skills_root / d.name
        if dest.exists():
            shutil.rmtree(dest)
        # skip __pycache__/*.pyc: pip byte-compiles the bundled skill scripts, and a --source repo
        # may carry dev caches — neither belongs in a deployed skill.
        shutil.copytree(d, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        result.skills_deployed.append(d.name)

    if all_servers:
        config = _load_mcp_config(mcp_path)
        result.mcp_added = _merge_mcp(config, all_servers, shape.provenance_key)
        _write_mcp_config(mcp_path, config)
    return result


def _installed_skill_dirs(skills_root: Path) -> list[Path]:
    if not skills_root.is_dir():
        return []
    return sorted(p for p in skills_root.iterdir() if (p / "apm.yml").is_file())


def uninstall(
    skill_names: list[str],
    *,
    root: Path = DEFAULT_ROOT,
    dry_run: bool = False,
    provenance_key: str | None = _PROVENANCE_KEY,
) -> DeployResult:
    """Remove named skills from MyHarness + prune MCP servers no surviving skill needs (§3.3).

    Reachability prune: after removing the named skills, recompute the required MCP set from the
    *remaining* installed skills' manifests; drop only owned servers absent from that set. User
    servers (not in our provenance) are never pruned. *provenance_key* must match what install
    used; with ``provenance_key=None`` nothing is owned, so no MCP server is pruned (only skills).
    """
    result = DeployResult()
    skills_root = root / "skills"
    mcp_path = root / "mcp.json"

    to_remove = [skills_root / n for n in skill_names if (skills_root / n).is_dir()]

    if dry_run:
        result.skills_removed = [p.name for p in to_remove]
    else:
        for p in to_remove:
            shutil.rmtree(p)
            result.skills_removed.append(p.name)

    # recompute required MCP from surviving skills.
    survivors = [p for p in _installed_skill_dirs(skills_root) if p.name not in skill_names]
    required: set[str] = set()
    for p in survivors:
        required.update(normalized_mcp(p))

    config = _load_mcp_config(mcp_path)
    if config:
        owned = _owned(config, provenance_key)
        servers_block = config.get("mcpServers", {})
        prunable = sorted(n for n in owned if n not in required and n in servers_block)
        if not dry_run:
            for n in prunable:
                servers_block.pop(n, None)
            if provenance_key and provenance_key in config:
                config[provenance_key]["owned_mcp"] = sorted(owned - set(prunable))
            _write_mcp_config(mcp_path, config)
        result.mcp_pruned = prunable
    return result
