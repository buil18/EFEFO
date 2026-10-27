from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

CONSOLE_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_FILE_NAME = "sap_inventory.log"


def configure_console() -> None:
    logging.basicConfig(level=logging.INFO, format=CONSOLE_FORMAT, datefmt="%H:%M:%S")


def add_file_handler(log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / LOG_FILE_NAME
    root = logging.getLogger()
    exists = any(
        isinstance(handler, TimedRotatingFileHandler) and Path(handler.baseFilename) == log_file.resolve()
        for handler in root.handlers
    )
    if not exists:
        file_handler = TimedRotatingFileHandler(log_file, when="midnight", backupCount=0, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(CONSOLE_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))
        root.addHandler(file_handler)
    logging.getLogger(__name__).info("Đã bật ghi log file: %s", log_file)
    return log_file
