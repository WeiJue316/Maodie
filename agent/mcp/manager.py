"""
MCPManager：管理所有 MCP Server 连接的生命周期。
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from .bridge import AsyncBridge
from .schema import apply_tool_filter, mcp_tool_to_openai
from .transport import create_http_client, create_stdio_params

logger = logging.getLogger(__name__)

_CACHE_FILENAME = "mcp_tools.json"


@dataclass
class MCPServerState:
    """单个 MCP Server 的运行时状态。"""
    config: Any                              # MCPServerConfig
    session: ClientSession | None = None
    tools: list[Any] = field(default_factory=list)   # MCP Tool 对象列表
    connected: bool = False
    error: str = ""


class MCPManager:
    """管理所有 MCP Server 连接。"""

    def __init__(self, server_configs: list[Any], bridge: AsyncBridge) -> None:
        self._configs = server_configs
        self._bridge = bridge
        self.states: dict[str, MCPServerState] = {}
        # 保存传输上下文管理器的引用，防止被 GC
        self._transports: dict[str, Any] = {}
        # 后台消息队列（后台线程写入，CLI 主线程读取显示）
        self.pending_messages: list[str] = []

    async def connect_all(self) -> None:
        """并行连接所有 server。失败的记录 error，不抛异常。"""
        async with asyncio.TaskGroup() as tg:
            for cfg in self._configs:
                tg.create_task(self._connect_one(cfg))

    async def _connect_one(self, cfg: Any) -> None:
        """连接单个 MCP Server。"""
        state = MCPServerState(config=cfg)
        try:
            if cfg.transport == "stdio":
                params = create_stdio_params(cfg)
                transport_ctx = stdio_client(params)
            elif cfg.transport == "sse":
                transport_ctx = sse_client(cfg.url, headers=cfg.headers or None)
            elif cfg.transport == "streamable_http":
                http_client = create_http_client(cfg.headers)
                transport_ctx = streamable_http_client(cfg.url, http_client=http_client)
            else:
                raise ValueError(f"未知传输类型：{cfg.transport}")

            # 进入传输上下文，获取 read/write streams
            streams = await transport_ctx.__aenter__()
            self._transports[cfg.name] = transport_ctx

            read_stream, write_stream = streams[0], streams[1]
            session = ClientSession(read_stream, write_stream)
            await session.__aenter__()
            await session.initialize()

            state.session = session

            # list tools
            tools_result = await session.list_tools()
            all_tools = tools_result.tools

            # 应用过滤
            if cfg.include or cfg.exclude:
                all_tools = apply_tool_filter(all_tools, cfg.include, cfg.exclude)

            state.tools = all_tools
            state.connected = True
            logger.info("MCP server '%s' 已连接，%d 个工具", cfg.name, len(all_tools))

        except Exception as e:
            state.error = str(e)
            state.connected = False
            logger.warning("MCP server '%s' 连接失败：%s", cfg.name, e)

        self.states[cfg.name] = state

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str:
        """调用指定 server 的工具。断连时自动重连一次。"""
        state = self.states.get(server_name)
        if state is None:
            return f"[错误] MCP Server '{server_name}' 不存在"

        if not state.connected:
            # 尝试重连
            await self._reconnect(server_name)
            state = self.states[server_name]
            if not state.connected:
                return f"[错误] MCP Server '{server_name}' 未连接：{state.error}"

        try:
            timeout = state.config.timeout
            result = await asyncio.wait_for(
                state.session.call_tool(tool_name, arguments),
                timeout=timeout,
            )
            return self._result_to_str(result)

        except asyncio.TimeoutError:
            return f"[错误] MCP 工具 {server_name}__{tool_name} 超时({timeout}s)"

        except Exception as e:
            # 可能是连接断开，标记状态
            state.connected = False
            state.error = str(e)
            return f"[错误] MCP 工具 {server_name}__{tool_name} 执行失败：{e}"

    async def disconnect_all(self) -> None:
        """优雅关闭所有 session。"""
        for name, state in self.states.items():
            if state.session is not None:
                try:
                    await state.session.__aexit__(None, None, None)
                except Exception:
                    pass
            if name in self._transports:
                try:
                    await self._transports[name].__aexit__(None, None, None)
                except Exception:
                    pass
        self.states.clear()
        self._transports.clear()

    async def _reconnect(self, server_name: str) -> None:
        """重连指定 server。"""
        state = self.states.get(server_name)
        if state is None:
            return
        # 清理旧连接
        if state.session is not None:
            try:
                await state.session.__aexit__(None, None, None)
            except Exception:
                pass
        if server_name in self._transports:
            try:
                await self._transports[server_name].__aexit__(None, None, None)
            except Exception:
                pass
        # 重新连接
        await self._connect_one(state.config)

    def get_all_tools(self) -> dict[str, list[dict[str, Any]]]:
        """返回所有已连接 server 的工具 schema（OpenAI 格式）。

        Returns:
            {server_name: [openai_schema, ...]}
        """
        result: dict[str, list[dict[str, Any]]] = {}
        for name, state in self.states.items():
            if not state.connected:
                continue
            schemas = [mcp_tool_to_openai(t, name) for t in state.tools]
            result[name] = schemas
        return result

    def get_status(self) -> list[dict[str, Any]]:
        """返回所有 server 的状态（供 /mcp 命令使用）。"""
        statuses = []
        for name, state in self.states.items():
            tool_names = [t.name for t in state.tools] if state.connected else []
            statuses.append({
                "name": name,
                "transport": state.config.transport,
                "connected": state.connected,
                "tool_count": len(tool_names),
                "tools": tool_names,
                "error": state.error,
            })
        return statuses

    # ------------------------------------------------------------------
    # Schema 缓存
    # ------------------------------------------------------------------

    def save_cache(self, cache_dir: Path) -> None:
        """将已连接 server 的工具 schema 缓存到本地文件。"""
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / _CACHE_FILENAME
        data: dict[str, Any] = {}
        for name, state in self.states.items():
            if not state.connected:
                continue
            tools_data = []
            for t in state.tools:
                schema = t.inputSchema if hasattr(t, "inputSchema") else {}
                tools_data.append({
                    "name": t.name,
                    "description": t.description or "",
                    "parameters": schema,
                })
            data[name] = {
                "tools": tools_data,
                "cached_at": datetime.now(timezone.utc).isoformat(),
            }
        cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("MCP 工具缓存已保存：%s", cache_path)

    @staticmethod
    def load_cache(cache_dir: Path) -> dict[str, list[dict[str, Any]]]:
        """从缓存加载工具 schema。返回 {server_name: [openai_schema, ...]}。"""
        cache_path = cache_dir / _CACHE_FILENAME
        if not cache_path.exists():
            return {}
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        result: dict[str, list[dict[str, Any]]] = {}
        for server_name, server_data in data.items():
            schemas = []
            for t in server_data.get("tools", []):
                schemas.append({
                    "type": "function",
                    "function": {
                        "name": f"{server_name}__{t['name']}",
                        "description": t.get("description", ""),
                        "parameters": t.get("parameters", {}),
                    },
                })
            result[server_name] = schemas
        return result

    def is_connecting(self) -> bool:
        """是否有 server 尚未完成连接（用于判断后台连接是否结束）。"""
        return any(
            not s.connected and not s.error
            for s in self.states.values()
        )

    @staticmethod
    def _result_to_str(result: Any) -> str:
        """MCP call_tool 返回值 → 字符串。"""
        content_list = result.content
        is_error = result.isError
        parts = []
        for item in content_list:
            if hasattr(item, "text"):
                parts.append(item.text)
            elif hasattr(item, "data"):
                mime = getattr(item, "mimeType", "unknown")
                parts.append(f"[{item.type}: {mime}] ({len(item.data)} bytes)")
            else:
                parts.append(str(item))
        text = "\n".join(parts)
        if is_error:
            return f"[错误] MCP 工具执行失败：{text}"
        return text
