from __future__ import annotations

import dataclasses
import os
import tomllib
import typing
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SITES_DIR = PROJECT_ROOT / "sites"


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class SiteInfo:
    code: str
    name: str


@dataclass(frozen=True)
class SapConfig:
    base_url: str
    odata_path: str
    client: str
    browser_channel: str
    max_relogin_attempts: int
    max_incomplete_retries: int
    incomplete_retry_wait_seconds: tuple[int, ...]
    test_max_pages: int


@dataclass(frozen=True)
class PathsConfig:
    onedrive_subdir: str
    fallback_dir: str
    input_subdir: str


@dataclass(frozen=True)
class SourcesConfig:
    stock_count_csv_url: str
    shelf_life_file: str
    capacity_file: str
    manual_materials_file: str
    fefo_file: str


@dataclass(frozen=True)
class LocationConfig:
    strip_prefixes: tuple[str, ...]
    warehouse_group_prefixes: tuple[str, ...]
    display_exclude_prefixes: tuple[str, ...]
    display_exclude_keywords: tuple[str, ...]
    empty_location_exclusions: tuple[str, ...]
    empty_location_capacity_column: str


@dataclass(frozen=True)
class ShelfLifeConfig:
    expired_max: float
    near_expiry_below: float
    traditional_below: float
    emart_below: float
    supermarket_max: float


@dataclass(frozen=True)
class FefoConfig:
    lot_split_days: int
    min_quantity: float
    display_max_slots: int
    workbook_sheet: str
    workbook_start_row: int


@dataclass(frozen=True)
class ManualConfig:
    location_history_retention_days: int


@dataclass(frozen=True)
class AuditConfig:
    enabled: bool
    history_retention_days: int
    qty_delta_threshold: float
    confirm_runs: int
    pending_max_age_minutes: int
    max_record_drop_ratio: float
    max_consecutive_suspect: int
    max_push_attempts: int


@dataclass(frozen=True)
class PublishConfig:
    fefo_to_google_sheet: bool
    empty_locations_to_google_sheet: bool
    audit_to_google_sheet: bool
    capacity_script_url: str
    fefo_script_url: str
    secret: str


@dataclass(frozen=True)
class RunConfig:
    lock_stale_hours: float


@dataclass(frozen=True)
class MonitoringConfig:
    expected_interval_minutes: int
    gap_warning_minutes: int


@dataclass(frozen=True)
class SiteConfig:
    site: SiteInfo
    sap: SapConfig
    paths: PathsConfig
    sources: SourcesConfig
    location: LocationConfig
    shelf_life: ShelfLifeConfig
    fefo: FefoConfig
    manual: ManualConfig
    audit: AuditConfig
    publish: PublishConfig
    run: RunConfig
    monitoring: MonitoringConfig


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _coerce(value, annotation, where: str):
    origin = typing.get_origin(annotation)
    if origin is tuple:
        if not isinstance(value, list | tuple):
            raise ConfigError(f"{where}: cần danh sách, nhận {value!r}")
        inner = typing.get_args(annotation)[0]
        return tuple(_coerce(v, inner, where) for v in value)
    if annotation is bool:
        if not isinstance(value, bool):
            raise ConfigError(f"{where}: cần true/false, nhận {value!r}")
        return value
    if annotation is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"{where}: cần số nguyên, nhận {value!r}")
        return value
    if annotation is float:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ConfigError(f"{where}: cần số, nhận {value!r}")
        return float(value)
    if annotation is str:
        if not isinstance(value, str):
            raise ConfigError(f"{where}: cần chuỗi, nhận {value!r}")
        return value
    if dataclasses.is_dataclass(annotation):
        return _build(annotation, value, where)
    raise ConfigError(f"{where}: kiểu không hỗ trợ {annotation!r}")


def _build(cls, data, where: str):
    if not isinstance(data, dict):
        raise ConfigError(f"{where}: cần một bảng [section]")
    hints = typing.get_type_hints(cls)
    names = [f.name for f in dataclasses.fields(cls)]
    unknown = sorted(set(data) - set(names))
    if unknown:
        raise ConfigError(f"{where}: khóa không hợp lệ {unknown}")
    missing = [n for n in names if n not in data]
    if missing:
        raise ConfigError(f"{where}: thiếu khóa {missing}")
    return cls(**{n: _coerce(data[n], hints[n], f"{where}.{n}") for n in names})


def site_file(code: str, sites_dir: Path = SITES_DIR) -> Path:
    return sites_dir / f"{code}.toml"


def local_site_file(code: str, sites_dir: Path = SITES_DIR) -> Path:
    return sites_dir / f"{code}.local.toml"


def load_site(code: str, sites_dir: Path = SITES_DIR) -> SiteConfig:
    path = site_file(code, sites_dir)
    if not path.exists():
        available = sorted(p.stem for p in sites_dir.glob("*.toml") if not p.stem.endswith(".local") and not p.stem.startswith("_"))
        raise ConfigError(f"Không có cấu hình site '{code}' ({path}). Các site hiện có: {available}")
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    local = local_site_file(code, sites_dir)
    if local.exists():
        with local.open("rb") as handle:
            data = _deep_merge(data, tomllib.load(handle))
    config = _build(SiteConfig, data, path.name)
    validate_site(config)
    return config


def validate_site(config: SiteConfig) -> None:
    problems = []
    if not config.sap.base_url.startswith("https://"):
        problems.append("sap.base_url phải bắt đầu bằng https://")
    if not config.sap.incomplete_retry_wait_seconds:
        problems.append("sap.incomplete_retry_wait_seconds không được rỗng")
    if config.fefo.lot_split_days < 1:
        problems.append("fefo.lot_split_days phải >= 1")
    if config.fefo.min_quantity < 0:
        problems.append("fefo.min_quantity phải >= 0 (0 = tắt)")
    if config.fefo.display_max_slots < 1:
        problems.append("fefo.display_max_slots phải >= 1")
    if config.fefo.workbook_start_row < 1:
        problems.append("fefo.workbook_start_row phải >= 1")
    if config.monitoring.expected_interval_minutes < 1 or config.monitoring.gap_warning_minutes < 1:
        problems.append("monitoring: số phút phải >= 1")
    if config.audit.confirm_runs < 1:
        problems.append("audit.confirm_runs phải >= 1")
    thresholds = config.shelf_life
    ordered = [thresholds.expired_max, thresholds.near_expiry_below, thresholds.traditional_below,
               thresholds.emart_below, thresholds.supermarket_max]
    if ordered != sorted(ordered):
        problems.append("shelf_life: các ngưỡng phải tăng dần")
    if any(p != p.upper() for p in config.location.strip_prefixes + config.location.warehouse_group_prefixes):
        problems.append("location: tiền tố phải viết HOA")
    if problems:
        raise ConfigError(f"Cấu hình site '{config.site.code}' không hợp lệ:\n  - " + "\n  - ".join(problems))


def env_flag(name: str) -> str:
    return os.environ.get(name, "").strip()
