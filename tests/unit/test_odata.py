from __future__ import annotations

import json

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from efefo.sap.odata import IncompleteDownloadError, RetryPolicy, download_with_recovery, fetch_odata_pages

POLICY = RetryPolicy(2, 3, (5, 15, 30))


class FakeLocator:
    def __init__(self, page):
        self.page = page

    def inner_text(self, timeout=None):
        body = self.page.current_body
        if isinstance(body, Exception):
            raise body
        return body


class FakePage:
    def __init__(self, pages: dict[str, list]):
        self.pages = {url: list(bodies) for url, bodies in pages.items()}
        self.current_body = ""
        self.visits: list[str] = []

    def goto(self, url):
        self.visits.append(url)
        queue = self.pages[url]
        body = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(body, ConnectionError):
            raise body
        self.current_body = body

    def wait_for_load_state(self, *args, **kwargs):
        if self.current_body == "SLOW":
            raise PlaywrightTimeoutError("slow")

    def wait_for_timeout(self, ms):
        pass

    def locator(self, selector):
        return FakeLocator(self)


def page_body(ids, next_url=None):
    d = {"results": [{"__metadata": {"id": i}, "Material": str(i)} for i in ids]}
    if next_url:
        d["__next"] = next_url
    return json.dumps({"d": d})


def test_pagination_follows_next_links():
    page = FakePage({"u1": [page_body([1, 2], "u2")], "u2": [page_body([3], "u3")], "u3": [page_body([4])]})
    records, expired, resume = fetch_odata_pages(page, "u1", 999)
    assert [r["Material"] for r in records] == ["1", "2", "3", "4"]
    assert (expired, resume) == (False, None)


def test_max_pages_stops_early():
    page = FakePage({"u1": [page_body([1], "u2")], "u2": [page_body([2], "u3")]})
    records, _, resume = fetch_odata_pages(page, "u1", 1)
    assert len(records) == 1 and resume is None


def test_pagination_loop_detected():
    page = FakePage({"u1": [page_body([1], "u1")]})
    with pytest.raises(IncompleteDownloadError):
        fetch_odata_pages(page, "u1", 999)


@pytest.mark.parametrize("body, expired", [
    ("Sign in to your account", True), ("", True), ("<html>500 Internal</html>", False),
    ('{"d": "oops"}', False), ("{broken", False), (RuntimeError("detached"), False),
])
def test_page_problems_return_resume_point(body, expired):
    page = FakePage({"u1": [page_body([1], "u2")], "u2": [body]})
    records, was_expired, resume = fetch_odata_pages(page, "u1", 999)
    assert len(records) == 1 and was_expired is expired and resume == "u2"


def test_network_error_returns_resume_point():
    page = FakePage({"u1": [ConnectionError("reset")]})
    assert fetch_odata_pages(page, "u1", 999) == ([], False, "u1")


def test_dom_timeout_still_reads_content():
    page = FakePage({"u1": ["SLOW"]})
    page.pages["u1"] = [page_body([7])]
    page.current_body = "SLOW"
    records, _, _ = fetch_odata_pages(page, "u1", 999)
    assert records[0]["Material"] == "7"


def test_recovery_resumes_after_transient_errors_without_duplicates():
    page = FakePage({"u1": [page_body([1], "u2")], "u2": ["<html>busy</html>", "<html>busy</html>", page_body([2])]})
    sleeps = []
    records, info = download_with_recovery(page, "u1", 999, POLICY, relogin=lambda: page, sleep=sleeps.append)
    assert [r["Material"] for r in records] == ["1", "2"]
    assert info == {"relogins": 0, "incomplete_retries": 2} and sleeps == [5, 15]


def test_recovery_relogs_in_on_expiry():
    page = FakePage({"u1": [page_body([1], "u2")], "u2": ["Pick an account", page_body([2])]})
    calls = []

    def relogin():
        calls.append(1)
        return page

    records, info = download_with_recovery(page, "u1", 999, POLICY, relogin=relogin, sleep=lambda s: None)
    assert len(records) == 2 and info["relogins"] == 1 and calls == [1]


def test_recovery_gives_up_after_limit():
    page = FakePage({"u1": ["<html>down</html>"]})
    sleeps = []
    with pytest.raises(IncompleteDownloadError):
        download_with_recovery(page, "u1", 999, POLICY, relogin=lambda: page, sleep=sleeps.append)
    assert sleeps == [5, 15, 30]


def test_recovery_relogin_limit():
    page = FakePage({"u1": ["sign in"]})
    with pytest.raises(RuntimeError, match="đăng nhập lại"):
        download_with_recovery(page, "u1", 999, POLICY, relogin=lambda: page, sleep=lambda s: None)
