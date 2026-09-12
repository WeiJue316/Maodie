"""
会话 API 路由。
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

if TYPE_CHECKING:
    from agent.session import SessionManager

logger = logging.getLogger(__name__)

router = APIRouter()


class CreateSessionRequest(BaseModel):
    work_dir: Optional[str] = None


class SendMessageRequest(BaseModel):
    content: str


def get_session_manager(request: Request) -> SessionManager:
    """获取 SessionManager 实例。"""
    return request.app.state.session_manager


@router.get("/")
async def list_sessions(request: Request):
    """获取会话列表。"""
    session_manager = get_session_manager(request)
    sessions = session_manager.list_sessions()
    return [
        {
            "id": s.id,
            "title": s.title,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
            "work_dir": s.work_dir,
        }
        for s in sessions
    ]


@router.post("/")
async def create_session(req: CreateSessionRequest, request: Request):
    """创建新会话。"""
    session_manager = get_session_manager(request)
    config = request.app.state.config

    work_dir = req.work_dir or str(config.resolved_work_dir())
    session = session_manager.new_session(work_dir=work_dir)
    session_manager.save_session(session)

    return {
        "id": session.id,
        "title": session.title,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "work_dir": session.work_dir,
    }


@router.get("/{session_id}")
async def get_session(session_id: str, request: Request):
    """获取会话详情。"""
    session_manager = get_session_manager(request)

    try:
        session = session_manager.load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "id": session.id,
        "title": session.title,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "work_dir": session.work_dir,
        "messages": session.messages,
    }


@router.delete("/{session_id}")
async def delete_session(session_id: str, request: Request):
    """删除会话。"""
    session_manager = get_session_manager(request)

    success = session_manager.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"message": "Session deleted"}


@router.get("/{session_id}/messages")
async def get_messages(session_id: str, request: Request):
    """获取消息历史。"""
    session_manager = get_session_manager(request)

    try:
        session = session_manager.load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")

    return session.messages


@router.post("/{session_id}/messages")
async def send_message(session_id: str, req: SendMessageRequest, request: Request):
    """发送消息（非流式）。"""
    session_manager = get_session_manager(request)

    try:
        session = session_manager.load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")

    # 创建 AgentLoop 并运行
    from agent.loop import AgentLoop
    from agent.llm import LLMClient

    config = request.app.state.config
    llm = LLMClient(config.llm)

    agent_loop = AgentLoop(
        config=config,
        session=session,
        llm=llm,
    )

    result = agent_loop.run(req.content)

    # 保存 session
    session_manager.save_session(session)

    return {"role": "assistant", "content": result}


@router.post("/{session_id}/chat")
async def chat(session_id: str, req: SendMessageRequest, request: Request):
    """流式对话（SSE）。"""
    session_manager = get_session_manager(request)

    try:
        session = session_manager.load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")

    # 创建 AgentLoop
    from agent.loop import AgentLoop
    from agent.llm import LLMClient

    config = request.app.state.config
    llm = LLMClient(config.llm)

    agent_loop = AgentLoop(
        config=config,
        session=session,
        llm=llm,
    )

    async def generate():
        """生成 SSE 事件流。"""
        try:
            # 添加用户消息
            session.messages.append({"role": "user", "content": req.content})

            # 流式运行
            for chunk in agent_loop.stream_run(req.content):
                if isinstance(chunk, str):
                    # 文本 token
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"
                elif isinstance(chunk, dict):
                    # 工具调用或结果
                    yield f"data: {json.dumps(chunk)}\n\n"

            # 保存 session
            session_manager.save_session(session)

            # 结束事件
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            logger.exception("Chat error")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
