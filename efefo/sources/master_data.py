from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from efefo.domain.capacity import map_capacity_group
from efefo.infra.columns import find_matching_column, material_codes

logger = logging.getLogger(__name__)

SHELF_LIFE_COLUMNS = ["Iteam_str", "Short Name", "Name", "Unit", "Qty (Carton/Crate)/Pallet", "Local Shelf Life"]


def merge_shelf_life(df: pd.DataFrame, path: Path) -> pd.DataFrame:
    logger.info("Đang đối chiếu thông tin Shelf Life...")
    df["Material_str"] = material_codes(df["Material"])

    if not path.exists():
        logger.warning("Không tìm thấy file Shelf Life tại %s. Bỏ qua.", path)
        return df

    df_sl = pd.read_excel(path)
    item_col = find_matching_column(df_sl, ["Iteam", "Item", "Code", "Material"]) or "Item"
    df_sl["Iteam_str"] = material_codes(df_sl[item_col])
    existing_sl_cols = [c for c in SHELF_LIFE_COLUMNS if c in df_sl.columns]
    df = pd.merge(df, df_sl[existing_sl_cols], left_on="Material_str", right_on="Iteam_str", how="left")

    if "Local Shelf Life" in df.columns:
        df["total_shellife"] = pd.to_numeric(df["Local Shelf Life"], errors="coerce")
    return df


def merge_unit_capacity(df: pd.DataFrame, path: Path) -> pd.DataFrame:
    logger.info("Đang đọc Unit và phân loại Capacity...")
    if path.exists():
        try:
            df_unit = pd.read_excel(path, sheet_name="Unit")
            mat_col = find_matching_column(df_unit, ["Material", "Item", "Code"])
            unit_col = find_matching_column(df_unit, ["Unit", "Units"])
            if mat_col and unit_col:
                df_unit["Material_str"] = material_codes(df_unit[mat_col])
                df_unit["units_str"] = df_unit[unit_col].astype(str).str.strip()
                df = pd.merge(df, df_unit[["Material_str", "units_str"]], on="Material_str", how="left")
                df.rename(columns={"units_str": "Unit_Capacity"}, inplace=True)
        except Exception as exc:
            logger.warning("Lỗi khi đọc sheet 'Unit' từ %s: %s", path, exc)
    else:
        logger.warning("Không tìm thấy file Capacity tại %s.", path)

    if "Unit_Capacity" in df.columns:
        df["Capacity_Group"] = df["Unit_Capacity"].apply(map_capacity_group)
    else:
        df["Unit_Capacity"] = ""
        df["Capacity_Group"] = "Uncategorized"
    return df

