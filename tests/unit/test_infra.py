from __future__ import annotations

import os
import time

import pandas as pd
import pytest

from efefo.infra import files
from efefo.infra.columns import find_matching_column, material_codes, normalize_material
from efefo.infra.run_lock import AlreadyRunningError, acquire_run_lock, release_run_lock


def test_lock_blocks_then_releases(tmp_path):
    lock = tmp_path / ".lock"
    acquire_run_lock(lock, 3)
    with pytest.raises(AlreadyRunningError):
        acquire_run_lock(lock, 3)
    release_run_lock(lock)
    assert not lock.exists()
    release_run_lock(lock)


def test_stale_lock_is_replaced(tmp_path):
    lock = tmp_path / ".lock"
    lock.write_text("old")
    old = time.time() - 4 * 3600
    os.utime(lock, (old, old))
    acquire_run_lock(lock, 3)
    assert lock.read_text() != "old"


def test_excel_write_retries_when_locked(tmp_path, monkeypatch):
    calls = []
    original = pd.DataFrame.to_excel

    def flaky(self, *args, **kwargs):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError("locked")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(pd.DataFrame, "to_excel", flaky)
    monkeypatch.setattr(files.time, "sleep", lambda s: None)
    assert files.to_excel_with_retry(pd.DataFrame({"a": [1]}), tmp_path / "x.xlsx")
    assert len(calls) == 3


def test_excel_write_gives_up(tmp_path, monkeypatch):
    monkeypatch.setattr(pd.DataFrame, "to_excel", lambda self, *a, **k: (_ for _ in ()).throw(PermissionError()))
    monkeypatch.setattr(files.time, "sleep", lambda s: None)
    assert not files.to_excel_with_retry(pd.DataFrame({"a": [1]}), tmp_path / "x.xlsx")


def test_column_matching():
    df = pd.DataFrame(columns=["  Location_1 ", "Qty (PL)", "Remaining shelf-life (%)_4"])
    assert find_matching_column(df, ["Location", "Bin"]) == "  Location_1 "
    assert find_matching_column(df, ["qty (pl)"]) == "Qty (PL)"
    assert find_matching_column(df, ["Nope"]) is None


def test_material_normalization():
    assert material_codes(pd.Series([10128309, "10128309.0", " 1 ", None])).tolist() == [
        "10128309", "10128309", "1", "None"]
    assert normalize_material(10128309.0) == "10128309"
    assert normalize_material(float("nan")) == ""
