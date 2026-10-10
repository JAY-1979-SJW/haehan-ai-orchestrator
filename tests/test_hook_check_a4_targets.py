"""hook_check_a4 훅이 부르는 점검 스크립트가 실제로 있어야 한다(P2 에서 check_a4.py 가 office/ 로 옮겨졌을 때 훅이 조용히 아무것도 안 하게 된 결함 방지)."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "tools" / "hooks" / "hook_check_a4.py"


def test_every_script_the_hook_runs_exists_next_to_the_office_tools():
    spec = importlib.util.spec_from_file_location("hook_check_a4_under_test", HOOK)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    names = sorted(set(re.findall(r'_run\("([\w]+\.py)"', HOOK.read_text(encoding="utf-8"))))
    assert names, "훅이 부르는 스크립트를 찾지 못했다(시험이 눈을 잃었다)"
    missing = [n for n in names if not (mod.OFFICE / n).is_file()]
    assert not missing, f"hook_check_a4 가 부르는 스크립트가 없다: {missing}"
