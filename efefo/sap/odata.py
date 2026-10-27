from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from efefo.sap.auth import is_login_body

logger = logging.getLogger(__name__)


class IncompleteDownloadError(RuntimeError):
    pass


@dataclass(frozen=True)
class RetryPolicy:
    max_relogin_attempts: int
    max_incomplete_retries: int
    incomplete_retry_wait_seconds: tuple[int, ...]


def fetch_odata_pages(page, first_url: str, max_pages: int, start_page_no: int = 1,
                      phase: str = "") -> tuple[list[dict], bool, str | None]:
    all_records: list[dict] = []
    next_url = first_url
    page_no = start_page_no
    visited: set[str] = set()

    while next_url:
        if next_url in visited:
            raise IncompleteDownloadError(
                "Phát hiện vòng lặp phân trang tại trang %s (__next trỏ lại trang đã tải)." % page_no
            )
        visited.add(next_url)

        logger.info("Đang tải trang %s%s ...", page_no, phase)
        try:
            page.goto(next_url)
            page.wait_for_load_state("domcontentloaded", timeout=15_000)
        except PlaywrightTimeoutError:
            logger.debug("Timeout DOM trang %s, tiếp tục đọc nội dung.", page_no)
        except Exception as exc:
            logger.warning("Lỗi mạng khi tải trang %s (%s) — giữ lại %s bản ghi đã có.",
                           page_no, exc, len(all_records))
            return all_records, False, next_url

        page.wait_for_timeout(500)

        try:
            body_text = page.locator("body").inner_text(timeout=10_000).strip()
        except Exception as exc:
            logger.warning("Không đọc được nội dung trang %s: %s", page_no, exc)
            return all_records, False, next_url

        if not body_text or is_login_body(body_text):
            logger.warning("Trang %s: phiên đăng nhập đã hết hạn. Sẽ đăng nhập lại và tải tiếp.", page_no)
            return all_records, True, next_url

        if not body_text.startswith(("{", "[")):
            logger.error("Trang %s trả về nội dung không phải JSON (có thể SAP đang lỗi): %s",
                         page_no, body_text[:200])
            return all_records, False, next_url

        try:
            data = json.loads(body_text)
        except json.JSONDecodeError as exc:
            logger.error("Lỗi parse JSON trang %s: %s", page_no, exc)
            return all_records, False, next_url

        if not isinstance(data, dict) or not isinstance(data.get("d"), dict) or "results" not in data["d"]:
            logger.error("Dữ liệu phản hồi không đúng cấu trúc OData tại trang %s: %s", page_no, body_text[:200])
            return all_records, False, next_url

        all_records.extend(data["d"]["results"])

        if page_no >= max_pages:
            if data["d"].get("__next"):
                logger.warning("Đã đạt giới hạn %s trang (chế độ thử) — dừng tải, dữ liệu CHƯA đầy đủ.", max_pages)
            break

        next_url = data["d"].get("__next")
        page_no += 1

    return all_records, False, None


def download_with_recovery(page, first_url: str, max_pages: int, policy: RetryPolicy, relogin,
                           sleep=None) -> tuple[list[dict], dict]:
    sleep = sleep or time.sleep
    all_records: list[dict] = []
    info = {"relogins": 0, "incomplete_retries": 0}
    resume_url: str | None = None
    first = True

    while True:
        if first:
            records, expired, resume_url = fetch_odata_pages(page, first_url, max_pages)
            first = False
        else:
            records, expired, resume_url = fetch_odata_pages(
                page, resume_url or first_url, max_pages, start_page_no=1,
                phase=" (tải tiếp lần %s)" % (info["relogins"] + info["incomplete_retries"]),
            )
        all_records.extend(records)

        if resume_url is None:
            return all_records, info

        if expired:
            if info["relogins"] >= policy.max_relogin_attempts:
                raise RuntimeError(
                    "Không thể duy trì phiên sau %s lần đăng nhập lại. Kiểm tra quyền OData."
                    % policy.max_relogin_attempts
                )
            info["relogins"] += 1
            logger.warning("Session hết hạn giữa chừng (lần %s/%s). Đã có %s bản ghi. Đang đăng nhập lại...",
                           info["relogins"], policy.max_relogin_attempts, len(all_records))
            page = relogin()
            continue

        if info["incomplete_retries"] >= policy.max_incomplete_retries:
            raise IncompleteDownloadError(
                "Tải OData chưa đủ: dừng sau %s bản ghi, đã thử tải tiếp %s lần. "
                "Bỏ qua lượt chạy này để giữ nguyên dữ liệu FEFO lần trước."
                % (len(all_records), policy.max_incomplete_retries)
            )
        waits = policy.incomplete_retry_wait_seconds
        wait = waits[min(info["incomplete_retries"], len(waits) - 1)]
        info["incomplete_retries"] += 1
        logger.warning("Tải dở dang (đã có %s bản ghi). Chờ %ss rồi tải tiếp từ chỗ dừng (lần %s/%s).",
                       len(all_records), wait, info["incomplete_retries"], policy.max_incomplete_retries)
        sleep(wait)


def log_download_diagnostics(records: list[dict], info: dict) -> None:
    ids = [(r.get("__metadata") or {}).get("id") for r in records if isinstance(r, dict)]
    ids = [i for i in ids if i]
    duplicates = len(ids) - len(set(ids))
    logger.info("Tải OData xong: %s bản ghi | tải tiếp do lỗi: %s lần | đăng nhập lại: %s lần.",
                len(records), info.get("incomplete_retries", 0), info.get("relogins", 0))
    if duplicates:
        seen: set[str] = set()
        sample: list[str] = []
        for i in ids:
            if i in seen and len(sample) < 3:
                sample.append(i)
            seen.add(i)
        logger.warning("CẢNH BÁO dữ liệu: có %s bản ghi trùng __metadata.id (mẫu: %s). "
                       "Có thể SAP đổi dữ liệu trong lúc đang tải.", duplicates, sample)
