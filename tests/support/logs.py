from __future__ import annotations

import datetime as dt
import random
from pathlib import Path


def run_lines(start: dt.datetime, kind: str, rng: random.Random) -> list[str]:
    t = start
    out = []

    def add(level, text, seconds=1):
        nonlocal t
        t += dt.timedelta(seconds=seconds)
        out.append(f"{t:%Y-%m-%d %H:%M:%S} [{level}] {text}")

    add("INFO", "Đã bật ghi log file: C:\\out\\logs\\sap_inventory.log", 0)
    add("INFO", "Đang tải trang 1 ...", rng.randint(5, 20))
    if kind == "partial":
        add("WARNING", "Tải dở dang (đã có 1000 bản ghi). Chờ 5s rồi tải tiếp từ chỗ dừng (lần 1/3).", 30)
        return out
    retries = 1 if kind == "retry" else 0
    relog = 1 if rng.random() < 0.1 else 0
    records = rng.choice([5200, 5210, 5190, 4700]) if kind != "fail" else 0
    if kind != "fail":
        add("INFO", f"Tải OData xong: {records} bản ghi | tải tiếp do lỗi: {retries} lần | đăng nhập lại: {relog} lần",
            rng.randint(30, 200))
    if kind == "warn":
        add("WARNING", "Lỗi cập nhật vị trí trống lên Google Sheet: timeout")
    if kind == "noscript":
        add("WARNING", "Chưa cấu hình GOOGLE_APPS_SCRIPT_URL — bỏ qua gửi FEFO lên Google Sheet.")
    if kind == "fail":
        add("ERROR", "Lỗi không mong đợi", 40)
        out.append("Traceback (most recent call last):")
        out.append('  File "x.py", line 1, in <module>')
        out.append("RuntimeError: boom")
    add("INFO", "Tổng kết lượt chạy:", rng.randint(10, 60))
    add("INFO", f"  sap       {'THÀNH CÔNG' if kind != 'fail' else 'THẤT BẠI'}    {rng.uniform(30, 250):.1f}s", 0)
    if kind != "fail":
        add("INFO", f"  report    THÀNH CÔNG    {rng.uniform(5, 40):.1f}s", 0)
        add("INFO", "Tất cả các bước đã hoàn tất", 0)
    else:
        add("WARNING", "Có bước chưa hoàn tất", 0)
    return out


def write_log_folder(folder: Path, seed: int, days: int = 4, cycle_minutes: int = 30,
                     start: dt.datetime = dt.datetime(2026, 10, 20, 0, 5)) -> Path:
    rng = random.Random(seed)
    folder.mkdir(parents=True, exist_ok=True)
    by_day: dict[dt.date, list[str]] = {}
    t = start
    end = start + dt.timedelta(days=days)
    while t < end:
        roll = rng.random()
        kind = ("ok" if roll < 0.75 else "retry" if roll < 0.8 else "warn" if roll < 0.85 else
                "noscript" if roll < 0.88 else "fail" if roll < 0.94 else "partial")
        if rng.random() < 0.04:
            t += dt.timedelta(minutes=rng.choice([60, 90, 180]))
        by_day.setdefault(t.date(), []).extend(run_lines(t, kind, rng))
        t += dt.timedelta(minutes=cycle_minutes, seconds=rng.randint(-30, 30))
    days_sorted = sorted(by_day)
    folder.joinpath("README.txt").write_text("not a log", encoding="utf-8")
    for day in days_sorted[:-1]:
        (folder / f"sap_inventory.log.{day:%Y-%m-%d}").write_text("\n".join(by_day[day]) + "\n", encoding="utf-8")
    (folder / "sap_inventory.log").write_text("noise before first run\n" + "\n".join(by_day[days_sorted[-1]]) + "\n",
                                              encoding="utf-8")
    return folder
