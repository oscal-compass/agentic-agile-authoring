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

from compliance_authoring_skills.selection import (
    parse_frontmatter,
    resolve_skill_list,
    unknown_names,
)

ALL = ["assessment", "catalog-authoring", "component-definition", "git-workflow"]


def test_default_selection_is_all():
    assert resolve_skill_list(ALL) == ALL


def test_exclude_subtracts_from_all():
    assert resolve_skill_list(ALL, exclude=["git-workflow", "assessment"]) == [
        "catalog-authoring",
        "component-definition",
    ]


def test_demo_resolves_to_its_skill_set():
    demo = ["catalog-authoring", "component-definition", "assessment"]
    assert resolve_skill_list(ALL, demo=demo) == demo


def test_demo_with_exclude():
    demo = ["catalog-authoring", "component-definition", "assessment"]
    assert resolve_skill_list(ALL, demo=demo, exclude=["assessment"]) == [
        "catalog-authoring",
        "component-definition",
    ]


def test_picks_win_over_demo_and_all():
    assert resolve_skill_list(ALL, picks=["catalog-authoring"], demo=["assessment"]) == [
        "catalog-authoring"
    ]


def test_selection_dedups_and_preserves_order():
    assert resolve_skill_list(["a", "b", "a", "c"]) == ["a", "b", "c"]


def test_unknown_names_flags_typos():
    assert unknown_names(ALL, exclude=["git-worklow"]) == ["git-worklow"]
    assert unknown_names(ALL, picks=["assessment"]) == []


def test_unknown_names_skipped_when_source_unenumerable():
    assert unknown_names([], picks=["whatever"]) == []


def test_parse_frontmatter_reads_skills_list():
    md = "---\nname: catalog-to-assessment\nskills:\n  - catalog-authoring\n  - assessment\n---\n\n# Steps\n"
    assert parse_frontmatter(md)["skills"] == ["catalog-authoring", "assessment"]


def test_parse_frontmatter_empty_without_frontmatter():
    assert parse_frontmatter("# just a heading\n") == {}
