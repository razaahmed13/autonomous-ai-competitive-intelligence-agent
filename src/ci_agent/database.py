from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Iterable

from .models import RawSourceItem, SourceType


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS raw_items (
                    id TEXT PRIMARY KEY,
                    source_name TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT UNIQUE NOT NULL,
                    published_at TEXT,
                    author TEXT,
                    raw_summary TEXT,
                    content TEXT,
                    fetched_at TEXT NOT NULL,
                    content_hash TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS intelligence_items (
                    id TEXT PRIMARY KEY,
                    canonical_title TEXT NOT NULL,
                    category TEXT NOT NULL,
                    importance_score REAL NOT NULL,
                    raw_score REAL NOT NULL DEFAULT 0,
                    summary TEXT NOT NULL,
                    source_links_json TEXT NOT NULL,
                    content_fingerprint TEXT UNIQUE NOT NULL,
                    reported_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS source_item_links (
                    intelligence_item_id TEXT NOT NULL,
                    raw_item_id TEXT NOT NULL,
                    PRIMARY KEY (intelligence_item_id, raw_item_id)
                );
                """
            )
            _ensure_column(conn, "intelligence_items", "raw_score", "REAL NOT NULL DEFAULT 0")
            _ensure_unique_index(conn, "idx_intelligence_items_content_fingerprint", "intelligence_items", "content_fingerprint")

    def upsert_raw_items(self, items: Iterable[RawSourceItem]) -> int:
        self.initialize()
        inserted = 0
        with self.connect() as conn:
            for item in items:
                before = conn.total_changes
                conn.execute(
                    """
                    INSERT OR IGNORE INTO raw_items (
                        id, source_name, source_type, title, url, published_at, author,
                        raw_summary, content, fetched_at, content_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.id,
                        item.source_name,
                        item.source_type.value,
                        item.title,
                        item.url,
                        item.published_at.isoformat() if item.published_at else None,
                        item.author,
                        item.raw_summary,
                        item.content,
                        item.fetched_at.isoformat(),
                        item.content_hash,
                    ),
                )
                if conn.total_changes > before:
                    inserted += 1
        return inserted

    def list_raw_items(self, limit: int = 100) -> list[RawSourceItem]:
        self.initialize()
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM raw_items ORDER BY fetched_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_raw_item(row) for row in rows]

    def list_recent_raw_items(self, *, hours: int = 24, limit: int = 200) -> list[RawSourceItem]:
        self.initialize()
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM raw_items
                WHERE fetched_at >= ?
                ORDER BY fetched_at DESC
                LIMIT ?
                """,
                (cutoff.isoformat(), limit),
            ).fetchall()
        return [self._row_to_raw_item(row) for row in rows]

    def has_reported_fingerprint(self, content_fingerprint: str) -> bool:
        self.initialize()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM intelligence_items WHERE content_fingerprint = ? LIMIT 1",
                (content_fingerprint,),
            ).fetchone()
        return row is not None

    def reported_fingerprints(self, fingerprints: Iterable[str]) -> set[str]:
        self.initialize()
        unique = sorted(set(fingerprints))
        if not unique:
            return set()
        placeholders = ",".join("?" for _ in unique)
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT content_fingerprint FROM intelligence_items WHERE content_fingerprint IN ({placeholders})",
                unique,
            ).fetchall()
        return {row["content_fingerprint"] for row in rows}

    def store_reported_intelligence_items(self, items: Iterable[dict]) -> int:
        self.initialize()
        inserted = 0
        reported_at = datetime.now(UTC).isoformat()
        with self.connect() as conn:
            for item in items:
                item_id = str(item["id"])
                raw_item_ids = [raw_id for raw_id in item.get("raw_item_ids", []) if raw_id]
                before = conn.total_changes
                conn.execute(
                    """
                    INSERT OR IGNORE INTO intelligence_items (
                        id, canonical_title, category, importance_score, raw_score,
                        summary, source_links_json, content_fingerprint, reported_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item_id,
                        item["canonical_title"],
                        item["category"],
                        float(item["importance_score"]),
                        float(item.get("raw_score", 0)),
                        item["summary"],
                        json.dumps(item["source_links"], ensure_ascii=False),
                        item["content_fingerprint"],
                        reported_at,
                    ),
                )
                if conn.total_changes > before:
                    inserted += 1
                    conn.executemany(
                        """
                        INSERT OR IGNORE INTO source_item_links (intelligence_item_id, raw_item_id)
                        VALUES (?, ?)
                        """,
                        [(item_id, raw_id) for raw_id in raw_item_ids],
                    )
        return inserted

    @staticmethod
    def _row_to_raw_item(row: sqlite3.Row) -> RawSourceItem:
        return RawSourceItem(
            id=row["id"],
            source_name=row["source_name"],
            source_type=SourceType(row["source_type"]),
            title=row["title"],
            url=row["url"],
            published_at=_parse_datetime(row["published_at"]),
            author=row["author"],
            raw_summary=row["raw_summary"],
            content=row["content"],
            fetched_at=_parse_datetime(row["fetched_at"]),
            content_hash=row["content_hash"],
        )


def _parse_datetime(value: str | None):
    if value is None:
        return None
    from datetime import datetime

    return datetime.fromisoformat(value)


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def _ensure_unique_index(conn: sqlite3.Connection, index_name: str, table: str, column: str) -> None:
    conn.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {table}({column})")
