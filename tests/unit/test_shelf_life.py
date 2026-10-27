from __future__ import annotations

import datetime

import pandas as pd
import pytest
from freezegun import freeze_time

from efefo.domain.shelf_life import compute_shelf_life_metrics, stock_health


@pytest.mark.parametrize("pct, label", [
    (-5, "6 - Expired"), (0, "6 - Expired"), (0.01, "5 - Hàng Cận Date"), (29.99, "5 - Hàng Cận Date"),
    (30, "4 - Chỉ xuất Kênh TT"), (65.99, "4 - Chỉ xuất Kênh TT"), (66, "3 - Khả dụng Emart"),
    (68.99, "3 - Khả dụng Emart"), (69, "2 - Khả dụng Siêu thị"), (71, "2 - Khả dụng Siêu thị"),
    (71.01, "1 - Khả dụng Toàn bộ"), (100, "1 - Khả dụng Toàn bộ"),
])
def test_stock_health_boundaries(site, pct, label):
    assert stock_health(pct, site.shelf_life) == label


@freeze_time("2026-10-19")
def test_metrics_use_production_then_entry_date(site):
    df = pd.DataFrame({
        "NgaySanXuat": [datetime.date(2026, 10, 9), None, None],
        "NgayNhapKho": [datetime.date(2026, 10, 12), datetime.date(2026, 9, 19), None],
        "total_shellife": [100, 30, 100],
        "EWMStockQuantityInBaseUnit": ["169.000", "84.5", None],
        "Qty (Carton/Crate)/Pallet": [169, 0, 169],
    })
    out = compute_shelf_life_metrics(df, site.shelf_life)
    assert out["Remaining_Shelf_Life_Days"].tolist() == [90, 0, 0]
    assert out["phantram_shelf_life"].tolist() == [90.0, 0.0, 0.0]
    assert out["Thoi_Gian_Luu_Kho_Ngay"].tolist()[:2] == [7, 30]
    assert out["Stock_Health_Status"].tolist() == ["1 - Khả dụng Toàn bộ", "6 - Expired", "6 - Expired"]
    assert out["Pallet_Quantity"].tolist() == [1.0, 0.0, 0.0]


@freeze_time("2026-10-19")
def test_zero_shelf_life_is_expired_not_error(site):
    df = pd.DataFrame({"NgaySanXuat": [datetime.date(2026, 10, 1)], "NgayNhapKho": [None], "total_shellife": [0],
                       "EWMStockQuantityInBaseUnit": [1], "Qty (Carton/Crate)/Pallet": [1]})
    out = compute_shelf_life_metrics(df, site.shelf_life)
    assert out["phantram_shelf_life"].iloc[0] == 0
    assert pd.isna(out["expirydate"].iloc[0])
