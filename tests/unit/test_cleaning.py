from __future__ import annotations

import datetime
import random

import pandas as pd

from efefo.sap.cleaning import clean_dataframe, clean_sap_date, clean_sap_dates, clean_sap_time


def test_scalar_date_variants():
    assert clean_sap_date("/Date(1760832000000)/") == datetime.date(2025, 10, 19)
    assert clean_sap_date("/Date(1760832000000+0700)/") == datetime.date(2025, 10, 19)
    assert clean_sap_date("/Date()/") == "/Date()/"
    assert clean_sap_date("/Date(99999999999999999999)/") == "/Date(99999999999999999999)/"
    assert clean_sap_date("/Date(123") == "/Date(123"
    assert clean_sap_date(None) is None


def test_time_variants():
    assert clean_sap_time("PT08H30M05S") == datetime.time(8, 30, 5)
    assert clean_sap_time("PT0H0M0S") == datetime.time(0, 0, 0)
    assert clean_sap_time("PT25H00M00S") == "PT25H00M00S"
    assert clean_sap_time("PTX") == datetime.time(0, 0, 0)
    assert clean_sap_time("08:30") == "08:30"


def test_vectorized_dates_match_scalar_on_random_input():
    rng = random.Random(7)
    values = []
    for _ in range(3000):
        kind = rng.random()
        if kind < 0.7:
            values.append(f"/Date({rng.randint(0, 4_000_000_000_000)})/")
        elif kind < 0.8:
            values.append(f"/Date({rng.randint(0, 10**22)})/")
        elif kind < 0.9:
            values.append(f"/Date({rng.randint(0, 10**12)}+0700)/")
        else:
            values.append(rng.choice(["/Date()/", "/Date(abc)/", "/Date(12"]))
    series = pd.Series(values)
    vectorized = clean_sap_dates(series)
    scalar = series.map(clean_sap_date)
    assert vectorized.tolist() == scalar.tolist()


def test_clean_dataframe_only_touches_sap_formats():
    df = pd.DataFrame({
        "NgaySanXuat": ["/Date(1760832000000)/", None, "/Date(1760918400000)/"],
        "Time": ["PT01H00M00S", "x", None],
        "Text": ["a", "b", "PTX-not-time"],
        "Qty": [1, 2, 3],
    })
    out = clean_dataframe(df.copy())
    assert out["NgaySanXuat"].tolist() == [datetime.date(2025, 10, 19), None, datetime.date(2025, 10, 20)]
    assert out["Time"].tolist()[:2] == [datetime.time(1, 0), "x"]
    assert out["Text"].tolist()[2] == datetime.time(0, 0)
    assert out["Qty"].tolist() == [1, 2, 3]
