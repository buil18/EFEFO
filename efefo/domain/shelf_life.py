from __future__ import annotations

import datetime
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

NUMERIC_COLUMNS = [
    "Unrestricted", "Blocked", "UnrestrictedUse", "BlockedThu",
    "EWMStockQuantityInBaseUnit", "EWMStockQuantityInBaseUnitTHU",
    "AvailableEWMStockQtyTHU", "AvailableEWMStockQty",
    "EWMStockQuantityBaseUnit", "QuantityNumerator", "QuantityDenominator",
    "total_shellife", "Qty (Carton/Crate)/Pallet",
]


def stock_health(pct: float, thresholds) -> str:
    if pct <= thresholds.expired_max:
        return "6 - Expired"
    if pct < thresholds.near_expiry_below:
        return "5 - Hàng Cận Date"
    if pct < thresholds.traditional_below:
        return "4 - Chỉ xuất Kênh TT"
    if pct < thresholds.emart_below:
        return "3 - Khả dụng Emart"
    if pct <= thresholds.supermarket_max:
        return "2 - Khả dụng Siêu thị"
    return "1 - Khả dụng Toàn bộ"


def compute_shelf_life_metrics(df: pd.DataFrame, thresholds) -> pd.DataFrame:
    logger.info("Đang tính toán các chỉ số Shelf Life và Pallet...")
    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    today_ts = pd.Timestamp(datetime.date.today())
    df["NgaySanXuat_dt"] = pd.to_datetime(df.get("NgaySanXuat"), errors="coerce")
    df["NgayNhapKho_dt"] = pd.to_datetime(df.get("NgayNhapKho"), errors="coerce")
    df["BaseDateForShelfLife"] = df["NgaySanXuat_dt"].fillna(df["NgayNhapKho_dt"])

    warehouse_entry_date = df["NgayNhapKho_dt"].fillna(df["NgaySanXuat_dt"])
    df["Thoi_Gian_Luu_Kho_Ngay"] = (today_ts - warehouse_entry_date).dt.days

    if "total_shellife" in df.columns:
        has_valid_base = df["BaseDateForShelfLife"].notna() & (df["total_shellife"] > 0)
        df["expirydate"] = pd.NaT
        df.loc[has_valid_base, "expirydate"] = (
            df.loc[has_valid_base, "BaseDateForShelfLife"]
            + pd.to_timedelta(df.loc[has_valid_base, "total_shellife"], unit="D")
        )
        rem_days = (df["expirydate"] - today_ts).dt.days.fillna(0).astype(int)
        pct = ((rem_days / df["total_shellife"].replace(0, np.nan)) * 100).fillna(0).round(2)
        df["Remaining_Shelf_Life_Days"] = rem_days
        df["phantram_shelf_life"] = pct
        df["Stock_Health_Status"] = df["phantram_shelf_life"].apply(lambda v: stock_health(v, thresholds))
        df["expirydate"] = df["expirydate"].dt.date

    if "EWMStockQuantityInBaseUnit" in df.columns and "Qty (Carton/Crate)/Pallet" in df.columns:
        qty_per_pallet = df["Qty (Carton/Crate)/Pallet"].replace(0, np.nan)
        df["Pallet_Quantity"] = (df["EWMStockQuantityInBaseUnit"] / qty_per_pallet).fillna(0).round(2)

    return df
