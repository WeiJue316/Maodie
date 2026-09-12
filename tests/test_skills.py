"""skills.py 的单元测试。"""

from pathlib import Path

import pytest

from agent.skills import (
    SkillManager, _parse_frontmatter, _load_skill,
    _parse_metadata, _check_runtime_eligibility,
)


# ---------------------------------------------------------------------------
# Frontmatter 解析
# ---------------------------------------------------------------------------


class TestParseFrontmatter:
    def test_with_frontmatter(self):
        text = "---\nname: my_skill\ndescription: test desc\n---\nBody here"
        meta, body = _parse_frontmatter(text)
        assert meta["name"] == "my_skill"
        assert meta["description"] == "test desc"
        assert body.strip() == "Body here"

    def test_no_frontmatter(self):
        text = "Just plain content"
        meta, body = _parse_frontmatter(text)
        assert meta == {}
        assert body == "Just plain content"

    def test_missing_fields(self):
        text = "---\nname: partial\n---\nContent"
        meta, body = _parse_frontmatter(text)
        assert meta["name"] == "partial"
        assert "description" not in meta

    def test_multiline_value(self):
        """YAML 多行值（| 语法）应被正确解析。"""
        text = "---\nname: test\ndescription: |\n  line one\n  line two\n---\nBody"
        meta, body = _parse_frontmatter(text)
        assert meta["name"] == "test"
        assert "line one" in meta["description"]
        assert "line two" in meta["description"]

    def test_invalid_yaml_fallback(self):
        """无效 YAML 应返回空 dict，不崩溃。"""
        text = "---\n{{invalid yaml::\n---\nBody"
        meta, body = _parse_frontmatter(text)
        assert meta == {}
        assert "Body" in body

    def test_parse_tools_list(self):
        """tools 字段应被解析为 list[str]。"""
        text = "---\nname: test\ntools: [read_file, write_file, shell]\n---\nBody"
        meta, body = _parse_frontmatter(text)
        assert meta["tools"] == ["read_file", "write_file", "shell"]

    def test_parse_tools_empty(self):
        """无 tools 字段时不出现在 meta 中。"""
        text = "---\nname: test\n---\nBody"
        meta, body = _parse_frontmatter(text)
        assert "tools" not in meta

    def test_parse_tools_single_item(self):
        """单个 tool 也应解析为列表。"""
        text = "---\nname: test\ntools:\n  - read_file\n---\nBody"
        meta, body = _parse_frontmatter(text)
        assert meta["tools"] == ["read_file"]


# ---------------------------------------------------------------------------
# SkillManager
# ---------------------------------------------------------------------------


