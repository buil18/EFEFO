from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from efefo.domain.location import normalize_bin, warehouse_group
from efefo.sources.capacity_sheet import read_capacity_sheet

logger = logging.getLogger(__name__)

CAPACITY_COLUMNS = ("Capacity Can", "Capacity Bot", "Capacity Keg")


def map_capacity_group(unit_val) -> str:
    if pd.isna(unit_val) or unit_val == "":
        return "Uncategorized"
    u = str(unit_val).upper()
    if "CS" in u or "CASE" in u or "TR" in u or "TRAY" in u:
        return "Capacity Can"
    if "CR" in u or "CRATE" in u:
        return "Capacity Bot"
    if "BR" in u or "KEG" in u or "PC" in u or "CO2" in u:
        return "Capacity Keg"
    return "Uncategorized"


def compute_occupancy(df: pd.DataFrame, capacity_file: Path, location_cfg) -> pd.DataFrame:
    logger.info("Đang tính Occupancy (%%) theo Capacity...")
    prefixes = location_cfg.strip_prefixes
    groups = location_cfg.warehouse_group_prefixes
    df["Normalized_Location"] = df["EWMStorageBin"].apply(lambda v: normalize_bin(v, prefixes))
    df["Warehouse_Group"] = df["Normalized_Location"].apply(lambda v: warehouse_group(v, groups))

    if not capacity_file.exists():
        df["Max_Capacity"] = 0
        df["Occupancy (%)"] = 0
        df["Available_Capacity"] = 0
        return df

    try:
        df_cap = read_capacity_sheet(capacity_file)
        merge_cols = ["Location_str", *CAPACITY_COLUMNS]
        existing_cols = [c for c in merge_cols if c in df_cap.columns]
        df = pd.merge(df, df_cap[existing_cols], left_on="Normalized_Location", right_on="Location_str", how="left")

        capacity_by_group = {name: df.get(name, 0) for name in CAPACITY_COLUMNS}
        df["Max_Capacity"] = 0
        for grp_name, col_values in capacity_by_group.items():
            mask = df.get("Capacity_Group") == grp_name
            df.loc[mask, "Max_Capacity"] = col_values[mask]

        df["Max_Capacity"] = pd.to_numeric(df["Max_Capacity"], errors="coerce").fillna(0)
        valid_capacity = df["Max_Capacity"] > 0
        df["Occupancy (%)"] = 0.0
        df.loc[valid_capacity, "Occupancy (%)"] = (
            (df.loc[valid_capacity, "Pallet_Quantity"] / df.loc[valid_capacity, "Max_Capacity"]) * 100
        ).round(2)
        df["Available_Capacity"] = df["Max_Capacity"] - df["Pallet_Quantity"]
    except Exception as exc:
        logger.warning("Lỗi khi xử lý sheet 'Capacity': %s", exc)
        df["Max_Capacity"] = 0
        df["Occupancy (%)"] = 0
        df["Available_Capacity"] = 0

    return df
