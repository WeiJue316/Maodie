"""
MCP API 路由。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request

if TYPE_CHECKING:
    from agent.mcp.manager import MCPManager

logger = logging.getLogger(__name__)

router = APIRouter()


def get_mcp_manager(request: Request) -> MCPManager | None:
    return request.app.state.mcp_manager


@router.get("/servers")
async def get_servers(request: Request):
    """获取所有 MCP Server 状态。"""
    mcp_manager = get_mcp_manager(request)
    if not mcp_manager:
        return []

    return mcp_manager.get_status()


@router.get("/servers/{name}")
async def get_server(name: str, request: Request):
    """获取单个 Server 详情。"""
    mcp_manager = get_mcp_manager(request)
    if not mcp_manager:
        raise HTTPException(status_code=404, detail="MCP manager not available")

    status = mcp_manager.get_status()
    for server in status:
        if server["name"] == name:
            return server

    raise HTTPException(status_code=404, detail="Server not found")


@router.post("/servers/{name}/reconnect")
async def reconnect_server(name: str, request: Request):
    """重连指定 Server。"""
    mcp_manager = get_mcp_manager(request)
    if not mcp_manager:
        raise HTTPException(status_code=404, detail="MCP manager not available")

    state = mcp_manager.states.get(name)
    if not state:
        raise HTTPException(status_code=404, detail="Server not found")

    await mcp_manager._reconnect(name)

    return {"message": f"Server {name} reconnected"}


@router.get("/tools")
async def get_tools(request: Request):
    """获取所有 MCP 工具。"""
    mcp_manager = get_mcp_manager(request)
    if not mcp_manager:
        return []

    tools = []
    for server_name, server_tools in mcp_manager.get_all_tools().items():
        for tool in server_tools:
            tools.append({
                "name": tool["function"]["name"],
                "description": tool["function"].get("description", ""),
                "parameters": tool["function"].get("parameters", {}),
                "server": server_name,
            })

    return tools


@router.get("/tools/{server}")
async def get_server_tools(server: str, request: Request):
    """获取指定 Server 的工具。"""
    mcp_manager = get_mcp_manager(request)
    if not mcp_manager:
        raise HTTPException(status_code=404, detail="MCP manager not available")

    all_tools = mcp_manager.get_all_tools()
    server_tools = all_tools.get(server, [])

    return [
        {
            "name": tool["function"]["name"],
            "description": tool["function"].get("description", ""),
            "parameters": tool["function"].get("parameters", {}),
            "server": server,
        }
        for tool in server_tools
    ]
