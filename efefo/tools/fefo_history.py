from __future__ import annotations

import datetime as dt
import gzip
import json
import sys
from dataclasses import dataclass
from pathlib import Path

STATE_SHOWN, STATE_HIDDEN, STATE_ABSENT, STATE_EXCLUDED = "HIỆN", "ẨN", "KHÔNG CÓ", "LOẠI"


@dataclass
class HistoryOptions:
    folder: Path
    materials: list[str]
    locations: list[str]
    date: str | None = None
    time_from: str | None = None
    time_to: str | None = None
    show_all: bool = False
    detail: bool = False
    out: Path | None = None
    max_shown: int = 6
    drop_warn_ratio: float = 0.05
    gap_warn_minutes: int = 45


class HistoryError(Exception):
    pass


def state_text(max_shown: int) -> dict[str, str]:
    return {
        STATE_SHOWN: "HIỆN trên E-FEFO",
        STATE_HIDDEN: "ẨN (hạng > %d, tablet không hiện)" % max_shown,
        STATE_ABSENT: "KHÔNG CÓ trong bảng FEFO (hết hàng SAP / vị trí Blocked / lô sản xuất hôm nay)",
        STATE_EXCLUDED: "BỊ LOẠI theo tên vị trí (K / H / LOOSE)",
    }


def parse_stamp(path: Path) -> dt.datetime | None:
    try:
        return dt.datetime.strptime(path.name[:15], "%Y%m%d_%H%M%S")
    except ValueError:
        return None


def parse_user_time(text: str, end_of_day: bool = False) -> dt.datetime:
    for fmt in ("%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M"):
        try:
            return dt.datetime.strptime(text.strip(), fmt)
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            day = dt.datetime.strptime(text.strip(), fmt)
            return day + dt.timedelta(days=1, seconds=-1) if end_of_day else day
        except ValueError:
            pass
    raise HistoryError(f"Không hiểu định dạng thời gian: {text!r} (dùng 2026-10-21 hoặc \"2026-10-21 08:00\")")


def list_snapshots(folder: Path) -> list[tuple[dt.datetime, Path]]:
    items = [(parse_stamp(p), p) for p in folder.glob("*.json.gz")]
    return sorted((t, p) for t, p in items if t is not None)


def read_snapshot(path: Path) -> dict | None:
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, EOFError, ValueError) as exc:
        print(f"  [bỏ qua {path.name}: không đọc được ({exc})]", file=sys.stderr)
        return None


def clean_loc(value) -> str:
    return str(value or "").strip().rstrip("*").upper()


def material_lots(data: dict, material: str) -> tuple[list[dict], list[dict]]:
    shown, excluded = [], []
    for row in data.get("fefo_rows", []):
        if str(row.get("Material", "")).strip() != material:
            continue
        lot = {
            "loc": clean_loc(row.get("Normalized_Location")),
            "prd": str(row.get("PRD_date", ""))[:10],
            "pct": float(row.get("phantram_shelf_life") or 0),
            "qty": row.get("Total_Quantity"),
            "manual": bool(row.get("_manual")),
        }
        lot["key"] = f'{lot["loc"]}|{lot["prd"]}'
        (excluded if row.get("_excluded") else shown).append(lot)
    shown.sort(key=lambda lot: lot["pct"])
    return shown, excluded


def qty_text(qty) -> str:
    return f"{qty:,.0f}".replace(",", ".") if isinstance(qty, (int, float)) else "?"


def describe_lot(lot: dict) -> str:
    star = "*" if lot["manual"] else ""
    return f'{lot["loc"]}{star} (SX {lot["prd"]}, {lot["pct"] * 100:.2f}%, SL {qty_text(lot["qty"])})'


