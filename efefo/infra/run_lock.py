from __future__ import annotations

import datetime
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class AlreadyRunningError(Exception):
    pass


def acquire_run_lock(lock_file: Path, stale_after_hours: float) -> Path:
    if lock_file.exists():
        age_hours = (datetime.datetime.now().timestamp() - lock_file.stat().st_mtime) / 3600
        if age_hours < stale_after_hours:
            raise AlreadyRunningError(
                f"Phát hiện file khóa còn hiệu lực ({age_hours:.1f}h). Dừng chạy để tránh trùng lặp."
            )
        logger.warning("Xóa file khóa cũ đã quá hạn (%.1fh).", age_hours)
    lock_file.write_text(str(datetime.datetime.now()), encoding="utf-8")
    return lock_file


def release_run_lock(lock_file: Path) -> None:
    try:
        lock_file.unlink(missing_ok=True)
    except Exception as exc:
        logger.warning("Không thể xóa file khóa %s: %s", lock_file, exc)
