"""Chrome 실행 인자 회귀 시험 — 이전 세션 복원 스위치의 올바른 형태.

2026-10-05 실측: 데몬이 `--restore-last-session=false` 를 넘겨 "복원 끄기"로 의도했지만 이 스위치는 값과 무관하게 있으면 켜진다 → 재시작마다 옛 탭이 되살아남.
실제 Chrome(임시 프로필)으로 비교해 보니 로그인(세션 쿠키) 유지에는 이 스위치(값 없이) + 정상 종료가 필요하다. 그래서 값 없는 스위치로 켜고
(`browser_lifecycle.RESTORE_SWITCH`) 복원된 옛 탭은 시작 직후 닫는다. 값을 붙인 형태는 어떤 실행 인자에도 없어야 한다.
"""

from __future__ import annotations

import re
from pathlib import Path

from scripts.browser.session import browser_lifecycle as lc

ROOT = Path(__file__).resolve().parents[2]
CDP_LAUNCHERS = ("scripts/browser/cdp/cdp_daemon.py", "scripts/browser/cdp/cdp_force_start.py")  # 로그인 유지가 필요한 9222 브라우저 실행 경로
ALL_LAUNCHERS = (*CDP_LAUNCHERS, "scripts/naver/browser_gate.py")


def _arg_lines(rel: str) -> list[str]:
    lines = (ROOT / rel).read_text(encoding="utf-8").splitlines()
    return [ln for ln in lines if re.search(r'^\s*(f?"--[a-z-]+|\*lifecycle\.session_args)', ln)]


def test_no_launcher_passes_the_switch_with_a_value():
    for rel in ALL_LAUNCHERS:
        args = _arg_lines(rel)
        assert args, f"{rel}: 검사할 Chrome 실행 인자를 하나도 찾지 못했습니다(시험이 공허해짐)"
        assert not [ln for ln in args if "restore-last-session=" in ln], f"{rel}: 값을 붙인 복원 스위치(=false 등)는 값과 무관하게 켜진다"


def test_cdp_launchers_use_the_bare_restore_switch_constant():
    for rel in CDP_LAUNCHERS:
        assert any("lifecycle.session_args(CDP_BROWSER_POLICY)" in ln for ln in _arg_lines(rel)), f"{rel}: 로그인 유지용 복원 스위치(정책)가 실행 인자에 없습니다"
    assert lc.RESTORE_SWITCH == "--restore-last-session"


def test_naver_browser_gate_does_not_restore_sessions():
    """네이버 시작 주소를 여는 별도 실행 경로는 복원 스위치를 쓰지 않는다(시작 주소만 열기)."""
    args = _arg_lines("scripts/naver/browser_gate.py")
    assert args, "검사할 Chrome 실행 인자를 하나도 찾지 못했습니다(시험이 공허해짐)"
    assert not [ln for ln in args if "restore-last-session" in ln or "RESTORE_SWITCH" in ln or "session_args" in ln]


def test_cdp_launchers_always_pass_a_custom_user_data_dir():
    """Chrome 136 부터 원격 디버깅 포트는 기본 프로필에서는 무시된다 — 반드시 별도 `--user-data-dir` 이 함께 있어야 한다(developer.chrome.com/blog/remote-debugging-port)."""
    for rel in CDP_LAUNCHERS:
        args = _arg_lines(rel)
        assert any("--remote-debugging-port" in ln for ln in args), f"{rel}: 원격 디버깅 포트 인자를 찾지 못했습니다(시험이 공허해짐)"
        assert any("--user-data-dir" in ln for ln in args), f"{rel}: --user-data-dir 가 없으면 Chrome 136+ 에서 디버깅 포트가 무시됩니다"


def test_cdp_launchers_apply_the_central_policy():
    """데몬·force_start 는 시작 정리·종료에서 설정의 정책(`CDP_BROWSER_POLICY`)을 그대로 쓴다 — 값이 코드에 흩어지지 않게(2026-10-05 구조화)."""
    from scripts.common.config import CDP_BROWSER_POLICY, CDP_START_URL, GOOGLE_URLS

    assert CDP_START_URL == CDP_BROWSER_POLICY["start_url"] == GOOGLE_URLS["home"] == "https://www.google.com/"
    for rel in CDP_LAUNCHERS:
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "apply_start_policy(CDP_PORT, CDP_BROWSER_POLICY)" in text, f"{rel}: 시작 정책을 적용하지 않습니다"
        assert 'graceful_first=CDP_BROWSER_POLICY["graceful_stop_first"]' in text, f"{rel}: 종료 정책을 적용하지 않습니다"
        assert "close_stale_tabs(" not in text, f"{rel}: 정책을 거치지 않고 탭 정리를 직접 부르고 있습니다"
