from __future__ import annotations

import re

import pandas as pd

LEADING_LETTERS = re.compile(r"^([A-Z]+)")
WHITESPACE = re.compile(r"\s+")


def normalize_location(loc) -> str:
    if pd.isna(loc):
        return ""
    return WHITESPACE.sub(" ", str(loc)).strip().upper()


def normalize_bin(bin_str, strip_prefixes) -> str:
    s = normalize_location(bin_str)
    if not s:
        return ""
    for prefix in strip_prefixes:
        if s.startswith(prefix):
            return s[len(prefix):].strip()
    return s


def warehouse_group(loc, group_prefixes) -> str:
    if pd.isna(loc) or not str(loc).strip():
        return "Unknown"
    loc_str = str(loc).strip().upper()
    for prefix in group_prefixes:
        if loc_str.startswith(prefix):
            return f"Kho {prefix}"
    match = LEADING_LETTERS.match(loc_str)
    return f"Kho {match.group(1)}" if match else "Kho Khác"


def strip_manual_marker(location) -> str:
    return str(location or "").strip().rstrip("*")


def is_display_excluded(location, exclude_prefixes, exclude_keywords) -> bool:
    text = strip_manual_marker(location).upper()
    if not text:
        return True
    if any(keyword in text for keyword in exclude_keywords):
        return True
    return text.startswith(tuple(exclude_prefixes))
