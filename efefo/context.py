from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from efefo.config import PROJECT_ROOT, SiteConfig
from efefo.sources.manual_materials import parse_manual_only_materials

logger = logging.getLogger(__name__)

SESSION_ROOT_NAME = ".session"
LOCK_FILE_NAME = ".sap_inventory.lock"
HISTORY_FILE_NAME = ".sap_location_history.json"
DAILY_DIR_NAME = "Daily_Reports"
LOG_DIR_NAME = "logs"
AUDIT_DIR_NAME = "audit"


@dataclass
class RunContext:
    site: SiteConfig
    sap_url: str
    first_url: str
    email: str | None
    output_dir: Path
    input_dir: Path
    session_dir: Path
    max_pages: int
    unattended: bool
    storage_state_path: Path
    browser_profile_dir: Path
    json_file: Path
    excel_file: Path
    recon_file: Path
    fefo_file: Path
    history_file: Path
    lock_file: Path
    daily_dir: Path
    log_dir: Path
    audit_dir: Path
    shelf_life_file: Path
    capacity_file: Path
    fefo_script_url: str
    capacity_script_url: str
    apps_script_secret: str
    manual_only_materials: set[str]

    @property
    def interactive_hint(self) -> str:
        return f"python -m efefo run --site {self.site.site.code} --interactive"


def is_unattended() -> bool:
    flag = os.environ.get("SAP_UNATTENDED", "").strip()
    if flag:
        return flag not in ("0", "false", "False")
    try:
        return not sys.stdin.isatty()
    except Exception:
        return True


def resolve_output_dir(site: SiteConfig) -> Path:
    explicit = os.environ.get("SAP_OUTPUT_DIR")
    if explicit:
        out = Path(explicit)
    else:
        onedrive_root = os.environ.get("OneDrive") or os.environ.get("OneDriveCommercial")
        if onedrive_root:
            out = Path(onedrive_root) / site.paths.onedrive_subdir
        else:
            logger.warning("Không tìm thấy OneDrive, dùng thư mục cục bộ ./%s.", site.paths.fallback_dir)
            out = Path.cwd() / site.paths.fallback_dir
    out.mkdir(parents=True, exist_ok=True)
    return out


def resolve_input_dir(site: SiteConfig, output_dir: Path) -> Path:
    explicit = os.environ.get("SAP_INPUT_DIR")
    in_dir = Path(explicit) if explicit else output_dir / site.paths.input_subdir
    in_dir.mkdir(parents=True, exist_ok=True)
    return in_dir


def resolve_session_dir(site: SiteConfig) -> Path:
    explicit = os.environ.get("SAP_SESSION_DIR")
    session_dir = Path(explicit) if explicit else PROJECT_ROOT / SESSION_ROOT_NAME / site.site.code
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def locate_input_file(filename: str, input_dir: Path, output_dir: Path) -> Path:
    preferred = input_dir / filename
    if preferred.exists():
        return preferred
    legacy = output_dir / filename
    if legacy.exists():
        logger.warning("Vẫn đang dùng %s ở thư mục cũ. Nên chuyển vào thư mục %s.", filename, input_dir)
        return legacy
    return preferred


def resolve_secret(site: SiteConfig) -> str:
    secret = os.environ.get("GOOGLE_APPS_SCRIPT_SECRET", "").strip()
    if secret:
        return secret
    if site.publish.secret:
        logger.warning(
            "Chưa đặt biến GOOGLE_APPS_SCRIPT_SECRET — đang dùng secret trong file cấu hình site. "
            "Nên đặt biến môi trường để tránh lộ secret."
        )
    return site.publish.secret


def build_context(site: SiteConfig, interactive: bool = False) -> RunContext:
    sap_url = os.environ.get("SAP_URL", site.sap.base_url)
    first_url = f"{sap_url}{site.sap.odata_path}?$format=json&sap-client={site.sap.client}"
    output_dir = resolve_output_dir(site)
    input_dir = resolve_input_dir(site, output_dir)
    session_dir = resolve_session_dir(site)

    test_mode = os.environ.get("SAP_TEST_MODE", "0").strip() not in ("", "0", "false", "False")
    max_pages = int(os.environ.get("SAP_MAX_PAGES", str(site.sap.test_max_pages))) if test_mode else 999_999
    if test_mode:
        logger.warning(
            "==> ĐANG CHẠY TEST MODE: tải tối đa %s trang. Bỏ đặt SAP_TEST_MODE để chạy full.", max_pages
        )

    sources = site.sources
    return RunContext(
        site=site,
        sap_url=sap_url,
        first_url=first_url,
        email=os.environ.get("SAP_USER_EMAIL"),
        output_dir=output_dir,
        input_dir=input_dir,
        session_dir=session_dir,
        max_pages=max_pages,
        unattended=False if interactive else is_unattended(),
        storage_state_path=session_dir / ".sap_session.json",
        browser_profile_dir=session_dir / ".sap_browser_profile",
        json_file=output_dir / "sap_response_full.json",
        excel_file=output_dir / "Inventory_Report_Full.xlsx",
        recon_file=output_dir / "Inventory_Reconciliation_Report.xlsx",
        fefo_file=output_dir / sources.fefo_file,
        history_file=output_dir / HISTORY_FILE_NAME,
        lock_file=output_dir / LOCK_FILE_NAME,
        daily_dir=output_dir / DAILY_DIR_NAME,
        log_dir=output_dir / LOG_DIR_NAME,
        audit_dir=output_dir / AUDIT_DIR_NAME,
        shelf_life_file=locate_input_file(sources.shelf_life_file, input_dir, output_dir),
        capacity_file=locate_input_file(sources.capacity_file, input_dir, output_dir),
        fefo_script_url=os.environ.get("GOOGLE_APPS_SCRIPT_URL", site.publish.fefo_script_url),
        capacity_script_url=os.environ.get("GOOGLE_CAPACITY_SCRIPT_URL", site.publish.capacity_script_url),
        apps_script_secret=resolve_secret(site),
        manual_only_materials=parse_manual_only_materials(
            locate_input_file(sources.manual_materials_file, input_dir, output_dir).parent,
            sources.manual_materials_file,
        ),
    )


def validate_input_files(ctx: RunContext) -> None:
    missing = [str(p) for p in (ctx.shelf_life_file, ctx.capacity_file) if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Thiếu file dữ liệu đầu vào bắt buộc:\n  - "
            + "\n  - ".join(missing)
            + f"\nHãy đặt các file này vào thư mục: {ctx.input_dir}"
        )
    logger.info("Đã kiểm tra đủ file đầu vào tại: %s", ctx.input_dir)
