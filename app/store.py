import json
import sqlite3
from pathlib import Path
from typing import Any

from app.models import GrabRequest


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

