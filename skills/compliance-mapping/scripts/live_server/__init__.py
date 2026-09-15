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

"""Ephemeral local server the skill agent boots at run start.

Purpose: give the user a demo-quality "watch the mapping build itself"
view without persisting anything beyond the output dir. Kept intentionally
minimal — no auth, no multi-user, no database, no GitHub integration.
Those are Downstream (`compliance-mapping-agents`) responsibilities and
staying stripped down here is what preserves the boundary between the two.

Public entry points:

  * launcher.py        — the script the agent invokes to start everything
  * server.build_app() — reusable factory if you want to embed the server
  * state.snapshot()   — pure-function view of the output dir on disk
"""