def observe(data: dict, material: str, location: str, max_shown: int) -> dict:
    shown, excluded = material_lots(data, material)
    mine = [(rank, lot) for rank, lot in enumerate(shown, 1) if lot["loc"] == location]
    if mine:
        best_rank, best_lot = min(mine, key=lambda item: item[0])
        state = STATE_SHOWN if best_rank <= max_shown else STATE_HIDDEN
    elif any(lot["loc"] == location for lot in excluded):
        best_rank, best_lot, state = None, None, STATE_EXCLUDED
    else:
        best_rank, best_lot, state = None, None, STATE_ABSENT
    meta = data.get("meta", {})
    return {
        "state": state, "rank": best_rank, "lot": best_lot, "lots": shown,
        "keys": {lot["key"] for lot in shown},
        "records": meta.get("record_count"), "suspect": bool(meta.get("suspect")),
    }


def explain_change(prev: dict, cur: dict) -> list[str]:
    lines: list[str] = []
    if cur["state"] == STATE_EXCLUDED:
        return ["Vị trí thuộc nhóm K / H / LOOSE nên không lên tablet (kiểm tra tên vị trí có bị đổi không)."]
    if cur["state"] == STATE_ABSENT:
        return ["Vị trí không còn lô nào của mã này trong bảng FEFO: SAP hết hàng, vị trí bị Blocked, "
                "hoặc lô vừa sản xuất hôm nay."]
    if prev["state"] in (STATE_ABSENT, STATE_EXCLUDED):
        lines.append("Vị trí xuất hiện trở lại trong bảng FEFO (hàng mới nhập/chuyển tới, hết Block, hoặc sang ngày mới).")
    pivot_lot = cur["lot"] or prev["lot"]
    pivot = pivot_lot["pct"] if pivot_lot else None

    prev_by_key = {lot["key"]: lot for lot in prev["lots"]}
    cur_by_key = {lot["key"]: lot for lot in cur["lots"]}
    added = [lot for key, lot in cur_by_key.items() if key not in prev["keys"]]
    removed = [lot for key, lot in prev_by_key.items() if key not in cur["keys"]]
    if pivot is not None:
        added = [lot for lot in added if lot["pct"] <= pivot]
        removed = [lot for lot in removed if lot["pct"] <= pivot]
    added.sort(key=lambda lot: lot["pct"])
    removed.sort(key=lambda lot: lot["pct"])

    if added:
        lines.append("Lô MỚI xuất hiện ở phía trước (già hơn hoặc bằng): " + "; ".join(map(describe_lot, added)))
    if removed:
        lines.append("Lô phía trước đã MẤT so với lượt trước: " + "; ".join(map(describe_lot, removed)))
    if not added and not removed:
        lines.append(
            "Không có lô nào thêm hoặc mất ở phía trước. Hạng đổi nhiều khả năng do SỐ LƯỢNG thay đổi giữa "
            "các lô cùng % shelf life (lô nhiều hàng xếp trước) — chạy thêm --chi-tiet để xem số lượng. "
            "Nếu không phải, kiểm tra: vị trí vừa hết/được Block, dòng kiểm kho (*), lô K/H/LOOSE đổi tên vị trí."
        )
    return lines


def fmt_time(moment: dt.datetime) -> str:
    return f"{moment:%d/%m %H:%M}"


