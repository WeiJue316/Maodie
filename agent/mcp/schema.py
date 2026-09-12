"""
MCP Tool schema → OpenAI function calling schema 转换 + 工具过滤。
"""

from __future__ import annotations

import re
from typing import Any


def mcp_tool_to_openai(tool: Any, prefix: str) -> dict[str, Any]:
    """将 MCP Tool 转为 OpenAI function calling schema。

    MCP 格式:
        {"name": "search", "description": "...", "inputSchema": {...}}
    OpenAI 格式:
        {"type": "function", "function": {"name": "prefix__search", ...}}
    """
    full_name = f"{prefix}__{tool.name}"
    schema = tool.inputSchema if hasattr(tool, "inputSchema") else {}

    return {
        "type": "function",
        "function": {
            "name": full_name,
            "description": tool.description or "",
            "parameters": schema,
        },
    }


def apply_tool_filter(
    tools: list[Any],
    include: list[str],
    exclude: list[str],
) -> list[Any]:
    """按 include/exclude 正则过滤工具列表。

    规则：
    - include 非空时，只保留名称匹配任一 include 模式的工具
    - exclude 非空时，排除名称匹配任一 exclude 模式的工具
    - include 优先于 exclude
    """
    result = tools

    if include:
        patterns = [re.compile(p) for p in include]
        result = [t for t in result if any(p.search(t.name) for p in patterns)]

    if exclude:
        patterns = [re.compile(p) for p in exclude]
        result = [t for t in result if not any(p.search(t.name) for p in patterns)]

    return result
