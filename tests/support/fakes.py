from __future__ import annotations

import copy
import json


class FakeResponse:
    def __init__(self, text: str = "", payload: dict | None = None, status_code: int = 200):
        self.text = text
        self._payload = payload
        self.status_code = status_code
        self.history = []

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"{self.status_code} error")

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeHttp:
    def __init__(self, csv_text: str | None = None, fail_posts: bool = False, get_error: Exception | None = None):
        self.csv_text = csv_text
        self.fail_posts = fail_posts
        self.get_error = get_error
        self.posts: list[tuple[str, dict]] = []
        self.gets: list[str] = []

    def factory(self):
        return self

    def get(self, url, timeout=None):
        self.gets.append(url)
        if self.get_error:
            raise self.get_error
        return FakeResponse(text=self.csv_text or "")

    def post(self, url, json=None, timeout=None, allow_redirects=True):
        self.posts.append((url, copy.deepcopy(json)))
        if self.fail_posts:
            import requests

            raise requests.ConnectionError("network down")
        return FakeResponse(payload={"status": "ok", "rows_written": len((json or {}).get("rows", []))})

    def posts_json(self) -> str:
        return json.dumps(self.posts, ensure_ascii=False, sort_keys=True, default=str)
