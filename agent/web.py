"""
FastAPI Web 应用。

提供 RESTful API 和静态文件服务。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

if TYPE_CHECKING:
    from agent.config import AgentConfig
    from agent.loop import AgentLoop
    from agent.memory import MemoryManager
    from agent.memory_search import MemorySearch
    from agent.mcp.manager import MCPManager
    from agent.observation import ObservationStore
    from agent.orchestrator import Orchestrator
    from agent.session import SessionManager
    from agent.skills import SkillManager
    from agent.tools import ToolRegistry

logger = logging.getLogger(__name__)


def create_app(
    config: AgentConfig,
    session_manager: SessionManager,
    memory_manager: MemoryManager | None = None,
    observation_store: ObservationStore | None = None,
    memory_search: MemorySearch | None = None,
    skill_manager: SkillManager | None = None,
    mcp_manager: MCPManager | None = None,
    orchestrator: Orchestrator | None = None,
    tool_registry: ToolRegistry | None = None,
) -> FastAPI:
    """创建 FastAPI 应用。"""

    app = FastAPI(
        title="Project Agent API",
        description="ReAct Agent Web API",
        version="0.1.0",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    from agent.api.sessions import router as sessions_router
    from agent.api.memory import router as memory_router
    from agent.api.tools import router as tools_router
    from agent.api.skills import router as skills_router
    from agent.api.mcp import router as mcp_router
    from agent.api.orchestrator import router as orchestrator_router
    from agent.api.config import router as config_router

    app.include_router(sessions_router, prefix="/api/sessions", tags=["sessions"])
    app.include_router(memory_router, prefix="/api/memory", tags=["memory"])
    app.include_router(tools_router, prefix="/api/tools", tags=["tools"])
    app.include_router(skills_router, prefix="/api/skills", tags=["skills"])
    app.include_router(mcp_router, prefix="/api/mcp", tags=["mcp"])
    app.include_router(orchestrator_router, prefix="/api/orchestrator", tags=["orchestrator"])
    app.include_router(config_router, prefix="/api/config", tags=["config"])

    # 依赖注入
    app.state.config = config
    app.state.session_manager = session_manager
    app.state.memory_manager = memory_manager
    app.state.observation_store = observation_store
    app.state.memory_search = memory_search
    app.state.skill_manager = skill_manager
    app.state.mcp_manager = mcp_manager
    app.state.orchestrator = orchestrator
    app.state.tool_registry = tool_registry

    # 静态文件（前端打包产物）
    frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True))
        logger.info("前端静态文件已挂载: %s", frontend_dist)
    else:
        logger.warning("前端静态文件目录不存在: %s", frontend_dist)

    return app
