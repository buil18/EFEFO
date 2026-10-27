from __future__ import annotations

import math

import pytest

from efefo.domain.location import is_display_excluded, normalize_bin, normalize_location, warehouse_group

PREFIXES = ("HMPKG", "PKG", "HM")
GROUPS = ("BL", "F", "G", "E", "D")


@pytest.mark.parametrize("raw, expected", [
    ("HMD01", "D01"), ("HMPKGF31", "F31"), ("PKGG07", "G07"), ("hm  d 01", "D 01"), (" HMBL05 ", "BL05"),
    ("D01", "D01"), ("", ""), (None, ""), (math.nan, ""), ("HM", ""), ("HMPKG", ""), ("PKG E12", "E12"),
    ("HMK12", "K12"), ("BL7.3", "BL7.3"),
])
def test_normalize_bin(raw, expected):
    assert normalize_bin(raw, PREFIXES) == expected


def test_normalize_location_collapses_whitespace():
    assert normalize_location(" a \t b\nc ") == "A B C"


@pytest.mark.parametrize("loc, expected", [
    ("BL7.3", "Kho BL"), ("FDD1", "Kho F"), ("F31", "Kho F"), ("G01", "Kho G"), ("E29", "Kho E"),
    ("D01", "Kho D"), ("K12", "Kho K"), ("Z99", "Kho Z"), ("7A", "Kho Khác"), ("", "Unknown"), (None, "Unknown"),
    ("b12", "Kho B"),
])
def test_warehouse_group(loc, expected):
    assert warehouse_group(loc, GROUPS) == expected


@pytest.mark.parametrize("loc, expected", [
    ("K12", True), ("K30*", True), ("H01", True), ("LOOSE-01", True), ("KHU LOOSE", True), ("d loose", True),
    ("", True), (None, True), ("*", True), ("B7.3", False), ("F31*", False), ("E29", False), ("BL7.3", False),
])
def test_display_exclusion(loc, expected):
    assert is_display_excluded(loc, ("K", "H"), ("LOOSE",)) is expected


def test_repeated_prefix_only_leading_one_removed():
    assert normalize_bin("HMPKGHMPKG", PREFIXES) == "HMPKG"
