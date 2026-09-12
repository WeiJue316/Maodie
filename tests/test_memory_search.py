"""MemorySearch 混合检索与晋升测试。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agent.observation import Observation, ObservationStore, compute_content_hash


def _make_obs(**kwargs) -> Observation:
    defaults = dict(
        id="obs-001",
        type="bugfix",
        title="fix timeout",
        narrative="set timeout=60 for API calls",
        facts=["API has no default timeout"],
        concepts=["api-design"],
        files_read=["llm.py"],
        files_modified=["llm.py"],
        session_id="s1",
        created_at="2026-05-20T10:00:00Z",
        relevance_count=0,
        content_hash="",
        promoted=0,
    )
    defaults.update(kwargs)
    if not defaults["content_hash"]:
        defaults["content_hash"] = compute_content_hash(
            defaults["session_id"], defaults["title"], defaults["narrative"]
        )
    return Observation(**defaults)


@pytest.fixture
def store(tmp_path: Path) -> ObservationStore:
    return ObservationStore(tmp_path / "test.db")


@pytest.fixture
def mock_config():
    cfg = MagicMock()
    cfg.search_limit = 5
    cfg.promotion_threshold = 3
    cfg.auto_promote = True
    return cfg


class TestHybridSearch:
    def test_fts_only_when_no_vector(self, store: ObservationStore, mock_config):
        from agent.memory_search import MemorySearch

        store.insert(_make_obs(title="fix API timeout"))
        store.insert(_make_obs(id="obs-002", title="add feature X", type="feature"))

        ms = MemorySearch(
            store=store,
            vector_store=None,
            memory_manager=None,
            llm_client=None,
            config=mock_config,
        )
        results = ms.search("timeout", limit=5)
        assert len(results) >= 1
        assert any("timeout" in r.title for r in results)

    def test_vector_and_fts_merge(self, store: ObservationStore, mock_config):
        from agent.memory_search import MemorySearch

        # 插入 3 条 observation
        for i in range(3):
            store.insert(_make_obs(id=f"obs-{i}", title=f"topic {i}"))

        # Mock vector store 返回 obs-0 和 obs-1
        mock_vs = MagicMock()
        mock_vs.available = True
        mock_vs.search.return_value = [("obs-0", 0.3), ("obs-1", 0.5)]

        ms = MemorySearch(
            store=store,
            vector_store=mock_vs,
            memory_manager=None,
            llm_client=None,
            config=mock_config,
        )
        results = ms.search("topic", limit=5)
        # 应该包含向量检索命中的
        result_ids = {r.id for r in results}
        assert "obs-0" in result_ids

    def test_search_increments_relevance(self, store: ObservationStore, mock_config):
        from agent.memory_search import MemorySearch

        store.insert(_make_obs(title="fix timeout"))
        ms = MemorySearch(
            store=store, vector_store=None, memory_manager=None,
            llm_client=None, config=mock_config,
        )
        ms.search("timeout")
        obs = store.get_by_id("obs-001")
        assert obs.relevance_count >= 1


class TestPromotion:
    def test_promote_when_threshold_met(self, store: ObservationStore, mock_config):
        from agent.memory_search import MemorySearch

        store.insert(_make_obs(relevance_count=3))
        mock_mm = MagicMock()
        mock_llm = MagicMock()
        mock_llm.chat_blocking.return_value.content = "API 调用需要设置 timeout。"

        ms = MemorySearch(
            store=store, vector_store=None, memory_manager=mock_mm,
            llm_client=mock_llm, config=mock_config,
        )
        obs = store.get_by_id("obs-001")
        count = ms.check_and_promote([obs])
        assert count == 1
        mock_mm.append.assert_called_once()
        assert mock_mm.append.call_args[0][0] == "项目约束"  # bugfix → 项目约束
        assert store.get_by_id("obs-001").promoted == 1

    def test_skip_below_threshold(self, store: ObservationStore, mock_config):
        from agent.memory_search import MemorySearch

        store.insert(_make_obs(relevance_count=1))
        ms = MemorySearch(
            store=store, vector_store=None, memory_manager=MagicMock(),
            llm_client=MagicMock(), config=mock_config,
        )
        obs = store.get_by_id("obs-001")
        assert ms.check_and_promote([obs]) == 0

    def test_skip_already_promoted(self, store: ObservationStore, mock_config):
        from agent.memory_search import MemorySearch

        store.insert(_make_obs(relevance_count=5, promoted=1))
        ms = MemorySearch(
            store=store, vector_store=None, memory_manager=MagicMock(),
            llm_client=MagicMock(), config=mock_config,
        )
        obs = store.get_by_id("obs-001")
        assert ms.check_and_promote([obs]) == 0

    def test_type_category_mapping(self, store: ObservationStore, mock_config):
        from agent.memory_search import MemorySearch

        store.insert(_make_obs(type="feature", relevance_count=3))
        mock_mm = MagicMock()
        mock_llm = MagicMock()
        mock_llm.chat_blocking.return_value.content = "新功能描述。"

        ms = MemorySearch(
            store=store, vector_store=None, memory_manager=mock_mm,
            llm_client=mock_llm, config=mock_config,
        )
        obs = store.get_by_id("obs-001")
        ms.check_and_promote([obs])
        assert mock_mm.append.call_args[0][0] == "历史上下文"


class TestFormatMemoryContext:
    def test_format(self, store: ObservationStore, mock_config):
        from agent.memory_search import MemorySearch

        ms = MemorySearch(
            store=store, vector_store=None, memory_manager=None,
            llm_client=None, config=mock_config,
        )
        obs = _make_obs()
        result = ms.format_memory_context([obs])
        assert "相关记忆" in result
        assert "[bugfix]" in result
        assert "fix timeout" in result
        assert "api-design" in result

    def test_empty_list(self, store: ObservationStore, mock_config):
        from agent.memory_search import MemorySearch

        ms = MemorySearch(
            store=store, vector_store=None, memory_manager=None,
            llm_client=None, config=mock_config,
        )
        assert ms.format_memory_context([]) == ""


class TestGetStats:
    def test_stats_structure(self, store: ObservationStore, mock_config):
        from agent.memory_search import MemorySearch

        store.insert(_make_obs())
        ms = MemorySearch(
            store=store, vector_store=None, memory_manager=None,
            llm_client=None, config=mock_config,
        )
        stats = ms.get_stats()
        assert stats["total_observations"] == 1
        assert "by_type" in stats
        assert "fts5_available" in stats
        assert stats["vectordb_available"] is False
