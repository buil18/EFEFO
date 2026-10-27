from __future__ import annotations

import datetime
from dataclasses import replace

import pandas as pd

from efefo.audit import detection
from efefo.audit.step import deliver
from efefo.audit.snapshot import display_rows

NOW = datetime.datetime(2026, 10, 19, 8, 0)


def lot(qty, status="hidden"):
    return {"location": "D01", "material": "1", "short_name": "A", "prd_date": "01/09/2026", "qty": qty,
            "status": status}


def test_hidden_detection_only_for_previously_hidden(site):
    prev = {"k1": lot(500), "k2": lot(500, "shown"), "k3": lot(500), "k4": lot(150)}
    cur = {"k1": lot(399), "k2": lot(0, "hidden"), "k3": lot(400)}
    found = detection.detect_hidden(prev, cur, site.audit.qty_delta_threshold)
    assert [f["key"] for f in found] == ["k1", "k4"]
    assert found[1]["qty_after"] == 0.0 and found[1]["delta"] == -150


def test_blocked_detection_any_change_including_unblock():
    prev = {"a": {**lot(10), "blocked": True}, "b": {**lot(10), "blocked": False}, "c": {**lot(10), "blocked": True}}
    cur = {"a": {**lot(10), "blocked": False}, "b": {**lot(3), "blocked": False}, "c": {**lot(9.5), "blocked": True}}
    assert [f["key"] for f in detection.detect_blocked(prev, cur)] == ["c"]


def test_change_needs_two_runs_then_confirms(site):
    cfg = site.audit
    cand = detection.candidate("HIDDEN_BIN", "k", lot(500), 300.0)
    confirmed, transient, pending = detection.resolve_pending({}, [cand], {}, {}, NOW, cfg)
    assert not confirmed and list(pending) == ["HIDDEN_BIN|k"]
    later = NOW + datetime.timedelta(hours=1)
    confirmed, transient, pending = detection.resolve_pending(pending, [cand], {"k": lot(250)}, {}, later, cfg)
    assert len(confirmed) == 1 and confirmed[0]["qty_after"] == 250 and confirmed[0]["runs"] == 2 and not pending


def test_change_that_recovers_is_transient(site):
    cfg = site.audit
    item = {**detection.candidate("HIDDEN_BIN", "k", lot(500), 300.0), "runs": 1, "detected_at": NOW.isoformat()}
    confirmed, transient, pending = detection.resolve_pending({"HIDDEN_BIN|k": item}, [], {"k": lot(480)}, {},
                                                              NOW + datetime.timedelta(hours=1), cfg)
    assert not confirmed and transient[0]["reason"] == "số lượng tự hồi lại"


def test_stale_pending_expires(site):
    cfg = site.audit
    item = {**detection.candidate("BLOCKED", "k", lot(5), 1.0), "runs": 1, "detected_at": NOW.isoformat()}
    _, transient, _ = detection.resolve_pending({"BLOCKED|k": item}, [], {}, {"k": lot(1)},
                                                NOW + datetime.timedelta(minutes=121), cfg)
    assert transient[0]["reason"] == "quá hạn chờ xác nhận"


def test_confirm_runs_one_reports_immediately(site):
    cfg = replace(site.audit, confirm_runs=1)
    cand = detection.candidate("BLOCKED", "k", lot(5), 1.0)
    confirmed, _, pending = detection.resolve_pending({}, [cand], {}, {}, NOW, cfg)
    assert len(confirmed) == 1 and not pending
    assert "đã xác nhận" not in detection.event_row(confirmed[0], "t", cfg)[-1]


def test_event_row_format(site):
    item = {**detection.candidate("HIDDEN_BIN", "k", lot(6760.0), 6500.5)}
    row = detection.event_row(item, "2026-10-19 08:00:00", site.audit)
    assert row[:6] == ["2026-10-19 08:00:00", "🟠 HIDDEN_BIN", "D01", "1", "A", "01/09/2026"]
    assert row[6:9] == [6760, 6500.5, -259.5]
    assert row[9] == ("Vị trí không hiển thị trên FEFO nhưng số lượng giảm > 100 "
                      "(đã xác nhận qua 2 lần chạy liên tiếp)")


def test_suspect_run_detection(site):
    cfg = site.audit
    assert detection.is_suspect_run({"record_count": 1000}, 940, cfg)
    assert not detection.is_suspect_run({"record_count": 1000}, 960, cfg)
    assert not detection.is_suspect_run({"record_count": 1000, "suspect_streak": 1}, 10, cfg)
    assert not detection.is_suspect_run(None, 10, cfg)


def test_unsent_events_retried_then_dropped(site, tmp_path):
    cfg = site.audit
    item = {**detection.candidate("BLOCKED", "k", lot(5), 1.0), "runs": 2}
    unsent = deliver([item], [], tmp_path, NOW, cfg, push=lambda rows: False)
    assert unsent[0]["attempts"] == 1
    unsent = deliver([], unsent, tmp_path, NOW, cfg, push=lambda rows: False)
    assert unsent[0]["attempts"] == 2
    assert deliver([], unsent, tmp_path, NOW, cfg, push=lambda rows: False) == []
    sent = []
    assert deliver([item], [], tmp_path, NOW, cfg, push=lambda rows: sent.append(rows) or True) == []
    assert len(sent[0]) == 1


def test_display_rank_simulates_tablet(site):
    summary = pd.DataFrame({
        "Normalized_Location": ["K01", "D01", "D02*", "D03", "D04", "D05", "D06", "D07", "LOOSE-1"],
        "Material": ["1"] * 9,
        "PRD_date": [datetime.date(2026, 9, 1)] * 9,
        "Total_Quantity": [1] * 9,
        "phantram_shelf_life": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.05],
    })
    disp = display_rows(summary, site.location, site.fefo.display_max_slots)
    assert disp.loc[disp["_excluded"], "Normalized_Location"].tolist() == ["K01", "LOOSE-1"]
    assert disp.loc[disp["_hidden"], "Normalized_Location"].tolist() == ["D07"]
    assert disp.loc[1, "_rank"] == 1 and bool(disp.loc[2, "_manual"])


def test_v6_lot_far_from_group_anchor_is_not_assigned():
    from efefo.audit.snapshot import find_group

    index = {("D01", "1"): [(pd.Timestamp("2026-09-01"), {"id": "g1"}), (pd.Timestamp("2026-09-20"), {"id": "g2"})]}
    assert find_group(index, "D01", "1", pd.Timestamp("2026-09-06"), 7)["id"] == "g1"
    assert find_group(index, "D01", "1", pd.Timestamp("2026-09-08"), 7) is None
    assert find_group(index, "D01", "1", pd.Timestamp("2026-09-21"), 7)["id"] == "g2"
    assert find_group(index, "D01", "1", pd.Timestamp("2026-08-30"), 7) is None
