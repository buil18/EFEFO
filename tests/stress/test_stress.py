from __future__ import annotations

import datetime
import json
import random
import time

import pytest
from freezegun import freeze_time

from tests.conftest import FROZEN_NOW
from tests.support.fakes import FakeHttp
from tests.support.runner_harness import run_new
from tests.support.scenario import build_scenario, mutate_records, prepare_site_dir

pytestmark = pytest.mark.stress

REAL_CLOCK = time.perf_counter


def timed_run(tmp_path, n_records, seed=1):
    scenario = build_scenario(seed, FROZEN_NOW.date(), n_records=n_records, n_stock_rows=max(n_records // 10, 50),
                              pool_size=80)
    root = prepare_site_dir(tmp_path / f"r{n_records}", scenario)
    start = REAL_CLOCK()
    result = run_new(root, tmp_path / f"s{n_records}", scenario.records, FakeHttp(scenario.stock_count_csv))
    return REAL_CLOCK() - start, result


def test_perf_20k_records_within_budget(tmp_path):
    elapsed, result = timed_run(tmp_path, 20_000)
    print(f"\n20k records: {elapsed:.1f}s, {len(result.summary)} dòng FEFO")
    assert elapsed < 90


def test_perf_scales_linearly(tmp_path):
    small, _ = timed_run(tmp_path, 4_000, seed=2)
    large, _ = timed_run(tmp_path, 16_000, seed=2)
    print(f"\n4k: {small:.1f}s  16k: {large:.1f}s  ratio {large / small:.1f}")
    assert large / small < 7


def fuzz_records(seed: int, n: int, bad_sap_dates: bool = True) -> list[dict]:
    rng = random.Random(seed)
    junk = [None, "", " ", "abc", "/Date(abc)/", "/Date()/", "/Date(-86400000)/", "\u2211", "-1", "1e309",
            "NaN", "1,5", "\u200b"]
    if not bad_sap_dates:
        junk = [j for j in junk if not (isinstance(j, str) and j.startswith("/Date(") and not j[6:-2].lstrip("-").isdigit())]
    key_fields = {"Material", "EWMStorageBin"}
    base = build_scenario(seed, FROZEN_NOW.date(), n_records=n).records
    for record in base:
        for key in list(record):
            if key == "__metadata" or key in key_fields:
                continue
            if rng.random() < 0.04:
                record[key] = rng.choice(junk)
        if rng.random() < 0.02:
            record["Material"] = rng.choice(["10128309.0", " 10128309 ", "", None, "ABC"])
        if rng.random() < 0.02:
            bins = ["HM 𝔇01", "hmk\t12", "*", "LOOSE", None] + (["HMPKGHMPKG"] if bad_sap_dates else [])
            record["EWMStorageBin"] = rng.choice(bins)
    return base


@pytest.mark.parametrize("seed", range(8))
def test_fuzz_malformed_records_never_crash(tmp_path, seed):
    records = fuzz_records(seed, 1500)
    scenario = build_scenario(seed, FROZEN_NOW.date())
    root = prepare_site_dir(tmp_path / "r", scenario)
    with freeze_time(FROZEN_NOW):
        result = run_new(root, tmp_path / "s", records, FakeHttp(scenario.stock_count_csv))
    assert result is not None
    assert (root / "Inventory_Report_Full.xlsx").exists()


@pytest.mark.parametrize("csv_text", [
    "", "\n\n", "a,b\n1,2", "Location\nD01", "Location,Item\n,\nD01,", "x\nLocation,Item,STATUS\nD01,1,Blocked",
    "Location,Item,PRD date,Qty (PL)\n" + "D01,10128309,31/02/2026,abc\n" * 50,
])
def test_fuzz_stock_count_sheet(tmp_path, csv_text):
    scenario = build_scenario(3, FROZEN_NOW.date())
    root = prepare_site_dir(tmp_path / "r", scenario)
    with freeze_time(FROZEN_NOW):
        result = run_new(root, tmp_path / "s", scenario.records, FakeHttp(csv_text))
    assert result is not None and result.summary is not None


def test_soak_48_hourly_runs(tmp_path):
    scenario = build_scenario(55, FROZEN_NOW.date(), n_records=800, pool_size=8)
    root = prepare_site_dir(tmp_path / "r", scenario)
    records = scenario.records
    durations = []
    events = 0
    for hour in range(48):
        records = mutate_records(records, hour, drop_ratio=0.01) if hour % 3 else records
        http = FakeHttp(scenario.stock_count_csv)
        start = REAL_CLOCK()
        with freeze_time(FROZEN_NOW + datetime.timedelta(hours=hour)):
            run_new(root, tmp_path / "s", records, http)
        durations.append(REAL_CLOCK() - start)
        events += sum(len(p["rows"]) for _, p in http.posts if p.get("type") == "audit")
    state = json.loads((root / "audit" / "audit_state.json").read_text(encoding="utf-8"))
    assert state["record_count"] > 0 and isinstance(state["pending"], dict)
    log_lines = (root / "audit" / "audit_log.jsonl").read_text(encoding="utf-8").splitlines()
    assert all(json.loads(line)["kind"] in {"event", "transient"} for line in log_lines)
    assert len(list((root / "Daily_Reports").glob("*.xlsx"))) == 3
    assert max(durations[1:]) < 4 * (sum(durations[1:]) / len(durations[1:]))
    print(f"\n48 lượt: trung bình {sum(durations) / 48:.2f}s/lượt, {events} sự kiện audit")
