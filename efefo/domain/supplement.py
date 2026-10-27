from __future__ import annotations

import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd

from efefo.domain.location import normalize_bin
from efefo.domain.location_history import (
    filter_rows_by_history,
    history_key,
    load_location_history,
    save_location_history,
)
from efefo.domain.prd_date import parse_prd_date
from efefo.infra.columns import (
    ITEM_COLUMN_CANDIDATES,
    LOCATION_COLUMN_CANDIDATES,
    PRD_DATE_COLUMN_CANDIDATES,
    QTY_PL_COLUMN_CANDIDATES,
    find_matching_column,
    material_codes,
)

logger = logging.getLogger(__name__)

DATA_SOURCE_SAP = "SAP"
DATA_SOURCE_MANUAL = "Google Sheet (SAP chưa ghi nhận)"
MANUAL_QTY_PL_COL = "Manual_Qty_PL"
MANUAL_QTY_CARTON_COL = "Manual_Qty_Carton"
CARTON_HEADER_FORMS = ("qty(carton/crate)", "qty(carton)", "qty(crate)")
QTY_COL = "EWMStockQuantityInBaseUnit"
CARTON_FORMULA_MISMATCH_RATIO = 0.5


def warn_unlisted_manual_materials(df_manual: pd.DataFrame, sap_materials: set[str], whitelist: set[str]) -> None:
    if "Material_str" not in df_manual.columns:
        return
    manual_materials = set(df_manual["Material_str"].dropna().unique()) - {""}
    for material in sorted(manual_materials - sap_materials - whitelist):
        rows = df_manual.loc[df_manual["Material_str"] == material]
        locations = sorted(set(rows["Normalized_Location"].dropna()) - {""})
        logger.warning("Mã %s có trên Sheet (%s dòng, vị trí: %s) nhưng chưa có trong SAP/whitelist.",
                       material, len(rows), locations[:10])


def find_carton_qty_column(df: pd.DataFrame) -> str | None:
    for col in df.columns:
        if re.sub(r"[\s'’`´]", "", str(col)).lower() in CARTON_HEADER_FORMS:
            return col
    return None


def parse_count(series: pd.Series) -> pd.Series:
    cleaned = series.astype(str).str.replace(r"[\s.,  ]", "", regex=True)
    return pd.to_numeric(cleaned, errors="coerce")


def prepare_manual_frame(df_manual: pd.DataFrame) -> pd.DataFrame | None:
    df = df_manual.copy()
    item_col = find_matching_column(df, ITEM_COLUMN_CANDIDATES)
    if not item_col:
        logger.warning("Không tìm thấy cột mã hàng trong Google Sheet để bổ sung mã. Các cột hiện có: %s",
                       list(df.columns))
        return None

    loc_col = find_matching_column(df, LOCATION_COLUMN_CANDIDATES) or "Location"
    qty_col = find_matching_column(df, QTY_PL_COLUMN_CANDIDATES)
    prd_col = find_matching_column(df, PRD_DATE_COLUMN_CANDIDATES)

    df["Material_str"] = material_codes(df[item_col])
    df["Manual_PRD_dt"] = parse_prd_date(df[prd_col]) if prd_col and prd_col in df.columns else pd.NaT
    df[MANUAL_QTY_PL_COL] = (
        pd.to_numeric(df[qty_col], errors="coerce").fillna(0) if qty_col and qty_col in df.columns else 0
    )
    carton_col = find_carton_qty_column(df)
    df[MANUAL_QTY_CARTON_COL] = parse_count(df[carton_col]) if carton_col else np.nan
    if not carton_col:
        logger.warning("Không thấy cột Q'TY (Carton/Crate) trên Google Sheet — số lượng dòng kiểm kho "
                       "sẽ tính theo Qty (PL) x quy cách pallet.")
    df["Manual_Location"] = df[loc_col].to_numpy() if loc_col in df.columns else ""
    return df


def build_manual_only_rows(df_sap: pd.DataFrame, df_manual: pd.DataFrame, whitelist: set[str],
                           strip_prefixes) -> pd.DataFrame:
    if not whitelist:
        return pd.DataFrame()

    selected = df_manual[
        df_manual["Material_str"].isin(whitelist)
        & df_manual["Normalized_Location"].notna()
        & (df_manual["Normalized_Location"] != "")
    ].copy()
    if selected.empty:
        return pd.DataFrame()

    sap_material = material_codes(df_sap["Material"])
    sap_location = df_sap["EWMStorageBin"].map(lambda v: normalize_bin(v, strip_prefixes))
    sap_prod_date = pd.to_datetime(df_sap.get("NgaySanXuat"), errors="coerce").fillna(
        pd.to_datetime(df_sap.get("NgayNhapKho"), errors="coerce")
    )
    sap_keys = set(zip(sap_location, sap_material, sap_prod_date.dt.normalize()))

    manual_keys = list(zip(selected["Normalized_Location"], selected["Material_str"],
                           selected["Manual_PRD_dt"].dt.normalize()))
    is_duplicate = pd.Series([k in sap_keys for k in manual_keys], index=selected.index)
    if is_duplicate.any():
        logger.warning("Bỏ qua %s dòng bổ sung đã xuất hiện trên SAP.", int(is_duplicate.sum()))
        selected = selected[~is_duplicate]
        if selected.empty:
            return pd.DataFrame()

    return pd.DataFrame({
        "Material": selected["Material_str"].to_numpy(),
        "EWMStorageBin": selected["Manual_Location"].to_numpy(),
        "NgaySanXuat": selected["Manual_PRD_dt"].dt.date.to_numpy(),
        MANUAL_QTY_PL_COL: selected[MANUAL_QTY_PL_COL].to_numpy(),
        MANUAL_QTY_CARTON_COL: selected[MANUAL_QTY_CARTON_COL].to_numpy(),
        "Data_Source": DATA_SOURCE_MANUAL,
    })


