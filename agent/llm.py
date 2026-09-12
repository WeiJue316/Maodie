"""
LLM 客户端封装。

使用 OpenAI SDK 连接 DeepSeek / OpenAI 兼容接口，支持：
- Function Calling（工具调用）
- 流式输出
- 非流式输出
"""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

from openai import OpenAI

from .config import LLMConfig


class LLMClient:
    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        self._client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        stream: bool | None = None,
    ) -> "LLMResponse":
        """
        发起一次对话请求。

        Args:
            messages: OpenAI 格式消息列表
            tools:    工具 schema 列表（OpenAI function calling 格式）
            stream:   是否流式；None 则使用 config.streaming

        Returns:
            LLMResponse 对象，可判断是否含 tool_calls，也可迭代流式 token
        """
        use_stream = self._config.streaming if stream is None else stream
        api_messages = prepare_messages_for_provider(messages, self._config.provider)

        kwargs: dict[str, Any] = {
            "model": self._config.model,
            "messages": api_messages,
            "temperature": self._config.temperature,
            "stream": use_stream,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        raw = self._client.chat.completions.create(**kwargs)

        if use_stream:
            return _StreamingLLMResponse(raw)
        else:
            return _BlockingLLMResponse(raw)

    def chat_blocking(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> "LLMResponse":
        """强制非流式调用（loop 内部使用，工具调用阶段不适合流式）。"""
        return self.chat(messages, tools, stream=False)


# ---------------------------------------------------------------------------
# 响应抽象
# ---------------------------------------------------------------------------

class LLMResponse:
    """统一的 LLM 响应接口。"""

    @property
    def content(self) -> str:
        """最终文本内容（阻塞直到完整）。"""
        raise NotImplementedError

    @property
    def tool_calls(self) -> list[dict[str, Any]]:
        """
        返回工具调用列表，格式：
        [
          {
            "id": "call_xxx",
            "name": "tool_name",
            "arguments": {...}   # 已解析的 dict
          }
        ]
        空列表表示无工具调用。
        """
        raise NotImplementedError

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0

    def stream_text(self) -> Generator[str, None, None]:
        """逐 token yield 文本（仅在无工具调用时有意义）。"""
        raise NotImplementedError

    def stream_labeled(self) -> Generator[tuple[str, str], None, None]:
        """逐 token yield (type, text) 元组。type 为 'reasoning' 或 'content'。"""
        raise NotImplementedError

    def to_message(self) -> dict[str, Any]:
        """将响应转为 messages 格式的 assistant 消息 dict。"""
        raise NotImplementedError


class _BlockingLLMResponse(LLMResponse):
    def __init__(self, completion: Any) -> None:
        self._msg = completion.choices[0].message

    @property
    def content(self) -> str:
        return self._msg.content or ""

    @property
    def tool_calls(self) -> list[dict[str, Any]]:
        if not self._msg.tool_calls:
            return []
        result = []
        for tc in self._msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            result.append({
                "id": tc.id,
                "name": tc.function.name,
                "arguments": args,
            })
        return result

    def stream_text(self) -> Generator[str, None, None]:
        yield self.content

    def stream_labeled(self) -> Generator[tuple[str, str], None, None]:
        yield ("content", self.content)

    def to_message(self) -> dict[str, Any]:
        msg: dict[str, Any] = {"role": "assistant"}
        if self._msg.content:
            msg["content"] = self._msg.content
        reasoning_content = _get_provider_extra(self._msg, "reasoning_content")
        if reasoning_content:
            msg["reasoning_content"] = reasoning_content
        if self._msg.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in self._msg.tool_calls
            ]
        return msg


class _StreamingLLMResponse(LLMResponse):
    """
    流式响应。

    - 纯文本路径：`stream_text()` 惰性消费上游 iterator，首 token 即时到达。
    - 工具调用路径：peek 到 tool_calls 时一次性 drain 剩余 chunks
      （执行工具需要完整的 arguments，没有流式化的空间）。
    """

    def __init__(self, stream: Any) -> None:
        self._iter = iter(stream)
        self._content_parts: list[str] = []
        self._reasoning_parts: list[str] = []
        self._tc_map: dict[int, dict[str, Any]] = {}
        self._is_tool_call_path: bool = False
        self._drained: bool = False

        # 预读到能判断路径的首个 chunk（含 content 或 tool_calls）
        self._peek_until_decisive()

    # ------------------------------------------------------------------
    # 内部：消费单个 chunk / 预读 / drain
    # ------------------------------------------------------------------

    def _consume_chunk(self, chunk: Any) -> None:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta is None:
            return
        if delta.content:
            self._content_parts.append(delta.content)
        reasoning = _get_provider_extra(delta, "reasoning_content")
        if reasoning:
            self._reasoning_parts.append(reasoning)
        if delta.tool_calls:
            for tc_delta in delta.tool_calls:
                idx = tc_delta.index
                if idx not in self._tc_map:
                    self._tc_map[idx] = {
                        "id": "",
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    }
                if tc_delta.id:
                    self._tc_map[idx]["id"] = tc_delta.id
                if tc_delta.function:
                    if tc_delta.function.name:
                        self._tc_map[idx]["function"]["name"] += tc_delta.function.name
                    if tc_delta.function.arguments:
                        self._tc_map[idx]["function"]["arguments"] += tc_delta.function.arguments

    def _peek_until_decisive(self) -> None:
        for chunk in self._iter:
            self._consume_chunk(chunk)
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue
            if delta.tool_calls:
                self._is_tool_call_path = True
                self._drain_remaining()
                return
            if delta.content:
                return
        # 流结束仍未见 content/tool_calls
        self._is_tool_call_path = bool(self._tc_map)
        self._drained = True

    def _drain_remaining(self) -> None:
        if self._drained:
            return
        for chunk in self._iter:
            self._consume_chunk(chunk)
        self._drained = True

    # ------------------------------------------------------------------
    # LLMResponse 接口
    # ------------------------------------------------------------------

    @property
    def content(self) -> str:
        self._drain_remaining()
        return "".join(self._content_parts)

    @property
    def tool_calls(self) -> list[dict[str, Any]]:
        # 文本路径下不 drain，避免破坏流式；工具路径在 peek 阶段已 drain
        if self._is_tool_call_path and not self._drained:
            self._drain_remaining()
        result = []
        for idx in sorted(self._tc_map):
            tc = self._tc_map[idx]
            try:
                args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                args = {}
            result.append({
                "id": tc["id"],
                "name": tc["function"]["name"],
                "arguments": args,
            })
        return result

    def stream_text(self) -> Generator[str, None, None]:
        """先吐 peek 阶段累积的 content，再边消费边 yield。"""
        yielded = 0
        # peek 阶段可能已累积首个 content chunk
        while yielded < len(self._content_parts):
            yield self._content_parts[yielded]
            yielded += 1

        while not self._drained:
            try:
                chunk = next(self._iter)
            except StopIteration:
                self._drained = True
                break
            self._consume_chunk(chunk)
            while yielded < len(self._content_parts):
                yield self._content_parts[yielded]
                yielded += 1

    def stream_labeled(self) -> Generator[tuple[str, str], None, None]:
        """先 yield reasoning，再 yield content，用 (type, text) 区分。"""
        # reasoning 部分（peek 阶段可能已累积）
        for part in self._reasoning_parts:
            yield ("reasoning", part)
        r_yielded = len(self._reasoning_parts)

        # content 部分
        c_yielded = 0
        while c_yielded < len(self._content_parts):
            yield ("content", self._content_parts[c_yielded])
            c_yielded += 1

        # 继续消费剩余 chunks
        while not self._drained:
            try:
                chunk = next(self._iter)
            except StopIteration:
                self._drained = True
                break
            self._consume_chunk(chunk)
            # yield 新的 reasoning parts
            while r_yielded < len(self._reasoning_parts):
                yield ("reasoning", self._reasoning_parts[r_yielded])
                r_yielded += 1
            # yield 新的 content parts
            while c_yielded < len(self._content_parts):
                yield ("content", self._content_parts[c_yielded])
                c_yielded += 1

    def to_message(self) -> dict[str, Any]:
        self._drain_remaining()
        msg: dict[str, Any] = {"role": "assistant"}
        content = "".join(self._content_parts)
        if content:
            msg["content"] = content
        reasoning = "".join(self._reasoning_parts)
        if reasoning:
            msg["reasoning_content"] = reasoning
        raw_tool_calls = [self._tc_map[i] for i in sorted(self._tc_map)]
        if raw_tool_calls:
            msg["tool_calls"] = raw_tool_calls
        return msg


def prepare_messages_for_provider(
    messages: list[dict[str, Any]],
    provider: str,
) -> list[dict[str, Any]]:
    """Return provider-compatible messages without mutating session history."""
    if _is_deepseek_provider(provider):
        return _prepare_deepseek_messages(messages)
    return [_strip_provider_reasoning_fields(m) for m in messages]


def _is_deepseek_provider(provider: str) -> bool:
    return provider.strip().lower() == "deepseek"


def _prepare_deepseek_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    has_reasoning_history = any(
        m.get("role") == "assistant" and bool(m.get("reasoning_content"))
        for m in messages
    )
    prepared: list[dict[str, Any]] = []
    valid_tool_call_ids: set[str] = set()

    for message in messages:
        msg = _prepare_deepseek_message(message)
        if msg.get("role") == "assistant" and has_reasoning_history and not msg.get("reasoning_content"):
            # Legacy sessions may contain assistant messages created before we
            # preserved DeepSeek reasoning_content. They cannot be repaired, and
            # DeepSeek rejects them in thinking mode, so omit them at API time.
            continue
        for tool_call in msg.get("tool_calls") or []:
            call_id = tool_call.get("id")
            if isinstance(call_id, str) and call_id:
                valid_tool_call_ids.add(call_id)
        prepared.append(msg)

    if not valid_tool_call_ids:
        return [m for m in prepared if m.get("role") != "tool"]

    return [
        m for m in prepared
        if m.get("role") != "tool" or m.get("tool_call_id") in valid_tool_call_ids
    ]


def _prepare_deepseek_message(message: dict[str, Any]) -> dict[str, Any]:
    msg = dict(message)
    if msg.get("role") != "assistant":
        msg.pop("reasoning_content", None)
        return msg
    if not msg.get("reasoning_content"):
        msg.pop("reasoning_content", None)
    return msg


def _strip_provider_reasoning_fields(message: dict[str, Any]) -> dict[str, Any]:
    msg = dict(message)
    msg.pop("reasoning_content", None)
    return msg


def _get_provider_extra(obj: Any, field: str) -> Any:
    value = getattr(obj, field, None)
    if value is not None:
        return value
    model_extra = getattr(obj, "model_extra", None)
    if isinstance(model_extra, dict):
        return model_extra.get(field)
    if isinstance(obj, dict):
        return obj.get(field)
    return None
