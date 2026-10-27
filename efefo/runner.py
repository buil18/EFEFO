from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from efefo.audit.step import push_events, run_audit_step
from efefo.context import RunContext, build_context, validate_input_files
from efefo.domain.capacity import compute_occupancy
from efefo.domain.fefo import build_fefo_summary
from efefo.domain.shelf_life import compute_shelf_life_metrics
from efefo.domain.supplement import (
    DATA_SOURCE_SAP,
    append_manual_only_rows,
    drop_manual_rows_without_quantity,
    drop_manual_rows_without_shelf_life,
    fill_manual_quantity,
)
from efefo.infra.http import session_with_retry
from efefo.infra.logging_setup import add_file_handler
from efefo.infra.run_lock import AlreadyRunningError, acquire_run_lock, release_run_lock
from efefo.reports.empty_locations import publish_empty_locations
from efefo.reports.fefo_workbook import export_fefo_workbook
from efefo.reports.google_sheet import publish_fefo
from efefo.reports.inventory import export_inventory_report
from efefo.reports.reconciliation import export_reconciliation
from efefo.sap.cleaning import clean_dataframe
from efefo.sources.master_data import merge_shelf_life, merge_unit_capacity
from efefo.sources.stock_count import blocked_locations, fetch_stock_count

logger = logging.getLogger(__name__)


def _default_fetch_records(ctx: RunContext) -> list[dict]:
    from efefo.sap.client import fetch_all_records

    return fetch_all_records(ctx)


@dataclass
class Services:
    fetch_records: Callable[[RunContext], list[dict]] = _default_fetch_records
    http_session: Callable = field(default=session_with_retry)


@dataclass
class RunResult:
    inventory: pd.DataFrame
    summary: pd.DataFrame | None
    stock_count: pd.DataFrame | None
    blocked: set


def transform(records: list[dict], df_manual: pd.DataFrame | None, ctx: RunContext) -> pd.DataFrame:
    site = ctx.site
    df = clean_dataframe(pd.DataFrame(records))
    df = append_manual_only_rows(
        df, df_manual, ctx.manual_only_materials, site.location.strip_prefixes,
        history_path=ctx.history_file, history_retention_days=site.manual.location_history_retention_days,
    )
    df = merge_shelf_life(df, ctx.shelf_life_file)
    df = merge_unit_capacity(df, ctx.capacity_file)
    df = fill_manual_quantity(df)
    df = drop_manual_rows_without_quantity(df)
    df = compute_shelf_life_metrics(df, site.shelf_life)
    df = compute_occupancy(df, ctx.capacity_file, site.location)
    return drop_manual_rows_without_shelf_life(df)


def summarize(df: pd.DataFrame, blocked: set, ctx: RunContext) -> pd.DataFrame | None:
    try:
        return build_fefo_summary(df, ctx.site.fefo.lot_split_days, blocked_locations=blocked,
                                  min_quantity=ctx.site.fefo.min_quantity)
    except KeyError as exc:
        logger.warning("Không thể tổng hợp FEFO: %s", exc)
        return None


def publish(df: pd.DataFrame, summary: pd.DataFrame | None, df_manual: pd.DataFrame | None, ctx: RunContext,
            services: Services) -> None:
    site = ctx.site
    export_reconciliation(df[df["Data_Source"] == DATA_SOURCE_SAP].copy(), df_manual, ctx.recon_file)
    export_inventory_report(df, ctx.excel_file, ctx.daily_dir)
    export_fefo_workbook(summary, ctx.fefo_file, site.fefo.workbook_sheet, site.fefo.workbook_start_row)

    if site.publish.fefo_to_google_sheet:
        publish_fefo(summary, ctx.fefo_script_url, ctx.apps_script_secret, services.http_session)
    if site.publish.empty_locations_to_google_sheet:
        publish_empty_locations(df, ctx.capacity_file, site.location, ctx.capacity_script_url,
                                ctx.apps_script_secret, services.http_session)

    if not site.audit.enabled:
        return
    try:
        if summary is None:
            raise RuntimeError("không có bảng FEFO tổng hợp")
        if site.publish.audit_to_google_sheet:
            def push(rows):
                return push_events(rows, ctx.fefo_script_url, ctx.apps_script_secret, services.http_session)
        else:
            def push(rows):
                return True
        run_audit_step(df, summary, df_manual, ctx.audit_dir, site, push)
    except Exception:
        logger.exception("Audit: lỗi không mong đợi — bỏ qua lượt audit này.")


def process(records: list[dict], ctx: RunContext, services: Services) -> RunResult:
    df_manual = fetch_stock_count(ctx.site.sources.stock_count_csv_url, services.http_session,
                                  ctx.site.location.strip_prefixes)
    blocked = blocked_locations(df_manual)
    df = transform(records, df_manual, ctx)
    summary = summarize(df, blocked, ctx)
    publish(df, summary, df_manual, ctx, services)
    return RunResult(inventory=df, summary=summary, stock_count=df_manual, blocked=blocked)


STEP_OK = "THÀNH CÔNG"
STEP_FAILED = "THẤT BẠI"
STEP_SKIPPED = "BỎ QUA"
ALL_STEPS_DONE = "Tất cả các bước đã hoàn tất"
SOME_STEPS_FAILED = "Có bước chưa hoàn tất"


class StepLog:
    def __init__(self):
        self.steps: list[tuple[str, str, float]] = []
        self._clock = time.perf_counter

    def start(self) -> float:
        return self._clock()

    def record(self, name: str, status: str, started: float) -> None:
        self.steps.append((name, status, self._clock() - started))

    def write(self) -> None:
        logger.info("Tổng kết lượt chạy:")
        for name, status, seconds in self.steps:
            logger.info("  %-8s  %-12s  %.1fs", name, status, seconds)
        if self.steps and all(status == STEP_OK for _, status, _ in self.steps):
            logger.info(ALL_STEPS_DONE)
        else:
            logger.warning(SOME_STEPS_FAILED)


def run(ctx: RunContext, services: Services | None = None) -> RunResult | None:
    services = services or Services()
    add_file_handler(ctx.log_dir)
    steps = StepLog()
    started = steps.start()
    try:
        return _run_steps(ctx, services, steps, started)
    except Exception:
        if not steps.steps or steps.steps[-1][1] == STEP_OK:
            steps.record("report" if steps.steps else "sap", STEP_FAILED, started)
        raise
    finally:
        steps.write()


def _run_steps(ctx: RunContext, services: Services, steps: StepLog, started: float) -> RunResult | None:
    validate_input_files(ctx)

    try:
        lock_file = acquire_run_lock(ctx.lock_file, ctx.site.run.lock_stale_hours)
    except AlreadyRunningError as exc:
        logger.warning(str(exc))
        steps.record("sap", STEP_SKIPPED, started)
        return None

    try:
        records = services.fetch_records(ctx)
        if not records:
            logger.error("Không có bản ghi OData nào từ SAP. Dừng chương trình.")
            steps.record("sap", STEP_FAILED, started)
            return None
        with open(ctx.json_file, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        steps.record("sap", STEP_OK, started)
        report_started = steps.start()
        result = process(records, ctx, services)
        steps.record("report", STEP_OK, report_started)
        return result
    finally:
        release_run_lock(lock_file)


def run_site(site, interactive: bool = False, services: Services | None = None) -> RunResult | None:
    return run(build_context(site, interactive=interactive), services)
