from __future__ import annotations

import pandas as pd

MATERIAL_SUFFIX_PATTERN = r"\.0$"


def find_matching_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    cols_clean = {str(c).strip().lower(): c for c in df.columns}
    for cand in candidates:
        cand_clean = cand.strip().lower()
        if cand_clean in cols_clean:
            return cols_clean[cand_clean]
    for cand in candidates:
        cand_clean = cand.strip().lower()
        for col_clean, actual_col in cols_clean.items():
            if cand_clean in col_clean:
                return actual_col
    return None


def material_codes(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.replace(MATERIAL_SUFFIX_PATTERN, "", regex=True)


def normalize_material(value) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text


ITEM_COLUMN_CANDIDATES = ["Item", "Iteam", "Code", "Material", "Item Code", "Mã hàng", "Mã SP"]
LOCATION_COLUMN_CANDIDATES = ["Location", "Location_1", "Vị trí", "Bin"]
QTY_PL_COLUMN_CANDIDATES = ["Qty (PL)", "Qty(PL)", "Quantity (PL)", "Qty", "Pallet", "Quantity"]
PRD_DATE_COLUMN_CANDIDATES = ["PRD date", "PRD Date", "PRD_date", "PRD date_3", "Ngày SX", "NSX"]
STATUS_COLUMN_CANDIDATES = ["STATUS", "Status", "Trạng thái"]
