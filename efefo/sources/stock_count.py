from __future__ import annotations

import io
import logging
import re

import pandas as pd

from efefo.domain.location import normalize_bin
from efefo.infra.columns import STATUS_COLUMN_CANDIDATES, find_matching_column

logger = logging.getLogger(__name__)

SHEET_LOCATION_CANDIDATES = ["Location", "Vị trí", "Bin", "Location_1"]
BLOCKED_STATUSES = {"block", "blocked"}
INVISIBLE_CHARS = re.compile(r"[\s​‌‍﻿⁠]")


def parse_stock_count_csv(text: str, strip_prefixes) -> pd.DataFrame | None:
    df_manual = pd.read_csv(io.StringIO(text), header=1)
    df_manual.columns = df_manual.columns.str.strip()
    loc_col = find_matching_column(df_manual, SHEET_LOCATION_CANDIDATES)

    if not loc_col:
        df_manual = pd.read_csv(io.StringIO(text), header=0)
        df_manual.columns = df_manual.columns.str.strip()
        loc_col = find_matching_column(df_manual, SHEET_LOCATION_CANDIDATES)

    if not loc_col:
        logger.warning("Không tìm thấy cột 'Location' trong Google Sheet. Các cột hiện có: %s",
                       list(df_manual.columns))
        return None

    df_manual["Normalized_Location"] = df_manual[loc_col].apply(lambda v: normalize_bin(v, strip_prefixes))
    return df_manual


def fetch_stock_count(csv_url: str, session_factory, strip_prefixes) -> pd.DataFrame | None:
    logger.info("Đang tải dữ liệu kiểm kê thực tế từ Google Sheets...")
    try:
        session = session_factory()
        response = session.get(csv_url, timeout=30)
        response.raise_for_status()
        return parse_stock_count_csv(response.text, strip_prefixes)
    except Exception as exc:
        logger.warning("Lỗi tải Google Sheets: %s", exc)
        return None


def blocked_locations(df_manual: pd.DataFrame | None) -> set:
    if df_manual is None:
        return set()
    status_col = find_matching_column(df_manual, STATUS_COLUMN_CANDIDATES)
    if not status_col:
        return set()
    is_blocked = df_manual[status_col].astype(str).str.strip().str.lower().isin(BLOCKED_STATUSES)
    blocked = set(df_manual.loc[is_blocked, "Normalized_Location"].dropna().unique())
    if blocked:
        logger.warning("Phát hiện %s vị trí 'Blocked' trên Google Sheet: %s", len(blocked), sorted(blocked))
    return blocked


def log_location_mismatches(sap_locations: set, manual_locations: set) -> None:
    only_in_sap = sap_locations - manual_locations
    only_in_manual = manual_locations - sap_locations
    if not only_in_sap or not only_in_manual:
        return
    sap_by_key: dict[str, list[str]] = {}
    for s_loc in only_in_sap:
        sap_by_key.setdefault(INVISIBLE_CHARS.sub("", s_loc), []).append(s_loc)
    for m_loc in sorted(only_in_manual):
        for s_loc in sorted(sap_by_key.get(INVISIBLE_CHARS.sub("", m_loc), [])):
            if s_loc != m_loc:
                logger.warning("Lệch ký tự ẩn giữa SAP %r và Google Sheet %r", s_loc, m_loc)

