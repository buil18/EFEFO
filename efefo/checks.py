from __future__ import annotations

import pandas as pd

from efefo.config import SiteConfig
from efefo.context import build_context
from efefo.infra.columns import find_matching_column

SHELF_LIFE_REQUIRED = ["Short Name", "Qty (Carton/Crate)/Pallet", "Local Shelf Life"]
CAPACITY_REQUIRED = ["Capacity Can", "Capacity Bot", "Capacity Keg"]


def check_site(site: SiteConfig) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    warnings: list[str] = []
    ctx = build_context(site, interactive=True)

    for path in (ctx.shelf_life_file, ctx.capacity_file):
        if not path.exists():
            problems.append(f"Thiếu file đầu vào: {path}")

    if ctx.shelf_life_file.exists():
        df_sl = pd.read_excel(ctx.shelf_life_file)
        if not find_matching_column(df_sl, ["Iteam", "Item", "Code", "Material"]):
            problems.append(f"{ctx.shelf_life_file.name}: không có cột mã hàng (Iteam/Item/Code/Material)")
        problems += [f"{ctx.shelf_life_file.name}: thiếu cột '{c}'" for c in SHELF_LIFE_REQUIRED if c not in df_sl.columns]

    if ctx.capacity_file.exists():
        sheets = pd.ExcelFile(ctx.capacity_file).sheet_names
        for sheet in ("Capacity", "Unit"):
            if sheet not in sheets:
                problems.append(f"{ctx.capacity_file.name}: thiếu sheet '{sheet}'")
        if "Capacity" in sheets:
            df_cap = pd.read_excel(ctx.capacity_file, sheet_name="Capacity")
            problems += [f"{ctx.capacity_file.name}/Capacity: thiếu cột '{c}'" for c in CAPACITY_REQUIRED
                         if c not in df_cap.columns]

    if not ctx.fefo_file.exists():
        warnings.append(f"Không có file mẫu FEFO (sẽ bỏ qua xuất FEFO.xlsx): {ctx.fefo_file}")
    if site.publish.fefo_to_google_sheet and not (ctx.fefo_script_url and ctx.apps_script_secret):
        warnings.append("publish.fefo_to_google_sheet = true nhưng thiếu GOOGLE_APPS_SCRIPT_URL hoặc secret")
    if not ctx.manual_only_materials:
        warnings.append(f"Danh sách mã bổ sung trống ({site.sources.manual_materials_file})")
    return problems, warnings
