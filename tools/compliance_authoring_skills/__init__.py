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

"""compliance-authoring-skills: a thin wrapper over OpenAPM (``apm-cli``, exact-pinned).

Installation, MCP wiring, the lockfile, and prune are **APM's** job — this package adds only what
APM can't do for us (design-spec §3, decision D4):

- **selection** over this repo (``--skill`` / ``--exclude`` / ``--demo``) — :mod:`.selection`
  + :mod:`.policy`;
- a **stable UX + prereq policy** that hides APM's project mechanics (synthesize a project context
  for a standalone skill install) — :mod:`.policy` + :mod:`.backends.apm_cli`;
- a **MyHarness** deployer for a custom harness APM doesn't know, reusing APM's target-agnostic
  resolve/normalize as a library — :mod:`.targets.myharness`.

Supported targets (claude, opencode, …) delegate to the pinned ``apm`` CLI; MyHarness uses APM
in-process. Baseline runtime prerequisite is ``uv`` (no Node).
"""

from importlib.metadata import PackageNotFoundError, version as _version

try:
    __version__ = _version("compliance-authoring-skills")
except PackageNotFoundError:
    # Running from a source checkout without an install (e.g. local dev).
    __version__ = "0.0.0+unknown"
