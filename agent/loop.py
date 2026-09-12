"""
Agent Loop：ReAct 核心循环。

流程：
  用户输入
    → 追加 user 消息
    → 循环：
        LLM.chat(messages, tools)
        有 tool_calls → 执行工具 → 追加 tool 结果 → 继续
        无 tool_calls → 最终回答 → 退出循环
    → 返回最终文本
"""

from __future__ import annotations

import json
from collections.abc import Generator
from dataclasses import dataclass
from typing import Any, Callable

from .config import AgentConfig
from .llm import LLMClient, LLMResponse
from .memory import MemoryManager
from .session import Session
from .skills import SkillManager
from .tools import ToolContext, execute_tool, get_openai_schemas


# ---------------------------------------------------------------------------
# 协作式取消标记
# ---------------------------------------------------------------------------

@dataclass
class CancellationToken:
    """协作式取消标记。Orchestrator 设置，AgentLoop 每轮迭代检查。"""
    cancelled: bool = False
    reason: str | None = None


# ---------------------------------------------------------------------------
# 回调类型（供 CLI 监听工具调用过程）
# ---------------------------------------------------------------------------

@dataclass
class ToolCallEvent:
    name: str
    arguments: dict[str, Any]
    call_id: str


@dataclass
class ToolResultEvent:
    name: str
    call_id: str
    result: str


OnToolCall = Callable[[ToolCallEvent], None]
OnToolResult = Callable[[ToolResultEvent], None]


# ---------------------------------------------------------------------------
# AgentLoop
# ---------------------------------------------------------------------------