class TestSkillManager:
    def test_discover_finds_skill_dirs(self, tmp_path: Path):
        skill_dir = tmp_path / "skills" / "test_skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.md").write_text(
            "---\nname: test_skill\ndescription: A test\n---\nContent",
            encoding="utf-8",
        )
        sm = SkillManager(tmp_path / "skills")
        skills = sm.discover()
        assert len(skills) == 1
        assert skills[0].name == "test_skill"
        assert skills[0].description == "A test"

    def test_discover_ignores_empty_dirs(self, tmp_path: Path):
        (tmp_path / "skills" / "no_skill").mkdir(parents=True)
        sm = SkillManager(tmp_path / "skills")
        skills = sm.discover()
        assert len(skills) == 0

    def test_discover_ignores_files(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "readme.txt").write_text("not a skill", encoding="utf-8")
        sm = SkillManager(skills_dir)
        skills = sm.discover()
        assert len(skills) == 0

    def test_discover_missing_dir(self, tmp_path: Path):
        sm = SkillManager(tmp_path / "nonexistent")
        skills = sm.discover()
        assert len(skills) == 0

    def test_get_skill_by_name(self, tmp_path: Path):
        skill_dir = tmp_path / "skills" / "s1"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.md").write_text(
            "---\nname: s1\ndescription: d1\n---\nBody",
            encoding="utf-8",
        )
        sm = SkillManager(tmp_path / "skills")
        sm.discover()
        assert sm.get_skill("s1") is not None
        assert sm.get_skill("s1").name == "s1"

    def test_get_skill_not_found(self, tmp_path: Path):
        sm = SkillManager(tmp_path / "skills")
        sm.discover()
        assert sm.get_skill("nonexistent") is None

    def test_get_skill_summaries(self, tmp_path: Path):
        for name in ("a", "b"):
            d = tmp_path / "skills" / name
            d.mkdir(parents=True)
            (d / "skill.md").write_text(
                f"---\nname: {name}\ndescription: desc-{name}\n---\nBody",
                encoding="utf-8",
            )
        sm = SkillManager(tmp_path / "skills")
        sm.discover()
        summary = sm.get_skill_summaries()
        assert "a: desc-a" in summary
        assert "b: desc-b" in summary

    def test_get_skill_summaries_empty(self, tmp_path: Path):
        sm = SkillManager(tmp_path / "skills")
        sm.discover()
        assert sm.get_skill_summaries() == "(无可用 Skill)"

    def test_discover_recursive_nested_skills(self, tmp_path: Path):
        """递归发现嵌套在子目录中的 skill。"""
        skills_dir = tmp_path / "skills"
        # 顶层 skill
        top = skills_dir / "top_skill"
        top.mkdir(parents=True)
        (top / "skill.md").write_text(
            "---\nname: top_skill\n---\nTop body", encoding="utf-8"
        )
        # 嵌套 skill（两层深）
        nested = skills_dir / "framework" / "sub" / "nested_skill"
        nested.mkdir(parents=True)
        (nested / "skill.md").write_text(
            "---\nname: nested_skill\n---\nNested body", encoding="utf-8"
        )
        sm = SkillManager(skills_dir)
        skills = sm.discover()
        names = [s.name for s in skills]
        assert "top_skill" in names
        assert "nested_skill" in names
        assert len(skills) == 2

    def test_discover_skips_examples_dir(self, tmp_path: Path):
        """跳过 examples/templates 子目录中的 skill。"""
        skills_dir = tmp_path / "skills"
        # 正常 skill
        normal = skills_dir / "normal"
        normal.mkdir(parents=True)
        (normal / "skill.md").write_text(
            "---\nname: normal\n---\nBody", encoding="utf-8"
        )
        # examples 中的 skill
        example = skills_dir / "framework" / "examples" / "example_skill"
        example.mkdir(parents=True)
        (example / "skill.md").write_text(
            "---\nname: example_skill\n---\nBody", encoding="utf-8"
        )
        sm = SkillManager(skills_dir)
        skills = sm.discover()
        names = [s.name for s in skills]
        assert "normal" in names
        assert "example_skill" not in names
        assert len(skills) == 1

    def test_discover_case_insensitive_skill_md(self, tmp_path: Path):
        """兼容 SKILL.md 大写变体。"""
        skills_dir = tmp_path / "skills"
        d = skills_dir / "upper_skill"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            "---\nname: upper_skill\n---\nBody", encoding="utf-8"
        )
        sm = SkillManager(skills_dir)
        skills = sm.discover()
        assert len(skills) == 1
        assert skills[0].name == "upper_skill"

    def test_discover_no_duplicate_mixed_case(self, tmp_path: Path):
        """同时存在 skill.md 和 SKILL.md 时，不产生重复。"""
        skills_dir = tmp_path / "skills"
        d = skills_dir / "mixed_skill"
        d.mkdir(parents=True)
        (d / "skill.md").write_text(
            "---\nname: mixed_skill\n---\nLower", encoding="utf-8"
        )
        (d / "SKILL.md").write_text(
            "---\nname: mixed_skill\n---\nUpper", encoding="utf-8"
        )
        sm = SkillManager(skills_dir)
        skills = sm.discover()
        # 应只发现一个（skill.md 优先）
        assert len(skills) == 1
        assert skills[0].name == "mixed_skill"

    def test_discover_warns_on_duplicate_names(self, tmp_path: Path):
        """不同目录的 skill 同名时，发出警告并跳过后者。"""
        import warnings

        skills_dir = tmp_path / "skills"
        for dirname in ("skill_a", "skill_b"):
            d = skills_dir / dirname
            d.mkdir(parents=True)
            (d / "skill.md").write_text(
                f"---\nname: same_name\n---\n{dirname}", encoding="utf-8"
            )
        sm = SkillManager(skills_dir)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            skills = sm.discover()
            assert len(skills) == 1
            assert len(w) == 1
            assert "same_name" in str(w[0].message)

    def test_parse_frontmatter_fallback_to_dirname(self, tmp_path: Path):
        """无 frontmatter name 时，使用目录名作为 Skill 名称。"""
        skill_dir = tmp_path / "skills" / "my_dir_name"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.md").write_text("Just body content", encoding="utf-8")
        sm = SkillManager(tmp_path / "skills")
        skills = sm.discover()
        assert len(skills) == 1
        assert skills[0].name == "my_dir_name"

    def test_discover_parses_tools_field(self, tmp_path: Path):
        """discover 应解析 skill 的 tools 字段。"""
        skill_dir = tmp_path / "skills" / "t1"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.md").write_text(
            "---\nname: t1\ntools: [read_file, shell]\n---\nBody",
            encoding="utf-8",
        )
        sm = SkillManager(tmp_path / "skills")
        sm.discover()
        assert sm.get_skill("t1").tools == ["read_file", "shell"]

    def test_discover_validates_tools_available(self, tmp_path: Path):
        """传入 available_tools 时，存在的工具保留在 tools 中。"""
        skill_dir = tmp_path / "skills" / "t1"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.md").write_text(
            "---\nname: t1\ntools: [read_file, shell]\n---\nBody",
            encoding="utf-8",
        )
        sm = SkillManager(tmp_path / "skills")
        sm.discover(available_tools={"read_file", "shell", "write_file"})
        skill = sm.get_skill("t1")
        assert skill.tools == ["read_file", "shell"]
        assert skill.unavailable_tools == []

    def test_discover_filters_unavailable_tools(self, tmp_path: Path):
        """不存在的工具被过滤到 unavailable_tools 并发出警告。"""
        import warnings

        skill_dir = tmp_path / "skills" / "t1"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.md").write_text(
            "---\nname: t1\ntools: [read_file, nonexistent_tool, shell]\n---\nBody",
            encoding="utf-8",
        )
        sm = SkillManager(tmp_path / "skills")
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            sm.discover(available_tools={"read_file", "shell"})
            assert any("nonexistent_tool" in str(x.message) for x in w)
        skill = sm.get_skill("t1")
        assert skill.tools == ["read_file", "shell"]
        assert skill.unavailable_tools == ["nonexistent_tool"]

    def test_discover_no_validation_without_available_tools(self, tmp_path: Path):
        """不传 available_tools 时，不做校验。"""
        skill_dir = tmp_path / "skills" / "t1"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.md").write_text(
            "---\nname: t1\ntools: [read_file, nonexistent_tool]\n---\nBody",
            encoding="utf-8",
        )
        sm = SkillManager(tmp_path / "skills")
        sm.discover()
        skill = sm.get_skill("t1")
        assert skill.tools == ["read_file", "nonexistent_tool"]
        assert skill.unavailable_tools == []

    def test_get_skill_summaries_with_tools(self, tmp_path: Path):
        """摘要应包含工具信息。"""
        skill_dir = tmp_path / "skills" / "t1"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.md").write_text(
            "---\nname: t1\ndescription: test\ntools: [read_file, shell]\n---\nBody",
            encoding="utf-8",
        )
        sm = SkillManager(tmp_path / "skills")
        sm.discover()
        summary = sm.get_skill_summaries()
        assert "[工具: read_file, shell]" in summary