def detail_section(observations: list[tuple[dt.datetime, dict]], max_shown: int) -> list[str]:
    out = ["\n4) DIỄN BIẾN SỐ LƯỢNG VÀ HẠNG (--chi-tiet)"]
    out.append("  Giờ          Trạng thái  Hạng  SL vị trí  % vị trí  Số lô cùng %  Hạng 6: SL / %")
    for moment, obs in observations:
        lot, lots = obs["lot"], obs["lots"]
        if lot is None:
            out.append(f"  {fmt_time(moment)}   {obs['state']}")
            continue
        pct_key = round(lot["pct"] * 100, 2)
        ties = sum(1 for other in lots if round(other["pct"] * 100, 2) == pct_key)
        cutoff = lots[max_shown - 1] if len(lots) >= max_shown else None
        cutoff_text = f'{cutoff["qty"]:,.0f}'.replace(",", ".") + f' / {cutoff["pct"] * 100:.2f}%' if cutoff else "-"
        out.append(f"  {fmt_time(moment)}   {obs['state']:<10}  {obs['rank']:>4}  {qty_text(lot['qty']):>9}  "
                   f"{lot['pct'] * 100:>7.2f}%  {ties:>12}  {cutoff_text}")

    out.append("\n  Bảng xếp hạng quanh ranh giới tại các lần đổi trạng thái (◄ = vị trí đang theo dõi):")
    for i in range(1, len(observations)):
        before, cur = observations[i - 1][1], observations[i][1]
        if before["state"] == cur["state"]:
            continue
        for label, (moment, obs) in (("TRƯỚC", observations[i - 1]), ("SAU", observations[i])):
            out.append(f"   [{label}] {fmt_time(moment)}")
            limit = min(len(obs["lots"]), max(13, (obs["rank"] or 0) + 2))
            for rank, other in enumerate(obs["lots"][:limit], 1):
                mark = " ◄" if obs["lot"] is not None and other["key"] == obs["lot"]["key"] else ""
                cut = "  --- ranh giới hiển thị ---" if rank == max_shown else ""
                out.append(f"     {rank:>2}. {other['loc']:<8} SX {other['prd']}  {other['pct'] * 100:6.2f}%  "
                           f"SL {qty_text(other['qty']):>8}{mark}{cut}")
    return out


def build_report(material: str, location: str, opts: HistoryOptions, observations: list[tuple[dt.datetime, dict]],
                 baseline_time, baseline_obs) -> list[str]:
    texts = state_text(opts.max_shown)
    out: list[str] = []
    out.append(f"KẾT QUẢ: mã {material} | vị trí {location.upper()} | {len(observations)} lượt chạy"
               + (f" (mốc so sánh trước đó: {fmt_time(baseline_time)})" if baseline_time else ""))
    out.append("=" * 78)
    if not observations:
        out.append("Không có snapshot nào trong khoảng thời gian đã chọn.")
        return out

    out.append("\n1) CÁC KHOẢNG THỜI GIAN")
    start = 0
    for i in range(1, len(observations) + 1):
        if i == len(observations) or observations[i][1]["state"] != observations[start][1]["state"]:
            first_time, first = observations[start]
            last_time = observations[i - 1][0]
            ranks = [o["rank"] for _, o in observations[start:i] if o["rank"] is not None]
            rank_text = f", hạng {min(ranks)}" + (f"–{max(ranks)}" if max(ranks) != min(ranks) else "") if ranks else ""
            out.append(f"  {fmt_time(first_time)} → {fmt_time(last_time)} ({i - start} lượt): "
                       f"{texts[first['state']]}{rank_text}")
            start = i

    out.append("\n2) CHI TIẾT KHI TRẠNG THÁI ĐỔI" + (" / MỖI LƯỢT CÓ THAY ĐỔI LÔ (--all)" if opts.show_all else ""))
    states = [o["state"] for _, o in observations]
    prev_time, prev_obs = (baseline_time, baseline_obs) if baseline_obs else (None, None)
    printed = False
    for i, (moment, obs) in enumerate(observations):
        before = prev_obs if i == 0 else observations[i - 1][1]
        before_time = prev_time if i == 0 else observations[i - 1][0]
        if before is None:
            continue
        changed = obs["state"] != before["state"]
        lots_changed = obs["keys"] != before["keys"]
        if not (changed or (opts.show_all and lots_changed)):
            continue
        printed = True
        head = (f"  {fmt_time(moment)}  {texts[before['state']].split(' (')[0]} → {texts[obs['state']].split(' (')[0]}"
                if changed else f"  {fmt_time(moment)}  (trạng thái giữ nguyên: {obs['state']}, hạng {obs['rank']})")
        out.append(head + f"   [so với lượt {fmt_time(before_time)}]")
        if changed:
            out.append(f"     hạng: {before['rank'] or '-'} → {obs['rank'] or '-'}")
        for line in explain_change(before, obs):
            out.append("     • " + line)
        if changed and i + 1 < len(observations) and states[i + 1] == before["state"]:
            out.append("     ⚠ Trạng thái QUAY LẠI NGAY ở lượt sau → nghi số liệu SAP nhảy tạm.")
    if not printed:
        out.append("  Trạng thái không đổi trong khoảng đã chọn.")

    out.append("\n3) CẢNH BÁO DỮ LIỆU")
    warnings = 0
    last_records, last_time = (baseline_obs["records"], baseline_time) if baseline_obs else (None, None)
    for moment, obs in observations:
        records = obs["records"]
        if obs["suspect"]:
            out.append(f"  ⚠ {fmt_time(moment)}: lượt này bị đánh dấu nghi tải thiếu (bản ghi SAP tụt mạnh).")
            warnings += 1
        elif last_records and records and (last_records - records) / last_records > opts.drop_warn_ratio:
            out.append(f"  ⚠ {fmt_time(moment)}: bản ghi SAP {last_records} → {records} "
                       f"(tụt > {opts.drop_warn_ratio:.0%}) → dữ liệu lượt này có thể thiếu.")
            warnings += 1
        if last_time and (moment - last_time).total_seconds() > opts.gap_warn_minutes * 60:
            out.append(f"  ⚠ Thiếu lượt chạy giữa {fmt_time(last_time)} và {fmt_time(moment)} "
                       f"({(moment - last_time).total_seconds() / 60:.0f} phút).")
            warnings += 1
        last_records, last_time = records or last_records, moment
    if not warnings:
        out.append("  Không có cảnh báo.")
    if opts.detail:
        out.extend(detail_section(observations, opts.max_shown))
    return out


