from typing import Any

import httpx

from app.config import Settings
from app.models import GrabRequest


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

