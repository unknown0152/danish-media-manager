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
                    query text not null,
                    media_type text not null,
                    title text not null,
                    download_url text,
                    release_json text not null
                )
                """
            )

    def cache_release(self, query: str, media_type: str, release: Release) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                insert into release_cache (
                    result_id, query, media_type, title, download_url, release_json
                )
                values (?, ?, ?, ?, ?, ?)
                on conflict(result_id) do update set
                    created_at = current_timestamp,
                    query = excluded.query,
                    media_type = excluded.media_type,
                    title = excluded.title,
                    download_url = excluded.download_url,
                    release_json = excluded.release_json
                """,
                (
                    release.result_id,
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
                select result_id, created_at, media_type, title, download_url, release_json
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
