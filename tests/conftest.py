from __future__ import annotations

import datetime
import logging
import os
from pathlib import Path

import pytest

from efefo.config import load_site

FROZEN_NOW = datetime.datetime(2026, 10, 19, 8, 0, 0)


@pytest.fixture(scope="session")
def site():
    return load_site("hm")


@pytest.fixture(scope="session")
def legacy_script_path():
    path = os.environ.get("EFEFO_LEGACY_SCRIPT", "")
    if not path or not Path(path).exists():
        pytest.skip("Đặt EFEFO_LEGACY_SCRIPT=<đường dẫn SAP_FULL_27_8_v5.py> để chạy test đối chứng")
    return path


@pytest.fixture(autouse=True)
def _isolate_logging():
    root = logging.getLogger()
    before = list(root.handlers)
    yield
    for handler in list(root.handlers):
        if handler not in before:
            root.removeHandler(handler)
            handler.close()
