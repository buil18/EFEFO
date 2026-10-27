from __future__ import annotations

import pandas as pd
import pytest
from freezegun import freeze_time

from efefo.domain.prd_date import detect_prd_date_order, parse_prd_date


def ts(text):
    return pd.Timestamp(text)


@freeze_time("2026-10-19")
def test_day_first_detected():
    out = parse_prd_date(pd.Series(["15/08/2026", "01/09/2026", "", None, "nan"]))
    assert out.tolist()[:2] == [ts("2026-08-15"), ts("2026-09-01")]
    assert out.iloc[2:].isna().all()


@freeze_time("2026-10-19")
def test_month_first_detected():
    out = parse_prd_date(pd.Series(["08/15/2026", "09/01/2026"]))
    assert out.tolist() == [ts("2026-08-15"), ts("2026-09-01")]


@freeze_time("2026-10-19")
def test_iso_and_alternative_formats():
    out = parse_prd_date(pd.Series(["2026-08-15", "2026/8/1", "15-08-2026", "15/08/26", "garbage"]))
    assert out.tolist()[:4] == [ts("2026-08-15"), ts("2026-08-01"), ts("2026-08-15"), ts("2026-08-15")]
    assert pd.isna(out.iloc[4])


def test_mixed_majority_wins():
    dayfirst, reason = detect_prd_date_order(pd.Series(["15/08/2026", "20/08/2026", "08/25/2026"]))
    assert dayfirst is True and reason == "trộn định dạng"


@pytest.mark.parametrize("forced, expected", [("dd/mm", True), ("monthfirst", False)])
def test_env_override(monkeypatch, forced, expected):
    monkeypatch.setenv("SAP_PRD_DATE_FORMAT", forced)
    assert detect_prd_date_order(pd.Series(["15/08/2026"]))[0] is expected


def test_ambiguous_defaults_to_day_first():
    assert detect_prd_date_order(pd.Series(["01/02/2026"])) == (True, "mặc định dd/mm/yyyy")
