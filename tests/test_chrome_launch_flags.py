"""Chrome 실행 인자 회귀 시험 — 2026-10-05 실측: `--restore-last-session=false` 를 넘겨 재시작 때마다 예전 탭이 되살아났다.

`restore-last-session` 은 값과 무관하게 스위치가 있으면 이전 세션을 복원한다(Chromium 의 HasSwitch 검사). 복원을 막으려면 스위치를 빼야 한다.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHERS = ("scripts/cdp_daemon.py", "scripts/cdp_force_start.py", "scripts/naver/browser_gate.py")


def test_chrome_launchers_never_pass_restore_last_session_switch():
    for rel in LAUNCHERS:
        lines = (ROOT / rel).read_text(encoding="utf-8").splitlines()
        args = [ln for ln in lines if re.search(r'^\s*"--[a-z-]+', ln)]
        assert args, f"{rel}: 검사할 Chrome 실행 인자를 하나도 찾지 못했습니다(시험이 공허해짐)"
        passed = [ln for ln in args if "--restore-last-session" in ln]
        assert not passed, f"{rel}: 이전 세션 복원 스위치를 인자로 넘기고 있습니다 — {passed}"
