"""
传输层工厂：根据配置创建 MCP 传输参数。
"""

from __future__ import annotations

from typing import Any

import httpx
from mcp import StdioServerParameters


def create_stdio_params(config: Any) -> StdioServerParameters:
    """创建 stdio 传输参数。"""
    return StdioServerParameters(
        command=config.command,
        args=config.args or [],
        env=config.env or None,
        cwd=config.cwd or None,
    )


def create_http_client(headers: dict[str, str] | None = None) -> httpx.AsyncClient | None:
    """创建带 headers 的 httpx 客户端（供 streamable_http 使用）。"""
    if not headers:
        return None
    return httpx.AsyncClient(headers=headers)
