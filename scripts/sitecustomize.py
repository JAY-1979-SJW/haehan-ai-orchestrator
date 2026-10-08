"""Keep direct script execution on repo-local temp and bytecode paths."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from common.runtime_temp import usable_temp_base  # type: ignore[import-not-found]  # scripts/ 가 sys.path[0] 일 때(직접 실행) 형제 패키지 common 을 바로 찾는다

ROOT = Path(__file__).resolve().parents[1]


def _repo_temp() -> Path:
    return usable_temp_base("python_runtime", "HAEHAN_WORKSPACE_TEMP")


temp_root = _repo_temp()
for key in ("TMP", "TEMP", "TMPDIR"):
    os.environ[key] = str(temp_root)

if "PYTHONPYCACHEPREFIX" not in os.environ:
    pycache = temp_root / "pycache"
    os.environ["PYTHONPYCACHEPREFIX"] = str(pycache)
    sys.pycache_prefix = str(pycache)
