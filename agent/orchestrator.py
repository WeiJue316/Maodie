"""
多 Agent 编排器。

管理子 Agent 任务的生命周期：创建、执行、状态查询、超时、取消、清理。
子 Agent 在 ThreadPoolExecutor 中并行运行，通过共享 Observation Store 交换信息。
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .config import AgentConfig, AgentSpec, OrchestratorConfig
from .llm import LLMClient
from .loop import AgentLoop, CancellationToken
from .observation import Observation, ObservationStore
from .session import Session, SessionManager
from .tools import ToolContext

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = {"completed", "failed", "timeout", "cancelled"}


# ---------------------------------------------------------------------------
# AgentTask
# ---------------------------------------------------------------------------

@dataclass
class AgentTask:
    """一个子 Agent 任务的完整状态。"""
    task_id: str
    agent_name: str
    task_description: str
    context: str
    depends_on: list[str]
    status: str                          # pending | running | completed | failed | timeout | cancelled
    created_at: float
    started_at: float | None = None
    completed_at: float | None = None
    result: str | None = None
    summary: str | None = None
    result_ref: str | None = None
    error: str | None = None
    error_type: str | None = None        # dependency_failed | agent_error | timeout | cancelled
    failed_dependency: str | None = None
    session_id: str | None = None
    last_accessed_at: float = 0.0
    cancellation_token: CancellationToken = field(default_factory=CancellationToken)
    future: Future | None = None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class Orchestrator:
    """多 Agent 编排器。"""

    def __init__(
        self,
        config: AgentConfig,
        session_manager: SessionManager,
        observation_store: ObservationStore | None = None,
        observation_extractor: Any | None = None,
    ) -> None:
        self._config = config
        self._orch_config: OrchestratorConfig = config.orchestrator
        self._session_manager = session_manager
        self._observation_store = observation_store
        self._observation_extractor = observation_extractor
        self._tasks: dict[str, AgentTask] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=self._orch_config.max_concurrent_tasks,
        )
        self._watchdog_stop = threading.Event()
        self._watchdog_thread = threading.Thread(
            target=self._watchdog, daemon=True, name="orchestrator-watchdog"
        )
        self._watchdog_thread.start()

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def spawn_agent(
        self,
        agent_name: str,
        task_description: str,
        context: str = "",
        depends_on: list[str] | None = None,
    ) -> dict[str, Any]:
        """创建子 agent 任务，返回结构化结果。"""
        depends_on = depends_on or []

        # 校验 agent 名称
        if agent_name not in self._config.agents:
            return {
                "ok": False,
                "status": "failed",
                "error": f"unknown agent: {agent_name}",
            }

        # 校验 depends_on 引用
        with self._lock:
            for dep_id in depends_on:
                if dep_id not in self._tasks:
                    return {
                        "ok": False,
                        "status": "failed",
                        "error": f"dependency task not found: {dep_id}",
                    }

        now = time.time()
        task = AgentTask(
            task_id=f"task_{uuid.uuid4().hex[:8]}",
            agent_name=agent_name,
            task_description=task_description,
            context=context,
            depends_on=list(depends_on),
            status="pending",
            created_at=now,
            last_accessed_at=now,
        )

        with self._lock:
            self._tasks[task.task_id] = task

            # 检查依赖是否全部完成
            if self._dependencies_completed(task):
                # 检查依赖是否有失败
                dep_failure = self._check_dependency_failures(task)
                if dep_failure:
                    task.status = "failed"
                    task.error_type = "dependency_failed"
                    task.failed_dependency = dep_failure["failed_dep"]
                    task.error = dep_failure["error"]
                    task.completed_at = now
                    return self._task_to_response(task)

                task.status = "running"
                task.started_at = now
                task.future = self._executor.submit(self._run_agent, task)
            # 否则保持 pending，由 watchdog 调度

        return self._task_to_response(task)

    def check_status(self, task_id: str) -> dict[str, Any]:
        """查询 task 状态，刷新 last_accessed_at。"""
        with self._lock:
            task = self._tasks.get(task_id)

        if task is None:
            return {
                "ok": False,
                "status": "failed",
                "error": f"task not found: {task_id}",
            }

        # 刷新 last_accessed_at
        with self._lock:
            task.last_accessed_at = time.time()

        return self._task_to_response(task)

    def cancel_task(self, task_id: str, reason: str = "") -> dict[str, Any]:
        """协作式取消任务。"""
        with self._lock:
            task = self._tasks.get(task_id)

        if task is None:
            return {
                "ok": False,
                "status": "failed",
                "error": f"task not found: {task_id}",
            }

        with self._lock:
            if task.status in TERMINAL_STATUSES:
                return {
                    "ok": True,
                    "status": task.status,
                    "error": f"task already in terminal status: {task.status}",
                }
            task.cancellation_token.cancelled = True
            task.cancellation_token.reason = reason or "user_cancelled"
            task.status = "cancelled"
            task.completed_at = time.time()
            task.error = f"Cancelled: {reason or 'user_cancelled'}"

        return {"ok": True, "task_id": task_id, "status": "cancelled"}

    def cleanup(self) -> None:
        """停止 watchdog，关闭 executor。"""
        self._watchdog_stop.set()
        self._executor.shutdown(wait=False)

    # ------------------------------------------------------------------
    # 任务执行
    # ------------------------------------------------------------------

    def _run_agent(self, task: AgentTask) -> None:
        """在线程中执行子 agent。"""
        try:
            # 检查取消
            if task.cancellation_token.cancelled:
                task.status = "cancelled"
                task.completed_at = time.time()
                return

            # 收集依赖上下文
            dependency_context = self._collect_dependency_context(task)
            if dependency_context.get("has_failures"):
                task.status = "failed"
                task.error_type = "dependency_failed"
                task.failed_dependency = dependency_context["first_failed"]
                task.error = f"Upstream task {task.failed_dependency} failed: {dependency_context['first_error']}"
                task.completed_at = time.time()
                return

            # 构建子 agent 完整输入
            full_input = task.task_description
            if dependency_context.get("summaries"):
                full_input += "\n\n## 依赖任务的输出\n\n" + "\n\n".join(dependency_context["summaries"])
            if task.context:
                full_input += f"\n\n## 补充上下文\n\n{task.context}"

            # 创建子 agent 的 AgentLoop
            agent_spec = self._config.agents[task.agent_name]
            agent_loop = self._create_child_agent_loop(task, agent_spec)
            task.session_id = agent_loop.session.id

            # 运行
            result = agent_loop.run(full_input)

            # 保存 session
            self._session_manager.save_session(agent_loop.session)

            # 截断 result
            max_chars = self._orch_config.max_result_chars
            if len(result) > max_chars:
                task.result = result[:max_chars] + "...[truncated]"
                task.summary = self._summarize_result(result)
            else:
                task.result = result
                task.summary = self._summarize_result(result)

            task.result_ref = f"session:{task.session_id}"
            task.status = "completed"
            task.completed_at = time.time()

            # 写入 observation store
            self._persist_observation(task, result)

            # 调度依赖此 task 的 pending tasks
            self._schedule_dependents(task.task_id)

        except Exception as e:
            task.status = "failed"
            task.error_type = "agent_error"
            task.error = str(e)
            task.completed_at = time.time()
            logger.exception("Agent %s (task %s) failed", task.agent_name, task.task_id)

    def _create_child_agent_loop(self, task: AgentTask, spec: AgentSpec) -> AgentLoop:
        """创建子 agent 的 AgentLoop 实例。"""
        # 派生子 agent config（不修改主 config）
        child_config = AgentConfig(
            llm=self._config.llm,
            session=self._config.session,
            skills=self._config.skills,
            memory=self._config.memory,
            observation=self._config.observation,
            vectordb=self._config.vectordb,
            memory_search=self._config.memory_search,
            mcp_servers=self._config.mcp_servers,
            max_iterations=spec.max_iterations or self._config.max_iterations,
            work_dir=str(self._config.resolved_work_dir()),
            system_prompt=spec.system_prompt or self._config.system_prompt,
            enabled_tools=spec.tools or list(self._config.enabled_tools),
            config_path=self._config.config_path,
            project_root=self._config.project_root,
        )

        # 创建独立 LLMClient（如果 agent 指定了不同 model）
        if spec.model and spec.model != self._config.llm.model:
            from .config import LLMConfig
            child_llm_config = LLMConfig(
                provider=self._config.llm.provider,
                api_key=self._config.llm.api_key,
                base_url=self._config.llm.base_url,
                model=spec.model,
                temperature=self._config.llm.temperature,
                timeout=self._config.llm.timeout,
                max_retries=self._config.llm.max_retries,
                streaming=self._config.llm.streaming,
            )
            child_llm = LLMClient(child_llm_config)
        else:
            child_llm = LLMClient(self._config.llm)

        # 创建独立 session
        session = self._session_manager.new_session(
            work_dir=str(self._config.resolved_work_dir())
        )

        # 创建 ToolContext，can_spawn_agents=False
        tool_ctx = ToolContext(
            work_dir=self._config.resolved_work_dir(),
            session_id=session.id,
            skill_manager=None,  # 子 agent 不需要 skill 管理
            memory_manager=None,
            memory_search=None,
            mcp_manager=None,
            orchestrator=None,
            can_spawn_agents=False,
        )

        agent_loop = AgentLoop(
            config=child_config,
            session=session,
            llm=child_llm,
        )
        # 覆盖 ToolContext
        agent_loop._tool_ctx = tool_ctx

        return agent_loop

    # ------------------------------------------------------------------
    # 依赖处理
    # ------------------------------------------------------------------

    def _dependencies_completed(self, task: AgentTask) -> bool:
        """检查所有依赖是否已完成（调用者需持有锁或在锁外调用）。"""
        for dep_id in task.depends_on:
            dep = self._tasks.get(dep_id)
            if dep is None or dep.status not in TERMINAL_STATUSES:
                return False
        return True

    def _check_dependency_failures(self, task: AgentTask) -> dict | None:
        """检查依赖是否有失败。返回第一个失败依赖的信息，无失败返回 None。"""
        for dep_id in task.depends_on:
            dep = self._tasks.get(dep_id)
            if dep and dep.status in ("failed", "timeout", "cancelled"):
                return {
                    "failed_dep": dep_id,
                    "error": dep.error or f"dependency {dep_id} status: {dep.status}",
                }
        return None

    def _collect_dependency_context(self, task: AgentTask) -> dict[str, Any]:
        """收集已完成依赖的摘要和失败信息。"""
        result: dict[str, Any] = {
            "summaries": [],
            "has_failures": False,
            "first_failed": None,
            "first_error": None,
        }

        with self._lock:
            for dep_id in task.depends_on:
                dep = self._tasks.get(dep_id)
                if dep is None:
                    continue

                if dep.status in ("failed", "timeout", "cancelled"):
                    result["has_failures"] = True
                    if result["first_failed"] is None:
                        result["first_failed"] = dep_id
                        result["first_error"] = dep.error or f"status: {dep.status}"
                elif dep.status == "completed" and dep.summary:
                    result["summaries"].append(
                        f"### [{dep.agent_name}] {dep.task_description[:50]}\n\n{dep.summary}"
                    )

        return result

    def _schedule_dependents(self, completed_task_id: str) -> None:
        """调度所有依赖 completed_task_id 的 pending tasks。"""
        with self._lock:
            for task in self._tasks.values():
                if task.status != "pending":
                    continue
                if completed_task_id not in task.depends_on:
                    continue
                if not self._dependencies_completed(task):
                    continue

                # 检查依赖失败
                dep_failure = self._check_dependency_failures(task)
                if dep_failure:
                    task.status = "failed"
                    task.error_type = "dependency_failed"
                    task.failed_dependency = dep_failure["failed_dep"]
                    task.error = dep_failure["error"]
                    task.completed_at = time.time()
                    continue

                task.status = "running"
                task.started_at = time.time()
                task.future = self._executor.submit(self._run_agent, task)

    # ------------------------------------------------------------------
    # Observation 写入
    # ------------------------------------------------------------------

    def _persist_observation(self, task: AgentTask, result: str) -> None:
        """将子 agent 产出写入共享 observation store。"""
        if not self._observation_store:
            return

        # 优先使用 ObservationExtractor
        if self._observation_extractor and task.session_id:
            try:
                observations = self._observation_extractor.extract_from_session(task.session_id)
                if observations:
                    self._observation_store.insert_batch(observations)
                    task.result_ref = f"session:{task.session_id}"
                    return
            except Exception as e:
                logger.warning("ObservationExtractor failed for task %s: %s", task.task_id, e)

        # fallback：写入一条轻量 observation
        type_map = {
            "architect": "decision",
            "coder": "feature",
            "reviewer": "discovery",
        }
        obs_type = type_map.get(task.agent_name, "change")

        observation = Observation(
            id=str(uuid.uuid4()),
            type=obs_type,
            title=f"[{task.agent_name}] {task.task_description[:50]}",
            narrative=result[:2000],  # 限制长度
            facts=[],
            concepts=[task.agent_name],
            files_read=[],
            files_modified=[],
            session_id=task.session_id or "",
            created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            relevance_count=0,
            content_hash=hashlib.sha256(
                ((task.session_id or "") + task.task_description[:50] + result[:200]).encode()
            ).hexdigest()[:16],
        )
        try:
            if self._observation_store.insert(observation):
                task.result_ref = f"observation:{observation.id}"
        except Exception as e:
            logger.warning("Failed to write observation for task %s: %s", task.task_id, e)

    # ------------------------------------------------------------------
    # Watchdog
    # ------------------------------------------------------------------

    def _watchdog(self) -> None:
        """后台守护线程：超时检查 + 依赖调度 + 终态清理。"""
        while not self._watchdog_stop.is_set():
            try:
                self._watchdog_tick()
            except Exception:
                logger.exception("Watchdog tick failed")
            self._watchdog_stop.wait(10)

    def _watchdog_tick(self) -> None:
        now = time.time()

        with self._lock:
            tasks = list(self._tasks.values())

        for task in tasks:
            # 1. 超时检查
            if task.status == "running":
                elapsed = now - (task.started_at or task.created_at)
                if elapsed > self._orch_config.task_timeout:
                    with self._lock:
                        task.status = "timeout"
                        task.error = f"Agent {task.agent_name} timed out after {elapsed:.0f}s"
                        task.error_type = "timeout"
                        task.cancellation_token.cancelled = True
                        task.cancellation_token.reason = "timeout"
                        task.completed_at = now

            # 2. 依赖调度
            if task.status == "pending":
                with self._lock:
                    if self._dependencies_completed(task):
                        dep_failure = self._check_dependency_failures(task)
                        if dep_failure:
                            task.status = "failed"
                            task.error_type = "dependency_failed"
                            task.failed_dependency = dep_failure["failed_dep"]
                            task.error = dep_failure["error"]
                            task.completed_at = now
                        else:
                            task.status = "running"
                            task.started_at = now
                            task.future = self._executor.submit(self._run_agent, task)

        # 3. 清理过期终态 task
        with self._lock:
            expired_ids = [
                tid for tid, t in self._tasks.items()
                if t.status in TERMINAL_STATUSES
                and now - t.last_accessed_at > self._orch_config.task_retention_seconds
            ]
            for tid in expired_ids:
                del self._tasks[tid]

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _task_to_response(self, task: AgentTask) -> dict[str, Any]:
        """将 task 转换为结构化响应。"""
        resp: dict[str, Any] = {
            "ok": task.status == "completed",
            "task_id": task.task_id,
            "agent": task.agent_name,
            "status": task.status,
        }
        if task.result:
            resp["result"] = task.result
        if task.summary:
            resp["summary"] = task.summary
        if task.result_ref:
            resp["result_ref"] = task.result_ref
        if task.error:
            resp["error"] = task.error
        if task.error_type:
            resp["error_type"] = task.error_type
        if task.failed_dependency:
            resp["failed_dependency"] = task.failed_dependency
        if task.started_at:
            resp["started_at"] = task.started_at
        if task.completed_at:
            resp["completed_at"] = task.completed_at
            if task.started_at:
                resp["duration_seconds"] = round(task.completed_at - task.started_at, 1)
        return resp

    def _summarize_result(self, result: str, max_chars: int = 1200) -> str:
        """生成结果摘要。截取前 max_chars 字符。"""
        if len(result) <= max_chars:
            return result
        return result[:max_chars] + "...[truncated]"
