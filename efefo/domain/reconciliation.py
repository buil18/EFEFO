from __future__ import annotations

import pandas as pd

from efefo.domain.prd_date import parse_prd_date
from efefo.infra.columns import (
    ITEM_COLUMN_CANDIDATES,
    LOCATION_COLUMN_CANDIDATES,
    PRD_DATE_COLUMN_CANDIDATES,
    QTY_PL_COLUMN_CANDIDATES,
    find_matching_column,
    material_codes,
)
from efefo.sources.stock_count import log_location_mismatches

SKU_COLUMN_CANDIDATES = ["SKU", "SKU_2", "Tên hàng", "Product Name", "Short Name"]
MATCH_TOLERANCE = 0.01
OUTPUT_COLUMNS = [
    "Normalized_Location", "GoogleSheet_Location", "SAP_Location", "Material_str", "Product_Name",
    "Physical_Qty_PL", "SAP_Qty_PL", "GAP_Qty_PL", "SAP_Total_Qty", "Batch",
    "PRD_date", "SAP_NgaySanXuat", "SAP_NgayNhapKho",
    "Stock_Health_Status", "STATUS",
]


class MissingItemColumn(Exception):
    pass


def status_label(row) -> str:
    if row["_merge"] == "both":
        return (
            "Match (Khớp hoàn toàn)"
            if abs(row["GAP_Qty_PL"]) < MATCH_TOLERANCE
            else f"Lệch số lượng (Thực tế: {row['Physical_Qty_PL']} PL vs SAP: {row['SAP_Qty_PL']} PL)"
        )
    if row["_merge"] == "left_only":
        return "Chưa có trên SAP"
    if row["_merge"] == "right_only":
        return "Có trên SAP nhưng kho thực tế không ghi nhận (hoặc lệch ngày SX)"
    return "Unknown"


def build_reconciliation(df: pd.DataFrame, df_manual: pd.DataFrame) -> pd.DataFrame:
    item_code_col = find_matching_column(df_manual, ITEM_COLUMN_CANDIDATES)
    sku_name_col = find_matching_column(df_manual, SKU_COLUMN_CANDIDATES) or "SKU"
    qty_pl_col = find_matching_column(df_manual, QTY_PL_COLUMN_CANDIDATES) or "Qty (PL)"
    prd_date_col = find_matching_column(df_manual, PRD_DATE_COLUMN_CANDIDATES)

    if not item_code_col:
        raise MissingItemColumn(list(df_manual.columns))

    df_manual = df_manual.copy()
    df_manual["Material_str"] = material_codes(df_manual[item_code_col])
    df_manual["Physical_Qty_PL"] = (
        pd.to_numeric(df_manual[qty_pl_col], errors="coerce").fillna(0) if qty_pl_col in df_manual.columns else 0
    )
    df_manual["PRD_date_parsed"] = (
        parse_prd_date(df_manual[prd_date_col]).dt.normalize()
        if prd_date_col and prd_date_col in df_manual.columns else pd.NaT
    )

    loc_col = find_matching_column(df_manual, LOCATION_COLUMN_CANDIDATES) or "Location"

    df_manual_grouped = df_manual.groupby(
        ["Normalized_Location", "Material_str", "PRD_date_parsed"], as_index=False, dropna=False
    ).agg({sku_name_col: "first", "Physical_Qty_PL": "sum", loc_col: "first"}).rename(
        columns={sku_name_col: "Product_Name", loc_col: "GoogleSheet_Location"}
    )

    df["SAP_ProdDate_dt"] = df["BaseDateForShelfLife"].dt.normalize()
    df_sap_grouped = df.groupby(
        ["Normalized_Location", "Material_str", "SAP_ProdDate_dt"], as_index=False, dropna=False
    ).agg(
        {
            "EWMStorageBin": "first",
            "Short Name": "first",
            "Pallet_Quantity": "sum",
            "EWMStockQuantityInBaseUnit": "sum",
            "Batch": "first",
            "Stock_Health_Status": "first",
            "NgayNhapKho_dt": "first",
        }
    ).rename(
        columns={
            "Pallet_Quantity": "SAP_Qty_PL",
            "EWMStockQuantityInBaseUnit": "SAP_Total_Qty",
            "EWMStorageBin": "SAP_Location",
            "NgayNhapKho_dt": "SAP_NgayNhapKho_dt",
        }
    )

    df_recon = pd.merge(
        df_manual_grouped, df_sap_grouped,
        left_on=["Normalized_Location", "Material_str", "PRD_date_parsed"],
        right_on=["Normalized_Location", "Material_str", "SAP_ProdDate_dt"],
        how="outer", indicator=True,
    )

    log_location_mismatches(
        sap_locations=set(df_sap_grouped["Normalized_Location"]),
        manual_locations=set(df_manual_grouped["Normalized_Location"]),
    )

    df_recon["Product_Name"] = df_recon["Product_Name"].fillna(df_recon["Short Name"])
    df_recon["Physical_Qty_PL"] = df_recon["Physical_Qty_PL"].fillna(0)
    df_recon["SAP_Qty_PL"] = df_recon["SAP_Qty_PL"].fillna(0)

    both_zero = (df_recon["Physical_Qty_PL"] == 0) & (df_recon["SAP_Qty_PL"] == 0)
    if both_zero.any():
        df_recon = df_recon[~both_zero].copy()

    df_recon["GAP_Qty_PL"] = df_recon["Physical_Qty_PL"] - df_recon["SAP_Qty_PL"]
    df_recon["PRD_date"] = df_recon["PRD_date_parsed"].dt.strftime("%d/%m/%Y").fillna("")
    df_recon["SAP_NgaySanXuat"] = df_recon["SAP_ProdDate_dt"].dt.strftime("%d/%m/%Y").fillna("")
    df_recon["SAP_NgayNhapKho"] = df_recon["SAP_NgayNhapKho_dt"].dt.strftime("%d/%m/%Y").fillna("")
    df_recon["STATUS"] = df_recon.apply(status_label, axis=1)

    return df_recon[[c for c in OUTPUT_COLUMNS if c in df_recon.columns]].copy()
