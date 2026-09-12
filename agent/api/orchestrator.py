"""
编排器 API 路由。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

if TYPE_CHECKING:
    from agent.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

router = APIRouter()


class CreateTaskRequest(BaseModel):
    agent_name: str
    task_description: str
    context: Optional[str] = ""
    depends_on: Optional[list[str]] = []


def get_orchestrator(request: Request) -> Orchestrator | None:
    return request.app.state.orchestrator


@router.get("/tasks")
async def get_tasks(request: Request):
    """获取所有任务列表。"""
    orchestrator = get_orchestrator(request)
    if not orchestrator:
        return []

    tasks = []
    for task in orchestrator._tasks.values():
        tasks.append(orchestrator._task_to_response(task))

    return tasks


@router.post("/tasks")
async def create_task(req: CreateTaskRequest, request: Request):
    """创建子 Agent 任务。"""
    orchestrator = get_orchestrator(request)
    if not orchestrator:
        raise HTTPException(status_code=404, detail="Orchestrator not available")

    result = orchestrator.spawn_agent(
        agent_name=req.agent_name,
        task_description=req.task_description,
        context=req.context or "",
        depends_on=req.depends_on or [],
    )

    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Unknown error"))

    return result


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, request: Request):
    """获取任务状态。"""
    orchestrator = get_orchestrator(request)
    if not orchestrator:
        raise HTTPException(status_code=404, detail="Orchestrator not available")

    result = orchestrator.check_status(task_id)

    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error", "Task not found"))

    return result


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, request: Request):
    """取消任务。"""
    orchestrator = get_orchestrator(request)
    if not orchestrator:
        raise HTTPException(status_code=404, detail="Orchestrator not available")

    result = orchestrator.cancel_task(task_id)

    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Cannot cancel task"))

    return result


@router.get("/agents")
async def get_agents(request: Request):
    """获取可用 Agent 列表。"""
    config = request.app.state.config

    agents = []
    for name, spec in config.agents.items():
        agents.append({
            "name": name,
            "system_prompt": spec.system_prompt,
            "max_iterations": spec.max_iterations,
            "tools": spec.tools,
            "model": spec.model,
        })

    return agents
