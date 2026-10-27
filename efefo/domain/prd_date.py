from __future__ import annotations

import datetime
import logging
import os
import re

import pandas as pd

logger = logging.getLogger(__name__)

PRD_DATE_FORMAT_ENV = "SAP_PRD_DATE_FORMAT"
NUMERIC_DATE = re.compile(r"^\s*(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\s*$")
ISO_DATE = re.compile(r"^\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})\s*$")
IMPLAUSIBLE_DAYS = 730


def detect_prd_date_order(raw_series: pd.Series) -> tuple[bool, str]:
    forced = os.environ.get(PRD_DATE_FORMAT_ENV, "").strip().lower()
    if forced in {"dayfirst", "dd/mm", "dd"}:
        return True, f"ép cứng dd/mm/yyyy ({PRD_DATE_FORMAT_ENV})"
    if forced in {"monthfirst", "mm/dd", "mm"}:
        return False, f"ép cứng mm/dd/yyyy ({PRD_DATE_FORMAT_ENV})"

    day_first_evidence = 0
    month_first_evidence = 0
    for text in raw_series.dropna().astype(str):
        matched = NUMERIC_DATE.match(text)
        if not matched:
            continue
        first, second = int(matched.group(1)), int(matched.group(2))
        if first > 12 and second <= 12:
            day_first_evidence += 1
        elif second > 12 and first <= 12:
            month_first_evidence += 1

    if day_first_evidence and month_first_evidence:
        dayfirst = day_first_evidence >= month_first_evidence
        logger.warning("Cột PRD date trộn lẫn định dạng (%s dd/mm, %s mm/dd). Chọn %s theo đa số.",
                       day_first_evidence, month_first_evidence, "dd/mm" if dayfirst else "mm/dd")
        return dayfirst, "trộn định dạng"
    if day_first_evidence:
        return True, f"tự nhận diện dd/mm/yyyy ({day_first_evidence} dòng)"
    if month_first_evidence:
        return False, f"tự nhận diện mm/dd/yyyy ({month_first_evidence} dòng)"
    return True, "mặc định dd/mm/yyyy"


def parse_prd_date(raw_series: pd.Series) -> pd.Series:
    text_series = raw_series.astype(str).str.strip()
    has_value = raw_series.notna() & (text_series != "") & (text_series.str.lower() != "nan")
    parsed = pd.Series(pd.NaT, index=raw_series.index, dtype="datetime64[ns]")

    iso_mask = has_value & text_series.str.match(ISO_DATE)
    if iso_mask.any():
        parsed.loc[iso_mask] = pd.to_datetime(text_series[iso_mask].str.replace("/", "-", regex=False), errors="coerce")

    remaining = has_value & parsed.isna()
    if remaining.any():
        dayfirst, _ = detect_prd_date_order(text_series[remaining])
        primary_fmt = "%d/%m/%Y" if dayfirst else "%m/%d/%Y"
        parsed.loc[remaining] = pd.to_datetime(text_series[remaining], format=primary_fmt, errors="coerce")
        leftover = remaining & parsed.isna()
        if leftover.any():
            alt_formats = ["%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"] if dayfirst else ["%m-%d-%Y", "%m/%d/%y", "%m-%d-%y"]
            for fmt in alt_formats:
                need = leftover & parsed.isna()
                if not need.any():
                    break
                parsed.loc[need] = pd.to_datetime(text_series[need], format=fmt, errors="coerce")

    today = pd.Timestamp(datetime.date.today())
    implausible = parsed.notna() & (
        (parsed > today + pd.Timedelta(days=IMPLAUSIBLE_DAYS)) | (parsed < today - pd.Timedelta(days=IMPLAUSIBLE_DAYS))
    )
    if implausible.any():
        logger.warning("Phát hiện %s dòng PRD date cách hiện tại hơn 2 năm.", int(implausible.sum()))
    return parsed
