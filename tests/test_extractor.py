"""ObservationExtractor 提取测试。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agent.observation import ObservationStore


@pytest.fixture
def store(tmp_path: Path) -> ObservationStore:
    return ObservationStore(tmp_path / "test.db")


@pytest.fixture
def mock_config():
    cfg = MagicMock()
    cfg.max_observations_per_session = 10
    cfg.extract_temperature = 0.3
    cfg.extract_model = ""
    return cfg


def _make_mock_llm(content: str):
    llm = MagicMock()
    response = MagicMock()
    response.content = content
    llm.chat_blocking.return_value = response
    return llm


class TestExtractValidJSON:
    def test_extract_two_observations(self, store: ObservationStore, mock_config):
        from agent.extractor import ObservationExtractor

        json_response = """[
            {
                "type": "bugfix",
                "title": "fix timeout",
                "narrative": "API calls need timeout=60",
                "facts": ["no default timeout"],
                "concepts": ["api"],
                "files_read": ["llm.py"],
                "files_modified": ["llm.py"]
            },
            {
                "type": "decision",
                "title": "use function calling",
                "narrative": "Switch from text parsing to FC",
                "facts": ["FC is more reliable"],
                "concepts": ["architecture"],
                "files_read": [],
                "files_modified": ["tools.py"]
            }
        ]"""
        llm = _make_mock_llm(json_response)
        ext = ObservationExtractor(llm, store, None, mock_config)

        results = ext.extract_from_messages(
            [{"role": "user", "content": "fix the timeout bug"}],
            session_id="s1",
        )
        assert len(results) == 2
        assert results[0].type == "bugfix"
        assert results[1].type == "decision"
        assert store.count() == 2


class TestExtractEmptyArray:
    def test_empty_returns_empty(self, store: ObservationStore, mock_config):
        from agent.extractor import ObservationExtractor

        llm = _make_mock_llm("[]")
        ext = ObservationExtractor(llm, store, None, mock_config)
        results = ext.extract_from_messages(
            [{"role": "user", "content": "hello"}], "s1"
        )
        assert results == []
        assert store.count() == 0


class TestExtractInvalidJSON:
    def test_invalid_json_returns_empty(self, store: ObservationStore, mock_config):
        from agent.extractor import ObservationExtractor

        llm = _make_mock_llm("this is not json at all")
        ext = ObservationExtractor(llm, store, None, mock_config)
        results = ext.extract_from_messages(
            [{"role": "user", "content": "test"}], "s1"
        )
        assert results == []

    def test_markdown_code_block(self, store: ObservationStore, mock_config):
        from agent.extractor import ObservationExtractor

        json_in_block = """```json
[{"type": "bugfix", "title": "fix", "narrative": "fixed", "facts": [], "concepts": [], "files_read": [], "files_modified": []}]
```"""
        llm = _make_mock_llm(json_in_block)
        ext = ObservationExtractor(llm, store, None, mock_config)
        results = ext.extract_from_messages(
            [{"role": "user", "content": "test"}], "s1"
        )
        assert len(results) == 1


class TestExtractPartialFields:
    def test_missing_optional_fields(self, store: ObservationStore, mock_config):
        from agent.extractor import ObservationExtractor

        json_response = """[{
            "type": "feature",
            "title": "new feature",
            "narrative": "added something"
        }]"""
        llm = _make_mock_llm(json_response)
        ext = ObservationExtractor(llm, store, None, mock_config)
        results = ext.extract_from_messages(
            [{"role": "user", "content": "test"}], "s1"
        )
        assert len(results) == 1
        assert results[0].facts == []
        assert results[0].concepts == []

    def test_invalid_type_defaults_to_discovery(self, store: ObservationStore, mock_config):
        from agent.extractor import ObservationExtractor

        json_response = """[{
            "type": "unknown_type",
            "title": "something",
            "narrative": "happened"
        }]"""
        llm = _make_mock_llm(json_response)
        ext = ObservationExtractor(llm, store, None, mock_config)
        results = ext.extract_from_messages(
            [{"role": "user", "content": "test"}], "s1"
        )
        assert results[0].type == "discovery"

    def test_missing_title_skipped(self, store: ObservationStore, mock_config):
        from agent.extractor import ObservationExtractor

        json_response = """[
            {"type": "bugfix", "title": "", "narrative": "desc"},
            {"type": "bugfix", "title": "ok", "narrative": "desc"}
        ]"""
        llm = _make_mock_llm(json_response)
        ext = ObservationExtractor(llm, store, None, mock_config)
        results = ext.extract_from_messages(
            [{"role": "user", "content": "test"}], "s1"
        )
        assert len(results) == 1


class TestExtractCapsAtMax:
    def test_cap_at_max(self, store: ObservationStore, mock_config):
        from agent.extractor import ObservationExtractor

        mock_config.max_observations_per_session = 2
        items = [
            {"type": "bugfix", "title": f"t{i}", "narrative": f"d{i}",
             "facts": [], "concepts": [], "files_read": [], "files_modified": []}
            for i in range(5)
        ]
        llm = _make_mock_llm(json.dumps(items))
        ext = ObservationExtractor(llm, store, None, mock_config)
        results = ext.extract_from_messages(
            [{"role": "user", "content": "test"}], "s1"
        )
        assert len(results) == 2


class TestExtractFromSession:
    def test_session_integration(self, store: ObservationStore, mock_config):
        from agent.extractor import ObservationExtractor
        from agent.session import Session

        json_response = """[{
            "type": "discovery",
            "title": "learned something",
            "narrative": "important discovery",
            "facts": ["fact 1"],
            "concepts": ["learning"],
            "files_read": [],
            "files_modified": []
        }]"""
        llm = _make_mock_llm(json_response)
        ext = ObservationExtractor(llm, store, None, mock_config)

        session = Session(
            id="test-session",
            created_at="2026-05-20T10:00:00Z",
            updated_at="2026-05-20T10:00:00Z",
            messages=[
                {"role": "system", "content": "you are helpful"},
                {"role": "user", "content": "tell me about python"},
                {"role": "assistant", "content": "python is great"},
            ],
        )
        results = ext.extract_from_session(session)
        assert len(results) == 1
        assert results[0].session_id == "test-session"
        assert store.count() == 1


import json  # noqa: E402 (needed for TestExtractCapsAtMax)
