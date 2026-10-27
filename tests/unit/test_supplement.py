from __future__ import annotations

import datetime
import json

import numpy as np
import pandas as pd
from freezegun import freeze_time

from efefo.domain.supplement import (
    DATA_SOURCE_MANUAL,
    DATA_SOURCE_SAP,
    MANUAL_QTY_CARTON_COL,
    MANUAL_QTY_PL_COL,
    append_manual_only_rows,
    drop_manual_rows_without_quantity,
    drop_manual_rows_without_shelf_life,
    fill_manual_quantity,
    find_carton_qty_column,
    parse_count,
)
from efefo.sources.manual_materials import parse_manual_only_materials, parse_material_list

PREFIXES = ("HMPKG", "PKG", "HM")


def sap_frame():
    return pd.DataFrame({
        "Material": ["10001", "10002"],
        "EWMStorageBin": ["HMD01", "HME02"],
        "NgaySanXuat": [datetime.date(2026, 9, 1), datetime.date(2026, 9, 2)],
        "NgayNhapKho": [None, None],
        "EWMStockQuantityInBaseUnit": [100.0, 200.0],
    })


def manual_frame():
    return pd.DataFrame({
        "Location": ["D01", "F09", "G10", "D01", "E02"],
        "Item": ["777", "777", "778.0", "10001", "777"],
        "PRD date": ["01/09/2026", "05/09/2026", "15/09/2026", "01/09/2026", "02/09/2026"],
        "Qty (PL)": ["1", "2", "0", "1", "1"],
        "Q'TY (Carton/Crate)": ["", "6.760", "", "", "1,250"],
        "Normalized_Location": ["D01", "F09", "G10", "D01", "E02"],
    })


@freeze_time("2026-10-19")
def test_only_whitelisted_rows_added_and_marked():
    out = append_manual_only_rows(sap_frame(), manual_frame(), {"777", "778"}, PREFIXES)
    manual = out[out["Data_Source"] == DATA_SOURCE_MANUAL]
    assert manual["Material"].tolist() == ["777", "777", "778", "777"]
    assert manual[MANUAL_QTY_CARTON_COL].tolist()[1] == 6760
    assert (out["Data_Source"] == DATA_SOURCE_SAP).sum() == 2


def test_no_whitelist_or_sheet_returns_sap_only():
    assert len(append_manual_only_rows(sap_frame(), None, {"777"}, PREFIXES)) == 2
    assert len(append_manual_only_rows(sap_frame(), manual_frame(), set(), PREFIXES)) == 2


@freeze_time("2026-10-19 08:00")
def test_history_drops_rows_whose_bin_emptied_in_sap(tmp_path):
    history_file = tmp_path / "history.json"
    history_file.write_text(json.dumps({"F09|777": "2026-10-18T08:00:00", "X|1": "2026-01-01T00:00:00"}))
    out = append_manual_only_rows(sap_frame(), manual_frame(), {"777", "778"}, PREFIXES, history_file, 7)
    manual = out[out["Data_Source"] == DATA_SOURCE_MANUAL]
    assert "F09" not in manual["EWMStorageBin"].tolist()
    saved = json.loads(history_file.read_text())
    assert "X|1" not in saved and "F09|777" in saved
    assert saved["D01|10001"] == "2026-10-19T08:00:00"


@freeze_time("2026-10-19 08:00")
def test_corrupt_history_is_ignored(tmp_path):
    history_file = tmp_path / "history.json"
    history_file.write_text("{not json")
    out = append_manual_only_rows(sap_frame(), manual_frame(), {"777"}, PREFIXES, history_file, 7)
    assert (out["Data_Source"] == DATA_SOURCE_MANUAL).sum() == 3


def test_quantity_prefers_carton_then_formula_then_drops_zero():
    df = pd.DataFrame({
        "Data_Source": [DATA_SOURCE_SAP, DATA_SOURCE_MANUAL, DATA_SOURCE_MANUAL, DATA_SOURCE_MANUAL],
        "EWMStorageBin": ["A", "B", "C", "D"],
        "Material": ["1", "2", "3", "4"],
        "EWMStockQuantityInBaseUnit": [50, np.nan, np.nan, np.nan],
        MANUAL_QTY_PL_COL: [np.nan, 2, 1, 3],
        MANUAL_QTY_CARTON_COL: [np.nan, 500, np.nan, np.nan],
        "Qty (Carton/Crate)/Pallet": [10, 100, 70, np.nan],
    })
    out = drop_manual_rows_without_quantity(fill_manual_quantity(df))
    assert out["EWMStockQuantityInBaseUnit"].tolist() == [50, 500, 70]
    assert out["EWMStorageBin"].tolist() == ["A", "B", "C"]


def test_manual_rows_without_master_dropped():
    df = pd.DataFrame({
        "Data_Source": [DATA_SOURCE_SAP, DATA_SOURCE_MANUAL, DATA_SOURCE_MANUAL],
        "total_shellife": [np.nan, 0, 300],
        "BaseDateForShelfLife": pd.to_datetime([None, "2026-01-01", "2026-01-01"]),
    })
    out = drop_manual_rows_without_shelf_life(df)
    assert out.index.tolist() == [0, 2]


def test_parse_count_and_carton_header():
    assert parse_count(pd.Series(["6.760", "6,760", "6 760", "6760", "", "x"])).tolist()[:4] == [6760] * 4
    assert find_carton_qty_column(pd.DataFrame(columns=["Q’TY (Carton / Crate)"])) == "Q’TY (Carton / Crate)"
    assert find_carton_qty_column(pd.DataFrame(columns=["Qty"])) is None


def test_material_list_parsing(tmp_path, monkeypatch):
    assert parse_material_list("# note\n1, 2;3\n\n # x\n4") == {"1", "2", "3", "4"}
    monkeypatch.setenv("SAP_MA_BO_SUNG", "9;8")
    assert parse_manual_only_materials(tmp_path, "missing.txt") == {"8", "9"}
    (tmp_path / "list.txt").write_text("﻿5\n6", encoding="utf-8")
    assert parse_manual_only_materials(tmp_path, "list.txt") == {"5", "6"}
