"""VectorStore 测试（Mock ChromaDB）。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent.observation import Observation, compute_content_hash


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
        content_hash=compute_content_hash("s1", "fix timeout", "set timeout=60 for API calls"),
        promoted=0,
    )
    defaults.update(kwargs)
    return Observation(**defaults)


class TestVectorStoreUnavailable:
    """chromadb 不可用时的行为。"""

    def test_available_is_false(self, tmp_path: Path):
        with patch.dict("sys.modules", {"chromadb": None}):
            from agent.vectordb import VectorStore
            vs = VectorStore(tmp_path / "chroma")
            assert vs.available is False

    def test_search_returns_empty(self, tmp_path: Path):
        with patch.dict("sys.modules", {"chromadb": None}):
            from agent.vectordb import VectorStore
            vs = VectorStore(tmp_path / "chroma")
            assert vs.search("test") == []

    def test_count_returns_zero(self, tmp_path: Path):
        with patch.dict("sys.modules", {"chromadb": None}):
            from agent.vectordb import VectorStore
            vs = VectorStore(tmp_path / "chroma")
            assert vs.count() == 0

    def test_add_is_noop(self, tmp_path: Path):
        with patch.dict("sys.modules", {"chromadb": None}):
            from agent.vectordb import VectorStore
            vs = VectorStore(tmp_path / "chroma")
            vs.add(_make_obs())  # should not raise


class TestVectorStoreWithMock:
    """使用 Mock 测试 VectorStore 的正常路径。"""

    def _make_vs(self, tmp_path: Path):
        """构造一个 Mock 化的 VectorStore。"""
        mock_collection = MagicMock()
        mock_collection.count.return_value = 0
        mock_collection.query.return_value = {
            "ids": [["obs-001", "obs-002"]],
            "distances": [[0.3, 0.7]],
        }
        mock_collection.get.return_value = {"ids": []}

        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection

        mock_chromadb = MagicMock()
        mock_chromadb.PersistentClient.return_value = mock_client

        with patch.dict("sys.modules", {
            "chromadb": mock_chromadb,
            "chromadb.config": MagicMock(),
            "fastembed": MagicMock(),
        }):
            from agent.vectordb import VectorStore
            vs = VectorStore(tmp_path / "chroma")
            vs._collection = mock_collection
            vs._available = True
            return vs, mock_collection

    def test_add_calls_collection(self, tmp_path: Path):
        vs, mock_col = self._make_vs(tmp_path)
        obs = _make_obs()
        vs.add(obs)
        mock_col.add.assert_called_once()
        call_args = mock_col.add.call_args
        assert call_args.kwargs["ids"] == [obs.id]

    def test_add_batch(self, tmp_path: Path):
        vs, mock_col = self._make_vs(tmp_path)
        obs_list = [_make_obs(id=f"obs-{i}") for i in range(3)]
        vs.add_batch(obs_list)
        mock_col.add.assert_called_once()
        assert len(mock_col.add.call_args.kwargs["ids"]) == 3

    def test_search_returns_results(self, tmp_path: Path):
        vs, mock_col = self._make_vs(tmp_path)
        results = vs.search("test query", limit=2)
        assert len(results) == 2
        assert results[0] == ("obs-001", 0.3)
        mock_col.query.assert_called_once_with(query_texts=["test query"], n_results=2)

    def test_delete(self, tmp_path: Path):
        vs, mock_col = self._make_vs(tmp_path)
        vs.delete("obs-001")
        mock_col.delete.assert_called_once_with(ids=["obs-001"])

    def test_count(self, tmp_path: Path):
        vs, mock_col = self._make_vs(tmp_path)
        mock_col.count.return_value = 42
        assert vs.count() == 42

    def test_sync_from_store(self, tmp_path: Path):
        vs, mock_col = self._make_vs(tmp_path)
        mock_store = MagicMock()
        mock_store.get_all_ids.return_value = {"obs-001", "obs-002"}
        mock_col.count.return_value = 0
        mock_col.get.return_value = {"ids": []}

        obs1 = _make_obs(id="obs-001")
        obs2 = _make_obs(id="obs-002", title="other")
        mock_store.get_by_id.side_effect = lambda oid: obs1 if oid == "obs-001" else obs2

        synced = vs.sync_from_store(mock_store)
        assert synced == 2
        mock_col.add.assert_called_once()
