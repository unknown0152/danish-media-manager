from typing import Any

import httpx

from app.config import Settings
from app.models import DownloadItem, DownloadStatus, GrabRequest


class AltMountClient:
    def __init__(self, settings: Settings):
        self.base_url = settings.altmount_url.rstrip("/")
        self.api_key = settings.altmount_api_key
        self.timeout = settings.request_timeout_seconds

    def ready(self) -> bool:
        if not self.api_key:
            return False
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(
                    f"{self.base_url}/api",
                    params={"mode": "version", "apikey": self.api_key, "output": "json"},
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def queue(self) -> dict[str, Any] | str:
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(
                f"{self.base_url}/api",
                params={"mode": "queue", "apikey": self.api_key, "output": "json"},
            )
            resp.raise_for_status()
            return _json_or_text(resp)

    def history(self, limit: int = 20, category: str | None = None) -> dict[str, Any] | str:
        params: dict[str, Any] = {
            "mode": "history",
            "apikey": self.api_key,
            "output": "json",
            "limit": limit,
        }
        if category:
            params["category"] = category
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(f"{self.base_url}/api", params=params)
            resp.raise_for_status()
            return _json_or_text(resp)

    def downloads(self) -> DownloadStatus:
        queue = self.queue()
        history = self.history(limit=20)
        return normalize_downloads(queue, history)

    def add_uri(self, request: GrabRequest) -> dict[str, Any] | str:
        if not self.api_key:
            raise RuntimeError("ALTMOUNT_API_KEY is not set")
        if not request.download_url:
            raise RuntimeError("Release does not include a download URL")

        category = request.category or ("movies" if request.media_type == "movie" else "tv")
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(
                f"{self.base_url}/api",
                params={
                    "mode": "addurl",
                    "apikey": self.api_key,
                    "name": request.download_url,
                    "nzbname": request.title,
                    "cat": category,
                    "output": "json",
                },
            )
            resp.raise_for_status()
            return _json_or_text(resp)


def _json_or_text(resp: httpx.Response) -> dict[str, Any] | str:
    try:
        data = resp.json()
    except ValueError:
        return resp.text
    return data if isinstance(data, dict) else {"response": data}


def normalize_downloads(queue: dict[str, Any] | str, history: dict[str, Any] | str) -> DownloadStatus:
    queue_dict = queue if isinstance(queue, dict) else {}
    history_dict = history if isinstance(history, dict) else {}
    queue_body = queue_dict.get("queue") if isinstance(queue_dict.get("queue"), dict) else {}

    return DownloadStatus(
        status=str(queue_body.get("status") or queue_dict.get("status") or "unknown"),
        paused=bool(queue_body.get("paused", False)),
        speed=_str_or_none(queue_body.get("speed") or queue_body.get("kbpersec")),
        size_left_mb=_float_or_none(queue_body.get("mbleft")),
        queue=[
            _download_item(slot, default_status="queued")
            for slot in _extract_items(queue_body, keys=("slots", "queue"))
        ],
        history=[
            _download_item(slot, default_status="history")
            for slot in _extract_history_items(history_dict)
        ],
    )


def _extract_items(parent: dict[str, Any], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    for key in keys:
        value = parent.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _extract_history_items(history: dict[str, Any]) -> list[dict[str, Any]]:
    body = history.get("history") if isinstance(history.get("history"), dict) else history
    return _extract_items(body, keys=("slots", "history", "items"))


def _download_item(item: dict[str, Any], default_status: str) -> DownloadItem:
    return DownloadItem(
        id=_str_or_none(item.get("nzo_id") or item.get("id")),
        name=str(item.get("name") or item.get("nzb_name") or item.get("filename") or "<unknown>"),
        status=str(item.get("status") or default_status),
        category=_str_or_none(item.get("cat") or item.get("category")),
        size_mb=_size_to_mb(item.get("mb") or item.get("size") or item.get("bytes")),
        progress_percent=_progress(item.get("percentage") or item.get("progress")),
        time_left=_str_or_none(item.get("timeleft") or item.get("time_left")),
    )


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _size_to_mb(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        number = float(value)
        return number / 1024 / 1024 if number > 1024 * 1024 else number

    text = str(value).strip().lower().replace(",", ".")
    try:
        if text.endswith("gb"):
            return float(text[:-2].strip()) * 1024
        if text.endswith("mb"):
            return float(text[:-2].strip())
        if text.endswith("kb"):
            return float(text[:-2].strip()) / 1024
        return float(text)
    except ValueError:
        return None


def _progress(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().removesuffix("%")
    try:
        parsed = float(text)
    except ValueError:
        return None
    return max(0.0, min(100.0, parsed))
