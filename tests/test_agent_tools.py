"""
test_agent_tools.py — 多 Agent 工具测试

覆盖 spawn_agent 和 check_agent_status 工具的各种场景。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agent.tools import ToolContext, execute_tool


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_orchestrator():
    """Mock Orchestrator。"""
    orch = MagicMock()
    orch.spawn_agent.return_value = {
        "ok": True,
        "task_id": "task_abc123",
        "agent": "coder",
        "status": "running",
    }
    orch.check_status.return_value = {
        "ok": True,
        "task_id": "task_abc123",
        "agent": "coder",
        "status": "completed",
        "result": "已完成实现",
    }
    return orch


@pytest.fixture
def main_agent_ctx(tmp_path, mock_orchestrator) -> ToolContext:
    """主 agent 的 ToolContext（can_spawn_agents=True）。"""
    return ToolContext(
        work_dir=tmp_path,
        session_id="main-session",
        orchestrator=mock_orchestrator,
        can_spawn_agents=True,
    )


@pytest.fixture
def child_agent_ctx(tmp_path, mock_orchestrator) -> ToolContext:
    """子 agent 的 ToolContext（can_spawn_agents=False）。"""
    return ToolContext(
        work_dir=tmp_path,
        session_id="child-session",
        orchestrator=mock_orchestrator,
        can_spawn_agents=False,
    )


@pytest.fixture
def no_orchestrator_ctx(tmp_path) -> ToolContext:
    """没有 orchestrator 的 ToolContext。"""
    return ToolContext(
        work_dir=tmp_path,
        session_id="test-session",
        orchestrator=None,
        can_spawn_agents=True,
    )


# ---------------------------------------------------------------------------
# 测试：spawn_agent
# ---------------------------------------------------------------------------

class TestSpawnAgentTool:
    def test_spawn_success(self, main_agent_ctx, mock_orchestrator):
        """主 agent 成功 spawn 子 agent。"""
        result = execute_tool("spawn_agent", {
            "agent": "coder",
            "task": "实现登录模块",
        }, main_agent_ctx)
        parsed = json.loads(result)
        assert parsed["ok"] is True
        assert parsed["task_id"] == "task_abc123"
        mock_orchestrator.spawn_agent.assert_called_once_with(
            agent_name="coder",
            task_description="实现登录模块",
            context="",
            depends_on=[],
        )

    def test_spawn_with_context(self, main_agent_ctx, mock_orchestrator):
        """spawn_agent 传递 context 参数。"""
        execute_tool("spawn_agent", {
            "agent": "coder",
            "task": "实现登录",
            "context": "参考架构师设计",
        }, main_agent_ctx)
        mock_orchestrator.spawn_agent.assert_called_once_with(
            agent_name="coder",
            task_description="实现登录",
            context="参考架构师设计",
            depends_on=[],
        )

    def test_spawn_with_depends_on(self, main_agent_ctx, mock_orchestrator):
        """spawn_agent 传递 depends_on 参数。"""
        execute_tool("spawn_agent", {
            "agent": "coder",
            "task": "实现登录",
            "depends_on": ["task_arch_001"],
        }, main_agent_ctx)
        mock_orchestrator.spawn_agent.assert_called_once_with(
            agent_name="coder",
            task_description="实现登录",
            context="",
            depends_on=["task_arch_001"],
        )

    def test_spawn_blocked_for_child_agent(self, child_agent_ctx):
        """子 agent 调用 spawn_agent 返回结构化错误。"""
        result = execute_tool("spawn_agent", {
            "agent": "coder",
            "task": "test",
        }, child_agent_ctx)
        parsed = json.loads(result)
        assert parsed["ok"] is False
        assert "only available to the main agent" in parsed["error"]

    def test_spawn_no_orchestrator(self, no_orchestrator_ctx):
        """orchestrator 未初始化时返回错误。"""
        result = execute_tool("spawn_agent", {
            "agent": "coder",
            "task": "test",
        }, no_orchestrator_ctx)
        parsed = json.loads(result)
        assert parsed["ok"] is False
        assert "orchestrator is not configured" in parsed["error"]


# ---------------------------------------------------------------------------
# 测试：check_agent_status
# ---------------------------------------------------------------------------

class TestCheckAgentStatusTool:
    def test_check_status_success(self, main_agent_ctx, mock_orchestrator):
        """查询 task 状态成功。"""
        result = execute_tool("check_agent_status", {
            "task_id": "task_abc123",
        }, main_agent_ctx)
        parsed = json.loads(result)
        assert parsed["ok"] is True
        assert parsed["status"] == "completed"
        mock_orchestrator.check_status.assert_called_once_with("task_abc123")

    def test_check_status_no_orchestrator(self, no_orchestrator_ctx):
        """orchestrator 未初始化时返回错误。"""
        result = execute_tool("check_agent_status", {
            "task_id": "task_abc123",
        }, no_orchestrator_ctx)
        parsed = json.loads(result)
        assert parsed["ok"] is False
        assert "orchestrator is not configured" in parsed["error"]

    def test_check_status_can_be_called_by_child(self, child_agent_ctx, mock_orchestrator):
        """子 agent 也可以调用 check_agent_status（查看自己依赖的 task）。"""
        result = execute_tool("check_agent_status", {
            "task_id": "task_abc123",
        }, child_agent_ctx)
        parsed = json.loads(result)
        assert parsed["ok"] is True
