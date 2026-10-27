from __future__ import annotations

import argparse
import logging
import re
import sys

from efefo.config import SITES_DIR, ConfigError, load_site, local_site_file, site_file
from efefo.infra.logging_setup import configure_console

logger = logging.getLogger("efefo")

SITE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,19}$")
EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_FAILED = 1


def command_run(args) -> int:
    from efefo.runner import run_site

    site = load_site(args.site)
    result = run_site(site, interactive=args.interactive)
    return EXIT_OK if result is not None else EXIT_FAILED


def command_check(args) -> int:
    from efefo.checks import check_site

    site = load_site(args.site)
    problems, warnings = check_site(site)
    for warning in warnings:
        logger.warning(warning)
    for problem in problems:
        logger.error(problem)
    if not problems:
        logger.info("Site '%s' sẵn sàng chạy.", site.site.code)
    return EXIT_OK if not problems else EXIT_FAILED


def command_new_site(args) -> int:
    code = args.code.lower()
    if not SITE_CODE_PATTERN.match(code):
        logger.error("Mã site chỉ gồm chữ thường, số, gạch dưới (2-20 ký tự), bắt đầu bằng chữ: %r", args.code)
        return EXIT_CONFIG
    target = site_file(code)
    if target.exists():
        logger.error("Site '%s' đã tồn tại: %s", code, target)
        return EXIT_CONFIG
    source = site_file(args.template)
    if not source.exists():
        logger.error("Không có site mẫu '%s' (%s)", args.template, source)
        return EXIT_CONFIG
    text = source.read_text(encoding="utf-8")
    text = re.sub(r'(?m)^code = ".*"$', f'code = "{code}"', text, count=1)
    text = re.sub(r'(?m)^name = ".*"$', f'name = "{code.upper()}"', text, count=1)
    target.write_text(text, encoding="utf-8")
    logger.info("Đã tạo %s từ mẫu %s. Hãy sửa các giá trị riêng của site trước khi chạy.", target, source.name)
    logger.info("Secret và thông số riêng máy đặt trong %s (không đưa lên git).", local_site_file(code))
    return EXIT_OK


def command_perf_report(args) -> int:
    from pathlib import Path

    from efefo.context import LOG_DIR_NAME, resolve_output_dir
    from efefo.tools.perf_report import DEFAULT_OUTPUT, PerfOptions, PerfReportError, run_perf_report

    site = load_site(args.site)
    output_dir = resolve_output_dir(site) if not (args.logs and args.out) else None
    opts = PerfOptions(
        logs=Path(args.logs) if args.logs else output_dir / LOG_DIR_NAME,
        out=Path(args.out) if args.out else output_dir / DEFAULT_OUTPUT,
        cycle_minutes=args.chu_ky or site.monitoring.expected_interval_minutes,
        gap_minutes=args.nguong_dut or site.monitoring.gap_warning_minutes,
        date_from=args.tu,
        date_to=args.den,
    )
    try:
        run_perf_report(opts)
    except PerfReportError as exc:
        logger.error(str(exc))
        return EXIT_FAILED
    return EXIT_OK


def command_fefo_history(args) -> int:
    from pathlib import Path

    from efefo.audit.storage import HISTORY_SUBDIR
    from efefo.context import AUDIT_DIR_NAME, resolve_output_dir
    from efefo.tools.fefo_history import HistoryError, HistoryOptions, run_history, split_list

    site = load_site(args.site)
    folder = Path(args.dir) if args.dir else resolve_output_dir(site) / AUDIT_DIR_NAME / HISTORY_SUBDIR
    opts = HistoryOptions(
        folder=folder,
        materials=split_list(args.mat),
        locations=split_list(args.loc, upper=True),
        date=args.date,
        time_from=args.t_from,
        time_to=args.t_to,
        show_all=args.all,
        detail=args.chi_tiet,
        out=Path(args.out) if args.out else None,
        max_shown=site.fefo.display_max_slots,
        drop_warn_ratio=site.audit.max_record_drop_ratio,
        gap_warn_minutes=site.monitoring.gap_warning_minutes,
    )
    try:
        return run_history(opts)
    except HistoryError as exc:
        logger.error(str(exc))
        return EXIT_FAILED


def command_list(args) -> int:
    for path in sorted(SITES_DIR.glob("*.toml")):
        if path.stem.endswith(".local") or path.stem.startswith("_"):
            continue
        print(path.stem)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="efefo", description="E-FEFO: SAP EWM inventory, FEFO và audit theo site")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Chạy toàn bộ pipeline cho một site")
    run.add_argument("--site", required=True)
    run.add_argument("--interactive", action="store_true", help="Cho phép mở trình duyệt để đăng nhập/MFA")
    run.set_defaults(handler=command_run)

    check = sub.add_parser("check", help="Kiểm tra cấu hình và file đầu vào của site")
    check.add_argument("--site", required=True)
    check.set_defaults(handler=command_check)

    new_site = sub.add_parser("new-site", help="Tạo cấu hình site mới từ site mẫu")
    new_site.add_argument("code")
    new_site.add_argument("--template", default="_template")
    new_site.set_defaults(handler=command_new_site)

    perf = sub.add_parser("perf-report", help="Báo cáo hiệu năng chạy tự động từ log -> Excel")
    perf.add_argument("--site", required=True)
    perf.add_argument("--logs", help="Thư mục log (mặc định: <output>/logs)")
    perf.add_argument("--out", help="File Excel kết quả (mặc định: <output>/Bao_cao_hieu_nang_PAD.xlsx)")
    perf.add_argument("--chu-ky", dest="chu_ky", type=int, help="Chu kỳ chạy mong đợi (phút)")
    perf.add_argument("--nguong-dut", dest="nguong_dut", type=int,
                      help="Khoảng cách giữa 2 lượt thành công bị coi là đứt (phút)")
    perf.add_argument("--tu", help="Từ ngày, ví dụ 2026-10-01")
    perf.add_argument("--den", help="Đến ngày, ví dụ 2026-10-24")
    perf.set_defaults(handler=command_perf_report)

    history = sub.add_parser("fefo-history", help="Lịch sử hiển thị của vị trí trên E-FEFO từ audit/history")
    history.add_argument("--site", required=True)
    history.add_argument("--dir", help="Thư mục audit/history (mặc định theo site)")
    history.add_argument("--mat", required=True, help="Mã hàng, nhiều mã cách nhau bằng dấu phẩy")
    history.add_argument("--loc", required=True, help="Vị trí, nhiều vị trí cách nhau bằng dấu phẩy")
    history.add_argument("--date", help="Chỉ xem một ngày, ví dụ 2026-10-21")
    history.add_argument("--from", dest="t_from", help='Từ thời điểm, ví dụ "2026-10-21 08:00"')
    history.add_argument("--to", dest="t_to", help='Đến thời điểm, ví dụ "2026-10-21 18:00"')
    history.add_argument("--all", action="store_true", help="In cả những lượt có đổi lô nhưng trạng thái không đổi")
    history.add_argument("--chi-tiet", dest="chi_tiet", action="store_true",
                         help="In thêm số lượng/hạng từng lượt và bảng xếp hạng quanh ranh giới")
    history.add_argument("--out", help="Lưu kết quả ra file văn bản")
    history.set_defaults(handler=command_fefo_history)

    list_sites = sub.add_parser("sites", help="Liệt kê các site đã cấu hình")
    list_sites.set_defaults(handler=command_list)
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_console()
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except ConfigError as exc:
        logger.error(str(exc))
        return EXIT_CONFIG
    except Exception:
        logger.exception("Lỗi không mong đợi")
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
