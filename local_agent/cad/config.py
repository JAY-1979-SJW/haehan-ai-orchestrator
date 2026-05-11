"""Configuration for the local CAD adapter."""

from __future__ import annotations

import os
import sys
from pathlib import Path


DEFAULT_CAD_WORK_ROOT = Path(
    r"C:\Users\skyjw\OneDrive\03. PYTHON\14. CAD 산출 프로그램_WORK"
)


def get_cad_work_root() -> Path:
    configured = os.environ.get("HAEHAN_CAD_WORK_ROOT", "").strip()
    return Path(configured) if configured else DEFAULT_CAD_WORK_ROOT


def ensure_cad_work_on_path() -> Path:
    root = get_cad_work_root()
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return root
