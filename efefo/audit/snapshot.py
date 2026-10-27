from __future__ import annotations

import datetime
import logging

import numpy as np
import pandas as pd

from efefo.domain.location import is_display_excluded, strip_manual_marker
from efefo.domain.supplement import DATA_SOURCE_SAP
from efefo.infra.columns import ITEM_COLUMN_CANDIDATES, STATUS_COLUMN_CANDIDATES, find_matching_column, normalize_material

logger = logging.getLogger(__name__)

STATUS_HIDDEN = "hidden"
STATUS_SHOWN = "shown"
STATUS_EXCLUDED = "excluded"
STATUS_NOT_DISPLAYED = "not_displayed"
BLOCKED_STATUSES = {"block", "blocked"}


def blocked_pairs(df_manual: pd.DataFrame | None) -> set[tuple[str, str]]:
    if df_manual is None or df_manual.empty:
        return set()
    status_col = find_matching_column(df_manual, STATUS_COLUMN_CANDIDATES)
    item_col = find_matching_column(df_manual, ITEM_COLUMN_CANDIDATES)
    if not status_col or not item_col or "Normalized_Location" not in df_manual.columns:
        logger.warning("Audit: Sheet kiểm kho thiếu cột Status / Mã hàng / Vị trí — bỏ qua Blocked.")
        return set()

    is_blocked = df_manual[status_col].astype(str).str.strip().str.lower().isin(BLOCKED_STATUSES)
    pairs = set()
    for location, material in zip(df_manual.loc[is_blocked, "Normalized_Location"], df_manual.loc[is_blocked, item_col]):
        material_norm = normalize_material(material)
        if location and material_norm:
            pairs.add((str(location), material_norm))
    return pairs


def sap_rows(df: pd.DataFrame) -> pd.DataFrame:
    rows = df[df["Data_Source"] == DATA_SOURCE_SAP] if "Data_Source" in df.columns else df
    has_location = rows["Normalized_Location"].notna() & (rows["Normalized_Location"] != "")
    rows = rows[has_location & rows["Material"].notna()].copy()
    rows["_loc"] = rows["Normalized_Location"].astype(str).str.strip()
    rows["_mat"] = rows["Material"].map(normalize_material)
    rows["_qty"] = pd.to_numeric(rows["EWMStockQuantityInBaseUnit"], errors="coerce").fillna(0.0)
    return rows[rows["_mat"] != ""]


def display_rows(summary: pd.DataFrame, location_cfg, max_slots: int) -> pd.DataFrame:
    disp = summary.copy()
    prefixes = location_cfg.display_exclude_prefixes
    keywords = location_cfg.display_exclude_keywords
    disp["_loc"] = disp["Normalized_Location"].map(strip_manual_marker)
    disp["_manual"] = disp["Normalized_Location"].astype(str).str.endswith("*")
    disp["_mat"] = disp["Material"].map(normalize_material)
    disp["_prd"] = pd.to_datetime(disp["PRD_date"], errors="coerce")
    disp["_excluded"] = disp["_loc"].map(lambda v: is_display_excluded(v, prefixes, keywords))
    disp["_rank"] = np.nan
    disp["_hidden"] = False

    shown = disp[~disp["_excluded"]].sort_values(["_mat", "phantram_shelf_life"], kind="stable")
    ranks = shown.groupby("_mat").cumcount() + 1
    disp.loc[shown.index, "_rank"] = ranks
    disp.loc[shown.index, "_hidden"] = ranks > max_slots
    return disp


def sequential_sum(values: pd.Series) -> float:
    return values.sum()


def group_index(disp: pd.DataFrame) -> dict[tuple[str, str], list[tuple[pd.Timestamp, dict]]]:
    index: dict[tuple[str, str], list[tuple[pd.Timestamp, dict]]] = {}
    for record in disp.to_dict("records"):
        if pd.isna(record["_prd"]):
            continue
        index.setdefault((record["_loc"], record["_mat"]), []).append((record["_prd"], record))
    for entries in index.values():
        entries.sort(key=lambda item: item[0])
    return index


