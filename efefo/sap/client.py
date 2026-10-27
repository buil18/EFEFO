from __future__ import annotations

import logging

from playwright.sync_api import sync_playwright

from efefo.context import RunContext
from efefo.sap.auth import get_credentials, interactive_login, session_is_valid
from efefo.sap.odata import RetryPolicy, download_with_recovery, log_download_diagnostics

logger = logging.getLogger(__name__)


def relaunch_headed(p, old_browser, sap_url: str, channel: str):
    try:
        old_browser.close()
    except Exception:
        pass
    browser = p.chromium.launch(channel=channel, headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto(sap_url)
    return browser, context, page


def fetch_all_records(ctx: RunContext) -> list[dict]:
    sap = ctx.site.sap
    storage_state_path = ctx.storage_state_path
    has_saved_session = storage_state_path.exists()
    unattended = ctx.unattended
    policy = RetryPolicy(sap.max_relogin_attempts, sap.max_incomplete_retries, sap.incomplete_retry_wait_seconds)

    if unattended:
        logger.info("Chạy ở chế độ TỰ ĐỘNG (không hỏi bàn phím, không mở cửa sổ).")

    with sync_playwright() as p:
        headless = has_saved_session
        browser = p.chromium.launch(channel=sap.browser_channel, headless=headless)
        try:
            context = browser.new_context(storage_state=str(storage_state_path) if has_saved_session else None)
            page = context.new_page()
            page.goto(ctx.sap_url)

            def login():
                nonlocal browser, context, page, headless
                if headless and not unattended:
                    browser, context, page = relaunch_headed(p, browser, ctx.sap_url, sap.browser_channel)
                    headless = False
                email, password = get_credentials(ctx.email, unattended)
                interactive_login(page, email, password, unattended, ctx.sap_url, ctx.interactive_hint)
                context.storage_state(path=str(storage_state_path))
                return page

            if not session_is_valid(page):
                logger.info("Session hết hạn hoặc chưa tồn tại — đang đăng nhập lại.")
                login()
                logger.info("Đã lưu session mới tại %s.", storage_state_path)
            else:
                logger.info("Tái sử dụng session đã lưu.")

            all_records, info = download_with_recovery(page, ctx.first_url, ctx.max_pages, policy, login)
        finally:
            browser.close()

    log_download_diagnostics(all_records, info)
    return all_records
