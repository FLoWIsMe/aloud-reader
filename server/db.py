"""SQLite storage for documents, their segmented content, and settings."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    source_name TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_opened_at TEXT,
    word_count INTEGER NOT NULL,
    char_count INTEGER NOT NULL,
    chunk_count INTEGER NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    finished_at TEXT,
    voice TEXT
);
CREATE TABLE IF NOT EXISTS document_content (
    document_id TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    blocks_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);
"""

DOCUMENT_COLUMNS = (
    "id, title, source_kind, source_name, created_at, updated_at, last_opened_at, "
    "word_count, char_count, chunk_count, position, finished_at, voice"
)


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class Database:
    """A small thread-safe wrapper around one SQLite file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        with self._lock:
            self._conn.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            else:
                self._conn.execute("COMMIT")

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    # Documents

    def list_documents(self) -> list[dict[str, Any]]:
        rows = self.query(
            f"SELECT {DOCUMENT_COLUMNS} FROM documents "
            "ORDER BY COALESCE(last_opened_at, created_at) DESC"
        )
        return [dict(row) for row in rows]

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        row = self.query_one(
            f"SELECT {DOCUMENT_COLUMNS} FROM documents WHERE id = ?", (document_id,)
        )
        return dict(row) if row else None

    def get_blocks(self, document_id: str) -> list[dict[str, Any]] | None:
        row = self.query_one(
            "SELECT blocks_json FROM document_content WHERE document_id = ?", (document_id,)
        )
        return json.loads(row["blocks_json"]) if row else None

    def insert_document(self, doc: dict[str, Any], blocks: list[dict[str, Any]]) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO documents (id, title, source_kind, source_name, created_at, "
                "updated_at, last_opened_at, word_count, char_count, chunk_count, position, "
                "finished_at, voice) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    doc["id"],
                    doc["title"],
                    doc["source_kind"],
                    doc.get("source_name"),
                    doc["created_at"],
                    doc["updated_at"],
                    doc.get("last_opened_at"),
                    doc["word_count"],
                    doc["char_count"],
                    doc["chunk_count"],
                    doc.get("position", 0),
                    doc.get("finished_at"),
                    doc.get("voice"),
                ),
            )
            conn.execute(
                "INSERT INTO document_content (document_id, blocks_json) VALUES (?, ?)",
                (doc["id"], json.dumps(blocks, ensure_ascii=False)),
            )

    def update_document(self, document_id: str, fields: dict[str, Any]) -> bool:
        allowed = {"title", "position", "finished_at", "voice", "last_opened_at", "updated_at"}
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return self.get_document(document_id) is not None
        assignments = ", ".join(f"{key} = ?" for key in updates)
        with self.transaction() as conn:
            cursor = conn.execute(
                f"UPDATE documents SET {assignments} WHERE id = ?",
                (*updates.values(), document_id),
            )
            return cursor.rowcount > 0

    def delete_document(self, document_id: str) -> bool:
        with self.transaction() as conn:
            cursor = conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            return cursor.rowcount > 0

    def count_documents(self) -> int:
        row = self.query_one("SELECT COUNT(*) AS n FROM documents")
        return int(row["n"]) if row else 0

    # Settings

    def get_settings(self) -> dict[str, Any]:
        rows = self.query("SELECT key, value_json FROM settings")
        return {row["key"]: json.loads(row["value_json"]) for row in rows}

    def set_settings(self, values: dict[str, Any]) -> None:
        with self.transaction() as conn:
            for key, value in values.items():
                conn.execute(
                    "INSERT INTO settings (key, value_json) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json",
                    (key, json.dumps(value)),
                )
