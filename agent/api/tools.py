"""
工具日志 API 路由。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from fastapi import APIRouter, HTTPException, Query, Request

if TYPE_CHECKING:
    from agent.tools import ToolRegistry

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/logs")
async def get_logs(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    tool_name: Optional[str] = None,
):
    """获取工具调用历史。"""
    # TODO: 从数据库或日志文件中读取工具调用历史
    # 目前返回空列表，后续可以添加工具调用日志记录功能
    return []


@router.get("/logs/{log_id}")
async def get_log(log_id: str, request: Request):
    """获取单条工具调用详情。"""
    # TODO: 从数据库中读取单条工具调用记录
    raise HTTPException(status_code=404, detail="Log not found")
