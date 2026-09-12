"""
Skill API 路由。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request

if TYPE_CHECKING:
    from agent.skills import SkillManager

logger = logging.getLogger(__name__)

router = APIRouter()


def get_skill_manager(request: Request) -> SkillManager | None:
    return request.app.state.skill_manager


@router.get("/")
async def list_skills(request: Request):
    """获取所有 Skill 列表。"""
    skill_manager = get_skill_manager(request)
    if not skill_manager:
        raise HTTPException(status_code=404, detail="Skill manager not available")

    skills = skill_manager.skills

    return [
        {
            "name": s.name,
            "description": s.description,
            "path": str(s.path),
            "file_path": str(s.file_path),
            "tools": s.tools,
            "unavailable_tools": s.unavailable_tools,
            "metadata": s.metadata,
        }
        for s in skills
    ]


@router.get("/available")
async def get_available_skills(request: Request):
    """获取可用 Skill。"""
    skill_manager = get_skill_manager(request)
    if not skill_manager:
        raise HTTPException(status_code=404, detail="Skill manager not available")

    skills = [s for s in skill_manager.skills if not s.unavailable_tools]

    return [
        {
            "name": s.name,
            "description": s.description,
            "path": str(s.path),
            "file_path": str(s.file_path),
            "tools": s.tools,
            "unavailable_tools": s.unavailable_tools,
            "metadata": s.metadata,
        }
        for s in skills
    ]


@router.get("/unavailable")
async def get_unavailable_skills(request: Request):
    """获取不可用 Skill。"""
    skill_manager = get_skill_manager(request)
    if not skill_manager:
        raise HTTPException(status_code=404, detail="Skill manager not available")

    skills = [s for s in skill_manager.skills if s.unavailable_tools]

    return [
        {
            "name": s.name,
            "description": s.description,
            "path": str(s.path),
            "file_path": str(s.file_path),
            "tools": s.tools,
            "unavailable_tools": s.unavailable_tools,
            "metadata": s.metadata,
        }
        for s in skills
    ]


@router.get("/{name}")
async def get_skill(name: str, request: Request):
    """获取单个 Skill 详情。"""
    skill_manager = get_skill_manager(request)
    if not skill_manager:
        raise HTTPException(status_code=404, detail="Skill manager not available")

    skill = skill_manager.get_skill(name)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    return {
        "name": skill.name,
        "description": skill.description,
        "path": str(skill.path),
        "file_path": str(skill.file_path),
        "tools": skill.tools,
        "unavailable_tools": skill.unavailable_tools,
        "metadata": skill.metadata,
    }


@router.get("/{name}/content")
async def get_skill_content(name: str, request: Request):
    """获取 skill.md 内容。"""
    skill_manager = get_skill_manager(request)
    if not skill_manager:
        raise HTTPException(status_code=404, detail="Skill manager not available")

    skill = skill_manager.get_skill(name)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    return {"content": skill.content}
