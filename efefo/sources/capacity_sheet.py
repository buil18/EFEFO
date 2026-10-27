from __future__ import annotations

from pathlib import Path

import pandas as pd

from efefo.infra.columns import find_matching_column


def read_capacity_sheet(path: Path) -> pd.DataFrame:
    df_cap = pd.read_excel(path, sheet_name="Capacity")
    loc_col = find_matching_column(df_cap, ["Location", "Location_str", "Vị trí"]) or "Location"
    df_cap["Location_str"] = df_cap[loc_col].astype(str).str.strip().str.upper()
    return df_cap