def append_manual_only_rows(df_sap: pd.DataFrame, df_manual: pd.DataFrame | None, whitelist: set[str],
                            strip_prefixes, history_path: Path | None = None,
                            history_retention_days: int = 7) -> pd.DataFrame:
    df_sap = df_sap.copy()
    df_sap["Data_Source"] = DATA_SOURCE_SAP

    if df_manual is None or not whitelist:
        return df_sap

    prepared = prepare_manual_frame(df_manual)
    if prepared is None or prepared.empty:
        return df_sap

    sap_materials = set(material_codes(df_sap["Material"]).unique())
    warn_unlisted_manual_materials(prepared, sap_materials, whitelist)

    rows = build_manual_only_rows(df_sap, prepared, whitelist, strip_prefixes)

    if history_path is not None:
        sap_keys_now = {
            history_key(loc, mat)
            for loc, mat in zip(
                df_sap["EWMStorageBin"].map(lambda v: normalize_bin(v, strip_prefixes)),
                material_codes(df_sap["Material"]),
            )
            if loc
        }
        history = load_location_history(history_path)
        if not rows.empty:
            row_keys = [
                history_key(loc, mat)
                for loc, mat in zip(rows["EWMStorageBin"].map(lambda v: normalize_bin(v, strip_prefixes)),
                                    rows["Material"].astype(str))
            ]
            rows = filter_rows_by_history(rows, row_keys, sap_keys_now, history)
        save_location_history(history_path, history, sap_keys_now, history_retention_days)

    return pd.concat([df_sap, rows], ignore_index=True) if not rows.empty else df_sap


def fill_manual_quantity(df: pd.DataFrame) -> pd.DataFrame:
    if MANUAL_QTY_PL_COL not in df.columns:
        return df
    is_manual = df["Data_Source"] == DATA_SOURCE_MANUAL
    if not is_manual.any():
        return df

    qty_per_pallet = pd.to_numeric(df.get("Qty (Carton/Crate)/Pallet", pd.Series(np.nan, index=df.index)),
                                   errors="coerce")
    df[QTY_COL] = pd.to_numeric(df.get(QTY_COL), errors="coerce")

    by_formula = (df[MANUAL_QTY_PL_COL] * qty_per_pallet).fillna(0)
    carton = (
        pd.to_numeric(df[MANUAL_QTY_CARTON_COL], errors="coerce")
        if MANUAL_QTY_CARTON_COL in df.columns
        else pd.Series(np.nan, index=df.index)
    )
    use_carton = is_manual & (carton > 0)
    df.loc[is_manual, QTY_COL] = by_formula[is_manual]
    df.loc[use_carton, QTY_COL] = carton[use_carton]

    n_carton = int(use_carton.sum())
    logger.info("Số lượng dòng kiểm kho: %s dòng lấy từ Q'TY (Carton/Crate), %s dòng tính theo Qty (PL) x quy cách.",
                n_carton, int(is_manual.sum()) - n_carton)
    both = use_carton & (by_formula > 0)
    diff = both & ((carton - by_formula).abs() > (by_formula * CARTON_FORMULA_MISMATCH_RATIO))
    if diff.any():
        sample = df.loc[diff, "EWMStorageBin"].astype(str).head(5).tolist()
        logger.warning("%s dòng có Q'TY lệch >50%% so với Qty (PL) x quy cách (mẫu vị trí: %s). Đang dùng Q'TY.",
                       int(diff.sum()), sample)
    return df


def drop_manual_rows_without_quantity(df: pd.DataFrame) -> pd.DataFrame:
    if "Data_Source" not in df.columns:
        return df
    is_manual = df["Data_Source"] == DATA_SOURCE_MANUAL
    if not is_manual.any():
        return df

    qty = pd.to_numeric(df[QTY_COL], errors="coerce").fillna(0)
    empty = is_manual & (qty <= 0)
    if empty.any():
        no_pallet_spec = empty & (pd.to_numeric(df[MANUAL_QTY_PL_COL], errors="coerce").fillna(0) > 0)
        if no_pallet_spec.any():
            logger.warning("%s dòng kiểm kho có Qty (PL) > 0 nhưng không ra số lượng (thiếu quy cách pallet "
                           "trong Capacity.xlsx và không có Q'TY): mã %s.",
                           int(no_pallet_spec.sum()), sorted(set(df.loc[no_pallet_spec, "Material"].astype(str)))[:10])
        logger.info("Loại %s dòng kiểm kho có số lượng 0 (vị trí: %s).",
                    int(empty.sum()), sorted(set(df.loc[empty, "EWMStorageBin"].astype(str)))[:15])
        df = df[~empty].copy()
    return df


def drop_manual_rows_without_shelf_life(df: pd.DataFrame) -> pd.DataFrame:
    if "Data_Source" not in df.columns:
        return df
    is_manual = df["Data_Source"] == DATA_SOURCE_MANUAL
    if not is_manual.any():
        return df
    total_sl = pd.to_numeric(df.get("total_shellife"), errors="coerce")
    invalid = is_manual & (total_sl.isna() | (total_sl <= 0) | df["BaseDateForShelfLife"].isna())
    if invalid.any():
        logger.warning("Loại %s dòng bổ sung do thiếu Master Data hạn sử dụng.", int(invalid.sum()))
        df = df[~invalid].copy()
    return df
