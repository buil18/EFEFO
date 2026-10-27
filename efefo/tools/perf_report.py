from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

LOG_PATTERN = "sap_inventory.log*"
RE_TS = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[(\w+)\] ?(.*)")
RE_ODATA = re.compile(r"Tải OData xong: (\d+) bản ghi \| tải tiếp do lỗi: (\d+) lần \| đăng nhập lại: (\d+) lần")
RE_STEP = re.compile(r"^\s+(sap|report|\w+)\s{2,}(THÀNH CÔNG|\S+(?: \S+)?)\s+([\d.]+)s")
RE_FILE_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})$")
START = "Đã bật ghi log file"
DONE = "Tất cả các bước đã hoàn tất"
RESULT_OK = "Hoàn tất"
RESULT_STEP_FAILED = "Có bước lỗi"
RESULT_PARTIAL = "Dở dang (không có dòng tổng kết)"
DEFAULT_OUTPUT = "Bao_cao_hieu_nang_PAD.xlsx"
DATA_DROP_RATIO = 0.95


@dataclass
class PerfOptions:
    logs: Path
    out: Path
    cycle_minutes: int = 30
    gap_minutes: int = 45
    date_from: str | None = None
    date_to: str | None = None


class PerfReportError(Exception):
    pass


def read_logs(folder: Path) -> tuple[list[str], int]:
    files = list(folder.glob(LOG_PATTERN))

    def key(path: Path):
        m = RE_FILE_DATE.search(path.name)
        return (m.group(1) if m else "9999-99-99", path.name)

    lines: list[str] = []
    for path in sorted(files, key=key):
        lines += path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines, len(files)


