from __future__ import annotations

import datetime

import pandas as pd
import pytest
from freezegun import freeze_time

from efefo.domain.fefo import build_fefo_summary, lot_group_numbers
from efefo.domain.supplement import DATA_SOURCE_MANUAL, DATA_SOURCE_SAP


def days(*values):
    return pd.Series([pd.Timestamp("2026-01-01") + pd.Timedelta(days=v) if v is not None else pd.NaT for v in values])


def test_lot_groups_measured_from_anchor_not_previous_lot():
    assert lot_group_numbers(days(0, 5, 10, 15, 20), 7).tolist() == [1, 1, 2, 2, 3]


def test_lot_groups_boundary_and_missing_dates():
    assert lot_group_numbers(days(0, 6, 7, None), 7).tolist() == [1, 1, 2, 0]


def frame(rows):
    df = pd.DataFrame(rows, columns=["Normalized_Location", "Material", "Short Name", "BaseDateForShelfLife",
                                     "EWMStockQuantityInBaseUnit", "phantram_shelf_life", "Data_Source"])
    df["BaseDateForShelfLife"] = pd.to_datetime(df["BaseDateForShelfLife"])
    return df


@freeze_time("2026-10-19")
def test_summary_rules():
    df = frame([
        ["D01", "1", "A", "2026-08-01", 100, 80.0, DATA_SOURCE_SAP],
        ["D01", "1", "A", "2026-08-03", 50, 81.0, DATA_SOURCE_SAP],
        ["D01", "1", "A", "2026-08-20", 70, 85.0, DATA_SOURCE_SAP],
        ["E01", "1", "A", "2026-08-01", 10, 80.0, DATA_SOURCE_MANUAL],
        ["F01", "1", "A", "2026-08-01", 300, 80.0, DATA_SOURCE_SAP],
        ["G01", "1", "A", "2026-10-19", 999, 99.0, DATA_SOURCE_SAP],
        ["BLK", "1", "A", "2026-01-01", 5, 10.0, DATA_SOURCE_SAP],
        ["", "1", "A", "2026-01-01", 5, 10.0, DATA_SOURCE_SAP],
        ["D02", "", "A", "2026-01-01", 5, 10.0, DATA_SOURCE_SAP],
    ])
    out = build_fefo_summary(df, 7, blocked_locations={"BLK"})
    assert out.columns.tolist() == ["Normalized_Location", "Material", "Short Name", "PRD_date", "Total_Quantity",
                                    "phantram_shelf_life"]
    assert out["Normalized_Location"].tolist() == ["D01", "F01", "E01*", "D01"]
    assert out["Total_Quantity"].tolist() == [150, 300, 10, 70]
    assert out["phantram_shelf_life"].tolist() == [0.8, 0.8, 0.8, 0.85]
    assert out["PRD_date"].tolist()[1] == datetime.date(2026, 8, 1)


@freeze_time("2026-10-19")
def test_blocked_filter_applies_before_manual_marker():
    df = frame([["E01", "1", "A", "2026-08-01", 10, 80.0, DATA_SOURCE_MANUAL]])
    assert build_fefo_summary(df, 7, blocked_locations={"E01"}).empty


def test_missing_columns_raise():
    with pytest.raises(KeyError):
        build_fefo_summary(pd.DataFrame({"Material": ["1"]}), 7)


@freeze_time("2026-10-19")
def test_empty_input_returns_empty_summary():
    out = build_fefo_summary(frame([]), 7)
    assert out.empty


@freeze_time("2026-10-19")
def test_v6_small_rows_dropped_and_ties_sorted_by_quantity_then_location():
    df = frame([
        ["F01", "1", "A", "2026-08-01", 300, 80.0, DATA_SOURCE_SAP],
        ["B01", "1", "A", "2026-08-01", 300, 80.0, DATA_SOURCE_SAP],
        ["D01", "1", "A", "2026-08-01", 120, 80.0, DATA_SOURCE_SAP],
        ["E01", "1", "A", "2026-08-01", 99.9, 80.0, DATA_SOURCE_SAP],
        ["G01", "1", "A", "2026-08-01", 0, 80.0, DATA_SOURCE_SAP],
        ["H01", "1", "A", "2026-08-01", -5, 80.0, DATA_SOURCE_SAP],
        ["C01", "1", "A", "2026-08-01", 100, 80.0, DATA_SOURCE_MANUAL],
    ])
    out = build_fefo_summary(df, 7, min_quantity=100)
    assert out["Normalized_Location"].tolist() == ["D01", "B01", "F01", "C01*"]


@freeze_time("2026-10-19")
def test_v6_min_quantity_zero_disables_filter():
    df = frame([["G01", "1", "A", "2026-08-01", 0, 80.0, DATA_SOURCE_SAP]])
    assert len(build_fefo_summary(df, 7, min_quantity=0)) == 1
