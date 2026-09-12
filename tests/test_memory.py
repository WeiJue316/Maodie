"""
memory.py 测试。

覆盖：
  - MemoryManager: load, save, append, get_all
  - check_trigger_words
  - write_memory 工具
  - System Prompt 注入
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.memory import MemoryManager, check_trigger_words
from agent.tools import ToolContext, execute_tool


# ---------------------------------------------------------------------------
# MemoryManager
# ---------------------------------------------------------------------------


class TestMemoryManagerLoad:
    def test_load_empty_when_no_file(self, tmp_path: Path) -> None:
        mm = MemoryManager(tmp_path / "MEMORY.md")
        assert mm.load() == ""

    def test_load_reads_content(self, tmp_path: Path) -> None:
        p = tmp_path / "MEMORY.md"
        p.write_text("# 长期记忆\n\n## 用户偏好\n- 喜欢中文\n", encoding="utf-8")
        mm = MemoryManager(p)
        content = mm.load()
        assert "喜欢中文" in content


class TestMemoryManagerSave:
    def test_save_creates_file(self, tmp_path: Path) -> None:
        p = tmp_path / "MEMORY.md"
        mm = MemoryManager(p)
        mm.save("# 长期记忆\n")
        assert p.exists()
        assert "长期记忆" in p.read_text(encoding="utf-8")

    def test_save_overwrites_content(self, tmp_path: Path) -> None:
        p = tmp_path / "MEMORY.md"
        mm = MemoryManager(p)
        mm.save("旧内容")
        mm.save("新内容")
        assert mm.load() == "新内容"


class TestMemoryManagerAppend:
    def test_append_to_existing_category(self, tmp_path: Path) -> None:
        p = tmp_path / "MEMORY.md"
        p.write_text(
            "# 长期记忆\n\n## 用户偏好\n- 喜欢中文\n",
            encoding="utf-8",
        )
        mm = MemoryManager(p)
        mm.append("用户偏好", "喜欢简洁回答")
        content = mm.load()
        assert "喜欢简洁回答" in content
        assert "喜欢中文" in content

    def test_append_creates_new_category(self, tmp_path: Path) -> None:
        p = tmp_path / "MEMORY.md"
        p.write_text(
            "# 长期记忆\n\n## 用户偏好\n- 喜欢中文\n",
            encoding="utf-8",
        )
        mm = MemoryManager(p)
        mm.append("项目约束", "API 必须有超时")
        content = mm.load()
        assert "项目约束" in content
        assert "API 必须有超时" in content

    def test_append_to_empty_file(self, tmp_path: Path) -> None:
        p = tmp_path / "MEMORY.md"
        mm = MemoryManager(p)
        mm.append("用户偏好", "喜欢中文")
        content = mm.load()
        assert "用户偏好" in content
        assert "喜欢中文" in content

    def test_append_inserts_at_category_end(self, tmp_path: Path) -> None:
        """新条目应插入到该分类的最后，而非下一个分类之前。"""
        p = tmp_path / "MEMORY.md"
        p.write_text(
            "# 长期记忆\n\n## 用户偏好\n- 喜欢中文\n\n## 项目约束\n- API 超时\n",
            encoding="utf-8",
        )
        mm = MemoryManager(p)
        mm.append("用户偏好", "喜欢简洁")
        content = mm.load()
        lines = content.splitlines()
        # "喜欢简洁" 应在 "喜欢中文" 之后、"项目约束" 之前
        pref_idx = next(i for i, l in enumerate(lines) if "喜欢简洁" in l)
        constraint_idx = next(i for i, l in enumerate(lines) if "## 项目约束" in l)
        assert pref_idx < constraint_idx


class TestMemoryManagerGetAll:
    def test_get_all_parses_categories(self, tmp_path: Path) -> None:
        p = tmp_path / "MEMORY.md"
        p.write_text(
            "# 长期记忆\n\n## 用户偏好\n- 喜欢中文\n- 喜欢简洁\n\n## 项目约束\n- API 超时\n",
            encoding="utf-8",
        )
        mm = MemoryManager(p)
        result = mm.get_all()
        assert "用户偏好" in result
        assert "项目约束" in result
        assert result["用户偏好"] == ["喜欢中文", "喜欢简洁"]
        assert result["项目约束"] == ["API 超时"]

    def test_get_all_empty_file(self, tmp_path: Path) -> None:
        mm = MemoryManager(tmp_path / "MEMORY.md")
        assert mm.get_all() == {}


# ---------------------------------------------------------------------------
# check_trigger_words
# ---------------------------------------------------------------------------


class TestTriggerWords:
    DEFAULT_TRIGGERS = [
        "记住", "记一下", "记着", "别忘了",
        "remember", "keep in mind", "don't forget",
    ]

    def test_trigger_word_detected_chinese(self) -> None:
        assert check_trigger_words("记住我喜欢中文", self.DEFAULT_TRIGGERS) is True

    def test_trigger_word_detected_english(self) -> None:
        assert check_trigger_words("remember my name", self.DEFAULT_TRIGGERS) is True

    def test_no_trigger_word(self) -> None:
        assert check_trigger_words("今天天气怎么样", self.DEFAULT_TRIGGERS) is False

    def test_trigger_word_case_insensitive(self) -> None:
        assert check_trigger_words("Remember this", self.DEFAULT_TRIGGERS) is True

    def test_trigger_word_in_middle(self) -> None:
        assert check_trigger_words("请帮我记一下这个规则", self.DEFAULT_TRIGGERS) is True


# ---------------------------------------------------------------------------
# write_memory 工具
# ---------------------------------------------------------------------------


class TestWriteMemoryTool:
    def test_write_memory_tool(self, tmp_path: Path) -> None:
        mm = MemoryManager(tmp_path / "MEMORY.md")
        ctx = ToolContext(
            work_dir=tmp_path,
            session_id="test",
            memory_manager=mm,
        )
        result = execute_tool(
            "write_memory",
            {"category": "用户偏好", "content": "喜欢中文"},
            ctx,
        )
        assert "已记住" in result
        assert "喜欢中文" in mm.load()

    def test_write_memory_no_manager(self, tmp_path: Path) -> None:
        ctx = ToolContext(work_dir=tmp_path, session_id="test")
        result = execute_tool(
            "write_memory",
            {"category": "用户偏好", "content": "喜欢中文"},
            ctx,
        )
        assert "未初始化" in result


# ---------------------------------------------------------------------------
# System Prompt 注入（集成测试）
# ---------------------------------------------------------------------------


class TestMemoryInjection:
    def test_memory_injected_to_system_prompt(
        self, tmp_path: Path, default_config, empty_session
    ) -> None:
        from agent.loop import AgentLoop
        from unittest.mock import MagicMock

        # 写入记忆文件
        memory_path = tmp_path / "MEMORY.md"
        memory_path.write_text(
            "# 长期记忆\n\n## 用户偏好\n- 喜欢中文\n",
            encoding="utf-8",
        )

        mm = MemoryManager(memory_path)
        default_config.memory.auto_inject = True

        mock_llm = MagicMock()
        loop = AgentLoop(default_config, empty_session, mock_llm, memory_manager=mm)
        loop.ensure_system_prompt()

        system_msg = empty_session.messages[0]
        assert "喜欢中文" in system_msg["content"]
        assert "长期记忆" in system_msg["content"]

    def test_no_injection_when_disabled(
        self, tmp_path: Path, default_config, empty_session
    ) -> None:
        from agent.loop import AgentLoop
        from unittest.mock import MagicMock

        memory_path = tmp_path / "MEMORY.md"
        memory_path.write_text(
            "# 长期记忆\n\n## 用户偏好\n- 喜欢中文\n",
            encoding="utf-8",
        )

        mm = MemoryManager(memory_path)
        default_config.memory.auto_inject = False

        mock_llm = MagicMock()
        loop = AgentLoop(default_config, empty_session, mock_llm, memory_manager=mm)
        loop.ensure_system_prompt()

        system_msg = empty_session.messages[0]
        assert "喜欢中文" not in system_msg["content"]