# ---------------------------------------------------------------------------
# select_skill 工具
# ---------------------------------------------------------------------------


class TestSelectSkillTool:
    def test_select_skill_returns_path(self, tmp_path: Path):
        from agent.tools import execute_tool, ToolContext

        skill_dir = tmp_path / "skills" / "test"
        skill_dir.mkdir(parents=True)
        content = "---\nname: test\ndescription: desc\n---\nSkill body content"
        (skill_dir / "skill.md").write_text(content, encoding="utf-8")

        sm = SkillManager(tmp_path / "skills")
        sm.discover()

        ctx = ToolContext(work_dir=tmp_path, session_id="test", skill_manager=sm)

        result = execute_tool("select_skill", {"name": "test"}, ctx)
        assert "Skill: test" in result
        assert "文件路径:" in result
        assert "read_file" in result
        # 不应返回全文内容
        assert "Skill body content" not in result

    def test_select_skill_not_found(self, tmp_path: Path):
        from agent.tools import execute_tool, ToolContext

        sm = SkillManager(tmp_path / "skills")
        sm.discover()

        ctx = ToolContext(work_dir=tmp_path, session_id="test", skill_manager=sm)

        result = execute_tool("select_skill", {"name": "nonexistent"}, ctx)
        assert "[错误]" in result

    def test_select_skill_no_manager(self, tmp_path: Path):
        from agent.tools import execute_tool, ToolContext

        ctx = ToolContext(work_dir=tmp_path, session_id="test")
        result = execute_tool("select_skill", {"name": "x"}, ctx)
        assert "未初始化" in result

    def test_select_skill_shows_available_tools(self, tmp_path: Path):
        from agent.tools import execute_tool, ToolContext

        skill_dir = tmp_path / "skills" / "t1"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.md").write_text(
            "---\nname: t1\ntools: [read_file, shell]\n---\nBody",
            encoding="utf-8",
        )
        sm = SkillManager(tmp_path / "skills")
        sm.discover(available_tools={"read_file", "shell"})
        ctx = ToolContext(work_dir=tmp_path, session_id="test", skill_manager=sm)

        result = execute_tool("select_skill", {"name": "t1"}, ctx)
        assert "可用工具" in result
        assert "read_file" in result
        assert "shell" in result

    def test_select_skill_shows_unavailable_tools(self, tmp_path: Path):
        from agent.tools import execute_tool, ToolContext
        import warnings

        skill_dir = tmp_path / "skills" / "t1"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.md").write_text(
            "---\nname: t1\ntools: [read_file, bad_tool]\n---\nBody",
            encoding="utf-8",
        )
        sm = SkillManager(tmp_path / "skills")
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            sm.discover(available_tools={"read_file"})
        ctx = ToolContext(work_dir=tmp_path, session_id="test", skill_manager=sm)

        result = execute_tool("select_skill", {"name": "t1"}, ctx)
        assert "不可用" in result
        assert "bad_tool" in result


