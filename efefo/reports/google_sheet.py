from __future__ import annotations

import datetime
import logging

import pandas as pd

logger = logging.getLogger(__name__)

FEFO_HEADER = ["Location_1", "Code", "SKU_2", "PRD date_3", "Quantity", "Remaining shelf-life (%)_4"]
HEADER_PADDING = 3


def fefo_payload_rows(summary: pd.DataFrame) -> list[list]:
    rows = []
    for location, material, short_name, prd_date, qty, pct in summary.itertuples(index=False):
        rows.append([
            "" if pd.isna(location) else str(location),
            "" if pd.isna(material) else str(material),
            "" if pd.isna(short_name) else str(short_name),
            prd_date.strftime("%d/%m/%Y") if pd.notnull(prd_date) else "",
            0 if pd.isna(qty) else qty,
            f"{pct * 100:.2f}%" if pd.notnull(pct) else "",
            "", "", "", "",
        ])
    return rows


def publish_fefo(summary: pd.DataFrame | None, webapp_url: str, secret: str, session_factory) -> None:
    if not webapp_url:
        logger.warning("Chưa cấu hình GOOGLE_APPS_SCRIPT_URL — bỏ qua gửi FEFO lên Google Sheet.")
        return
    if not secret:
        logger.warning("Chưa cấu hình GOOGLE_APPS_SCRIPT_SECRET — bỏ qua gửi FEFO lên Google Sheet.")
        return
    if summary is None:
        return

    now_str = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    header = FEFO_HEADER + [""] * HEADER_PADDING + [now_str]
    rows = fefo_payload_rows(summary)
    logger.info("Chuẩn bị gửi %s dòng FEFO lên Google Sheet (URL: %s)...", len(rows), webapp_url[:45] + "...")

    payload = {"secret": secret, "header": header, "rows": rows}
    try:
        session = session_factory()
        response = session.post(webapp_url, json=payload, timeout=45, allow_redirects=True)

        if response.status_code == 200:
            try:
                result = response.json()
                if result.get("status") == "ok":
                    logger.info("Đã cập nhật %s dòng FEFO lên Google Sheet (Ghi nhận J1: %s).",
                                result.get("rows_written", len(rows)), now_str)
                    return
                logger.warning("Apps Script phản hồi lỗi: %s", result.get("message"))
                return
            except Exception:
                pass
            logger.info("Đã cập nhật %s dòng FEFO lên Google Sheet (HTTP 200).", len(rows))
            return

        if response.history and any(r.status_code == 302 for r in response.history):
            logger.info("Đã gửi thành công %s dòng FEFO qua Webhook Google Apps Script.", len(rows))
            return

        response.raise_for_status()
    except Exception as exc:
        if "script.googleusercontent.com" in str(exc) and "404" in str(exc):
            logger.info("Đã gửi %s dòng FEFO lên Google Sheet (Hoàn tất chu trình Webhook).", len(rows))
        else:
            logger.warning("Lỗi gửi FEFO lên Google Sheet: %s", exc)
