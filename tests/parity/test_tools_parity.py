from __future__ import annotations

import datetime
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
from freezegun import freeze_time

from efefo.tools.fefo_history import HistoryOptions, history_report, split_list
from efefo.tools.perf_report import PerfOptions, run_perf_report
from tests.conftest import FROZEN_NOW
from tests.support.fakes import FakeHttp
from tests.support.logs import write_log_folder
from tests.support.runner_harness import run_new
from tests.support.scenario import build_scenario, mutate_records, prepare_site_dir

pytestmark = pytest.mark.parity


def legacy_tool(name: str) -> str:
    path = os.environ.get(name, "")
    if not path or not Path(path).exists():
        pytest.skip(f"Đặt {name}=<đường dẫn script gốc> để chạy test đối chứng công cụ")
    return path


def run_script(script: str, args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, script, *args], cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", env=env, check=False)


@pytest.mark.parametrize("seed, extra", [
    (1, []), (2, ["--chu-ky", "30", "--nguong-dut", "45"]), (3, ["--tu", "2026-10-21", "--den", "2026-10-22"]),
    (4, ["--chu-ky", "15", "--nguong-dut", "20"]),
])
def test_perf_report_identical(tmp_path, seed, extra, capsys):
    script = legacy_tool("EFEFO_LEGACY_PERF_SCRIPT")
    logs = write_log_folder(tmp_path / "logs", seed)
    old_out, new_out = tmp_path / "old.xlsx", tmp_path / "new.xlsx"
    result = run_script(script, ["--logs", str(logs), "--out", str(old_out), *extra], tmp_path)
    assert result.returncode == 0, result.stderr

    options = dict(zip(extra[::2], extra[1::2]))
    run_perf_report(PerfOptions(
        logs=logs, out=new_out,
        cycle_minutes=int(options.get("--chu-ky", 30)), gap_minutes=int(options.get("--nguong-dut", 45)),
        date_from=options.get("--tu"), date_to=options.get("--den"),
    ))
    printed = capsys.readouterr().out
    assert printed.replace(str(new_out), "OUT") == result.stdout.replace(str(old_out), "OUT")

    old_sheets = pd.read_excel(old_out, sheet_name=None)
    new_sheets = pd.read_excel(new_out, sheet_name=None)
    assert list(old_sheets) == list(new_sheets)
    for name in old_sheets:
        pd.testing.assert_frame_equal(old_sheets[name], new_sheets[name], obj=name)


def test_perf_report_on_real_pipeline_logs(tmp_path, capsys, caplog):
    script = legacy_tool("EFEFO_LEGACY_PERF_SCRIPT")
    caplog.set_level("INFO")
    scenario = build_scenario(4, FROZEN_NOW.date(), n_records=300)
    root = prepare_site_dir(tmp_path / "site", scenario)
    records = scenario.records
    for hour in range(6):
        with freeze_time(FROZEN_NOW + datetime.timedelta(minutes=30 * hour)):
            run_new(root, tmp_path / "s", records if hour != 3 else [], FakeHttp(scenario.stock_count_csv))
    old_out, new_out = tmp_path / "old.xlsx", tmp_path / "new.xlsx"
    result = run_script(script, ["--logs", str(root / "logs"), "--out", str(old_out)], tmp_path)
    assert result.returncode == 0, result.stderr
    run_perf_report(PerfOptions(logs=root / "logs", out=new_out))
    capsys.readouterr()
    detail = pd.read_excel(new_out, sheet_name="Chi tiết từng lượt")
    assert detail["Kết quả"].tolist() == ["Hoàn tất"] * 3 + ["Có bước lỗi"] + ["Hoàn tất"] * 2
    for name, frame in pd.read_excel(old_out, sheet_name=None).items():
        pd.testing.assert_frame_equal(frame, pd.read_excel(new_out, sheet_name=name), obj=name)


@pytest.fixture(scope="module")
def audit_history(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("hist")
    scenario = build_scenario(202, FROZEN_NOW.date(), n_records=700, pool_size=5)
    root = prepare_site_dir(tmp_path / "site", scenario)
    records = scenario.records
    for step in range(14):
        if step in (5, 9):
            continue
        records = mutate_records(records, step, drop_ratio=0.12 if step == 7 else 0.02)
        with freeze_time(FROZEN_NOW + datetime.timedelta(minutes=30 * step)):
            run_new(root, tmp_path / "s", records, FakeHttp(scenario.stock_count_csv))
    (root / "audit" / "history" / "20261019_999999.json.gz").write_bytes(b"garbage")
    (root / "audit" / "history" / "20261019_093000.json.gz").write_bytes(b"not gzip")
    return root / "audit" / "history", scenario, None


TIE_PREFIXES = ("     • Lô MỚI xuất hiện ở phía trước (già hơn hoặc bằng): ", "     • Lô phía trước đã MẤT so với lượt trước: ")


def normalize_ties(text: str) -> str:
    lines = []
    for line in text.split("\n"):
        for prefix in TIE_PREFIXES:
            if line.startswith(prefix):
                line = prefix + "; ".join(sorted(line[len(prefix):].split("; ")))
        lines.append(line)
    return "\n".join(lines)


def pick_targets(folder: Path) -> list[tuple[str, str]]:
    import gzip
    import json

    last = sorted(folder.glob("2026*_0*.json.gz"))[-3]
    with gzip.open(last, "rt", encoding="utf-8") as handle:
        rows = json.load(handle)["fefo_rows"]
    frame = pd.DataFrame(rows)
    counts = frame.groupby("Material").size().sort_values(ascending=False)
    targets = []
    for material in counts.index[:3]:
        part = frame[frame["Material"] == material]
        for loc in part["Normalized_Location"].astype(str).str.rstrip("*").unique()[::3][:3]:
            targets.append((str(material), loc))
    targets.append((str(counts.index[0]), "ZZ99"))
    return targets


@pytest.mark.parametrize("extra", [
    [], ["--all"], ["--chi-tiet"], ["--all", "--chi-tiet"], ["--date", "2026-10-19"],
    ["--from", "2026-10-19 09:00", "--to", "2026-10-19 12:00", "--chi-tiet"], ["--date", "2030-01-01"],
])
def test_fefo_history_identical(audit_history, tmp_path, extra):
    script = legacy_tool("EFEFO_LEGACY_HISTORY_SCRIPT")
    folder, _, _ = audit_history
    targets = pick_targets(folder)
    mats = ",".join(dict.fromkeys(m for m, _ in targets))
    locs = ",".join(dict.fromkeys(loc.lower() + "*" for _, loc in targets))
    result = run_script(script, ["--dir", str(folder), "--mat", mats, "--loc", locs, *extra], tmp_path)
    assert result.returncode == 0, result.stderr

    options = {k: v for k, v in zip(extra, extra[1:] + [None]) if k in ("--date", "--from", "--to")}
    text = history_report(HistoryOptions(
        folder=folder, materials=split_list(mats), locations=split_list(locs, upper=True),
        date=options.get("--date"), time_from=options.get("--from"), time_to=options.get("--to"),
        show_all="--all" in extra, detail="--chi-tiet" in extra,
    ))
    expected = result.stdout.rstrip("\n")
    if text is None:
        assert expected == "Không có snapshot nào trong khoảng thời gian đã chọn."
    else:
        assert normalize_ties(text) == normalize_ties(expected)
        assert "KẾT QUẢ" in text
