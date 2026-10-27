from __future__ import annotations

import datetime
import re

import pandas as pd

DATE_DIGITS = r"(\d+)"
MAX_SAFE_MILLIS = 9_000_000_000_000_000
TIME_PATTERN = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def clean_sap_date(val):
    if isinstance(val, str) and val.startswith("/Date(") and val.endswith(")/"):
        try:
            found = re.search(r"\d+", val)
            if found is None:
                return val
            ms = int(found.group())
            return pd.to_datetime(ms, unit="ms").date()
        except (ValueError, TypeError):
            return val
    return val


def clean_sap_time(val):
    if isinstance(val, str) and val.startswith("PT"):
        match = TIME_PATTERN.match(val)
        if match:
            try:
                h = int(match.group(1) or 0)
                m = int(match.group(2) or 0)
                s = int(match.group(3) or 0)
                return datetime.time(h, m, s)
            except ValueError:
                return val
    return val


def clean_sap_dates(values: pd.Series) -> pd.Series:
    text = values.astype(str)
    wrapped = text.str.endswith(")/")
    millis = pd.to_numeric(text.where(wrapped).str.extract(DATE_DIGITS, expand=False), errors="coerce")
    millis = millis.where(millis < MAX_SAFE_MILLIS)
    converted = pd.to_datetime(millis, unit="ms", errors="coerce")
    result = values.astype(object).copy()
    ok = converted.notna()
    result[ok] = converted[ok].dt.date
    fallback = ~ok & wrapped
    if fallback.any():
        result[fallback] = values[fallback].map(clean_sap_date)
    return result


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.select_dtypes(include=["object", "string"]).columns.tolist():
        col_as_str = df[col].astype("string")
        date_mask = col_as_str.str.startswith("/Date(", na=False)
        time_mask = col_as_str.str.startswith("PT", na=False)
        if not date_mask.any() and not time_mask.any():
            continue
        df[col] = df[col].astype(object)
        if date_mask.any():
            df.loc[date_mask, col] = clean_sap_dates(df.loc[date_mask, col])
        if time_mask.any():
            df.loc[time_mask, col] = df.loc[time_mask, col].map(clean_sap_time)
    return df
