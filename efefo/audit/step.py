from __future__ import annotations

import datetime
import logging
from pathlib import Path

import pandas as pd
import requests

from efefo.audit import detection, snapshot, storage

logger = logging.getLogger(__name__)


def push_events(rows: list[list], webapp_url: str, secret: str, session_factory) -> bool:
    if not rows:
        return True
    if not webapp_url or not secret:
        logger.warning("Audit: thiếu GOOGLE_APPS_SCRIPT_URL/SECRET — bỏ qua đẩy Audit_Log.")
        return True
    try:
        session = session_factory()
        response = session.post(webapp_url, json={"secret": secret, "type": "audit", "rows": rows},
                                timeout=45, allow_redirects=True)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Audit: lỗi gửi Audit_Log lên Google Sheet: %s", exc)
        return False
    try:
        result = response.json()
    except ValueError:
        result = {}
    if result.get("status", "ok") != "ok":
        logger.warning("Audit: Apps Script phản hồi lỗi khi ghi Audit_Log: %s", result.get("message"))
        return False
    logger.info("Audit: đã đẩy %s sự kiện lên Google Sheet (Audit_Log).", len(rows))
    return True


def compare(prev: dict | None, cur_lots: dict, cur_blocked: dict, audit_dir: Path, now: datetime.datetime,
            cfg) -> tuple[list[dict], dict, list[dict]]:
    if prev is None:
        logger.info("Audit: chưa có mốc cũ — lượt này chỉ ghi mốc.")
        return [], {}, []
    candidates = detection.detect_hidden(prev.get("lots", {}), cur_lots, cfg.qty_delta_threshold) + \
        detection.detect_blocked(prev.get("blocked", {}), cur_blocked)
    confirmed, transient, still_pending = detection.resolve_pending(
        prev.get("pending", {}), candidates, cur_lots, cur_blocked, now, cfg
    )
    storage.append_log(audit_dir, "transient", transient, now)
    return confirmed, still_pending, prev.get("unsent", [])


def deliver(confirmed: list[dict], carry_over: list[dict], audit_dir: Path, now: datetime.datetime, cfg,
            push) -> list[dict]:
    time_str = f"{now:%Y-%m-%d %H:%M:%S}"
    to_send = carry_over + [{**item, "time": time_str} for item in confirmed]
    storage.append_log(audit_dir, "event", confirmed, now)
    if push([detection.event_row(item, item["time"], cfg) for item in to_send]):
        return []
    return [
        {**item, "attempts": item.get("attempts", 0) + 1}
        for item in to_send
        if item.get("attempts", 0) + 1 < cfg.max_push_attempts
    ]


def run_audit_step(df: pd.DataFrame, summary: pd.DataFrame, df_manual: pd.DataFrame | None, audit_dir: Path,
                   site, push) -> None:
    cfg = site.audit
    audit_dir.mkdir(parents=True, exist_ok=True)
    state_path = audit_dir / storage.STATE_FILE
    history_dir = audit_dir / storage.HISTORY_SUBDIR
    now = datetime.datetime.now()

    prev = storage.read_state(state_path)
    rows = snapshot.sap_rows(df)
    disp = snapshot.display_rows(summary, site.location, site.fefo.display_max_slots)
    cur_lots = snapshot.build_lot_state(rows, disp, site.fefo.lot_split_days)
    active_pairs = snapshot.blocked_pairs(df_manual)
    cur_blocked = snapshot.build_blocked_state(rows, active_pairs | snapshot.previous_blocked_pairs(prev), active_pairs)

    record_count = len(rows)
    suspect = detection.is_suspect_run(prev, record_count, cfg)
    meta = {"time": now.isoformat(timespec="seconds"), "record_count": record_count,
            "duplicate_rows": snapshot.count_duplicates(rows, storage.DETAIL_COLUMNS), "suspect": suspect}

    if suspect:
        logger.warning("Audit: số dòng SAP tụt từ %s xuống %s — nghi tải thiếu, bỏ qua so sánh lượt này.",
                       prev.get("record_count"), record_count)
        prev["suspect_streak"] = int(prev.get("suspect_streak", 0)) + 1
        storage.write_json_atomic(state_path, prev)
        storage.save_history(history_dir, now, rows, disp, cur_lots, cur_blocked, meta, cfg.history_retention_days)
        return

    confirmed, still_pending, carry_over = compare(prev, cur_lots, cur_blocked, audit_dir, now, cfg)
    unsent = deliver(confirmed, carry_over, audit_dir, now, cfg, push)

    storage.write_json_atomic(state_path, {
        "saved_at": meta["time"], "record_count": record_count, "suspect_streak": 0,
        "lots": cur_lots, "blocked": cur_blocked, "pending": still_pending, "unsent": unsent,
    })
    meta["events_confirmed"] = len(confirmed)
    storage.save_history(history_dir, now, rows, disp, cur_lots, cur_blocked, meta, cfg.history_retention_days)
    logger.info("Audit: %s lô theo dõi, %s sự kiện xác nhận, %s đang chờ xác nhận.",
                len(cur_lots), len(confirmed), len(still_pending))
