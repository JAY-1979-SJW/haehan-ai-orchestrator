"""Module-scoped quality gate runner — 책임별 leaf 모듈 aggregator.

common/models/checks/runner 기능이 각 leaf 에 구현돼 있다.
직접 실행(`python scripts/module_quality_gate.py`) 또는
패키지 import(`import scripts.module_quality_gate`) 양쪽 모두 지원.
[docs/module_separation_standard.md]
"""

from __future__ import annotations

import os  # noqa: F401 — tests access gate.os
import shutil  # noqa: F401 — tests access gate.shutil
import subprocess  # noqa: F401 — tests access gate.subprocess

# 직접 실행 시 sys.path에 scripts/ 부모를 추가하여 상대 import를 절대 import로 대체
import sys as _sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[1]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

try:
    from .module_quality_gate_exports import *  # noqa: F403
    from .module_quality_gate_exports import _is_secret_scan_excluded, _run_check_command, _source_contains
    from .module_quality_gate_runner import CHECKS, main, print_module_list, run_step
except ImportError:
    from scripts.module_quality_gate_exports import *  # noqa: F403
    from scripts.module_quality_gate_exports import (  # noqa: F401
        _is_secret_scan_excluded,
        _run_check_command,
        _source_contains,
    )
    from scripts.module_quality_gate_runner import CHECKS, main, print_module_list, run_step  # noqa: F401

# py alias — tests access gate.py
py = PY  # noqa: F405

if __name__ == "__main__":
    raise SystemExit(main())
