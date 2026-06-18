import json
import sqlite3
from pathlib import Path
from typing import Any

from app.models import GrabRequest, Release


class Store:
    def __init__(self, database_path: str):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                create table if not exists grabs (
                    id integer primary key autoincrement,
                    created_at text not null default current_timestamp,
                    title text not null,
                    media_type text not null,
                    category text,
                    payload text not null,
                    response text
                )
                """
            )
            conn.execute(
                """
                create table if not exists release_cache (
                    result_id text primary key,
                    created_at text not null default current_timestamp,
                    request_id integer,
                    query text not null,
                    media_type text not null,
                    title text not null,
                    download_url text,
                    release_json text not null
                )
                """
            )
            conn.execute(
                """
                create table if not exists media_requests (
                    id integer primary key autoincrement,
                    created_at text not null default current_timestamp,
                    updated_at text not null default current_timestamp,
                    query text not null,
                    media_type text not null,
                    min_resolution text not null default 'any',
                    status text not null default 'new',
                    best_result_id text,
                    best_title text,
                    best_score integer,
                    total integer not null default 0,
                    accepted integer not null default 0,
                    rejected integer not null default 0
                )
                """
            )
            self._ensure_column(conn, "release_cache", "request_id", "integer")
            self._ensure_column(
                conn,
                "media_requests",
                "min_resolution",
                "text not null default 'any'",
            )

    def _ensure_column(
        self, conn: sqlite3.Connection, table: str, column: str, definition: str
    ) -> None:
        columns = {
            row["name"]
            for row in conn.execute(f"pragma table_info({table})").fetchall()
            if isinstance(row["name"], str)
        }
        if column not in columns:
            conn.execute(f"alter table {table} add column {column} {definition}")

    def create_media_request(
        self,
        query: str,
        media_type: str,
        min_resolution: str = "any",
    ) -> dict[str, Any]:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                insert into media_requests (query, media_type, min_resolution)
                values (?, ?, ?)
                """,
                (query, media_type, min_resolution),
            )
            row = conn.execute(
                """
                select *
                from media_requests
                where id = ?
                """,
                (cursor.lastrowid,),
            ).fetchone()
        return dict(row)

    def update_media_request_search(
        self,
        request_id: int,
        *,
        status: str,
        best_result_id: str | None,
        best_title: str | None,
        best_score: int | None,
        total: int,
        accepted: int,
        rejected: int,
    ) -> dict[str, Any] | None:
        with self._connect() as conn:
            conn.execute(
                """
                update media_requests
                set updated_at = current_timestamp,
                    status = ?,
                    best_result_id = ?,
                    best_title = ?,
                    best_score = ?,
                    total = ?,
                    accepted = ?,
                    rejected = ?
                where id = ?
                """,
                (
                    status,
                    best_result_id,
                    best_title,
                    best_score,
                    total,
                    accepted,
                    rejected,
                    request_id,
                ),
            )
            row = conn.execute(
                """
                select *
                from media_requests
                where id = ?
                """,
                (request_id,),
            ).fetchone()
        return dict(row) if row else None

    def set_media_request_status(self, request_id: int, status: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            conn.execute(
                """
                update media_requests
                set updated_at = current_timestamp,
                    status = ?
                where id = ?
                """,
                (status, request_id),
            )
            row = conn.execute(
                """
                select *
                from media_requests
                where id = ?
                """,
                (request_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_media_request(self, request_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                select *
                from media_requests
                where id = ?
                """,
                (request_id,),
            ).fetchone()
        return dict(row) if row else None

    def recent_media_requests(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                select *
                from media_requests
                order by id desc
                limit ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def cache_release(
        self, query: str, media_type: str, release: Release, request_id: int | None = None
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                insert into release_cache (
                    result_id, request_id, query, media_type, title, download_url, release_json
                )
                values (?, ?, ?, ?, ?, ?, ?)
                on conflict(result_id) do update set
                    created_at = current_timestamp,
                    request_id = excluded.request_id,
                    query = excluded.query,
                    media_type = excluded.media_type,
                    title = excluded.title,
                    download_url = excluded.download_url,
                    release_json = excluded.release_json
                """,
                (
                    release.result_id,
                    request_id,
                    query,
                    media_type,
                    release.title,
                    release.download_url,
                    release.model_dump_json(),
                ),
            )

    def get_cached_release(self, result_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                select result_id, request_id, created_at, media_type, title, download_url, release_json
                from release_cache
                where result_id = ?
                """,
                (result_id,),
            ).fetchone()
        return dict(row) if row else None

    def record_grab(self, request: GrabRequest, response: Any) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                insert into grabs (title, media_type, category, payload, response)
                values (?, ?, ?, ?, ?)
                """,
                (
                    request.title,
                    request.media_type,
                    request.category,
                    request.model_dump_json(),
                    json.dumps(response, ensure_ascii=False),
                ),
            )

    def recent_grabs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                select id, created_at, title, media_type, category, response
                from grabs
                order by id desc
                limit ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
