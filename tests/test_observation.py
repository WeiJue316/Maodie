"""Observation 存储层测试。"""

from __future__ import annotations

import pytest
from pathlib import Path

from agent.observation import (
    Observation,
    ObservationStore,
    compute_content_hash,
    escape_fts5_query,
    generate_daily_memory,
)


def _make_obs(**kwargs) -> Observation:
    """构建测试用 Observation，允许覆盖默认值。"""
    defaults = dict(
        id="obs-001",
        type="bugfix",
        title="修复 API 超时问题",
        narrative="在调用 DeepSeek API 时需要设置 timeout=60",
        facts=["DeepSeek API 默认无超时限制"],
        concepts=["api-design", "error-handling"],
        files_read=["agent/llm.py"],
        files_modified=["agent/llm.py"],
        session_id="session-001",
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


# ---------------------------------------------------------------------------
# 插入与去重
# ---------------------------------------------------------------------------

class TestObservationInsert:
    def test_insert_and_get(self, store: ObservationStore):
        obs = _make_obs()
        assert store.insert(obs) is True
        got = store.get_by_id(obs.id)
        assert got is not None
        assert got.title == obs.title
        assert got.facts == obs.facts

    def test_duplicate_hash_returns_false(self, store: ObservationStore):
        obs1 = _make_obs()
        obs2 = _make_obs(id="obs-002")  # 不同 id，相同 content_hash
        assert store.insert(obs1) is True
        assert store.insert(obs2) is False

    def test_insert_batch(self, store: ObservationStore):
        obs_list = [
            _make_obs(id=f"obs-{i}", title=f"title {i}")
            for i in range(3)
        ]
        assert store.insert_batch(obs_list) == 3
        assert store.count() == 3

    def test_insert_batch_with_duplicates(self, store: ObservationStore):
        obs_list = [_make_obs(id=f"obs-{i}") for i in range(3)]
        store.insert_batch(obs_list)
        # 再插入相同内容
        assert store.insert_batch(obs_list) == 0


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------

class TestGetBySession:
    def test_filter_by_session(self, store: ObservationStore):
        store.insert(_make_obs(session_id="s1"))
        store.insert(_make_obs(id="obs-002", session_id="s2", title="other"))
        results = store.get_by_session("s1")
        assert len(results) == 1
        assert results[0].session_id == "s1"


class TestGetRecent:
    def test_returns_limited_results(self, store: ObservationStore):
        for i in range(5):
            store.insert(_make_obs(id=f"obs-{i}", title=f"t{i}", created_at=f"2026-05-20T{i:02d}:00:00Z"))
        results = store.get_recent(limit=3)
        assert len(results) == 3

    def test_ordered_by_created_at_desc(self, store: ObservationStore):
        store.insert(_make_obs(id="old", created_at="2026-05-20T01:00:00Z"))
        store.insert(_make_obs(id="new", title="new", created_at="2026-05-20T23:00:00Z"))
        results = store.get_recent()
        assert results[0].id == "new"


class TestGetByDate:
    def test_date_prefix_match(self, store: ObservationStore):
        store.insert(_make_obs(created_at="2026-05-20T10:00:00Z"))
        store.insert(_make_obs(id="obs-002", title="other", created_at="2026-05-21T10:00:00Z"))
        results = store.get_by_date("2026-05-20")
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Relevance 追踪
# ---------------------------------------------------------------------------

class TestIncrementRelevance:
    def test_increment(self, store: ObservationStore):
        store.insert(_make_obs())
        store.increment_relevance("obs-001")
        store.increment_relevance("obs-001")
        obs = store.get_by_id("obs-001")
        assert obs.relevance_count == 2


class TestGetPromotable:
    def test_below_threshold(self, store: ObservationStore):
        store.insert(_make_obs(relevance_count=2))
        assert len(store.get_promotable(threshold=3)) == 0

    def test_at_threshold(self, store: ObservationStore):
        store.insert(_make_obs(relevance_count=3))
        assert len(store.get_promotable(threshold=3)) == 1

    def test_already_promoted_excluded(self, store: ObservationStore):
        store.insert(_make_obs(relevance_count=5, promoted=1))
        assert len(store.get_promotable(threshold=3)) == 0


class TestMarkPromoted:
    def test_mark_and_filter(self, store: ObservationStore):
        store.insert(_make_obs(relevance_count=5))
        store.mark_promoted("obs-001")
        assert len(store.get_promotable(threshold=3)) == 0
        obs = store.get_by_id("obs-001")
        assert obs.promoted == 1


# ---------------------------------------------------------------------------
# FTS5 检索
# ---------------------------------------------------------------------------

class TestFTSSearch:
    def test_search_by_keyword_ascii(self, store: ObservationStore):
        """英文关键词 FTS5 和 LIKE 都能匹配。"""
        store.insert(_make_obs(title="fix API timeout issue"))
        results = store.search_fts("timeout")
        assert len(results) >= 1

    def test_search_by_keyword_like_fallback(self, store: ObservationStore):
        """中文关键词用 LIKE 降级匹配（FTS5 默认分词器不支持中文）。"""
        store.insert(_make_obs())
        # 直接用 LIKE 测试
        pattern = "%超时%"
        rows = store._conn.execute(
            "SELECT * FROM observations WHERE title LIKE ? OR narrative LIKE ?",
            (pattern, pattern),
        ).fetchall()
        assert len(rows) >= 1

    def test_search_empty_query(self, store: ObservationStore):
        store.insert(_make_obs())
        assert store.search_fts("") == []

    def test_search_no_match(self, store: ObservationStore):
        store.insert(_make_obs())
        results = store.search_fts("completely_unrelated_xyz_12345")
        assert len(results) == 0


# ---------------------------------------------------------------------------
# 去重哈希
# ---------------------------------------------------------------------------

class TestContentHash:
    def test_same_input_same_hash(self):
        h1 = compute_content_hash("s1", "title", "narrative")
        h2 = compute_content_hash("s1", "title", "narrative")
        assert h1 == h2

    def test_different_input_different_hash(self):
        h1 = compute_content_hash("s1", "title", "narrative")
        h2 = compute_content_hash("s1", "title", "different")
        assert h1 != h2

    def test_hash_length(self):
        h = compute_content_hash("s", "t", "n")
        assert len(h) == 16


# ---------------------------------------------------------------------------
# FTS5 转义
# ---------------------------------------------------------------------------

class TestEscapeFTS5:
    def test_wraps_in_quotes(self):
        assert escape_fts5_query("hello") == '"hello"'

    def test_escapes_double_quote(self):
        assert escape_fts5_query('say "hi"') == '"say" AND """hi"""'

    def test_multi_word_uses_and(self):
        assert escape_fts5_query("foo bar") == '"foo" AND "bar"'


# ---------------------------------------------------------------------------
# 每日记忆
# ---------------------------------------------------------------------------

class TestDailyMemory:
    def test_empty_day(self, store: ObservationStore):
        result = generate_daily_memory("2026-05-20", store)
        assert "没有新的记忆" in result

    def test_with_observations(self, store: ObservationStore):
        store.insert(_make_obs(created_at="2026-05-20T10:00:00Z"))
        result = generate_daily_memory("2026-05-20", store)
        assert "2026-05-20" in result
        assert "修复 API 超时问题" in result


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------

class TestStats:
    def test_count(self, store: ObservationStore):
        assert store.count() == 0
        store.insert(_make_obs())
        assert store.count() == 1

    def test_count_by_type(self, store: ObservationStore):
        store.insert(_make_obs(type="bugfix"))
        store.insert(_make_obs(id="obs-002", type="feature", title="f"))
        by_type = store.count_by_type()
        assert by_type["bugfix"] == 1
        assert by_type["feature"] == 1

    def test_count_promoted(self, store: ObservationStore):
        store.insert(_make_obs(promoted=1))
        store.insert(_make_obs(id="obs-002", title="t"))
        assert store.count_promoted() == 1


# ---------------------------------------------------------------------------
# 数据序列化
# ---------------------------------------------------------------------------

class TestObservationSerialization:
    def test_to_dict_from_dict_roundtrip(self):
        obs = _make_obs()
        d = obs.to_dict()
        obs2 = Observation.from_dict(d)
        assert obs2.id == obs.id
        assert obs2.facts == obs.facts
        assert obs2.concepts == obs.concepts