# ---------------------------------------------------------------------------
# format_skills_catalog
# ---------------------------------------------------------------------------


class TestFormatSkillsCatalog:
    def test_catalog_basic(self, tmp_path: Path):
        skill_dir = tmp_path / "skills" / "s1"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.md").write_text(
            "---\nname: s1\ndescription: test skill\n---\nBody",
            encoding="utf-8",
        )
        sm = SkillManager(tmp_path / "skills")
        sm.discover()
        catalog = sm.format_skills_catalog()
        assert "<available_skills>" in catalog
        assert "<name>s1</name>" in catalog
        assert "<description>test skill</description>" in catalog
        assert "<location>" in catalog

    def test_catalog_empty(self, tmp_path: Path):
        sm = SkillManager(tmp_path / "skills")
        sm.discover()
        assert sm.format_skills_catalog() == ""

    def test_catalog_with_tools(self, tmp_path: Path):
        skill_dir = tmp_path / "skills" / "s1"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.md").write_text(
            "---\nname: s1\ntools: [read_file, shell]\n---\nBody",
            encoding="utf-8",
        )
        sm = SkillManager(tmp_path / "skills")
        sm.discover()
        catalog = sm.format_skills_catalog()
        assert "<tools>read_file, shell</tools>" in catalog

    def test_catalog_without_tools(self, tmp_path: Path):
        skill_dir = tmp_path / "skills" / "s1"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.md").write_text(
            "---\nname: s1\n---\nBody",
            encoding="utf-8",
        )
        sm = SkillManager(tmp_path / "skills")
        sm.discover()
        catalog = sm.format_skills_catalog()
        assert "<tools>" not in catalog

    def test_catalog_escapes_xml(self, tmp_path: Path):
        skill_dir = tmp_path / "skills" / "s1"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.md").write_text(
            "---\nname: s1\ndescription: test <bold> & \"quoted\"\n---\nBody",
            encoding="utf-8",
        )
        sm = SkillManager(tmp_path / "skills")
        sm.discover()
        catalog = sm.format_skills_catalog()
        assert "&lt;bold&gt;" in catalog
        assert "&amp;" in catalog
        assert "&quot;quoted&quot;" in catalog

    def test_catalog_truncates_long_description(self, tmp_path: Path):
        skill_dir = tmp_path / "skills" / "s1"
        skill_dir.mkdir(parents=True)
        long_desc = "A" * 200
        (skill_dir / "skill.md").write_text(
            f"---\nname: s1\ndescription: {long_desc}\n---\nBody",
            encoding="utf-8",
        )
        sm = SkillManager(tmp_path / "skills")
        sm.discover()
        catalog = sm.format_skills_catalog(max_desc_len=50)
        # 描述应被截断
        assert "A" * 51 not in catalog
        assert "…" in catalog

    def test_catalog_budget_compact_fallback(self, tmp_path: Path):
        """超出预算时降级为精简格式。"""
        skills_dir = tmp_path / "skills"
        for i in range(5):
            d = skills_dir / f"s{i}"
            d.mkdir(parents=True)
            (d / "skill.md").write_text(
                f"---\nname: s{i}\ndescription: desc-{i}\ntools: [read_file, shell, write_file]\n---\nBody",
                encoding="utf-8",
            )
        sm = SkillManager(skills_dir)
        sm.discover()
        # 完整格式（含描述和工具）超预算，精简格式不超
        full_catalog = sm.format_skills_catalog(max_chars=99999)
        compact_budget = 600
        catalog = sm.format_skills_catalog(max_chars=compact_budget)
        # 如果完整格式已经超预算，应该降级
        if len(full_catalog) > compact_budget:
            assert "精简格式" in catalog
            assert "<description>" not in catalog
        # 无论如何，skill 名称应该在
        assert "<name>s0</name>" in catalog

    def test_catalog_budget_truncate(self, tmp_path: Path):
        """精简格式仍超预算时截断 skill 数量。"""
        skills_dir = tmp_path / "skills"
        for i in range(10):
            d = skills_dir / f"s{i}"
            d.mkdir(parents=True)
            (d / "skill.md").write_text(
                f"---\nname: s{i}\n---\nBody",
                encoding="utf-8",
            )
        sm = SkillManager(skills_dir)
        sm.discover()
        # 设置极小预算，只能容纳几个 skill
        catalog = sm.format_skills_catalog(max_chars=500)
        assert "已截断" in catalog
        assert "s0" in catalog  # 第一个应该还在

    def test_catalog_budget_zero_returns_warning(self, tmp_path: Path):
        """预算为 0 时返回警告。"""
        skill_dir = tmp_path / "skills" / "s1"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.md").write_text(
            "---\nname: s1\n---\nBody",
            encoding="utf-8",
        )
        sm = SkillManager(tmp_path / "skills")
        sm.discover()
        catalog = sm.format_skills_catalog(max_chars=0)
        assert "过大" in catalog


