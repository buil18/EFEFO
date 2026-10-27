from __future__ import annotations

import datetime
import logging

import pandas as pd

from efefo.domain.supplement import DATA_SOURCE_MANUAL

logger = logging.getLogger(__name__)

OUTPUT_COLUMNS = [
    "Normalized_Location", "Material", "Short Name", "PRD_date", "Total_Quantity", "phantram_shelf_life",
]
PERCENT_COLUMNS = ("phantram_shelf_life",)
REQUIRED_COLUMNS = [
    "Normalized_Location", "Material", "Short Name",
    "BaseDateForShelfLife", "EWMStockQuantityInBaseUnit", "phantram_shelf_life",
]
MANUAL_FLAG = "Is_Manual_Source"
LOT_GROUP = "_Lot_Group"
MANUAL_MARKER = "*"


def flag_manual_source(df: pd.DataFrame) -> pd.DataFrame:
    if "Data_Source" in df.columns:
        df[MANUAL_FLAG] = (df["Data_Source"] == DATA_SOURCE_MANUAL).astype(int)
    else:
        df[MANUAL_FLAG] = 0
    return df


def mark_manual_locations(summary: pd.DataFrame) -> pd.DataFrame:
    manual_rows = summary[MANUAL_FLAG] == 1
    if manual_rows.any():
        summary.loc[manual_rows, "Normalized_Location"] = (
            summary.loc[manual_rows, "Normalized_Location"].astype(str) + MANUAL_MARKER
        )
        logger.info("Đã đánh dấu %s vị trí trên FEFO bằng hậu tố '*' (dữ liệu từ kiểm kho, cần xác nhận thực tế).",
                    int(manual_rows.sum()))
    return summary.drop(columns=[MANUAL_FLAG])


def lot_group_numbers(dates: pd.Series, split_days: int) -> pd.Series:
    anchor = None
    group_no = 0
    result = []
    for day in dates:
        if pd.isna(day):
            result.append(0)
            continue
        if anchor is None or (day - anchor).days >= split_days:
            group_no += 1
            anchor = day
        result.append(group_no)
    return pd.Series(result, index=dates.index)


def assign_lot_groups(df: pd.DataFrame, split_days: int) -> pd.DataFrame:
    df = df.copy()
    df["_prd_day"] = df["BaseDateForShelfLife"].dt.normalize()
    df = df.sort_values(["Normalized_Location", "Material", "_prd_day"])
    df[LOT_GROUP] = (
        df.groupby(["Normalized_Location", "Material"], sort=False)["_prd_day"]
        .transform(lambda s: lot_group_numbers(s, split_days))
    )
    return df.drop(columns=["_prd_day"])


def drop_small_rows(summary: pd.DataFrame, min_quantity: float) -> pd.DataFrame:
    if min_quantity <= 0:
        return summary
    too_small = pd.to_numeric(summary["Total_Quantity"], errors="coerce").fillna(0) < min_quantity
    if too_small.any():
        logger.info("Loại %s dòng FEFO có số lượng dưới %s (hàng lẻ / hết hàng).", int(too_small.sum()),
                    f"{min_quantity:g}")
        summary = summary[~too_small].reset_index(drop=True)
    return summary


def build_fefo_summary(df: pd.DataFrame, lot_split_days: int, blocked_locations: set | None = None,
                       min_quantity: float = 0) -> pd.DataFrame:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise KeyError(f"Thiếu cột tổng hợp FEFO: {missing}")

    df = df[
        df["Normalized_Location"].notna() & (df["Normalized_Location"] != "")
        & df["Material"].notna() & (df["Material"] != "")
    ].copy()

    today = datetime.date.today()
    produced_today = df["BaseDateForShelfLife"].dt.date == today
    if produced_today.any():
        logger.info("Loại %s dòng sản xuất trong ngày hôm nay khỏi FEFO.", produced_today.sum())
        df = df[~produced_today].copy()

    pairs_before = len(df.drop_duplicates(subset=["Normalized_Location", "Material"]))
    df = assign_lot_groups(df, lot_split_days)
    group_keys = ["Normalized_Location", "Material", LOT_GROUP]
    rows_after = len(df.drop_duplicates(subset=group_keys))
    if rows_after > pairs_before:
        logger.info("Tách lô theo ngày sản xuất (ngưỡng %s ngày): %s vị trí-mã thành %s dòng FEFO.",
                    lot_split_days, pairs_before, rows_after)

    qty_by_group = (
        df.groupby(group_keys, as_index=False)["EWMStockQuantityInBaseUnit"]
        .sum()
        .rename(columns={"EWMStockQuantityInBaseUnit": "Total_Quantity"})
    )

    representative = df.sort_values("phantram_shelf_life", ascending=True).drop_duplicates(
        subset=group_keys, keep="first"
    ).copy()
    representative["PRD_date"] = representative["BaseDateForShelfLife"].dt.date
    representative = flag_manual_source(representative)

    summary = pd.merge(representative, qty_by_group, on=group_keys, how="left")
    summary = summary[OUTPUT_COLUMNS + [MANUAL_FLAG]].reset_index(drop=True)

    for col in PERCENT_COLUMNS:
        if col in summary.columns:
            summary[col] = summary[col] / 100

    if blocked_locations:
        summary = summary[~summary["Normalized_Location"].isin(blocked_locations)].reset_index(drop=True)

    summary = drop_small_rows(summary, min_quantity)

    summary = summary.sort_values(
        ["phantram_shelf_life", MANUAL_FLAG, "Total_Quantity", "Normalized_Location"],
        ascending=[True, True, True, True],
    ).reset_index(drop=True)

    return mark_manual_locations(summary)
