"""
配置 API 路由。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

if TYPE_CHECKING:
    from agent.config import AgentConfig

logger = logging.getLogger(__name__)

router = APIRouter()


class UpdateConfigRequest(BaseModel):
    llm: Optional[dict[str, Any]] = None
    agent: Optional[dict[str, Any]] = None
    session: Optional[dict[str, Any]] = None
    memory: Optional[dict[str, Any]] = None
    observation: Optional[dict[str, Any]] = None
    vectordb: Optional[dict[str, Any]] = None
    memory_search: Optional[dict[str, Any]] = None


def get_config(request: Request) -> AgentConfig:
    return request.app.state.config


@router.get("/")
async def get_config_handler(request: Request):
    """获取当前配置。"""
    config = get_config(request)

    return {
        "llm": {
            "provider": config.llm.provider,
            "model": config.llm.model,
            "base_url": config.llm.base_url,
            "temperature": config.llm.temperature,
            "timeout": config.llm.timeout,
            "streaming": config.llm.streaming,
        },
        "agent": {
            "max_iterations": config.max_iterations,
            "work_dir": config.work_dir,
            "system_prompt": config.system_prompt,
        },
        "session": {
            "dir": config.session.dir,
            "max_history": config.session.max_history,
            "auto_save": config.session.auto_save,
        },
        "memory": {
            "enabled": config.memory.enabled,
        },
        "observation": {
            "enabled": config.observation.enabled,
            "db_path": config.observation.db_path,
        },
        "vectordb": {
            "enabled": config.vectordb.enabled,
        },
        "memory_search": {
            "enabled": config.memory_search.enabled,
            "search_limit": config.memory_search.search_limit,
            "promotion_threshold": config.memory_search.promotion_threshold,
        },
    }


@router.put("/")
async def update_config(req: UpdateConfigRequest, request: Request):
    """更新配置。"""
    config = get_config(request)

    # 更新 LLM 配置
    if req.llm:
        if "provider" in req.llm:
            config.llm.provider = req.llm["provider"]
        if "model" in req.llm:
            config.llm.model = req.llm["model"]
        if "base_url" in req.llm:
            config.llm.base_url = req.llm["base_url"]
        if "temperature" in req.llm:
            config.llm.temperature = req.llm["temperature"]
        if "timeout" in req.llm:
            config.llm.timeout = req.llm["timeout"]
        if "streaming" in req.llm:
            config.llm.streaming = req.llm["streaming"]

    # 更新 Agent 配置
    if req.agent:
        if "max_iterations" in req.agent:
            config.max_iterations = req.agent["max_iterations"]
        if "work_dir" in req.agent:
            config.work_dir = req.agent["work_dir"]
        if "system_prompt" in req.agent:
            config.system_prompt = req.agent["system_prompt"]

    # 更新 Session 配置
    if req.session:
        if "dir" in req.session:
            config.session.dir = req.session["dir"]
        if "max_history" in req.session:
            config.session.max_history = req.session["max_history"]
        if "auto_save" in req.session:
            config.session.auto_save = req.session["auto_save"]

    # 更新 Memory 配置
    if req.memory:
        if "enabled" in req.memory:
            config.memory.enabled = req.memory["enabled"]

    # 更新 Observation 配置
    if req.observation:
        if "enabled" in req.observation:
            config.observation.enabled = req.observation["enabled"]
        if "db_path" in req.observation:
            config.observation.db_path = req.observation["db_path"]

    # 更新 VectorDB 配置
    if req.vectordb:
        if "enabled" in req.vectordb:
            config.vectordb.enabled = req.vectordb["enabled"]

    # 更新 Memory Search 配置
    if req.memory_search:
        if "enabled" in req.memory_search:
            config.memory_search.enabled = req.memory_search["enabled"]
        if "search_limit" in req.memory_search:
            config.memory_search.search_limit = req.memory_search["search_limit"]
        if "promotion_threshold" in req.memory_search:
            config.memory_search.promotion_threshold = req.memory_search["promotion_threshold"]

    # TODO: 保存配置到文件

    return {"message": "Config updated"}
