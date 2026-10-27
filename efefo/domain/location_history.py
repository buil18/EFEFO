from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def history_key(location: str, material: str) -> str:
    return f"{location}|{material}"


def load_location_history(path: Path) -> dict[str, str]:
    if not path.exists():
        logger.info("Chưa có lịch sử vị trí SAP — lượt chạy này giữ nguyên mọi dòng kiểm kho.")
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError) as exc:
        logger.warning("Không đọc được lịch sử vị trí SAP (%s) — coi như chưa có.", exc)
        return {}


def save_location_history(path: Path, history: dict[str, str], sap_keys: set[str], retention_days: int) -> None:
    now = datetime.datetime.now()
    cutoff = now - datetime.timedelta(days=retention_days)
    stamp = now.isoformat(timespec="seconds")

    updated = {}
    for key, seen_at in history.items():
        try:
            if datetime.datetime.fromisoformat(seen_at) >= cutoff:
                updated[key] = seen_at
        except (TypeError, ValueError):
            continue
    for key in sap_keys:
        updated[key] = stamp

    try:
        with path.open("w", encoding="utf-8") as f:
            json.dump(updated, f, ensure_ascii=False, indent=1)
        logger.info("Đã lưu lịch sử %s vị trí SAP.", len(updated))
    except OSError as exc:
        logger.warning("Không ghi được lịch sử vị trí SAP: %s", exc)


def filter_rows_by_history(rows: pd.DataFrame, row_keys: list[str], sap_keys_now: set[str],
                           history: dict[str, str]) -> pd.DataFrame:
    if rows.empty or not history:
        return rows
    was_seen_before = pd.Series([k in history for k in row_keys], index=rows.index)
    is_gone_now = pd.Series([k not in sap_keys_now for k in row_keys], index=rows.index)
    emptied = was_seen_before & is_gone_now
    if emptied.any():
        logger.info("Loại %s dòng kiểm kho: SAP từng ghi nhận vị trí này nhưng nay đã hết hàng.", int(emptied.sum()))
        rows = rows[~emptied]
    return rows