def split_runs(lines: list[str]) -> list[dict]:
    runs, cur = [], None
    for raw in lines:
        m = RE_TS.match(raw)
        if m and START in m.group(3):
            cur = {"lines": []}
            runs.append(cur)
        if cur is None:
            continue
        if m:
            cur["lines"].append((dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"), m.group(2), m.group(3)))
        elif cur["lines"]:
            t, lv, tx = cur["lines"][-1]
            cur["lines"][-1] = (t, lv, tx + " " + raw.strip())
    return runs


def analyze_run(run: dict) -> dict:
    lines = run["lines"]
    r = {"Bắt đầu": lines[0][0], "Kết thúc": lines[-1][0]}
    r["Thời lượng (giây)"] = int((r["Kết thúc"] - r["Bắt đầu"]).total_seconds())
    r["Số dòng SAP"] = None
    r["Tải lại do lỗi"] = 0
    r["Đăng nhập lại"] = 0
    r["Cảnh báo"] = sum(1 for _, lv, _ in lines if lv == "WARNING")
    r["Lỗi"] = sum(1 for _, lv, _ in lines if lv == "ERROR")
    failed_steps, finished, notes, odata_time = [], False, [], None
    for t, lv, tx in lines:
        m = RE_ODATA.search(tx)
        if m:
            r["Số dòng SAP"], r["Tải lại do lỗi"], r["Đăng nhập lại"] = map(int, m.groups())
            odata_time = t
        if DONE in tx:
            finished = True
        m = RE_STEP.match(" " + tx) if tx.startswith("  ") else None
        if m and m.group(2) != "THÀNH CÔNG":
            failed_steps.append(f"{m.group(1)}: {m.group(2)}")
        if lv == "ERROR":
            notes.append(tx[:120])
        elif "Lỗi cập nhật" in tx or "Lỗi tải" in tx:
            notes.append(tx[:120])
        elif "Tải dở dang" in tx:
            notes.append("Tải dở dang, phải tải tiếp")
        elif "thiếu GOOGLE_APPS_SCRIPT" in tx or "Chưa cấu hình GOOGLE_APPS_SCRIPT" in tx:
            notes.append("Thiếu cấu hình Google Script (có thể chạy thử)")
    if finished and not failed_steps:
        r["Kết quả"] = RESULT_OK
    elif failed_steps:
        r["Kết quả"] = RESULT_STEP_FAILED
    else:
        r["Kết quả"] = RESULT_PARTIAL
    r["Dữ liệu mới lúc"] = odata_time if r["Số dòng SAP"] else None
    r["Ghi chú"] = " | ".join(dict.fromkeys(failed_steps + notes))[:300]
    return r


def gaps_and_streaks(ok: pd.DataFrame, opts: PerfOptions) -> tuple[pd.DataFrame, pd.DataFrame]:
    gaps, streaks = [], []
    s0 = 0
    for i in range(1, len(ok)):
        d = (ok.loc[i, "Bắt đầu"] - ok.loc[i - 1, "Bắt đầu"]).total_seconds() / 60
        if d > opts.gap_minutes:
            gaps.append({"Lượt thành công trước": ok.loc[i - 1, "Bắt đầu"], "Lượt thành công sau": ok.loc[i, "Bắt đầu"],
                         "Dữ liệu cũ (phút)": round(d),
                         "Ước tính số lượt bị mất": max(1, round(d / opts.cycle_minutes) - 1)})
            streaks.append((s0, i - 1))
            s0 = i
    if len(ok):
        streaks.append((s0, len(ok) - 1))
    gaps_df = pd.DataFrame(gaps, columns=["Lượt thành công trước", "Lượt thành công sau", "Dữ liệu cũ (phút)",
                                          "Ước tính số lượt bị mất"])
    streak_df = pd.DataFrame([
        {"Từ": ok.loc[a, "Bắt đầu"], "Đến": ok.loc[b, "Bắt đầu"], "Số lượt liên tục": b - a + 1,
         "Thời gian (giờ)": round((ok.loc[b, "Bắt đầu"] - ok.loc[a, "Bắt đầu"]).total_seconds() / 3600, 1)}
        for a, b in streaks
    ]).sort_values("Thời gian (giờ)", ascending=False) if streaks else pd.DataFrame()
    return gaps_df, streak_df


def by_day(df: pd.DataFrame, opts: PerfOptions) -> pd.DataFrame:
    rows = []
    for day, g in df.groupby("Ngày"):
        o = g[g["Kết quả"] == RESULT_OK]
        span = (g["Bắt đầu"].max() - g["Bắt đầu"].min()).total_seconds() / 60
        expected = max(len(g), int(span // opts.cycle_minutes) + 1)
        longest = 0
        if len(o) > 1:
            longest = int(max((b - a).total_seconds() / 60 for a, b in zip(o["Bắt đầu"], o["Bắt đầu"].iloc[1:])))
        rows.append({"Ngày": day, "Lượt chạy": len(g), "Hoàn tất": len(o), "Lỗi/dở dang": len(g) - len(o),
                     "Tỷ lệ hoàn tất (%)": round(100 * len(o) / len(g), 1),
                     "Khoảng cách dài nhất giữa 2 lượt hoàn tất (phút)": longest,
                     "Thời lượng TB (giây)": int(g["Thời lượng (giây)"].mean()),
                     "Thời lượng dài nhất (giây)": int(g["Thời lượng (giây)"].max()),
                     "Số lượt phải tải lại/đăng nhập lại": int(((g["Tải lại do lỗi"] > 0) | (g["Đăng nhập lại"] > 0)).sum()),
                     "Lượt mong đợi (theo chu kỳ)": expected})
    return pd.DataFrame(rows)


def by_hour(df: pd.DataFrame, gaps: pd.DataFrame) -> pd.DataFrame:
    hours = df.groupby("Giờ").agg(Lượt=("Kết quả", "size"), Hỏng=("Kết quả", lambda s: int((s != RESULT_OK).sum())),
                                  TB_giây=("Thời lượng (giây)", "mean")).reset_index()
    hours["Thời lượng TB (giây)"] = hours.pop("TB_giây").round().astype(int)
    hours.columns = ["Giờ trong ngày", "Số lượt", "Lượt lỗi/dở dang", "Thời lượng TB (giây)"]
    gap_hours = pd.Series([g.hour for g in gaps["Lượt thành công trước"]]).value_counts() if len(gaps) else {}
    hours["Số lần bắt đầu khoảng đứt"] = hours["Giờ trong ngày"].map(gap_hours).fillna(0).astype(int)
    return hours


def data_quality(ok: pd.DataFrame) -> pd.DataFrame:
    q = ok.dropna(subset=["Số dòng SAP"]).copy()
    if len(q):
        med = q["Số dòng SAP"].median()
        q["Chênh so với trung vị (%)"] = ((q["Số dòng SAP"] / med - 1) * 100).round(1)
        q["Bất thường"] = q["Số dòng SAP"] < med * DATA_DROP_RATIO
        q = q[["Bắt đầu", "Số dòng SAP", "Chênh so với trung vị (%)", "Bất thường", "Tải lại do lỗi", "Đăng nhập lại"]]
    return q


def build_report(lines: list[str], n_files: int, opts: PerfOptions) -> tuple[dict[str, pd.DataFrame], list[tuple]]:
    if not lines:
        raise PerfReportError("Không đọc được dòng log nào. Kiểm tra --logs.")
    df = pd.DataFrame([analyze_run(r) for r in split_runs(lines)])
    if df.empty:
        raise PerfReportError("Không tìm thấy lượt chạy nào.")
    if opts.date_from:
        df = df[df["Bắt đầu"] >= pd.Timestamp(opts.date_from)]
    if opts.date_to:
        df = df[df["Bắt đầu"] < pd.Timestamp(opts.date_to) + pd.Timedelta(days=1)]
    df = df.sort_values("Bắt đầu").reset_index(drop=True)
    df["Ngày"] = df["Bắt đầu"].dt.date
    df["Giờ"] = df["Bắt đầu"].dt.hour
    ok = df[df["Kết quả"] == RESULT_OK].reset_index(drop=True)

    gaps, streaks = gaps_and_streaks(ok, opts)
    quality = data_quality(ok)
    failed = df[df["Kết quả"] != RESULT_OK][["Bắt đầu", "Kết thúc", "Kết quả", "Thời lượng (giây)", "Ghi chú"]]
    warnings = df[(df["Kết quả"] == RESULT_OK) & (df["Ghi chú"] != "")][["Bắt đầu", "Ghi chú"]]

    summary = [
        ("Khoảng thời gian trong log", f"{df['Bắt đầu'].min():%d/%m/%Y %H:%M} → {df['Bắt đầu'].max():%d/%m/%Y %H:%M}"),
        ("Số file log đã đọc", n_files), ("Tổng số lượt chạy", len(df)), ("Lượt hoàn tất", len(ok)),
        ("Lượt lỗi / dở dang", len(df) - len(ok)), ("Tỷ lệ hoàn tất (%)", round(100 * len(ok) / len(df), 1)),
        (f"Số khoảng đứt (> {opts.gap_minutes} phút không có dữ liệu mới)", len(gaps)),
        ("Khoảng đứt dài nhất (phút)", int(gaps["Dữ liệu cũ (phút)"].max()) if len(gaps) else 0),
        ("Chuỗi chạy liên tục dài nhất (giờ)", float(streaks["Thời gian (giờ)"].max()) if len(streaks) else 0),
        ("Thời lượng TB mỗi lượt (giây)", int(df["Thời lượng (giây)"].mean())),
        ("Thời lượng dài nhất (giây)", int(df["Thời lượng (giây)"].max())),
        ("Lượt phải tải lại / đăng nhập lại", int(((df["Tải lại do lỗi"] > 0) | (df["Đăng nhập lại"] > 0)).sum())),
    ]
    sheets = {
        "Tổng quan": pd.DataFrame(summary, columns=["Chỉ số", "Giá trị"]),
        "Theo ngày": by_day(df, opts),
        "Khoảng đứt": gaps,
        "Chạy liên tục": streaks,
        "Lượt lỗi": failed,
        "Theo giờ": by_hour(df, gaps),
        "Chất lượng dữ liệu": quality if len(quality) else pd.DataFrame(),
        "Cảnh báo trong lượt OK": warnings,
        "Chi tiết từng lượt": df.drop(columns=["Ngày", "Giờ"]),
    }
    return sheets, summary


def write_excel(sheets: dict[str, pd.DataFrame], out: Path) -> None:
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
        for ws in writer.book.worksheets:
            ws.freeze_panes = "A2"
            for col in ws.columns:
                width = max(len(str(c.value)) if c.value is not None else 0 for c in col)
                ws.column_dimensions[col[0].column_letter].width = min(max(12, width + 2), 60)
            for row in ws.iter_rows(min_row=2):
                for c in row:
                    if isinstance(c.value, (dt.datetime, pd.Timestamp)):
                        c.number_format = "dd/mm/yyyy hh:mm"


def run_perf_report(opts: PerfOptions) -> list[tuple]:
    lines, n_files = read_logs(opts.logs)
    sheets, summary = build_report(lines, n_files, opts)
    write_excel(sheets, opts.out)
    print(f"Xong: {opts.out}")
    for key, value in summary:
        print(f"  {key}: {value}")
    return summary