# ---------------------------------------------------------------------------
# _parse_metadata
# ---------------------------------------------------------------------------


class TestParseMetadata:
    def test_json_format(self):
        raw = '{"requires": {"bins": ["curl"]}, "os": ["win32"]}'
        result = _parse_metadata(raw)
        assert result["requires"]["bins"] == ["curl"]
        assert result["os"] == ["win32"]

    def test_yaml_format(self):
        raw = "requires:\n  bins:\n    - curl\nos:\n  - win32"
        result = _parse_metadata(raw)
        assert result["requires"]["bins"] == ["curl"]
        assert result["os"] == ["win32"]

    def test_empty_string(self):
        assert _parse_metadata("") == {}

    def test_none(self):
        assert _parse_metadata(None) == {}

    def test_invalid_string(self):
        assert _parse_metadata("{{invalid}}") == {}

    def test_non_dict_yaml(self):
        assert _parse_metadata("- item1\n- item2") == {}


# ---------------------------------------------------------------------------
# _check_runtime_eligibility
# ---------------------------------------------------------------------------


class TestRuntimeEligibility:
    def test_empty_metadata_eligible(self):
        eligible, _ = _check_runtime_eligibility({})
        assert eligible is True

    def test_os_match(self):
        import sys
        eligible, _ = _check_runtime_eligibility({"os": [sys.platform]})
        assert eligible is True

    def test_os_mismatch(self):
        eligible, reason = _check_runtime_eligibility({"os": ["nonexistent_platform"]})
        assert eligible is False
        assert "平台" in reason

    def test_bins_all_present(self):
        # python 应该存在
        eligible, _ = _check_runtime_eligibility(
            {"requires": {"bins": ["python"]}}
        )
        assert eligible is True

    def test_bins_missing(self):
        eligible, reason = _check_runtime_eligibility(
            {"requires": {"bins": ["nonexistent_binary_12345"]}}
        )
        assert eligible is False
        assert "缺少" in reason

    def test_any_bins_one_present(self):
        eligible, _ = _check_runtime_eligibility(
            {"requires": {"anyBins": ["nonexistent_binary_12345", "python"]}}
        )
        assert eligible is True

    def test_any_bins_none_present(self):
        eligible, reason = _check_runtime_eligibility(
            {"requires": {"anyBins": ["nonexistent_aaa", "nonexistent_bbb"]}}
        )
        assert eligible is False
        assert "均未找到" in reason

    def test_env_present(self):
        import os
        os.environ["_TEST_SKILL_ENV_VAR_"] = "1"
        try:
            eligible, _ = _check_runtime_eligibility(
                {"requires": {"env": ["_TEST_SKILL_ENV_VAR_"]}}
            )
            assert eligible is True
        finally:
            del os.environ["_TEST_SKILL_ENV_VAR_"]

    def test_env_missing(self):
        eligible, reason = _check_runtime_eligibility(
            {"requires": {"env": ["NONEXISTENT_ENV_VAR_12345"]}}
        )
        assert eligible is False
        assert "环境变量" in reason


# ---------------------------------------------------------------------------
# discover() 门控集成
# ---------------------------------------------------------------------------


class TestDiscoverGating:
    def test_ineligible_skill_filtered(self, tmp_path: Path):
        import warnings

        skill_dir = tmp_path / "skills" / "s1"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.md").write_text(
            '---\nname: s1\nmetadata:\n  os:\n    - nonexistent_platform\n---\nBody',
            encoding="utf-8",
        )
        sm = SkillManager(tmp_path / "skills")
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            skills = sm.discover()
            assert len(skills) == 0
            assert any("不满足" in str(x.message) for x in w)

    def test_eligible_skill_kept(self, tmp_path: Path):
        import sys

        skill_dir = tmp_path / "skills" / "s1"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.md").write_text(
            f'---\nname: s1\nmetadata:\n  os:\n    - {sys.platform}\n---\nBody',
            encoding="utf-8",
        )
        sm = SkillManager(tmp_path / "skills")
        skills = sm.discover()
        assert len(skills) == 1
        assert skills[0].name == "s1"
