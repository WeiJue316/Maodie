"""
Observation 结构化记忆存储层。

SQLite + FTS5 全文检索，支持去重、relevance 追踪和晋升。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class Observation:
    """一条结构化记忆。"""
    id: str
    type: str                # bugfix | feature | refactor | change | discovery | decision
    title: str
    narrative: str
    facts: list[str]
    concepts: list[str]
    files_read: list[str]
    files_modified: list[str]
    session_id: str
    created_at: str          # ISO-8601
    relevance_count: int = 0
    content_hash: str = ""
    promoted: int = 0        # 0=未晋升, 1=已晋升

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "narrative": self.narrative,
            "facts": self.facts,
            "concepts": self.concepts,
            "files_read": self.files_read,
            "files_modified": self.files_modified,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "relevance_count": self.relevance_count,
            "content_hash": self.content_hash,
            "promoted": self.promoted,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Observation:
        return cls(
            id=d["id"],
            type=d["type"],
            title=d["title"],
            narrative=d["narrative"],
            facts=d.get("facts", []),
            concepts=d.get("concepts", []),
            files_read=d.get("files_read", []),
            files_modified=d.get("files_modified", []),
            session_id=d["session_id"],
            created_at=d["created_at"],
            relevance_count=d.get("relevance_count", 0),
            content_hash=d.get("content_hash", ""),
            promoted=d.get("promoted", 0),
        )


def compute_content_hash(session_id: str, title: str, narrative: str) -> str:
    """计算去重哈希：SHA-256(session_id + title + narrative)[:16]。"""
    raw = f"{session_id}{title}{narrative}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def escape_fts5_query(query: str) -> str:
    """将查询转为 FTS5 安全格式。

    多词查询拆分后用 AND 连接，避免空格导致短语匹配失败。
    """
    # 按空白拆分，每段双引号包裹后 AND 连接
    words = query.split()
    if not words:
        return '""'
    parts = []
    for w in words:
        escaped = w.replace('"', '""')
        parts.append(f'"{escaped}"')
    return " AND ".join(parts)


def generate_daily_memory(date: str, store: ObservationStore) -> str:
    """从 SQLite 渲染指定日期的每日记忆 Markdown。"""
    observations = store.get_by_date(date)
    if not observations:
        return f"# {date} 每日记忆\n\n今天没有新的记忆。\n"
    lines = [f"# {date} 每日记忆\n"]
    for obs in observations:
        lines.append(f"## [{obs.type}] {obs.title}")
        lines.append(f"\n{obs.narrative}\n")
        if obs.facts:
            lines.append("**事实**：")
            for fact in obs.facts:
                lines.append(f"- {fact}")
        lines.append(f"\n*来源 Session: {obs.session_id}*\n")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# ObservationStore
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    narrative TEXT NOT NULL,
    facts TEXT NOT NULL,
    concepts TEXT NOT NULL,
    files_read TEXT NOT NULL,
    files_modified TEXT NOT NULL,
    session_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    relevance_count INTEGER DEFAULT 0,
    content_hash TEXT NOT NULL UNIQUE,
    promoted INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_obs_type ON observations(type);
CREATE INDEX IF NOT EXISTS idx_obs_session ON observations(session_id);
CREATE INDEX IF NOT EXISTS idx_obs_created ON observations(created_at);
"""