def time_window(opts: HistoryOptions) -> tuple[dt.datetime | None, dt.datetime | None]:
    t_from = t_to = None
    if opts.date:
        t_from, t_to = parse_user_time(opts.date), parse_user_time(opts.date, end_of_day=True)
    if opts.time_from:
        t_from = parse_user_time(opts.time_from)
    if opts.time_to:
        t_to = parse_user_time(opts.time_to, end_of_day=True)
    return t_from, t_to


def history_report(opts: HistoryOptions) -> str | None:
    if not opts.folder.is_dir():
        raise HistoryError(f"Không thấy thư mục: {opts.folder}")
    t_from, t_to = time_window(opts)
    snapshots = list_snapshots(opts.folder)
    in_range = [i for i, (t, _) in enumerate(snapshots)
                if (t_from is None or t >= t_from) and (t_to is None or t <= t_to)]
    if not in_range:
        return None
    if not opts.materials or not opts.locations:
        raise HistoryError("Cần ít nhất một mã (--mat) và một vị trí (--loc).")

    first = in_range[0]
    baseline = None
    if first > 0:
        data = read_snapshot(snapshots[first - 1][1])
        if data is not None:
            baseline = (snapshots[first - 1][0], data)
    loaded = []
    for i in in_range:
        data = read_snapshot(snapshots[i][1])
        if data is not None:
            loaded.append((snapshots[i][0], data))

    reports: list[str] = []
    for material in opts.materials:
        for location in opts.locations:
            baseline_time = baseline[0] if baseline else None
            baseline_obs = observe(baseline[1], material, location, opts.max_shown) if baseline else None
            observations = [(t, observe(d, material, location, opts.max_shown)) for t, d in loaded]
            reports.append("\n".join(build_report(material, location, opts, observations, baseline_time, baseline_obs)))
    return ("\n\n" + "#" * 78 + "\n\n").join(reports)


def split_list(text: str, upper: bool = False) -> list[str]:
    items = [item.strip() for item in text.split(",") if item.strip()]
    return [item.upper().rstrip("*") for item in items] if upper else items


def run_history(opts: HistoryOptions) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    text = history_report(opts)
    if text is None:
        print("Không có snapshot nào trong khoảng thời gian đã chọn.")
        return 0
    print(text)
    if opts.out:
        Path(opts.out).write_text(text + "\n", encoding="utf-8")
        print(f"\n(đã lưu vào {opts.out})")
    return 0
