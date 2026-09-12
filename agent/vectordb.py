"""
ChromaDB 向量检索层。

依赖 chromadb 和 fastembed，不可用时降级为 FTS5-only 模式。
"""

from __future__ import annotations

import numpy as np
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.observation import Observation, ObservationStore


class EmbeddingModel:
    """fastembed 本地 embedding 封装（延迟加载模型权重）。"""

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        self._model_name = model_name
        self._model = None

    def _ensure_loaded(self):
        if self._model is None:
            from fastembed import TextEmbedding
            self._model = TextEmbedding(model_name=self._model_name)

    def embed(self, text: str) -> np.ndarray:
        self._ensure_loaded()
        return next(self._model.embed([text or ""]))

    def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        self._ensure_loaded()
        return list(self._model.embed(texts))


class ChromaEmbeddingFunction:
    """适配 ChromaDB 的 EmbeddingFunction 接口。"""

    def __init__(self, model: EmbeddingModel, model_name: str = ""):
        self._model = model
        self._model_name = model_name

    def __call__(self, input: list[str]) -> list[np.ndarray]:
        safe = [str(t) if t is not None else "" for t in input]
        return self._model.embed_batch(safe)

    def name(self) -> str:
        return self._model_name or "custom"

    def embed_query(self, input) -> list[np.ndarray]:
        if isinstance(input, list):
            emb = self._model.embed_batch(input)[0] if input else np.array([])
        else:
            emb = self._model.embed(input or "")
        return [emb]

    def embed_documents(self, input: list[str]) -> list[np.ndarray]:
        return self._model.embed_batch(input)


class VectorStore:
    """ChromaDB 向量存储，不可用时 available=False。"""

    def __init__(
        self,
        persist_dir: Path,
        collection_name: str = "observations",
        embedding_model_name: str = "BAAI/bge-small-zh-v1.5",
    ) -> None:
        self._available = False
        self._collection = None
        try:
            import chromadb
            from chromadb.config import Settings

            persist_dir.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=str(persist_dir),
                settings=Settings(anonymized_telemetry=False),
            )
            model = EmbeddingModel(embedding_model_name)
            self._ef = ChromaEmbeddingFunction(model, model_name=embedding_model_name)
            self._collection = self._client.get_or_create_collection(
                name=collection_name,
                embedding_function=self._ef,
            )
            self._check_dimension(collection_name, model)
            self._available = True
        except ImportError:
            pass

    def _check_dimension(self, collection_name: str, model: EmbeddingModel) -> None:
        """检测向量维度是否匹配，不匹配时自动重建 collection。"""
        if self._collection is None or self._collection.count() == 0:
            return
        # 从现有数据取一条，对比维度
        sample = self._collection.get(limit=1, include=["embeddings"])
        embeddings = sample.get("embeddings")
        if embeddings is None or len(embeddings) == 0:
            return
        old_dim = len(embeddings[0])
        new_dim = len(model.embed("test"))
        if old_dim != new_dim:
            import logging
            logging.getLogger(__name__).info(
                "向量维度变更 %d → %d，重建 collection", old_dim, new_dim,
            )
            self._client.delete_collection(collection_name)
            self._collection = self._client.get_or_create_collection(
                name=collection_name,
                embedding_function=self._ef,
            )

    @property
    def available(self) -> bool:
        return self._available

    def add(self, obs: Observation) -> None:
        """将 observation 添加到向量库。"""
        if not self._available or self._collection is None:
            return
        self._collection.add(
            ids=[obs.id],
            documents=[f"{obs.title}\n{obs.narrative}"],
            metadatas=[{
                "observation_id": obs.id,
                "type": obs.type,
                "session_id": obs.session_id,
                "created_at": obs.created_at,
                "concepts": ",".join(obs.concepts),
            }],
        )

    def add_batch(self, observations: list[Observation]) -> None:
        """批量添加。"""
        if not self._available or self._collection is None or not observations:
            return
        self._collection.add(
            ids=[obs.id for obs in observations],
            documents=[f"{obs.title}\n{obs.narrative}" for obs in observations],
            metadatas=[{
                "observation_id": obs.id,
                "type": obs.type,
                "session_id": obs.session_id,
                "created_at": obs.created_at,
                "concepts": ",".join(obs.concepts),
            } for obs in observations],
        )

    def search(self, query: str, limit: int = 10) -> list[tuple[str, float]]:
        """语义检索，返回 (observation_id, distance) 列表。distance 越小越相似。"""
        if not self._available or self._collection is None or not query:
            return []
        results = self._collection.query(query_texts=[query], n_results=limit)
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]
        return list(zip(ids, distances))

    def delete(self, obs_id: str) -> None:
        if not self._available or self._collection is None:
            return
        self._collection.delete(ids=[obs_id])

    def count(self) -> int:
        if not self._available or self._collection is None:
            return 0
        return self._collection.count()

    def sync_from_store(self, store: ObservationStore) -> int:
        """启动时补全：将 SQLite 中缺失的 observation 同步到 ChromaDB。"""
        if not self._available or self._collection is None:
            return 0

        store_ids = store.get_all_ids()
        # 获取 ChromaDB 中已有的 ID
        existing = set()
        if self._collection.count() > 0:
            all_docs = self._collection.get()
            existing = set(all_docs.get("ids", []))

        missing_ids = store_ids - existing
        if not missing_ids:
            return 0

        observations = []
        for obs_id in missing_ids:
            obs = store.get_by_id(obs_id)
            if obs:
                observations.append(obs)

        if observations:
            self.add_batch(observations)
        return len(observations)
