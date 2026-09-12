"""
混合检索与晋升机制。

编排 FTS5 + ChromaDB 双路检索，追踪 relevance_count，驱动自动晋升。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.config import MemorySearchConfig
    from agent.llm import LLMClient
    from agent.memory import MemoryManager
    from agent.observation import Observation, ObservationStore
    from agent.vectordb import VectorStore

# Observation type → MEMORY.md 分类映射
_TYPE_CATEGORY_MAP = {
    "bugfix": "项目约束",
    "decision": "项目约束",
    "feature": "历史上下文",
    "discovery": "历史上下文",
    "refactor": "历史上下文",
    "change": "历史上下文",
}

_PROMOTION_PROMPT = """请将以下 observation 压缩为一句话（<30字），用于写入长期记忆文件。

标题：{title}
描述：{narrative}
事实：{facts}

只输出压缩后的一句话，不要其他内容。"""


class MemorySearch:
    """混合检索编排器。"""

    def __init__(
        self,
        store: ObservationStore,
        vector_store: VectorStore | None,
        memory_manager: MemoryManager | None,
        llm_client: LLMClient | None,
        config: MemorySearchConfig,
    ) -> None:
        self._store = store
        self._vector_store = vector_store
        self._memory_manager = memory_manager
        self._llm_client = llm_client
        self._config = config

    @property
    def vector_store(self) -> VectorStore | None:
        return self._vector_store

    @property
    def store(self) -> ObservationStore:
        return self._store

    def search(self, query: str, limit: int | None = None) -> list[Observation]:
        """混合检索：向量 + FTS5 → merge → top-N。"""
        limit = limit or self._config.search_limit
        k = limit * 2  # 多取一些用于合并

        results: dict[str, float] = {}  # obs_id -> score（越小越好）

        # 向量检索路径
        if self._vector_store and self._vector_store.available:
            vec_results = self._vector_store.search(query, limit=k)
            for rank, (obs_id, _distance) in enumerate(vec_results):
                results[obs_id] = rank

        # FTS5 检索路径
        fts_results = self._store.search_fts(query, limit=k)
        for rank, obs in enumerate(fts_results):
            if obs.id in results:
                # 两条路径都命中：取更好排名
                results[obs.id] = min(results[obs.id], rank)
            else:
                results[obs.id] = rank + len(results)

        # 排序取 top-N
        sorted_ids = sorted(results, key=results.get)[:limit]

        # 获取完整 observation 并追踪引用
        observations = []
        for obs_id in sorted_ids:
            obs = self._store.get_by_id(obs_id)
            if obs:
                self._store.increment_relevance(obs_id)
                observations.append(obs)

        return observations

    def check_and_promote(self, observations: list[Observation]) -> int:
        """检查并执行晋升。返回晋升条数。"""
        promoted_count = 0
        threshold = self._config.promotion_threshold

        for obs in observations:
            if obs.relevance_count < threshold:
                continue
            if obs.promoted:
                continue

            # LLM 压缩
            compressed = self._compress_observation(obs)
            if not compressed:
                continue

            # 映射分类
            category = _TYPE_CATEGORY_MAP.get(obs.type, "历史上下文")

            # 写入 MEMORY.md
            if self._memory_manager:
                self._memory_manager.append(category, compressed)

            # 标记已晋升
            self._store.mark_promoted(obs.id)
            promoted_count += 1

        return promoted_count

    def _compress_observation(self, obs: Observation) -> str | None:
        """用 LLM 将 observation 压缩为一句话。"""
        if not self._llm_client:
            return None

        prompt = _PROMOTION_PROMPT.format(
            title=obs.title,
            narrative=obs.narrative,
            facts="; ".join(obs.facts) if obs.facts else "无",
        )

        try:
            response = self._llm_client.chat_blocking(
                messages=[{"role": "user", "content": prompt}]
            )
            text = response.content.strip()
            return text if text else None
        except Exception:
            return None

    def format_memory_context(self, observations: list[Observation]) -> str:
        """将检索结果格式化为 system prompt 注入文本。"""
        if not observations:
            return ""

        lines = [
            "# 相关记忆",
            "以下是与当前对话相关的历史记忆，请参考：",
            "",
        ]

        for obs in observations:
            lines.append(f"## [{obs.type}] {obs.title}")
            lines.append(obs.narrative)
            if obs.facts:
                lines.append("- 事实：" + "；".join(obs.facts))
            if obs.concepts:
                lines.append("- 概念：" + ", ".join(obs.concepts))
            if obs.files_read:
                lines.append("- 涉及文件：" + ", ".join(obs.files_read))
            lines.append("")

        return "\n".join(lines)

    def get_stats(self) -> dict:
        """返回记忆系统统计信息。"""
        stats: dict = {
            "total_observations": self._store.count(),
            "by_type": self._store.count_by_type(),
            "promoted_count": self._store.count_promoted(),
            "fts5_available": self._store.fts5_available,
            "vectordb_available": False,
            "vectordb_count": 0,
        }
        if self._vector_store:
            stats["vectordb_available"] = self._vector_store.available
            if self._vector_store.available:
                stats["vectordb_count"] = self._vector_store.count()
        return stats
