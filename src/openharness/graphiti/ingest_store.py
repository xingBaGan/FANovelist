"""SQLite ingest index and submit audit log."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class StoredParagraph:
    paragraph_uid: str
    source_path: str
    content_hash: str
    paragraph_text: str
    paragraph_index: int
    section_heading: str | None
    tombstone: bool
    episode_uuids: tuple[str, ...]
    edge_uuids: tuple[str, ...]


@dataclass(frozen=True)
class SubmitRun:
    id: int
    submitted_at: str
    submit_gate: str
    source_path: str
    source_kind: str
    submit_scope: str


class IngestStateStore:
    """Persist paragraph ingest state and submit history."""

    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            # Create schema_version table if it doesn't exist
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY
                )
                """
            )
            row = conn.execute("SELECT MAX(version) AS version FROM schema_version").fetchone()
            current_version = row["version"] if (row and row["version"] is not None) else 0

            # Sequential migrations list
            migrations = [
                # Migration 1: Basic original tables
                """
                CREATE TABLE IF NOT EXISTS documents (
                    source_path TEXT PRIMARY KEY,
                    source_kind TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS paragraphs (
                    paragraph_uid TEXT PRIMARY KEY,
                    source_path TEXT NOT NULL,
                    paragraph_index INTEGER NOT NULL,
                    section_heading TEXT,
                    content_hash TEXT NOT NULL,
                    tombstone INTEGER NOT NULL DEFAULT 0,
                    last_submitted_at TEXT
                );
                CREATE TABLE IF NOT EXISTS paragraph_edges (
                    paragraph_uid TEXT NOT NULL,
                    edge_uuid TEXT NOT NULL,
                    PRIMARY KEY (paragraph_uid, edge_uuid)
                );
                CREATE TABLE IF NOT EXISTS submit_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    submitted_at TEXT NOT NULL,
                    submit_gate TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    submit_scope TEXT NOT NULL,
                    actor TEXT,
                    report_json TEXT
                );
                CREATE TABLE IF NOT EXISTS submit_paragraph_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    submit_run_id INTEGER NOT NULL,
                    paragraph_uid TEXT,
                    action TEXT NOT NULL,
                    old_hash TEXT,
                    new_hash TEXT,
                    episodes_removed TEXT,
                    edges_removed TEXT,
                    episode_created TEXT,
                    llm_summary_excerpt TEXT,
                    FOREIGN KEY (submit_run_id) REFERENCES submit_runs(id)
                );
                """,
                # Migration 2: Add paragraph_text to paragraphs
                """
                ALTER TABLE paragraphs ADD COLUMN paragraph_text TEXT NOT NULL DEFAULT '';
                """,
                # Migration 3: Add chapters, value shifts, graph links, and chapter_path column
                """
                CREATE TABLE IF NOT EXISTS chapters (
                    chapter_path TEXT PRIMARY KEY,
                    title TEXT,
                    chapter_index INTEGER NOT NULL,
                    approval_status TEXT
                );
                ALTER TABLE paragraphs ADD COLUMN chapter_path TEXT;
                CREATE TABLE IF NOT EXISTS paragraph_graph_links (
                    paragraph_uid TEXT NOT NULL,
                    episode_uuid TEXT NOT NULL,
                    PRIMARY KEY (paragraph_uid, episode_uuid)
                );
                """
            ]

            # Execute migrations sequentially
            for ver_idx, sql in enumerate(migrations, 1):
                if current_version < ver_idx:
                    if ver_idx == 3:
                        # If a physical paragraph_episodes table already exists, copy data and drop it
                        table_check = conn.execute(
                            "SELECT name FROM sqlite_master WHERE type='table' AND name='paragraph_episodes'"
                        ).fetchone()
                        if table_check:
                            conn.execute(
                                """
                                INSERT OR IGNORE INTO paragraph_graph_links (paragraph_uid, episode_uuid)
                                SELECT paragraph_uid, episode_uuid FROM paragraph_episodes
                                """
                            )
                            conn.execute("DROP TABLE paragraph_episodes")

                        # Create scene_value_shifts table
                        conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS scene_value_shifts (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                chapter_path TEXT,
                                paragraph_uid TEXT,
                                conflict_focus TEXT,
                                value_dimension TEXT,
                                initial_value INTEGER,
                                target_value INTEGER,
                                FOREIGN KEY (chapter_path) REFERENCES chapters(chapter_path),
                                FOREIGN KEY (paragraph_uid) REFERENCES paragraphs(paragraph_uid)
                            );
                            """
                        )

                        # Create backward compatible VIEW and INSTEAD OF triggers for paragraph_episodes
                        conn.execute(
                            """
                            CREATE VIEW IF NOT EXISTS paragraph_episodes AS
                            SELECT * FROM paragraph_graph_links;
                            """
                        )
                        conn.execute(
                            """
                            CREATE TRIGGER IF NOT EXISTS insert_paragraph_episodes INSTEAD OF INSERT ON paragraph_episodes
                            BEGIN
                                INSERT OR IGNORE INTO paragraph_graph_links (paragraph_uid, episode_uuid)
                                VALUES (new.paragraph_uid, new.episode_uuid);
                            END;
                            """
                        )
                        conn.execute(
                            """
                            CREATE TRIGGER IF NOT EXISTS delete_paragraph_episodes INSTEAD OF DELETE ON paragraph_episodes
                            BEGIN
                                DELETE FROM paragraph_graph_links
                                WHERE paragraph_uid = old.paragraph_uid AND episode_uuid = old.episode_uuid;
                            END;
                            """
                        )

                    conn.executescript(sql)
                    current_version = ver_idx
                    conn.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (?)", (current_version,))

    def list_paragraphs(self, source_path: str) -> list[StoredParagraph]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM paragraphs WHERE source_path = ? AND tombstone = 0",
                (source_path,),
            ).fetchall()
            return [
                self._row_to_stored(row, _episode_edge_uuids(conn, row["paragraph_uid"]))
                for row in rows
            ]

    def get_paragraph(self, paragraph_uid: str) -> StoredParagraph | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM paragraphs WHERE paragraph_uid = ?",
                (paragraph_uid,),
            ).fetchone()
            if row is None:
                return None
            eps, eds = _episode_edge_uuids(conn, paragraph_uid)
        return self._row_to_stored(row, (eps, eds))

    def upsert_document(self, source_path: str, source_kind: str, group_id: str) -> None:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO documents (source_path, source_kind, group_id, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(source_path) DO UPDATE SET
                    source_kind = excluded.source_kind,
                    group_id = excluded.group_id,
                    updated_at = excluded.updated_at
                """,
                (source_path, source_kind, group_id, now),
            )

    def save_paragraph_links(
        self,
        *,
        paragraph_uid: str,
        source_path: str,
        paragraph_index: int,
        section_heading: str | None,
        content_hash: str,
        paragraph_text: str,
        episode_uuids: list[str],
        edge_uuids: list[str],
    ) -> None:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO paragraphs (
                    paragraph_uid, source_path, paragraph_index, section_heading,
                    content_hash, paragraph_text, tombstone, last_submitted_at, chapter_path
                ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
                ON CONFLICT(paragraph_uid) DO UPDATE SET
                    content_hash = excluded.content_hash,
                    paragraph_text = excluded.paragraph_text,
                    paragraph_index = excluded.paragraph_index,
                    section_heading = excluded.section_heading,
                    tombstone = 0,
                    last_submitted_at = excluded.last_submitted_at,
                    chapter_path = excluded.chapter_path
                """,
                (
                    paragraph_uid,
                    source_path,
                    paragraph_index,
                    section_heading,
                    content_hash,
                    paragraph_text,
                    now,
                    source_path,
                ),
            )
            conn.execute(
                "DELETE FROM paragraph_graph_links WHERE paragraph_uid = ?",
                (paragraph_uid,),
            )
            conn.execute(
                "DELETE FROM paragraph_edges WHERE paragraph_uid = ?",
                (paragraph_uid,),
            )
            for ep in episode_uuids:
                conn.execute(
                    "INSERT INTO paragraph_graph_links (paragraph_uid, episode_uuid) VALUES (?, ?)",
                    (paragraph_uid, ep),
                )
            for edge in edge_uuids:
                conn.execute(
                    "INSERT INTO paragraph_edges (paragraph_uid, edge_uuid) VALUES (?, ?)",
                    (paragraph_uid, edge),
                )

    def tombstone_paragraph(self, paragraph_uid: str) -> tuple[list[str], list[str]]:
        with self._connect() as conn:
            conn.execute(
                "UPDATE paragraphs SET tombstone = 1 WHERE paragraph_uid = ?",
                (paragraph_uid,),
            )
            episodes, edges = _episode_edge_uuids(conn, paragraph_uid)
            conn.execute(
                "DELETE FROM paragraph_graph_links WHERE paragraph_uid = ?",
                (paragraph_uid,),
            )
            conn.execute(
                "DELETE FROM paragraph_edges WHERE paragraph_uid = ?",
                (paragraph_uid,),
            )
        return episodes, edges

    def start_submit_run(
        self,
        *,
        submit_gate: str,
        source_path: str,
        source_kind: str,
        submit_scope: str,
        actor: str | None = None,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO submit_runs (
                    submitted_at, submit_gate, source_path, source_kind, submit_scope, actor
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (_utc_now(), submit_gate, source_path, source_kind, submit_scope, actor),
            )
            return int(cur.lastrowid)

    def log_paragraph_event(
        self,
        *,
        submit_run_id: int,
        paragraph_uid: str | None,
        action: str,
        old_hash: str | None = None,
        new_hash: str | None = None,
        episodes_removed: list[str] | None = None,
        edges_removed: list[str] | None = None,
        episode_created: str | None = None,
        llm_summary_excerpt: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO submit_paragraph_events (
                    submit_run_id, paragraph_uid, action, old_hash, new_hash,
                    episodes_removed, edges_removed, episode_created, llm_summary_excerpt
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    submit_run_id,
                    paragraph_uid,
                    action,
                    old_hash,
                    new_hash,
                    json.dumps(episodes_removed or []),
                    json.dumps(edges_removed or []),
                    episode_created,
                    (llm_summary_excerpt or "")[:500],
                ),
            )

    def finish_submit_run(self, submit_run_id: int, report: dict[str, object]) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE submit_runs SET report_json = ? WHERE id = ?",
                (json.dumps(report), submit_run_id),
            )

    def upsert_chapter(
        self,
        chapter_path: str,
        title: str,
        chapter_index: int,
        approval_status: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chapters (chapter_path, title, chapter_index, approval_status)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(chapter_path) DO UPDATE SET
                    title = excluded.title,
                    chapter_index = excluded.chapter_index,
                    approval_status = excluded.approval_status
                """,
                (chapter_path, title, chapter_index, approval_status),
            )

    def get_chapter(self, chapter_path: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM chapters WHERE chapter_path = ?",
                (chapter_path,),
            ).fetchone()
            if row is None:
                return None
            return dict(row)

    def list_chapters(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM chapters ORDER BY chapter_index").fetchall()
            return [dict(r) for r in rows]

    def save_scene_value_shift(
        self,
        chapter_path: str,
        paragraph_uid: str,
        conflict_focus: str,
        value_dimension: str,
        initial_value: int,
        target_value: int,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO scene_value_shifts (
                    chapter_path, paragraph_uid, conflict_focus, value_dimension, initial_value, target_value
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (chapter_path, paragraph_uid, conflict_focus, value_dimension, initial_value, target_value),
            )

    def list_scene_value_shifts(self, chapter_path: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM scene_value_shifts WHERE chapter_path = ?",
                (chapter_path,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_paragraph_graph_links(self, paragraph_uid: str) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT episode_uuid FROM paragraph_graph_links WHERE paragraph_uid = ?",
                (paragraph_uid,),
            ).fetchall()
            return [r[0] for r in rows]

    @staticmethod
    def _row_to_stored(
        row: sqlite3.Row,
        links: tuple[tuple[str, ...], tuple[str, ...]],
    ) -> StoredParagraph:
        eps, eds = links[0], links[1]
        return StoredParagraph(
            paragraph_uid=row["paragraph_uid"],
            source_path=row["source_path"],
            content_hash=row["content_hash"],
            paragraph_text=row["paragraph_text"] or "",
            paragraph_index=row["paragraph_index"],
            section_heading=row["section_heading"],
            tombstone=bool(row["tombstone"]),
            episode_uuids=tuple(eps),
            edge_uuids=tuple(eds),
        )


def _episode_edge_uuids(conn: sqlite3.Connection, paragraph_uid: str) -> tuple[list[str], list[str]]:
    eps = [
        r[0]
        for r in conn.execute(
            "SELECT episode_uuid FROM paragraph_episodes WHERE paragraph_uid = ?",
            (paragraph_uid,),
        ).fetchall()
    ]
    eds = [
        r[0]
        for r in conn.execute(
            "SELECT edge_uuid FROM paragraph_edges WHERE paragraph_uid = ?",
            (paragraph_uid,),
        ).fetchall()
    ]
    return eps, eds





def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
