"""Module-scoped quality gate runner — 책임별 leaf 모듈 aggregator.

common/models/checks/runner 기능이 각 leaf 에 구현돼 있다.
직접 실행(`python tools/quality/module_quality_gate.py`) 또는
패키지 import(`import tools.quality.module_quality_gate`) 양쪽 모두 지원.
[docs/module_separation_standard.md]
"""

from __future__ import annotations

import os  # noqa: F401 — tests access gate.os
import shutil  # noqa: F401 — tests access gate.shutil
import subprocess  # noqa: F401 — tests access gate.subprocess
import sys

# 직접 실행 시 sys.path에 scripts/ 부모를 추가하여 상대 import를 절대 import로 대체
import sys as _sys
from pathlib import Path
from pathlib import Path as _Path

_BOOT = Path(__file__).resolve().parents[2]  # 정본을 import 하기 전 sys.path 부트스트랩(G5 예외: scripts/ 독립 실행)
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402

_ROOT = repo_root()
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

try:
    from tools.quality.module_quality_gate_exports import *  # noqa: F403
    from tools.quality.module_quality_gate_exports import (
        _is_secret_scan_excluded,
        _run_check_command,
        _source_contains,
    )
    from tools.quality.module_quality_gate_runner import CHECKS, main, print_module_list, run_step
    from tools.quality.module_quality_gate_modules import MODULES, iter_selected_steps, module_names, selected_modules
except ImportError:
    from tools.quality.module_quality_gate_exports import *  # noqa: F403
    from tools.quality.module_quality_gate_exports import (  # noqa: F401
        _is_secret_scan_excluded,
        _run_check_command,
        _source_contains,
    )
    from tools.quality.module_quality_gate_runner import CHECKS, main, print_module_list, run_step  # noqa: F401
    from tools.quality.module_quality_gate_modules import MODULES, iter_selected_steps, module_names, selected_modules  # noqa: F401

# py alias — tests access gate.py
py = PY  # noqa: F405

if __name__ == "__main__":
    raise SystemExit(main())
