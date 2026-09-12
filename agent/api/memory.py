"""
记忆 API 路由。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

if TYPE_CHECKING:
    from agent.memory import MemoryManager
    from agent.memory_search import MemorySearch
    from agent.observation import ObservationStore

logger = logging.getLogger(__name__)

router = APIRouter()


class UpdateLongTermRequest(BaseModel):
    content: str


class AppendMemoryRequest(BaseModel):
    category: str
    content: str


class AdvancedSearchRequest(BaseModel):
    query: str
    type: Optional[str] = None
    limit: Optional[int] = None


def get_memory_manager(request: Request) -> MemoryManager | None:
    return request.app.state.memory_manager


def get_observation_store(request: Request) -> ObservationStore | None:
    return request.app.state.observation_store


def get_memory_search(request: Request) -> MemorySearch | None:
    return request.app.state.memory_search


@router.get("/long-term")
async def get_long_term(request: Request):
    """获取 MEMORY.md。"""
    memory_manager = get_memory_manager(request)
    if not memory_manager:
        raise HTTPException(status_code=404, detail="Memory manager not available")

    content = memory_manager.load()
    categories = memory_manager.get_all()

    return {
        "content": content,
        "categories": categories,
    }


@router.put("/long-term")
async def update_long_term(req: UpdateLongTermRequest, request: Request):
    """更新 MEMORY.md。"""
    memory_manager = get_memory_manager(request)
    if not memory_manager:
        raise HTTPException(status_code=404, detail="Memory manager not available")

    memory_manager.save(req.content)
    return {"message": "Memory updated"}


@router.post("/long-term/append")
async def append_memory(req: AppendMemoryRequest, request: Request):
    """追加记忆。"""
    memory_manager = get_memory_manager(request)
    if not memory_manager:
        raise HTTPException(status_code=404, detail="Memory manager not available")

    memory_manager.append(req.category, req.content)
    return {"message": "Memory appended"}


@router.get("/observations")
async def list_observations(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    type: Optional[str] = None,
):
    """获取 Observation 列表。"""
    store = get_observation_store(request)
    if not store:
        raise HTTPException(status_code=404, detail="Observation store not available")

    observations = store.get_recent(limit=page_size * page)

    # 按类型过滤
    if type:
        observations = [o for o in observations if o.type == type]

    # 分页
    start = (page - 1) * page_size
    end = start + page_size
    observations = observations[start:end]

    return [
        {
            "id": o.id,
            "type": o.type,
            "title": o.title,
            "narrative": o.narrative,
            "facts": o.facts,
            "concepts": o.concepts,
            "files_read": o.files_read,
            "files_modified": o.files_modified,
            "session_id": o.session_id,
            "created_at": o.created_at,
            "relevance_count": o.relevance_count,
            "content_hash": o.content_hash,
            "promoted": o.promoted,
        }
        for o in observations
    ]


@router.get("/observations/{obs_id}")
async def get_observation(obs_id: str, request: Request):
    """获取单条 Observation。"""
    store = get_observation_store(request)
    if not store:
        raise HTTPException(status_code=404, detail="Observation store not available")

    obs = store.get_by_id(obs_id)
    if not obs:
        raise HTTPException(status_code=404, detail="Observation not found")

    return {
        "id": obs.id,
        "type": obs.type,
        "title": obs.title,
        "narrative": obs.narrative,
        "facts": obs.facts,
        "concepts": obs.concepts,
        "files_read": obs.files_read,
        "files_modified": obs.files_modified,
        "session_id": obs.session_id,
        "created_at": obs.created_at,
        "relevance_count": obs.relevance_count,
        "content_hash": obs.content_hash,
        "promoted": obs.promoted,
    }


@router.get("/observations/today")
async def get_today_observations(request: Request):
    """获取今天的 Observation。"""
    store = get_observation_store(request)
    if not store:
        raise HTTPException(status_code=404, detail="Observation store not available")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    observations = store.get_by_date(today)

    return [
        {
            "id": o.id,
            "type": o.type,
            "title": o.title,
            "narrative": o.narrative,
            "facts": o.facts,
            "concepts": o.concepts,
            "files_read": o.files_read,
            "files_modified": o.files_modified,
            "session_id": o.session_id,
            "created_at": o.created_at,
            "relevance_count": o.relevance_count,
            "content_hash": o.content_hash,
            "promoted": o.promoted,
        }
        for o in observations
    ]


@router.get("/observations/date/{date}")
async def get_observations_by_date(date: str, request: Request):
    """按日期获取 Observation。"""
    store = get_observation_store(request)
    if not store:
        raise HTTPException(status_code=404, detail="Observation store not available")

    observations = store.get_by_date(date)

    return [
        {
            "id": o.id,
            "type": o.type,
            "title": o.title,
            "narrative": o.narrative,
            "facts": o.facts,
            "concepts": o.concepts,
            "files_read": o.files_read,
            "files_modified": o.files_modified,
            "session_id": o.session_id,
            "created_at": o.created_at,
            "relevance_count": o.relevance_count,
            "content_hash": o.content_hash,
            "promoted": o.promoted,
        }
        for o in observations
    ]


@router.get("/search")
async def search_memory(request: Request, q: str = Query(..., min_length=1)):
    """搜索记忆。"""
    memory_search = get_memory_search(request)
    if not memory_search:
        raise HTTPException(status_code=404, detail="Memory search not available")

    observations = memory_search.search(q)

    return [
        {
            "id": o.id,
            "type": o.type,
            "title": o.title,
            "narrative": o.narrative,
            "facts": o.facts,
            "concepts": o.concepts,
            "files_read": o.files_read,
            "files_modified": o.files_modified,
            "session_id": o.session_id,
            "created_at": o.created_at,
            "relevance_count": o.relevance_count,
            "content_hash": o.content_hash,
            "promoted": o.promoted,
        }
        for o in observations
    ]


@router.post("/search")
async def advanced_search(req: AdvancedSearchRequest, request: Request):
    """高级搜索。"""
    memory_search = get_memory_search(request)
    if not memory_search:
        raise HTTPException(status_code=404, detail="Memory search not available")

    observations = memory_search.search(req.query, limit=req.limit)

    # 按类型过滤
    if req.type:
        observations = [o for o in observations if o.type == req.type]

    return [
        {
            "id": o.id,
            "type": o.type,
            "title": o.title,
            "narrative": o.narrative,
            "facts": o.facts,
            "concepts": o.concepts,
            "files_read": o.files_read,
            "files_modified": o.files_modified,
            "session_id": o.session_id,
            "created_at": o.created_at,
            "relevance_count": o.relevance_count,
            "content_hash": o.content_hash,
            "promoted": o.promoted,
        }
        for o in observations
    ]


@router.get("/promotable")
async def get_promotable(request: Request):
    """获取可晋升列表。"""
    store = get_observation_store(request)
    if not store:
        raise HTTPException(status_code=404, detail="Observation store not available")

    observations = store.get_promotable()

    return [
        {
            "id": o.id,
            "type": o.type,
            "title": o.title,
            "narrative": o.narrative,
            "facts": o.facts,
            "concepts": o.concepts,
            "files_read": o.files_read,
            "files_modified": o.files_modified,
            "session_id": o.session_id,
            "created_at": o.created_at,
            "relevance_count": o.relevance_count,
            "content_hash": o.content_hash,
            "promoted": o.promoted,
        }
        for o in observations
    ]


@router.post("/promote/{obs_id}")
async def promote(obs_id: str, request: Request):
    """手动晋升。"""
    memory_search = get_memory_search(request)
    store = get_observation_store(request)

    if not memory_search or not store:
        raise HTTPException(status_code=404, detail="Memory search not available")

    obs = store.get_by_id(obs_id)
    if not obs:
        raise HTTPException(status_code=404, detail="Observation not found")

    count = memory_search.check_and_promote([obs])

    return {"message": f"Promoted {count} observations"}


@router.post("/extract")
async def extract(request: Request):
    """手动触发提取。"""
    from agent.extractor import ObservationExtractor
    from agent.llm import LLMClient

    config = request.app.state.config
    store = get_observation_store(request)
    memory_search = get_memory_search(request)

    if not store:
        raise HTTPException(status_code=404, detail="Observation store not available")

    # 获取当前 session
    session_manager = request.app.state.session_manager
    session = session_manager.get_latest_session()

    if not session:
        raise HTTPException(status_code=404, detail="No session found")

    llm = LLMClient(config.llm)
    extractor = ObservationExtractor(
        llm_client=llm,
        store=store,
        vector_store=memory_search.vector_store if memory_search else None,
        config=config.observation,
    )

    observations = extractor.extract_from_session(session)

    return {"count": len(observations)}


@router.post("/extract/{session_id}")
async def extract_from_session(session_id: str, request: Request):
    """从指定 Session 提取。"""
    from agent.extractor import ObservationExtractor
    from agent.llm import LLMClient

    config = request.app.state.config
    store = get_observation_store(request)
    memory_search = get_memory_search(request)

    if not store:
        raise HTTPException(status_code=404, detail="Observation store not available")

    session_manager = request.app.state.session_manager

    try:
        session = session_manager.load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")

    llm = LLMClient(config.llm)
    extractor = ObservationExtractor(
        llm_client=llm,
        store=store,
        vector_store=memory_search.vector_store if memory_search else None,
        config=config.observation,
    )

    observations = extractor.extract_from_session(session)

    return {"count": len(observations)}


@router.get("/stats")
async def get_stats(request: Request):
    """获取记忆系统统计。"""
    memory_search = get_memory_search(request)
    if not memory_search:
        raise HTTPException(status_code=404, detail="Memory search not available")

    return memory_search.get_stats()
