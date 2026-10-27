from __future__ import annotations

import datetime
import logging
from pathlib import Path

import pandas as pd

from efefo.infra.files import copy_with_retry, stringify_date_time_columns, to_excel_with_retry

logger = logging.getLogger(__name__)

DESIRED_COLUMNS = [
    "Data_Source", "Material", "Short Name", "Name", "Batch", "EWMWarehouse", "EWMStorageType",
    "EWMStorageBin", "Normalized_Location", "Warehouse_Group", "ProductType", "ProductTypeName",
    "ProductGroup", "NgayNhapKho", "NgaySanXuat", "expirydate", "total_shellife",
    "Remaining_Shelf_Life_Days", "Thoi_Gian_Luu_Kho_Ngay", "phantram_shelf_life",
    "Stock_Health_Status", "ThoiGianSanXuat", "ThoiGianSanXuat2", "Unrestricted", "Blocked",
    "UnrestrictedUse", "BlockedThu", "EWMStockQuantityInBaseUnit", "EWMStockQuantityInBaseUnitTHU",
    "AvailableEWMStockQtyTHU", "AvailableEWMStockQty", "EWMStockQuantityBaseUnit",
    "Qty (Carton/Crate)/Pallet", "Pallet_Quantity", "Unit_Capacity", "Capacity_Group",
    "Max_Capacity", "Occupancy (%)", "Available_Capacity", "EWMStorBinIsBlockedForPutaway",
    "EWMStorBinIsBlockedForRemoval", "MaterialBasicText", "BaseUnit", "EANCode", "LabelDate",
    "LabelTime", "OT", "ProductionLine", "ST", "WorkOrder", "HandlingUnitNumber",
]
DAILY_FILE_PATTERN = "Inventory_Report_Full_{date}.xlsx"


def export_inventory_report(df: pd.DataFrame, excel_file: Path, daily_dir: Path) -> None:
    existing_columns = [c for c in DESIRED_COLUMNS if c in df.columns]
    df_final = stringify_date_time_columns(df[existing_columns].copy())

    latest_written = to_excel_with_retry(df_final, excel_file)
    if latest_written:
        logger.info("Xuất file SAP Inventory thành công: %s", excel_file)

    try:
        daily_dir.mkdir(parents=True, exist_ok=True)
        daily_file = daily_dir / DAILY_FILE_PATTERN.format(date=datetime.date.today().strftime("%Y-%m-%d"))
        if not daily_file.exists():
            saved = copy_with_retry(excel_file, daily_file) if latest_written else to_excel_with_retry(df_final, daily_file)
            if saved:
                logger.info("Đã lưu bản chốt đầu ngày tại: %s", daily_file)
        else:
            logger.info("Bản chốt đầu ngày đã tồn tại (%s) — bỏ qua không ghi đè.", daily_file.name)
    except Exception as exc:
        logger.warning("Không thể lưu bản chốt đầu ngày: %s", exc)
