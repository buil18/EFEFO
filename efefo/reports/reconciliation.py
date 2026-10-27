from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from efefo.domain.reconciliation import MissingItemColumn, build_reconciliation
from efefo.infra.files import stringify_date_time_columns, to_excel_with_retry

logger = logging.getLogger(__name__)


def export_reconciliation(df: pd.DataFrame, df_manual: pd.DataFrame | None, recon_file: Path) -> None:
    if df_manual is None:
        logger.warning("Không có dữ liệu Google Sheet — bỏ qua đối chiếu.")
        return

    logger.info("Đang đối chiếu dữ liệu kiểm kê thực tế với SAP...")
    try:
        report = build_reconciliation(df, df_manual)
        report = stringify_date_time_columns(report)
        if to_excel_with_retry(report, recon_file):
            logger.info("Đã lưu báo cáo đối chiếu tại: %s", recon_file)
    except MissingItemColumn as exc:
        logger.warning("Không tìm thấy cột mã hàng trong Google Sheet. Các cột hiện có: %s", exc.args[0])
    except Exception as exc:
        logger.warning("Lỗi đối chiếu Google Sheets: %s", exc)