def find_group(index, location: str, material: str, lot_date: pd.Timestamp, lot_split_days: int) -> dict | None:
    chosen = None
    chosen_date = None
    for group_date, record in index.get((location, material), []):
        if group_date > lot_date:
            break
        chosen, chosen_date = record, group_date
    if chosen is not None and (lot_date - chosen_date).days >= lot_split_days:
        return None
    return chosen


def lot_status(group: dict | None, lot_date: pd.Timestamp, today: pd.Timestamp) -> str:
    if lot_date == today or group is None:
        return STATUS_NOT_DISPLAYED
    if group["_excluded"]:
        return STATUS_EXCLUDED
    return STATUS_HIDDEN if group["_hidden"] else STATUS_SHOWN


def build_lot_state(rows: pd.DataFrame, disp: pd.DataFrame, lot_split_days: int) -> dict[str, dict]:
    today = pd.Timestamp(datetime.date.today())
    lots = rows.assign(_lot_date=pd.to_datetime(rows["BaseDateForShelfLife"], errors="coerce").dt.normalize())
    lots = lots[lots["_lot_date"].notna()]
    short_names = lots["Short Name"].astype(str) if "Short Name" in lots.columns else ""
    lots = lots.assign(_short=short_names)
    index = group_index(disp)

    keys = ["_loc", "_mat", "_lot_date"]
    grouped = lots[keys + ["_short", "_qty"]].groupby(keys).agg(
        _short=("_short", "first"), _qty=("_qty", sequential_sum)
    )
    state: dict[str, dict] = {}
    for (location, material, lot_date), short_name, qty in zip(grouped.index, grouped["_short"], grouped["_qty"]):
        group = find_group(index, location, material, lot_date, lot_split_days)
        state[f"{location}||{material}||{lot_date:%d/%m/%Y}"] = {
            "location": location,
            "material": material,
            "short_name": str(short_name),
            "prd_date": f"{lot_date:%d/%m/%Y}",
            "qty": float(qty),
            "status": lot_status(group, lot_date, today),
            "rank": None if group is None or pd.isna(group["_rank"]) else int(group["_rank"]),
        }
    return state


def build_blocked_state(rows: pd.DataFrame, tracked_pairs: set[tuple[str, str]],
                        active_pairs: set[tuple[str, str]]) -> dict[str, dict]:
    if not tracked_pairs:
        return {}
    in_scope = pd.Series([(loc, mat) in tracked_pairs for loc, mat in zip(rows["_loc"], rows["_mat"])],
                         index=rows.index)
    state: dict[str, dict] = {}
    for (location, material), part in rows[in_scope].groupby(["_loc", "_mat"]):
        dates = pd.to_datetime(part["BaseDateForShelfLife"], errors="coerce").dropna()
        state[f"{location}||{material}"] = {
            "location": location,
            "material": material,
            "short_name": str(part["Short Name"].iloc[0]) if "Short Name" in part.columns else "",
            "prd_date": f"{dates.min():%d/%m/%Y}" if not dates.empty else "",
            "qty": float(part["_qty"].sum()),
            "blocked": (location, material) in active_pairs,
        }
    return state


def previous_blocked_pairs(prev_state: dict | None) -> set[tuple[str, str]]:
    if not prev_state:
        return set()
    return {
        (item["location"], item["material"])
        for item in prev_state.get("blocked", {}).values()
        if item.get("blocked")
    }


def count_duplicates(rows: pd.DataFrame, detail_columns) -> int:
    key_columns = [c for c in detail_columns[:8] if c in rows.columns]
    duplicates = int(rows.duplicated(subset=key_columns).sum())
    if duplicates:
        logger.warning("Audit: %s dòng SAP trùng hệt nhau (nghi đọc trùng trang) — chỉ ghi nhận.", duplicates)
    return duplicates
