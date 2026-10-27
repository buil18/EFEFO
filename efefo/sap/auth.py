from __future__ import annotations

import logging
import os
from getpass import getpass
from urllib.parse import urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

LOGIN_HOSTS = (
    "login.microsoftonline.com",
    "accounts.sap.com",
    "adfs",
    "okta.com",
)

LOGIN_BODY_MARKERS = (
    "sign in",
    "pick an account",
    "j_username",
    "could not authenticate",
)

UNATTENDED_LOGIN_TIMEOUT_MS = 25_000
INTERACTIVE_LOGIN_TIMEOUT_MS = 120_000


class UnattendedCredentialError(RuntimeError):
    pass


def get_credentials(saved_email: str | None, unattended: bool = False) -> tuple[str, str]:
    email = saved_email or os.environ.get("SAP_USER_EMAIL")
    password = os.environ.get("SAP_USER_PASS")
    if unattended:
        if not email or not password:
            raise UnattendedCredentialError(
                "Đang chạy chế độ tự động nhưng thiếu SAP_USER_EMAIL hoặc SAP_USER_PASS. "
                "Hãy đặt hai biến môi trường này (xem docs/OPERATIONS.md)."
            )
        return email, password
    email = email or input("SAP email: ").strip()
    password = password or getpass("SAP password (ẩn khi gõ): ")
    return email, password


def is_login_body(body_text: str) -> bool:
    lowered = body_text.lower()
    return any(marker in lowered for marker in LOGIN_BODY_MARKERS)


def is_login_host(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(h in host for h in LOGIN_HOSTS)


def session_is_valid(page) -> bool:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=10_000)
    except PlaywrightTimeoutError:
        pass

    if is_login_host(page.url):
        logger.info("Đã bị chuyển hướng sang trang đăng nhập: %s", urlparse(page.url).netloc.lower())
        return False

    try:
        body_text = page.locator("body").inner_text(timeout=5_000)
    except Exception as exc:
        logger.warning("Không đọc được nội dung trang để kiểm tra session: %s", exc)
        return False

    return not is_login_body(body_text)


def back_on_sap_predicate(sap_url: str | None):
    sap_host = urlparse(sap_url).netloc.lower() if sap_url else ""

    def back_on_sap(url: str) -> bool:
        host = urlparse(url).netloc.lower()
        if not host:
            return False
        if any(h in host for h in LOGIN_HOSTS):
            return False
        return host == sap_host if sap_host else True

    return back_on_sap


def interactive_login(page, email: str, password: str, unattended: bool, sap_url: str | None,
                      rerun_hint: str) -> None:
    logger.info("Bắt đầu đăng nhập...")
    form_filled = False
    try:
        username_input = page.locator("#j_username")
        username_input.wait_for(state="visible", timeout=15_000)
        username_input.fill(email)
        password_input = page.locator("#j_password")
        password_input.fill(password)
        password_input.press("Enter")
        form_filled = True
    except PlaywrightTimeoutError:
        if unattended:
            raise UnattendedCredentialError(
                "Không tìm thấy form đăng nhập SAP trong chế độ tự động. "
                "Nhiều khả năng trang đang yêu cầu xác thực nhiều bước (MFA). "
                f"Hãy chạy tay một lần bằng lệnh: {rerun_hint} để tạo lại phiên đăng nhập."
            )
        logger.info("Không tìm thấy form đăng nhập tự động — vui lòng thao tác trên trình duyệt.")

    timeout_ms = UNATTENDED_LOGIN_TIMEOUT_MS if unattended else INTERACTIVE_LOGIN_TIMEOUT_MS
    try:
        page.wait_for_url(back_on_sap_predicate(sap_url), timeout=timeout_ms)
    except PlaywrightTimeoutError:
        if unattended:
            raise UnattendedCredentialError(
                "Đăng nhập tự động thất bại (%s). Có thể mật khẩu đã đổi hoặc đang bị chặn bởi MFA. "
                "Hãy chạy tay: %s"
                % ("form đã điền nhưng không quay về SAP" if form_filled else "không điền được form", rerun_hint)
            )
        raise RuntimeError("Hết thời gian chờ đăng nhập (120s).")

    page.wait_for_timeout(2000)

    if not session_is_valid(page):
        if unattended:
            raise UnattendedCredentialError(
                f"Đã quay về trang SAP nhưng phiên vẫn chưa hợp lệ. Hãy chạy tay: {rerun_hint}"
            )
        raise RuntimeError("Đã quay về trang SAP nhưng phiên vẫn chưa hợp lệ.")

    logger.info("Đăng nhập thành công.")
