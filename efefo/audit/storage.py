from __future__ import annotations

import datetime
import gzip
import json
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

STATE_FILE = "audit_state.json"
HISTORY_SUBDIR = "history"
LOG_FILE = "audit_log.jsonl"
DETAIL_COLUMNS = (
    "EWMStorageBin", "Normalized_Location", "Material", "Batch", "HandlingUnitNumber",
    "EWMStorageType", "BaseDateForShelfLife", "EWMStockQuantityInBaseUnit",
    "Unrestricted", "Blocked", "phantram_shelf_life",
)
DISPLAY_COLUMNS = ["Normalized_Location", "Material", "PRD_date", "Total_Quantity",
                   "phantram_shelf_life", "_rank", "_hidden", "_excluded", "_manual"]


def read_state(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError) as exc:
        logger.warning("Audit: không đọc được trạng thái cũ (%s) — coi như lần đầu.", exc)
        return None


def write_json_atomic(path: Path, payload: dict) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
    tmp_path.replace(path)


def frame_records(frame: pd.DataFrame, columns) -> list[dict]:
    present = [c for c in columns if c in frame.columns]
    return json.loads(frame[present].to_json(orient="records", date_format="iso", force_ascii=False))


def save_history(history_dir: Path, now: datetime.datetime, rows: pd.DataFrame, disp: pd.DataFrame,
                 cur_lots: dict, cur_blocked: dict, meta: dict, retention_days: int) -> None:
    history_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": meta,
        "fefo_rows": frame_records(disp, DISPLAY_COLUMNS),
        "lots": cur_lots,
        "blocked": cur_blocked,
        "sap_rows": frame_records(rows, DETAIL_COLUMNS),
    }
    target = history_dir / f"{now:%Y%m%d_%H%M%S}.json.gz"
    with gzip.open(target, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, default=str)

    cutoff = now.timestamp() - retention_days * 86400
    for old in history_dir.glob("*.json.gz"):
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink()
        except OSError as exc:
            logger.warning("Audit: không xóa được bản lịch sử cũ %s: %s", old, exc)


def append_log(audit_dir: Path, kind: str, items: list[dict], now: datetime.datetime) -> None:
    if not items:
        return
    try:
        with (audit_dir / LOG_FILE).open("a", encoding="utf-8") as handle:
            for item in items:
                record = {"time": f"{now:%Y-%m-%d %H:%M:%S}", "kind": kind, **item}
                handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except OSError as exc:
        logger.warning("Audit: không ghi được nhật ký cục bộ: %s", exc)
