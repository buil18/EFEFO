from __future__ import annotations

import datetime

import pytest
from freezegun import freeze_time

from tests.conftest import FROZEN_NOW
from tests.support.fakes import FakeHttp
from tests.support.runner_harness import (
    assert_snapshots_equal,
    load_legacy,
    run_legacy,
    run_new,
    snapshot_outputs,
)
from tests.support.scenario import build_scenario, mutate_records, prepare_site_dir

pytestmark = pytest.mark.parity


@pytest.fixture(scope="module")
def legacy(legacy_script_path):
    return load_legacy(legacy_script_path)


def run_both(legacy, tmp_path, scenario, runs, include_manual_master=True, with_fefo_template=True):
    old_root = prepare_site_dir(tmp_path / "old", scenario, include_manual_master, with_fefo_template)
    new_root = prepare_site_dir(tmp_path / "new", scenario, include_manual_master, with_fefo_template)
    old_http = FakeHttp(scenario.stock_count_csv)
    new_http = FakeHttp(scenario.stock_count_csv)
    for moment, records in runs:
        with freeze_time(moment):
            run_legacy(legacy, old_root, tmp_path / "s_old", records, old_http)
        with freeze_time(moment):
            run_new(new_root, tmp_path / "s_new", records, new_http)
        assert_snapshots_equal(snapshot_outputs(old_root), snapshot_outputs(new_root))
        assert old_http.posts_json() == new_http.posts_json()
    return old_http, new_http


@pytest.mark.parametrize("seed", list(range(12)))
def test_single_run_identical(legacy, tmp_path, seed):
    scenario = build_scenario(seed, FROZEN_NOW.date())
    old_http, _ = run_both(legacy, tmp_path, scenario, [(FROZEN_NOW, scenario.records)])
    assert len(old_http.posts) >= 2


@pytest.mark.parametrize("seed", [101, 202, 303, 404])
def test_multi_run_audit_identical(legacy, tmp_path, seed):
    scenario = build_scenario(seed, FROZEN_NOW.date(), n_records=600, pool_size=6)
    second = mutate_records(scenario.records, seed + 1, drop_ratio=0.02)
    third = mutate_records(second, seed + 2, drop_ratio=0.0)
    fourth = mutate_records(third, seed + 3, drop_ratio=0.3)
    runs = [
        (FROZEN_NOW, scenario.records),
        (FROZEN_NOW + datetime.timedelta(hours=1), second),
        (FROZEN_NOW + datetime.timedelta(hours=2), second),
        (FROZEN_NOW + datetime.timedelta(hours=3), third),
        (FROZEN_NOW + datetime.timedelta(hours=4), fourth),
        (FROZEN_NOW + datetime.timedelta(hours=5), fourth),
        (FROZEN_NOW + datetime.timedelta(days=1, hours=1), third),
    ]
    old_http, _ = run_both(legacy, tmp_path, scenario, runs)
    assert any(payload.get("type") == "audit" for _, payload in old_http.posts)


def test_without_manual_master_and_template(legacy, tmp_path):
    scenario = build_scenario(77, FROZEN_NOW.date())
    run_both(legacy, tmp_path, scenario, [(FROZEN_NOW, scenario.records)], include_manual_master=False,
             with_fefo_template=False)


def test_stock_count_unavailable(legacy, tmp_path):
    scenario = build_scenario(5, FROZEN_NOW.date())
    scenario.stock_count_csv = "garbage\nno,location,column\n1,2,3\n"
    run_both(legacy, tmp_path, scenario, [(FROZEN_NOW, scenario.records)])


def test_large_dataset_identical(legacy, tmp_path):
    scenario = build_scenario(999, FROZEN_NOW.date(), n_records=6000, n_stock_rows=800, pool_size=40)
    run_both(legacy, tmp_path, scenario, [(FROZEN_NOW, scenario.records),
                                          (FROZEN_NOW + datetime.timedelta(hours=1),
                                           mutate_records(scenario.records, 1000))])


def test_real_master_files_identical(legacy, tmp_path):
    import os
    import shutil
    from pathlib import Path

    from tests.support.scenario import scenario_from_real_inputs

    real_dir = os.environ.get("EFEFO_REAL_INPUT_DIR", "")
    if not real_dir or not (Path(real_dir) / "Shelflife.xlsx").exists():
        pytest.skip("Đặt EFEFO_REAL_INPUT_DIR=<thư mục chứa Shelflife.xlsx, Capacity.xlsx> để test với master thật")
    shelf, cap = Path(real_dir) / "Shelflife.xlsx", Path(real_dir) / "Capacity.xlsx"
    scenario = scenario_from_real_inputs(2024, FROZEN_NOW.date(), shelf, cap)
    for side in ("old", "new"):
        prepare_site_dir(tmp_path / side, scenario)
        shutil.copy(shelf, tmp_path / side / "Data_Input" / "Shelflife.xlsx")
        shutil.copy(cap, tmp_path / side / "Data_Input" / "Capacity.xlsx")
    old_http, new_http = FakeHttp(scenario.stock_count_csv), FakeHttp(scenario.stock_count_csv)
    for moment, records in [(FROZEN_NOW, scenario.records),
                            (FROZEN_NOW + datetime.timedelta(hours=1), mutate_records(scenario.records, 9))]:
        with freeze_time(moment):
            run_legacy(legacy, tmp_path / "old", tmp_path / "s_old", records, old_http)
        with freeze_time(moment):
            run_new(tmp_path / "new", tmp_path / "s_new", records, new_http)
        assert_snapshots_equal(snapshot_outputs(tmp_path / "old"), snapshot_outputs(tmp_path / "new"))
        assert old_http.posts_json() == new_http.posts_json()


@pytest.mark.parametrize("seed", range(4))
def test_malformed_records_identical(legacy, tmp_path, seed):
    from tests.stress.test_stress import fuzz_records

    scenario = build_scenario(seed, FROZEN_NOW.date())
    records = fuzz_records(seed, 1500, bad_sap_dates=False)
    later = fuzz_records(seed + 50, 1500, bad_sap_dates=False)
    run_both(legacy, tmp_path, scenario, [(FROZEN_NOW, records), (FROZEN_NOW + datetime.timedelta(hours=1), later)])


def test_known_legacy_crash_on_empty_sap_date_is_fixed(legacy, tmp_path):
    scenario = build_scenario(1, FROZEN_NOW.date())
    records = [dict(r) for r in scenario.records]
    records[0]["NgaySanXuat"] = "/Date()/"
    old_root = prepare_site_dir(tmp_path / "old", scenario)
    new_root = prepare_site_dir(tmp_path / "new", scenario)
    with freeze_time(FROZEN_NOW), pytest.raises(AttributeError):
        run_legacy(legacy, old_root, tmp_path / "s1", records, FakeHttp(scenario.stock_count_csv))
    with freeze_time(FROZEN_NOW):
        result = run_new(new_root, tmp_path / "s2", records, FakeHttp(scenario.stock_count_csv))
    assert result is not None and (new_root / "Inventory_Report_Full.xlsx").exists()
