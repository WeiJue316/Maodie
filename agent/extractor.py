"""
Observation 提取器。

Session 结束时用 LLM 从对话历史中提取结构化 observation。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from agent.observation import Observation, compute_content_hash

if TYPE_CHECKING:
    from agent.config import ObservationConfig
    from agent.llm import LLMClient
    from agent.observation import ObservationStore
    from agent.session import Session
    from agent.vectordb import VectorStore

_EXTRACTION_PROMPT = """你是一个信息提取专家。请从以下对话中提取值得长期记住的关键信息。

## 对话历史
{history}

## 输出格式
以 JSON 数组返回，每条包含：
- type: "bugfix" | "feature" | "refactor" | "change" | "discovery" | "decision"
- title: 一句话标题（<50字）
- narrative: 详细描述（1-3段）
- facts: 关键事实列表（每条一句话）
- concepts: 概念标签列表
- files_read: 涉及的读取文件路径列表
- files_modified: 涉及的修改文件路径列表

## 规则
1. 只提取有长期价值的信息，忽略寒暄和简单问答
2. 每条 observation 应是独立完整的，不依赖上下文
3. 如果对话中没有值得提取的信息，返回空数组 []
4. facts 应是可验证的具体事实，不是模糊的总结
5. 只输出 JSON 数组，不要其他内容"""


def _format_messages(messages: list[dict]) -> str:
    """将消息列表格式化为可读文本。"""
    parts = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "system":
            continue
        elif role == "user":
            parts.append(f"用户：{content}")
        elif role == "assistant":
            if content:
                parts.append(f"助手：{content}")
            # 处理 tool_calls
            tool_calls = msg.get("tool_calls", [])
            for tc in tool_calls:
                func = tc.get("function", {})
                name = func.get("name", "")
                args = func.get("arguments", "")
                parts.append(f"[工具调用] {name} {args}")
        elif role == "tool":
            # 工具结果可能很长，截断
            truncated = content[:500] + "..." if len(content) > 500 else content
            parts.append(f"[工具结果] {truncated}")

    return "\n".join(parts)


class ObservationExtractor:
    """从对话中提取结构化 observation。"""

    def __init__(
        self,
        llm_client: LLMClient,
        store: ObservationStore,
        vector_store: VectorStore | None,
        config: ObservationConfig,
    ) -> None:
        self._llm = llm_client
        self._store = store
        self._vector_store = vector_store
        self._config = config

    def extract_from_session(self, session: Session) -> list[Observation]:
        """从 Session 提取 observation。"""
        return self.extract_from_messages(session.messages, session.id)

    def extract_from_messages(
        self, messages: list[dict], session_id: str
    ) -> list[Observation]:
        """从消息列表提取 observation。"""
        # 格式化对话历史
        history = _format_messages(messages)
        if not history.strip():
            return []

        # 构建 prompt
        prompt = _EXTRACTION_PROMPT.format(history=history)

        # 调用 LLM
        try:
            response = self._llm.chat_blocking(
                messages=[{"role": "user", "content": prompt}]
            )
            raw_text = response.content.strip()
        except Exception:
            return []

        # 解析 JSON
        observations = self._parse_response(raw_text, session_id)
        if not observations:
            return []

        # 截断到上限
        max_obs = self._config.max_observations_per_session
        if len(observations) > max_obs:
            observations = observations[:max_obs]

        # 写入 SQLite
        self._store.insert_batch(observations)

        # 同步到 ChromaDB
        if self._vector_store and self._vector_store.available:
            self._vector_store.add_batch(observations)

        return observations

    def _parse_response(
        self, raw_text: str, session_id: str
    ) -> list[Observation]:
        """解析 LLM 返回的 JSON 为 Observation 列表。"""
        # 尝试提取 JSON（可能被 markdown 代码块包裹）
        json_text = raw_text
        if "```" in json_text:
            # 提取 ```...``` 之间的内容
            parts = json_text.split("```")
            for part in parts[1::2]:  # 奇数段是代码块内容
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("["):
                    json_text = part
                    break

        try:
            data = json.loads(json_text)
        except (json.JSONDecodeError, ValueError):
            return []

        if not isinstance(data, list):
            return []

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        observations = []

        for item in data:
            if not isinstance(item, dict):
                continue

            obs_type = item.get("type", "")
            title = item.get("title", "")
            narrative = item.get("narrative", "")

            # 必须有 title 和 narrative
            if not title or not narrative:
                continue

            # 验证 type
            valid_types = {"bugfix", "feature", "refactor", "change", "discovery", "decision"}
            if obs_type not in valid_types:
                obs_type = "discovery"  # 默认类型

            obs = Observation(
                id=str(uuid.uuid4()),
                type=obs_type,
                title=title,
                narrative=narrative,
                facts=item.get("facts", []),
                concepts=item.get("concepts", []),
                files_read=item.get("files_read", []),
                files_modified=item.get("files_modified", []),
                session_id=session_id,
                created_at=now,
                relevance_count=0,
                content_hash=compute_content_hash(session_id, title, narrative),
                promoted=0,
            )
            observations.append(obs)

        return observations