class ObservationStore:
    """SQLite + FTS5 结构化记忆存储。"""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._path = db_path
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._fts5_available = False
        self._init_schema()
        self._init_fts5()

    @property
    def fts5_available(self) -> bool:
        return self._fts5_available

    # ----- 初始化 -----

    def _init_schema(self) -> None:
        for stmt in _SCHEMA_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                self._conn.execute(stmt)
        self._conn.commit()

    def _init_fts5(self) -> None:
        try:
            self._conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_probe USING fts5(x)"
            )
            self._conn.execute("DROP TABLE _fts5_probe")
            self._fts5_available = True
        except Exception:
            return

        # 检查现有 FTS5 表是否使用 trigram 分词器（支持中文搜索）
        need_rebuild = False
        row = self._conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'observations_fts'"
        ).fetchone()
        if row and "trigram" not in row[0].lower():
            # 旧表没有 trigram 分词器，需要重建
            self._conn.execute("DROP TABLE IF EXISTS observations_fts")
            self._conn.execute("DROP TRIGGER IF EXISTS obs_ai")
            self._conn.execute("DROP TRIGGER IF EXISTS obs_ad")
            self._conn.execute("DROP TRIGGER IF EXISTS obs_au")
            need_rebuild = True

        self._conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS observations_fts USING fts5(
                title, narrative, facts, concepts,
                content='observations', content_rowid='rowid',
                tokenize='trigram'
            )
        """)
        # 自动同步触发器
        self._conn.executescript("""
            CREATE TRIGGER IF NOT EXISTS obs_ai AFTER INSERT ON observations BEGIN
                INSERT INTO observations_fts(rowid, title, narrative, facts, concepts)
                VALUES (new.rowid, new.title, new.narrative, new.facts, new.concepts);
            END;
            CREATE TRIGGER IF NOT EXISTS obs_ad AFTER DELETE ON observations BEGIN
                INSERT INTO observations_fts(observations_fts, rowid, title, narrative, facts, concepts)
                VALUES ('delete', old.rowid, old.title, old.narrative, old.facts, old.concepts);
            END;
            CREATE TRIGGER IF NOT EXISTS obs_au AFTER UPDATE ON observations BEGIN
                INSERT INTO observations_fts(observations_fts, rowid, title, narrative, facts, concepts)
                VALUES ('delete', old.rowid, old.title, old.narrative, old.facts, old.concepts);
                INSERT INTO observations_fts(rowid, title, narrative, facts, concepts)
                VALUES (new.rowid, new.title, new.narrative, new.facts, new.concepts);
            END;
        """)

        # 如果重建了 FTS5 表，从 observations 表同步数据
        if need_rebuild:
            self._conn.execute("""
                INSERT INTO observations_fts(rowid, title, narrative, facts, concepts)
                SELECT rowid, title, narrative, facts, concepts FROM observations
            """)

        self._conn.commit()

    # ----- 行转换 -----

    @staticmethod
    def _row_to_obs(row: sqlite3.Row) -> Observation:
        return Observation(
            id=row["id"],
            type=row["type"],
            title=row["title"],
            narrative=row["narrative"],
            facts=json.loads(row["facts"]),
            concepts=json.loads(row["concepts"]),
            files_read=json.loads(row["files_read"]),
            files_modified=json.loads(row["files_modified"]),
            session_id=row["session_id"],
            created_at=row["created_at"],
            relevance_count=row["relevance_count"],
            content_hash=row["content_hash"],
            promoted=row["promoted"],
        )

    # ----- 写入 -----

    def insert(self, obs: Observation) -> bool:
        """插入一条 observation。去重时返回 False。"""
        if not obs.content_hash:
            obs.content_hash = compute_content_hash(
                obs.session_id, obs.title, obs.narrative
            )
        try:
            self._conn.execute(
                """INSERT INTO observations
                   (id, type, title, narrative, facts, concepts,
                    files_read, files_modified, session_id, created_at,
                    relevance_count, content_hash, promoted)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    obs.id, obs.type, obs.title, obs.narrative,
                    json.dumps(obs.facts, ensure_ascii=False),
                    json.dumps(obs.concepts, ensure_ascii=False),
                    json.dumps(obs.files_read, ensure_ascii=False),
                    json.dumps(obs.files_modified, ensure_ascii=False),
                    obs.session_id, obs.created_at,
                    obs.relevance_count, obs.content_hash, obs.promoted,
                ),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def insert_batch(self, observations: list[Observation]) -> int:
        """批量插入，返回实际新增条数。"""
        count = 0
        for obs in observations:
            if self.insert(obs):
                count += 1
        return count

    # ----- 查询 -----

    def get_by_id(self, obs_id: str) -> Observation | None:
        row = self._conn.execute(
            "SELECT * FROM observations WHERE id = ?", (obs_id,)
        ).fetchone()
        return self._row_to_obs(row) if row else None

    def get_by_session(self, session_id: str) -> list[Observation]:
        rows = self._conn.execute(
            "SELECT * FROM observations WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        ).fetchall()
        return [self._row_to_obs(r) for r in rows]

    def get_by_date(self, date_prefix: str) -> list[Observation]:
        """按日期前缀查询（如 '2026-05-20'）。"""
        rows = self._conn.execute(
            "SELECT * FROM observations WHERE created_at LIKE ? ORDER BY created_at",
            (f"{date_prefix}%",),
        ).fetchall()
        return [self._row_to_obs(r) for r in rows]

    def get_recent(self, limit: int = 20) -> list[Observation]:
        rows = self._conn.execute(
            "SELECT * FROM observations ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_obs(r) for r in rows]

    def get_all_ids(self) -> set[str]:
        """返回所有 observation id 集合（用于同步检查）。"""
        rows = self._conn.execute("SELECT id FROM observations").fetchall()
        return {r["id"] for r in rows}

    # ----- Relevance 追踪 -----

    def increment_relevance(self, obs_id: str) -> None:
        self._conn.execute(
            "UPDATE observations SET relevance_count = relevance_count + 1 WHERE id = ?",
            (obs_id,),
        )
        self._conn.commit()

    def get_promotable(self, threshold: int = 3) -> list[Observation]:
        """返回 relevance_count >= threshold 且未晋升的 observation。"""
        rows = self._conn.execute(
            "SELECT * FROM observations WHERE relevance_count >= ? AND promoted = 0",
            (threshold,),
        ).fetchall()
        return [self._row_to_obs(r) for r in rows]

    def mark_promoted(self, obs_id: str) -> None:
        self._conn.execute(
            "UPDATE observations SET promoted = 1 WHERE id = ?", (obs_id,)
        )
        self._conn.commit()

    # ----- FTS5 检索 -----

    def search_fts(self, query: str, limit: int = 10) -> list[Observation]:
        """全文检索。FTS5 可用时用 MATCH，否则降级为 LIKE。"""
        if not query.strip():
            return []

        if self._fts5_available:
            # 先用 AND 查询（所有词都出现）
            fts_query = escape_fts5_query(query)
            rows = self._conn.execute(
                """SELECT o.* FROM observations o
                   JOIN observations_fts f ON f.rowid = o.rowid
                   WHERE observations_fts MATCH ?
                   ORDER BY f.rank
                   LIMIT ?""",
                (fts_query, limit),
            ).fetchall()

            # AND 无结果时，降级为 OR 查询（任一词出现即可）
            if not rows:
                words = query.split()
                if len(words) > 1:
                    or_query = " OR ".join(f'"{w.replace(chr(34), chr(34)*2)}"' for w in words)
                    rows = self._conn.execute(
                        """SELECT o.* FROM observations o
                           JOIN observations_fts f ON f.rowid = o.rowid
                           WHERE observations_fts MATCH ?
                           ORDER BY f.rank
                           LIMIT ?""",
                        (or_query, limit),
                    ).fetchall()

            # FTS5 仍无结果，降级为 LIKE 模糊匹配
            if not rows:
                pattern = f"%{query}%"
                rows = self._conn.execute(
                    """SELECT * FROM observations
                       WHERE title LIKE ? OR narrative LIKE ?
                       LIMIT ?""",
                    (pattern, pattern, limit),
                ).fetchall()
        else:
            pattern = f"%{query}%"
            rows = self._conn.execute(
                """SELECT * FROM observations
                   WHERE title LIKE ? OR narrative LIKE ?
                   LIMIT ?""",
                (pattern, pattern, limit),
            ).fetchall()

        return [self._row_to_obs(r) for r in rows]

    # ----- 统计 -----

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) as c FROM observations").fetchone()
        return row["c"] if row else 0

    def count_by_type(self) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT type, COUNT(*) as c FROM observations GROUP BY type"
        ).fetchall()
        return {r["type"]: r["c"] for r in rows}

    def count_promoted(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) as c FROM observations WHERE promoted = 1"
        ).fetchone()
        return row["c"] if row else 0

    # ----- 生命周期 -----

    def close(self) -> None:
        self._conn.close()
