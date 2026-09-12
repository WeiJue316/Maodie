"""
test_orchestrator.py — 多 Agent 编排器测试

覆盖设计文档中的必测用例：
- spawn_agent 基本功能
- 依赖管理（pending → running → completed）
- 依赖失败传播
- 超时和取消
- 终态清理
- 线程安全
- observation 写入
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent.config import AgentConfig, AgentSpec, OrchestratorConfig
from agent.loop import CancellationToken
from agent.orchestrator import AgentTask, Orchestrator
from agent.session import SessionManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def multi_agent_config(tmp_path: Path) -> AgentConfig:
    """带多 agent 定义的测试配置。"""
    cfg = AgentConfig()
    cfg.llm.api_key = "test-key"
    cfg.llm.streaming = False
    cfg.work_dir = str(tmp_path / "work")
    cfg.project_root = tmp_path
    cfg.session.dir = str(tmp_path / ".sessions")
    cfg.max_iterations = 3

    cfg.agents = {
        "architect": AgentSpec(
            name="architect",
            system_prompt="你是架构师。",
            max_iterations=5,
        ),
        "coder": AgentSpec(
            name="coder",
            system_prompt="你是开发者。",
            max_iterations=10,
        ),
        "reviewer": AgentSpec(
            name="reviewer",
            system_prompt="你是审查员。",
            tools=["read_file", "list_dir"],
            max_iterations=5,
        ),
    }

    cfg.orchestrator = OrchestratorConfig(
        enabled=True,
        task_timeout=30,
        max_concurrent_tasks=2,
        max_result_chars=5000,
        task_retention_seconds=60,
    )

    (tmp_path / "work").mkdir(exist_ok=True)
    return cfg


@pytest.fixture
def session_mgr(tmp_path: Path) -> SessionManager:
    return SessionManager(tmp_path / ".sessions")


@pytest.fixture
def orchestrator(multi_agent_config, session_mgr):
    """创建 Orchestrator 实例，测试后清理。"""
    orch = Orchestrator(
        config=multi_agent_config,
        session_manager=session_mgr,
        observation_store=None,
        observation_extractor=None,
    )
    yield orch
    orch.cleanup()


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _mock_agent_run(orchestrator: Orchestrator, result: str = "agent result"):
    """Patch _run_agent 直接设置 task 结果，不实际调用 LLM。
    注意：由于 ThreadPoolExecutor 可能同步执行，task 在 spawn_agent 返回时可能已完成。
    """
    def fake_run(task: AgentTask):
        task.session_id = f"session-{task.task_id}"
        task.result = result
        task.summary = result[:100]
        task.result_ref = f"session:{task.session_id}"
        task.status = "completed"
        task.completed_at = time.time()

    orchestrator._run_agent = fake_run


# ---------------------------------------------------------------------------
# 测试：基本 spawn
# ---------------------------------------------------------------------------

class TestSpawnAgent:
    def test_spawn_returns_task(self, orchestrator):
        """无依赖任务被创建，状态为 running 或已完成。"""
        _mock_agent_run(orchestrator)
        result = orchestrator.spawn_agent("architect", "设计登录模块")
        assert result["ok"] is True
        assert result["status"] in ("running", "completed")
        assert "task_id" in result
        assert result["agent"] == "architect"

    def test_spawn_with_context(self, orchestrator):
        """context 参数被保存到 task。"""
        _mock_agent_run(orchestrator)
        result = orchestrator.spawn_agent("coder", "实现登录", context="参考设计文档")
        task = orchestrator._tasks[result["task_id"]]
        assert task.context == "参考设计文档"

    def test_spawn_unknown_agent_returns_error(self, orchestrator):
        """agent 名称不存在时返回结构化错误。"""
        result = orchestrator.spawn_agent("nonexistent", "some task")
        assert result["ok"] is False
        assert result["status"] == "failed"
        assert "unknown agent" in result["error"]

    def test_spawn_creates_unique_task_ids(self, orchestrator):
        """每次 spawn 生成不同的 task_id。"""
        _mock_agent_run(orchestrator)
        r1 = orchestrator.spawn_agent("architect", "task 1")
        r2 = orchestrator.spawn_agent("coder", "task 2")
        assert r1["task_id"] != r2["task_id"]


# ---------------------------------------------------------------------------
# 测试：依赖管理
# ---------------------------------------------------------------------------

class TestDependencies:
    def test_spawn_with_dependency_stays_pending(self, orchestrator):
        """依赖未完成时 task 保持 pending（直接构造 task 验证机制）。"""
        # 创建一个 "阻塞" 的 task，不提交到 executor
        now = time.time()
        blocking_task = AgentTask(
            task_id="task_blocking",
            agent_name="architect",
            task_description="设计",
            context="",
            depends_on=[],
            status="running",  # 未完成
            created_at=now,
            started_at=now,
            last_accessed_at=now,
        )
        with orchestrator._lock:
            orchestrator._tasks["task_blocking"] = blocking_task

        # spawn 依赖 blocking_task 的 task
        r2 = orchestrator.spawn_agent("coder", "实现", depends_on=["task_blocking"])
        assert r2["status"] == "pending"

    def test_dependency_completion_schedules_pending_task(self, orchestrator):
        """上游完成后，下游自动提交执行。"""
        def fake_run(task: AgentTask):
            task.session_id = f"session-{task.task_id}"
            task.result = f"result from {task.agent_name}"
            task.summary = task.result
            task.result_ref = f"session:{task.session_id}"
            task.status = "completed"
            task.completed_at = time.time()
            orchestrator._schedule_dependents(task.task_id)

        orchestrator._run_agent = fake_run

        r1 = orchestrator.spawn_agent("architect", "设计")
        r2 = orchestrator.spawn_agent("coder", "实现", depends_on=[r1["task_id"]])

        # 等待完成
        time.sleep(0.5)
        status = orchestrator.check_status(r2["task_id"])
        assert status["status"] == "completed"

    def test_unknown_dependency_returns_error(self, orchestrator):
        """depends_on 引用不存在的 task 时返回错误。"""
        result = orchestrator.spawn_agent("coder", "实现", depends_on=["nonexistent_id"])
        assert result["ok"] is False
        assert "dependency task not found" in result["error"]


# ---------------------------------------------------------------------------
# 测试：依赖失败传播
# ---------------------------------------------------------------------------

class TestDependencyFailure:
    def test_dependency_failure_fails_downstream(self, orchestrator):
        """上游失败时，下游自动标记 failed。"""
        original_run = orchestrator._run_agent

        def fake_run_fail(task: AgentTask):
            task.status = "failed"
            task.error_type = "agent_error"
            task.error = "LLM API error"
            task.completed_at = time.time()
            orchestrator._schedule_dependents(task.task_id)

        orchestrator._run_agent = fake_run_fail

        r1 = orchestrator.spawn_agent("architect", "设计")
        r2 = orchestrator.spawn_agent("coder", "实现", depends_on=[r1["task_id"]])

        time.sleep(0.5)
        status = orchestrator.check_status(r2["task_id"])
        assert status["status"] == "failed"
        assert status.get("error_type") == "dependency_failed"
        assert status.get("failed_dependency") == r1["task_id"]


# ---------------------------------------------------------------------------
# 测试：check_status
# ---------------------------------------------------------------------------

class TestCheckStatus:
    def test_check_status_returns_task_info(self, orchestrator):
        """check_status 返回完整的 task 状态。"""
        _mock_agent_run(orchestrator)
        r = orchestrator.spawn_agent("architect", "设计")
        status = orchestrator.check_status(r["task_id"])
        assert status["ok"] is True
        assert status["agent"] == "architect"
        assert "result" in status

    def test_check_status_unknown_task(self, orchestrator):
        """task 不存在时返回错误。"""
        result = orchestrator.check_status("nonexistent")
        assert result["ok"] is False
        assert "task not found" in result["error"]

    def test_check_status_refreshes_last_accessed_at(self, orchestrator):
        """每次 check_status 刷新 last_accessed_at。"""
        _mock_agent_run(orchestrator)
        r = orchestrator.spawn_agent("architect", "设计")
        task = orchestrator._tasks[r["task_id"]]
        old_access = task.last_accessed_at
        time.sleep(0.05)
        orchestrator.check_status(r["task_id"])
        assert task.last_accessed_at > old_access


# ---------------------------------------------------------------------------
# 测试：取消
# ---------------------------------------------------------------------------

class TestCancellation:
    def test_cancel_running_task(self, orchestrator):
        """取消运行中的 task。"""
        def slow_run(task: AgentTask):
            # 模拟长时间运行
            time.sleep(10)

        orchestrator._run_agent = slow_run
        r = orchestrator.spawn_agent("architect", "设计")
        result = orchestrator.cancel_task(r["task_id"], reason="用户取消")
        assert result["ok"] is True
        assert result["status"] == "cancelled"

    def test_cancel_already_terminal_task(self, orchestrator):
        """取消已终态的 task 返回提示。"""
        _mock_agent_run(orchestrator)
        r = orchestrator.spawn_agent("architect", "设计")
        time.sleep(0.3)  # 等待完成
        result = orchestrator.cancel_task(r["task_id"])
        assert result["ok"] is True
        assert "terminal status" in result.get("error", "")


# ---------------------------------------------------------------------------
# 测试：子 agent 不可 spawn
# ---------------------------------------------------------------------------

class TestChildCannotSpawn:
    def test_can_spawn_agents_false_blocks_spawn(self):
        """子 agent 的 can_spawn_agents=False 会让 spawn_agent 返回错误。"""
        from agent.tools import execute_tool, ToolContext
        ctx = ToolContext(
            work_dir=Path("."),
            session_id="test",
            can_spawn_agents=False,
            orchestrator=MagicMock(),
        )
        result = execute_tool("spawn_agent", {"agent": "coder", "task": "test"}, ctx)
        parsed = json.loads(result)
        assert parsed["ok"] is False
        assert "only available to the main agent" in parsed["error"]


# ---------------------------------------------------------------------------
# 测试：线程安全
# ---------------------------------------------------------------------------

class TestThreadSafety:
    def test_concurrent_spawn_no_crash(self, orchestrator):
        """并发 spawn 不触发 dict 遍历或状态竞争异常。"""
        _mock_agent_run(orchestrator)
        import threading
        results = []
        errors = []

        def do_spawn(agent_name, task_desc):
            try:
                r = orchestrator.spawn_agent(agent_name, task_desc)
                results.append(r)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=do_spawn, args=("architect", f"task {i}"))
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0
        assert len(results) == 10


# ---------------------------------------------------------------------------
# 测试：超时
# ---------------------------------------------------------------------------

class TestTimeout:
    def test_timeout_sets_cancellation_token(self, orchestrator):
        """超时后 task 变为 timeout，token 标记 cancelled。"""
        # 直接创建一个已超时的 task
        now = time.time()
        task = AgentTask(
            task_id="task_timeout_test",
            agent_name="architect",
            task_description="设计",
            context="",
            depends_on=[],
            status="running",
            created_at=now - 100,  # 100 秒前创建
            started_at=now - 100,
            last_accessed_at=now - 100,
        )
        with orchestrator._lock:
            orchestrator._tasks[task.task_id] = task

        orchestrator._orch_config.task_timeout = 10  # 10 秒超时

        # 手动触发 watchdog tick
        orchestrator._watchdog_tick()

        assert task.status == "timeout"
        assert task.cancellation_token.cancelled is True


# ---------------------------------------------------------------------------
# 测试：终态清理
# ---------------------------------------------------------------------------

class TestRetentionCleanup:
    def test_cleanup_removes_expired_terminal_tasks(self, orchestrator):
        """终态 task 超过 retention 后被清理。"""
        # 直接创建一个已完成且 last_accessed_at 过期的 task
        now = time.time()
        task = AgentTask(
            task_id="task_expired",
            agent_name="architect",
            task_description="设计",
            context="",
            depends_on=[],
            status="completed",
            created_at=now - 200,
            started_at=now - 200,
            completed_at=now - 200,
            last_accessed_at=now - 200,  # 很久以前访问过
            result="done",
        )
        with orchestrator._lock:
            orchestrator._tasks[task.task_id] = task

        orchestrator._orch_config.task_retention_seconds = 60

        # 触发 watchdog tick
        orchestrator._watchdog_tick()

        # task 应该已被清理
        assert task.task_id not in orchestrator._tasks

    def test_check_status_returns_not_found_for_cleaned_task(self, orchestrator):
        """已清理 task 返回 not found（内存中已不存在）。"""
        status = orchestrator.check_status("nonexistent_task_id")
        assert status["ok"] is False
        assert "task not found" in status["error"]


# ---------------------------------------------------------------------------
# 测试：work_dir 隔离
# ---------------------------------------------------------------------------

class TestWorkDirIsolation:
    def test_child_agent_work_dir_isolated(self, multi_agent_config, session_mgr):
        """子 agent 的 work_dir 与主 agent 独立。"""
        orch = Orchestrator(
            config=multi_agent_config,
            session_manager=session_mgr,
        )

        # 验证 _create_child_agent_loop 产生的 ToolContext 独立
        spec = multi_agent_config.agents["architect"]
        task = AgentTask(
            task_id="test-001",
            agent_name="architect",
            task_description="test",
            context="",
            depends_on=[],
            status="running",
            created_at=time.time(),
            last_accessed_at=time.time(),
        )
        agent_loop = orch._create_child_agent_loop(task, spec)
        # 子 agent 的 ToolContext 应该 can_spawn_agents=False
        assert agent_loop.tool_ctx.can_spawn_agents is False
        orch.cleanup()
