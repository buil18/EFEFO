from __future__ import annotations

import datetime

from efefo.audit.snapshot import STATUS_HIDDEN

CATEGORY_BLOCKED = "BLOCKED"
CATEGORY_HIDDEN = "HIDDEN_BIN"
CATEGORY_EMOJI = {CATEGORY_BLOCKED: "🔴", CATEGORY_HIDDEN: "🟠"}
EPSILON = 1e-9


def candidate(category: str, key: str, prev: dict, cur_qty: float) -> dict:
    return {
        "category": category,
        "key": key,
        "location": prev["location"],
        "material": prev["material"],
        "short_name": prev.get("short_name", ""),
        "prd_date": prev.get("prd_date", ""),
        "qty_before": prev["qty"],
        "qty_after": cur_qty,
        "delta": cur_qty - prev["qty"],
    }


def detect_hidden(prev_lots: dict, cur_lots: dict, threshold: float) -> list[dict]:
    found = []
    for key, prev in prev_lots.items():
        if prev.get("status") != STATUS_HIDDEN:
            continue
        cur = cur_lots.get(key)
        cur_qty = cur["qty"] if cur else 0.0
        if cur_qty - prev["qty"] < -threshold:
            found.append(candidate(CATEGORY_HIDDEN, key, prev, cur_qty))
    return found


def detect_blocked(prev_blocked: dict, cur_blocked: dict) -> list[dict]:
    found = []
    for key, prev in prev_blocked.items():
        cur = cur_blocked.get(key)
        if not prev.get("blocked") and not (cur and cur.get("blocked")):
            continue
        cur_qty = cur["qty"] if cur else 0.0
        if abs(cur_qty - prev["qty"]) > EPSILON:
            found.append(candidate(CATEGORY_BLOCKED, key, prev, cur_qty))
    return found


def change_persists(category: str, qty_before: float, qty_now: float, threshold: float) -> bool:
    if category == CATEGORY_BLOCKED:
        return abs(qty_now - qty_before) > EPSILON
    return qty_now - qty_before < -threshold


def check_pending_item(item: dict, cur_lots: dict, cur_blocked: dict, now: datetime.datetime,
                       cfg) -> tuple[str, dict]:
    detected = datetime.datetime.fromisoformat(item["detected_at"])
    if (now - detected).total_seconds() > cfg.pending_max_age_minutes * 60:
        return "transient", {**item, "reason": "quá hạn chờ xác nhận"}

    source = cur_blocked if item["category"] == CATEGORY_BLOCKED else cur_lots
    current = source.get(item["key"])
    qty_now = current["qty"] if current else 0.0
    if not change_persists(item["category"], item["qty_before"], qty_now, cfg.qty_delta_threshold):
        return "transient", {**item, "qty_now": qty_now, "reason": "số lượng tự hồi lại"}

    updated = {**item, "runs": item["runs"] + 1, "qty_after": qty_now, "delta": qty_now - item["qty_before"]}
    return ("confirmed" if updated["runs"] >= cfg.confirm_runs else "pending"), updated


def register_candidates(candidates: list[dict], pending: dict, now: datetime.datetime,
                        confirm_runs: int) -> tuple[list[dict], dict]:
    confirmed: list[dict] = []
    waiting: dict = {}
    for cand in candidates:
        pending_key = f"{cand['category']}|{cand['key']}"
        if pending_key in pending:
            continue
        cand = {**cand, "runs": 1, "detected_at": now.isoformat(timespec="seconds")}
        if confirm_runs <= 1:
            confirmed.append(cand)
        else:
            waiting[pending_key] = cand
    return confirmed, waiting


def resolve_pending(pending: dict, candidates: list[dict], cur_lots: dict, cur_blocked: dict,
                    now: datetime.datetime, cfg) -> tuple[list[dict], list[dict], dict]:
    confirmed: list[dict] = []
    transient: list[dict] = []
    still_pending: dict = {}
    for pending_key, item in pending.items():
        outcome, updated = check_pending_item(item, cur_lots, cur_blocked, now, cfg)
        if outcome == "confirmed":
            confirmed.append(updated)
        elif outcome == "pending":
            still_pending[pending_key] = updated
        else:
            transient.append(updated)
    new_confirmed, waiting = register_candidates(candidates, pending, now, cfg.confirm_runs)
    return confirmed + new_confirmed, transient, {**still_pending, **waiting}


def audit_number(value):
    number = float(value)
    return int(number) if number.is_integer() else round(number, 3)


def event_row(item: dict, time_str: str, cfg) -> list:
    if item["category"] == CATEGORY_BLOCKED:
        note = "Số lượng vị trí Blocked thay đổi"
    else:
        note = f"Vị trí không hiển thị trên FEFO nhưng số lượng giảm > {cfg.qty_delta_threshold:g}"
    if cfg.confirm_runs > 1:
        note += f" (đã xác nhận qua {cfg.confirm_runs} lần chạy liên tiếp)"
    emoji = CATEGORY_EMOJI.get(item["category"], "")
    return [
        time_str, f"{emoji} {item['category']}", item["location"], item["material"],
        item.get("short_name", ""), item.get("prd_date", ""),
        audit_number(item["qty_before"]), audit_number(item["qty_after"]), audit_number(item["delta"]), note,
    ]


def is_suspect_run(prev_state: dict | None, record_count: int, cfg) -> bool:
    if not prev_state:
        return False
    prev_count = int(prev_state.get("record_count") or 0)
    if prev_count <= 0:
        return False
    dropped = (prev_count - record_count) / prev_count > cfg.max_record_drop_ratio
    return dropped and int(prev_state.get("suspect_streak", 0)) < cfg.max_consecutive_suspect
