"""
MCP Client 模块。

提供与 MCP Server 的连接管理、工具调用和 schema 转换。
需要安装 mcp 包：pip install mcp
"""

from .bridge import AsyncBridge
from .schema import apply_tool_filter, mcp_tool_to_openai

__all__ = ["AsyncBridge", "MCPManager", "mcp_tool_to_openai", "apply_tool_filter"]


def __getattr__(name: str):
    """延迟导入 MCPManager，避免 mcp 包未安装时整个模块崩溃。"""
    if name == "MCPManager":
        from .manager import MCPManager
        return MCPManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
