from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from efefo.domain.location import warehouse_group
from efefo.sources.capacity_sheet import read_capacity_sheet

logger = logging.getLogger(__name__)

HEADER = ["Khu vực Kho", "Location", "Max Capacity (PL)", "Current Pallets (PL)", "Available Capacity (PL)", "Status"]
EMPTY_STATUS = "Trống hoàn toàn"
ROW_COLUMNS = ["Warehouse_Group", "Location_str", "Max_Capacity", "Current_Pallets", "Available_Capacity", "Status"]


def build_empty_locations(df: pd.DataFrame, capacity_file: Path, location_cfg) -> pd.DataFrame:
    df_cap = read_capacity_sheet(capacity_file)
    column = location_cfg.empty_location_capacity_column
    if column in df_cap.columns:
        df_cap["Max_Capacity"] = pd.to_numeric(df_cap[column], errors="coerce").fillna(0)
    else:
        df_cap["Max_Capacity"] = 0

    current = df.groupby("Normalized_Location", as_index=False)["Pallet_Quantity"].sum().rename(
        columns={"Pallet_Quantity": "Current_Pallets"}
    )
    df_empty = pd.merge(df_cap, current, left_on="Location_str", right_on="Normalized_Location", how="left")
    df_empty["Current_Pallets"] = df_empty["Current_Pallets"].fillna(0).round(2)
    df_empty["Available_Capacity"] = (df_empty["Max_Capacity"] - df_empty["Current_Pallets"]).round(2)

    df_empty = df_empty[df_empty["Current_Pallets"] == 0].copy()
    df_empty["Status"] = EMPTY_STATUS
    groups = location_cfg.warehouse_group_prefixes
    df_empty["Warehouse_Group"] = df_empty["Location_str"].apply(lambda v: warehouse_group(v, groups))
    df_empty = df_empty[~df_empty["Location_str"].isin(set(location_cfg.empty_location_exclusions))]
    return df_empty.sort_values(["Warehouse_Group", "Available_Capacity"], ascending=[True, False])


def empty_location_rows(df_empty: pd.DataFrame) -> list[list]:
    return [
        [str(r.Warehouse_Group), str(r.Location_str), float(r.Max_Capacity), float(r.Current_Pallets),
         float(r.Available_Capacity), str(r.Status)]
        for r in df_empty[ROW_COLUMNS].itertuples(index=False)
    ]


def publish_empty_locations(df: pd.DataFrame, capacity_file: Path, location_cfg, webapp_url: str, secret: str,
                            session_factory) -> None:
    if not webapp_url or not secret or not capacity_file.exists():
        return

    logger.info("Đang phân tích các vị trí trống để gửi lên Google Sheet...")
    try:
        rows = empty_location_rows(build_empty_locations(df, capacity_file, location_cfg))
        payload = {"secret": secret, "header": HEADER, "rows": rows}
        session = session_factory()
        response = session.post(webapp_url, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        if result.get("status") == "ok":
            logger.info("Đã cập nhật %s vị trí trống lên Google Sheet.", result.get("rows_written", len(rows)))
        else:
            logger.warning("Apps Script báo lỗi Capacity: %s", result.get("message"))
    except Exception as exc:
        logger.warning("Lỗi cập nhật vị trí trống lên Google Sheet: %s", exc)
