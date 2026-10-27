from __future__ import annotations

import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

ENV_FALLBACK = "SAP_MA_BO_SUNG"


def parse_material_list(raw: str) -> set[str]:
    content = "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("#"))
    return {m.strip() for m in re.split(r"[,;\r\n]+", content) if m.strip()}


def parse_manual_only_materials(folder: Path | None, filename: str) -> set[str]:
    raw = ""
    source = ""

    if folder is not None:
        material_file = folder / filename
        if material_file.exists():
            try:
                raw = material_file.read_text(encoding="utf-8-sig")
                source = str(material_file)
            except OSError as exc:
                logger.warning("Lỗi đọc %s: %s", material_file, exc)
        else:
            logger.warning("Không tìm thấy file %s", material_file)

    if not raw.strip():
        raw = os.environ.get(ENV_FALLBACK, "")
        if raw.strip():
            source = f"biến môi trường {ENV_FALLBACK}"
            logger.warning("Không đọc được nội dung từ %s — đang dùng biến môi trường thay thế. "
                           "Danh sách có thể đã cũ.", filename)

    materials = parse_material_list(raw)
    if materials:
        logger.info("Bổ sung %s mã hàng ngoài SAP (nguồn: %s): %s", len(materials), source, sorted(materials))
    else:
        logger.warning("Không tìm thấy mã bổ sung nào. Kiểm tra file %s.", filename)
    return materials