class AgentLoop:
    def __init__(
        self,
        config: AgentConfig,
        session: Session,
        llm: LLMClient,
        skill_manager: SkillManager | None = None,
        memory_manager: MemoryManager | None = None,
        memory_search: Any | None = None,
        mcp_manager: Any | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        self._config = config
        self._session = session
        self._llm = llm
        self._skill_manager = skill_manager
        self._memory_manager = memory_manager
        self._memory_search = memory_search
        self._cancellation_token = cancellation_token
        # ToolContext 持有当前工作目录，change_dir 工具会修改它
        self._tool_ctx = ToolContext(
            work_dir=config.resolved_work_dir(),
            session_id=session.id,
            skill_manager=skill_manager,
            memory_manager=memory_manager,
            memory_search=memory_search,
            mcp_manager=mcp_manager,
        )
    @property
    def tool_ctx(self) -> ToolContext:
        return self._tool_ctx

    # ------------------------------------------------------------------
    # 初始化 system prompt
    # ------------------------------------------------------------------

    def ensure_system_prompt(self, user_input: str | None = None) -> None:
        """若 messages 为空，插入 system prompt（含长期记忆）。"""
        if not self._session.messages:
            prompt = self._config.formatted_system_prompt()
            # 注入长期记忆
            if self._memory_manager and self._config.memory.auto_inject:
                memory_content = self._memory_manager.load()
                if memory_content.strip():
                    prompt += (
                        "\n\n# 长期记忆\n"
                        "以下是用户之前要求记住的信息，在回答时参考：\n"
                        + memory_content
                    )
            # 注入 skill 目录
            if self._skill_manager and self._skill_manager.skills:
                catalog = self._skill_manager.format_skills_catalog(
                    max_skills=self._config.skills.max_skills_in_prompt,
                    max_chars=self._config.skills.max_prompt_chars,
                )
                if catalog:
                    prompt += "\n\n" + catalog
            # 注入可用 agent 列表（多 agent 协作）
            if self._config.orchestrator.enabled and self._config.agents:
                prompt += self._format_agent_catalog()
            # 注入 observation 检索结果
            if (self._memory_search
                    and self._config.memory_search.enabled
                    and self._config.memory_search.auto_search
                    and user_input):
                observations = self._memory_search.search(user_input)
                if observations:
                    context = self._memory_search.format_memory_context(observations)
                    prompt += "\n\n" + context
                    # 检查晋升
                    if self._config.memory_search.auto_promote:
                        self._memory_search.check_and_promote(observations)
            self._session.messages.append({
                "role": "system",
                "content": prompt,
            })

    # ------------------------------------------------------------------
    # 主接口：阻塞
    # ------------------------------------------------------------------

    def _format_agent_catalog(self) -> str:
        """格式化可用 agent 列表，注入 system prompt。"""
        agents = self._config.agents
        if not agents:
            return ""

        lines = [
            "",
            "## Available Agents",
            "",
            "Use the spawn_agent tool to delegate tasks to specialized agents.",
            "Each agent runs independently and returns results asynchronously.",
            "Use check_agent_status to poll for results.",
            "If one agent depends on another agent's output, pass depends_on with the upstream task_id.",
            "",
        ]

        for name, spec in agents.items():
            prompt_preview = spec.system_prompt.split("\n")[0][:80] if spec.system_prompt else ""
            lines.append(f"- **{name}**: {prompt_preview}")
            # 从 system_prompt 中提取 USE WHEN / DON'T USE FOR（如果有）
            for line in spec.system_prompt.split("\n"):
                stripped = line.strip()
                if stripped.startswith("USE WHEN:") or stripped.startswith("DON'T USE FOR:"):
                    lines.append(f"  {stripped}")
            lines.append("")

        lines.extend([
            "## Collaboration",
            "",
            "You may work alongside other agents. When your task depends on another agent's",
            "output (e.g., \"implement based on the design\"), prefer depends_on so the",
            "orchestrator injects the upstream summary/result reference before the dependent",
            "agent starts. Use search_memory for broader background or older observations.",
            "",
            "IMPORTANT: Only spawn agents when the task genuinely benefits from specialization.",
            "For simple tasks, handle them yourself. Don't spawn agents just because they exist.",
            "",
        ])

        return "\n".join(lines)

    def run(
        self,
        user_input: str,
        on_tool_call: OnToolCall | None = None,
        on_tool_result: OnToolResult | None = None,
    ) -> str:
        """
        执行一轮 Agent Loop（非流式最终回答）。

        Args:
            user_input:     用户消息文本
            on_tool_call:   工具调用前回调
            on_tool_result: 工具执行后回调

        Returns:
            最终回答文本
        """
        self.ensure_system_prompt(user_input)
        self._append_user(user_input)

        tool_schemas = get_openai_schemas(self._config.enabled_tools)
        max_iter = self._config.max_iterations

        for _ in range(max_iter):
            # 协作式取消检查
            if self._cancellation_token and self._cancellation_token.cancelled:
                return f"[已取消] {self._cancellation_token.reason or '任务被取消'}"

            # 有工具调用时强制非流式，便于处理 tool_calls 结构
            response = self._llm.chat_blocking(
                messages=self._session.messages,
                tools=tool_schemas if tool_schemas else None,
            )

            self._session.messages.append(response.to_message())

            if not response.has_tool_calls:
                return response.content

            self._handle_tool_calls(response, on_tool_call, on_tool_result)

        return "[警告] 已达最大迭代次数，请检查任务是否过于复杂。"

    # ------------------------------------------------------------------
    # 主接口：流式最终回答
    # ------------------------------------------------------------------

    def stream_run(
        self,
        user_input: str,
        on_tool_call: OnToolCall | None = None,
        on_tool_result: OnToolResult | None = None,
    ) -> Generator[tuple[str, str], None, None]:
        """
        执行一轮 Agent Loop，最终回答以流式 yield (label, token) 元组。
        label 为 'reasoning' 或 'content'。工具调用阶段依然阻塞。
        """
        self.ensure_system_prompt(user_input)
        self._append_user(user_input)

        tool_schemas = get_openai_schemas(self._config.enabled_tools)
        max_iter = self._config.max_iterations

        for iteration in range(max_iter):
            # 协作式取消检查
            if self._cancellation_token and self._cancellation_token.cancelled:
                yield f"[已取消] {self._cancellation_token.reason or '任务被取消'}"
                return

            is_last_possible = (iteration == max_iter - 1)

            if is_last_possible:
                # 最后一次迭代强制流式
                response = self._llm.chat(
                    messages=self._session.messages,
                    tools=tool_schemas if tool_schemas else None,
                    stream=True,
                )
            else:
                response = self._llm.chat_blocking(
                    messages=self._session.messages,
                    tools=tool_schemas if tool_schemas else None,
                )

            if not response.has_tool_calls:
                # 最终回答，流式输出（含 reasoning）
                content_parts: list[str] = []
                for label, token in response.stream_labeled():
                    if label == "content":
                        content_parts.append(token)
                    yield (label, token)
                # 将完整回答写入 messages（reasoning 由 to_message 保留）
                message = response.to_message()
                if content_parts:
                    message["content"] = "".join(content_parts)
                self._session.messages.append(message)
                return

            # 工具调用阶段（不流式）
            self._session.messages.append(response.to_message())
            self._handle_tool_calls(response, on_tool_call, on_tool_result)

        yield "[警告] 已达最大迭代次数，请检查任务是否过于复杂。"

    # ------------------------------------------------------------------
    # 私有方法
    # ------------------------------------------------------------------

    def _handle_tool_calls(
        self,
        response: LLMResponse,
        on_tool_call: OnToolCall | None,
        on_tool_result: OnToolResult | None,
    ) -> None:
        """执行 response 中的所有 tool_calls，并将结果追加到 messages。"""
        tool_results: list[dict[str, Any]] = []
        for tc in response.tool_calls:
            if on_tool_call:
                on_tool_call(ToolCallEvent(
                    name=tc["name"],
                    arguments=tc["arguments"],
                    call_id=tc["id"],
                ))

            result = execute_tool(tc["name"], tc["arguments"], self._tool_ctx)

            if on_tool_result:
                on_tool_result(ToolResultEvent(
                    name=tc["name"],
                    call_id=tc["id"],
                    result=result,
                ))

            tool_results.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            })

        self._session.messages.extend(tool_results)

    def _append_user(self, text: str) -> None:
        self._session.messages.append({"role": "user", "content": text})
