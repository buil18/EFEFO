from __future__ import annotations

import datetime as dt
import gzip
import json

import pandas as pd
import pytest
from freezegun import freeze_time

from efefo.tools.fefo_history import HistoryError, HistoryOptions, history_report, parse_user_time, split_list
from efefo.tools.perf_report import PerfOptions, PerfReportError, analyze_run, run_perf_report, split_runs
from tests.conftest import FROZEN_NOW
from tests.support.fakes import FakeHttp
from tests.support.logs import write_log_folder
from tests.support.runner_harness import run_new
from tests.support.scenario import build_scenario, prepare_site_dir

LOG = """2026-10-20 08:00:00 [INFO] Đã bật ghi log file: x
2026-10-20 08:01:00 [INFO] Tải OData xong: 5200 bản ghi | tải tiếp do lỗi: 1 lần | đăng nhập lại: 0 lần
2026-10-20 08:02:00 [INFO]   sap       THÀNH CÔNG    60.0s
2026-10-20 08:02:00 [INFO]   report    THÀNH CÔNG    20.0s
2026-10-20 08:02:00 [INFO] Tất cả các bước đã hoàn tất
2026-10-20 08:30:00 [INFO] Đã bật ghi log file: x
2026-10-20 08:31:00 [ERROR] Lỗi không mong đợi
Traceback line
2026-10-20 08:31:00 [INFO]   sap       THẤT BẠI      60.0s
2026-10-20 09:00:00 [INFO] Đã bật ghi log file: x
2026-10-20 09:00:30 [WARNING] Tải dở dang (đã có 10 bản ghi).
"""


def test_perf_run_classification():
    runs = [analyze_run(r) for r in split_runs(LOG.splitlines())]
    assert [r["Kết quả"] for r in runs] == ["Hoàn tất", "Có bước lỗi", "Dở dang (không có dòng tổng kết)"]
    assert runs[0]["Số dòng SAP"] == 5200 and runs[0]["Tải lại do lỗi"] == 1 and runs[0]["Thời lượng (giây)"] == 120
    assert "sap: THẤT BẠI" in runs[1]["Ghi chú"] and "Traceback line" in runs[1]["Ghi chú"]
    assert runs[2]["Ghi chú"] == "Tải dở dang, phải tải tiếp"


def test_perf_report_workbook(tmp_path, capsys):
    logs = write_log_folder(tmp_path / "logs", 9, days=3)
    out = tmp_path / "r.xlsx"
    summary = dict(run_perf_report(PerfOptions(logs=logs, out=out)))
    sheets = pd.read_excel(out, sheet_name=None)
    assert list(sheets) == ["Tổng quan", "Theo ngày", "Khoảng đứt", "Chạy liên tục", "Lượt lỗi", "Theo giờ",
                            "Chất lượng dữ liệu", "Cảnh báo trong lượt OK", "Chi tiết từng lượt"]
    assert summary["Số file log đã đọc"] == 3
    detail = sheets["Chi tiết từng lượt"]
    assert summary["Tổng số lượt chạy"] == len(detail)
    assert summary["Lượt hoàn tất"] == int((detail["Kết quả"] == "Hoàn tất").sum())
    assert "Xong:" in capsys.readouterr().out


def test_perf_report_errors(tmp_path):
    with pytest.raises(PerfReportError, match="Không đọc được"):
        run_perf_report(PerfOptions(logs=tmp_path, out=tmp_path / "x.xlsx"))
    (tmp_path / "sap_inventory.log").write_text("no runs here\n", encoding="utf-8")
    with pytest.raises(PerfReportError, match="Không tìm thấy"):
        run_perf_report(PerfOptions(logs=tmp_path, out=tmp_path / "x.xlsx"))


def test_runner_writes_step_summary_for_perf_report(tmp_path, caplog, capsys):
    caplog.set_level("INFO")
    scenario = build_scenario(2, FROZEN_NOW.date(), n_records=200)
    root = prepare_site_dir(tmp_path / "site", scenario)
    for i, records in enumerate([scenario.records, [], scenario.records]):
        with freeze_time(FROZEN_NOW + dt.timedelta(minutes=30 * i)):
            run_new(root, tmp_path / "s", records, FakeHttp(scenario.stock_count_csv))
    (root / ".sap_inventory.lock").write_text("busy")
    with freeze_time(FROZEN_NOW + dt.timedelta(minutes=90)):
        run_new(root, tmp_path / "s", scenario.records, FakeHttp(scenario.stock_count_csv))
    run_perf_report(PerfOptions(logs=root / "logs", out=tmp_path / "p.xlsx"))
    detail = pd.read_excel(tmp_path / "p.xlsx", sheet_name="Chi tiết từng lượt")
    assert detail["Kết quả"].tolist() == ["Hoàn tất", "Có bước lỗi", "Hoàn tất", "Có bước lỗi"]
    assert detail["Ghi chú"].iloc[3].startswith("sap: BỎ QUA")


def snapshot(folder, stamp, rows, records=1000, suspect=False):
    payload = {"meta": {"record_count": records, "suspect": suspect}, "fefo_rows": rows}
    with gzip.open(folder / f"{stamp}.json.gz", "wt", encoding="utf-8") as handle:
        json.dump(payload, handle)


def row(loc, pct, qty=200, excluded=False, prd="2026-10-01"):
    return {"Material": "1", "Normalized_Location": loc, "PRD_date": prd, "phantram_shelf_life": pct,
            "Total_Quantity": qty, "_manual": loc.endswith("*"), "_excluded": excluded}


def test_history_states_and_explanations(tmp_path):
    shown = [row(f"D0{i}", 0.5 + i / 100) for i in range(1, 7)]
    snapshot(tmp_path, "20261020_080000", shown + [row("E23", 0.6)])
    snapshot(tmp_path, "20261020_083000", [row("A01", 0.1)] + shown + [row("E23", 0.6)])
    snapshot(tmp_path, "20261020_090000", shown, records=900)
    snapshot(tmp_path, "20261020_110000", shown + [row("E23", 0.6, excluded=True)])
    snapshot(tmp_path, "20261020_113000", shown + [row("E23", 0.4)], suspect=True)
    text = history_report(HistoryOptions(folder=tmp_path, materials=["1"], locations=["E23"], detail=True,
                                         show_all=True))
    assert "20/10 08:00 → 20/10 08:30 (2 lượt): ẨN (hạng > 6, tablet không hiện), hạng 7–8" in text
    assert "20/10 11:30 → 20/10 11:30 (1 lượt): HIỆN trên E-FEFO, hạng 1" in text
    assert "Lô MỚI xuất hiện ở phía trước (già hơn hoặc bằng): A01" in text
    assert "KHÔNG CÓ trong bảng FEFO" in text and "BỊ LOẠI theo tên vị trí" in text
    assert "bản ghi SAP 1000 → 900" in text
    assert "Thiếu lượt chạy giữa 20/10 09:00 và 20/10 11:00 (120 phút)" in text
    assert "nghi tải thiếu" in text
    assert "--- ranh giới hiển thị ---" in text


def test_history_inputs(tmp_path):
    assert split_list(" e23*, e54 ,", upper=True) == ["E23", "E54"]
    assert parse_user_time("21/10/2026", end_of_day=True) == dt.datetime(2026, 10, 21, 23, 59, 59)
    with pytest.raises(HistoryError):
        parse_user_time("hôm qua")
    with pytest.raises(HistoryError):
        history_report(HistoryOptions(folder=tmp_path / "missing", materials=["1"], locations=["A"]))
    assert history_report(HistoryOptions(folder=tmp_path, materials=["1"], locations=["A"])) is None
