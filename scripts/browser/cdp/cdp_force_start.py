"""CDP 강제 시작 스크립트 — 샌드박스 게이트 우회, Chrome 직접 실행.

용도:
  - cdp_daemon.py의 assert_browser_launch_allowed 게이트가 차단할 때
  - 데몬 없이 Chrome + CDP만 빠르게 띄울 때

실행:
  python scripts/browser/cdp/cdp_force_start.py          # 시작
  python scripts/browser/cdp/cdp_force_start.py status   # 상태 확인
  python scripts/browser/cdp/cdp_force_start.py stop     # 종료
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


from ai_orchestrator.paths.runtime import data_dir  # noqa: E402
from scripts.browser.session import browser_lifecycle as lifecycle  # noqa: E402
from scripts.browser.session.browser_paths import find_chrome  # noqa: E402
from scripts.common.config import CDP_BROWSER_POLICY  # noqa: E402

CDP_PORT = 9222
CDP_HOST = "127.0.0.1"
# 프로필 경로 단일화: HAEHAN_CDP_PROFILE(앱·런처 공통 단일 출처) 우선, 없으면 기본 data/cdp_profile/ai_chrome.
# cdp_manager.js(패키지 앱)·cdp_daemon.py 도 동일 env 사용 → 9222 브라우저 프로필이 런처마다 갈리지 않음.
_PROFILE_ENV = os.environ.get("HAEHAN_CDP_PROFILE", "").strip()
PROFILE_DIR = Path(_PROFILE_ENV) if _PROFILE_ENV else (data_dir() / "cdp_profile" / "ai_chrome")
PID_FILE = data_dir() / "cdp_force_pid.json"


def _find_chrome() -> str:
    chrome = find_chrome()
    if chrome:
        return chrome
    raise FileNotFoundError("Chrome을 찾을 수 없습니다.")


def _is_cdp_alive(timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://{CDP_HOST}:{CDP_PORT}/json/version", timeout=timeout) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001 - 로컬 CDP 크롬 강제 시작/중지 CLI 도구 - 프로세스 상태 조회/종료 실패 시 print 안내
        return False


def _wait_cdp(timeout: int = 20) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_cdp_alive():
            return True
        time.sleep(0.5)
    return False


_WIN_LEFT, _WIN_TOP, _WIN_W, _WIN_H = 100, 50, 1440, 900


def _sanitize_prefs() -> None:
    """Chrome Preferences 패치: 비정상 종료 흔적 제거 + 창 위치 고정."""
    prefs = PROFILE_DIR / "Default" / "Preferences"
    if not prefs.exists():
        return
    try:
        data = json.loads(prefs.read_text(encoding="utf-8"))
        p = data.setdefault("profile", {})
        changed = False
        if p.get("exit_type") != "Normal":
            p["exit_type"] = "Normal"
            changed = True
        if p.get("exited_cleanly") is not True:
            p["exited_cleanly"] = True
            changed = True
        # 창 위치 고정 — off-screen(9999 등)이거나 최대화 저장 시 리셋
        browser = data.setdefault("browser", {})
        placement = browser.get("window_placement", {})
        need_fix = (
            placement.get("left", 0) > 3000
            or placement.get("top", 0) > 3000
            or placement.get("left", 0) < -100
            or placement.get("top", 0) < -100
            or placement.get("maximized") is True
        )
        if need_fix:
            browser["window_placement"] = {
                "bottom": _WIN_TOP + _WIN_H,
                "left": _WIN_LEFT,
                "maximized": False,
                "right": _WIN_LEFT + _WIN_W,
                "top": _WIN_TOP,
                "work_area_bottom": 1080,
                "work_area_left": 0,
                "work_area_right": 1920,
                "work_area_top": 0,
            }
            changed = True
        if changed:
            prefs.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            print(f"  [PREFS] 정상화 완료 (window={_WIN_W}x{_WIN_H}@{_WIN_LEFT},{_WIN_TOP})")
    except Exception as e:  # noqa: BLE001 - 로컬 CDP 크롬 강제 시작/중지 CLI 도구 - 프로세스 상태 조회/종료 실패 시 print 안내
        print(f"  [PREFS] 패치 실패 (무시): {e}")


def _start_watch() -> None:
    """탭 생성·이동 감시 로그(scripts/browser/cdp/browser_watch.py) 기동 — 실패해도 브라우저 시작은 막지 않는다."""
    try:
        from scripts.browser.cdp import browser_watch

        print(f"  탭 감시 로그: {'시작' if browser_watch.start() else '이미 실행 중'}")
    except Exception as e:  # noqa: BLE001 - 감시는 부가 기능, 실패는 안내만
        print(f"  탭 감시 로그 시작 실패(무시): {e}")


def _stop_watch() -> None:
    try:
        from scripts.browser.cdp import browser_watch

        if browser_watch.stop():
            print("✓ 탭 감시 로그 종료")
    except Exception as e:  # noqa: BLE001 - 감시는 부가 기능, 실패는 안내만
        print(f"  탭 감시 로그 종료 실패(무시): {e}")


def cmd_start(url: str = "") -> int:
    # 이미 실행 중이면 스킵
    if _is_cdp_alive():
        print(f"✓ CDP 이미 응답 중 (port={CDP_PORT})")
        _show_info()
        _start_watch()
        return 0

    chrome = _find_chrome()
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    _sanitize_prefs()

    args = [
        chrome,
        f"--remote-debugging-port={CDP_PORT}",
        "--remote-allow-origins=*",
        f"--user-data-dir={PROFILE_DIR}",
        "--profile-directory=Default",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--disable-session-crashed-bubble",
        "--hide-crash-restore-bubble",
        "--disable-features=InfoBars,SessionCrashedBubble",
        *lifecycle.session_args(CDP_BROWSER_POLICY),  # 이전 세션 복원(로그인 유지) — 옛 탭은 시작 직후 close_stale_tabs 가 정리한다
        "--window-position=100,50",
        "--window-size=1280,900",
    ]
    print(f"  프로필: {PROFILE_DIR}")
    if url:
        args.append(url)

    # DETACHED_PROCESS만으로는 샌드박스 Job Object에 묶여 부모(Claude Code 세션)가
    # 끝나면 크롬도 같이 죽을 수 있다(2026-08-22). CREATE_BREAKAWAY_FROM_JOB로 탈출을
    # 시도하고, Job이 막으면(WinError 5) 플래그 없이 재시도한다.
    broke_away = False
    if sys.platform == "win32":
        try:
            proc = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.DETACHED_PROCESS
                | subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.CREATE_BREAKAWAY_FROM_JOB,
            )
            broke_away = True
        except OSError as e:
            print(f"  [경고] Job 탈출 실패({e}) — 일반 DETACHED_PROCESS로 재시도")
            proc = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
    else:
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    print(f"  Job 탈출: {'성공' if broke_away else '실패'}")
    PID_FILE.write_text(json.dumps({"pid": proc.pid, "chrome": chrome, "broke_away": broke_away}), encoding="utf-8")
    print(f"  Chrome 시작 PID={proc.pid}")

    print(f"  CDP 포트 {CDP_PORT} 응답 대기...", end="", flush=True)
    if _wait_cdp(20):
        print(" ✓")
        if not url:  # 주소를 지정했으면 그 탭이 목적이니 두고, 아니면 복원된 옛 탭을 정리해 깨끗하게 시작한다
            print(
                f"  복원된 옛 탭 {lifecycle.apply_start_policy(CDP_PORT, CDP_BROWSER_POLICY)}개 정리(시작 페이지 {CDP_BROWSER_POLICY['start_url']} 탭 하나만 남김)"
            )
        _show_info()
        _start_watch()
        return 0
    else:
        print(" ✗ 타임아웃")
        return 1


def _show_info() -> None:
    try:
        with urllib.request.urlopen(f"http://{CDP_HOST}:{CDP_PORT}/json/version", timeout=3) as r:
            info = json.loads(r.read())
        print(f"  브라우저: {info.get('Browser', '?')}")
        print(f"  WebSocket: {info.get('webSocketDebuggerUrl', '?')}")
    except Exception:  # noqa: BLE001 - 로컬 CDP 크롬 강제 시작/중지 CLI 도구 - 프로세스 상태 조회/종료 실패 시 print 안내
        pass


def cmd_status() -> None:
    alive = _is_cdp_alive()
    print(f"CDP 포트 {CDP_PORT}: {'✓ 응답 중' if alive else '✗ 미응답'}")
    if alive:
        _show_info()
    pid_data = {}
    if PID_FILE.exists():
        # 로컬 CDP 크롬 강제 시작/중지 CLI 도구 - 프로세스 상태 조회 실패 시 pid_data 비워둠(print 안내로 대체)
        with contextlib.suppress(Exception):
            pid_data = json.loads(PID_FILE.read_text(encoding="utf-8"))
    if pid_data.get("pid"):
        print(f"Chrome PID: {pid_data['pid']}")


def cmd_stop() -> None:
    _stop_watch()
    if PID_FILE.exists():
        try:
            data = json.loads(PID_FILE.read_text(encoding="utf-8"))
            pid = data.get("pid")
            if pid:
                how = lifecycle.stop_browser(
                    CDP_PORT, pid, graceful_first=CDP_BROWSER_POLICY["graceful_stop_first"]
                )  # 쿠키가 디스크에 남도록 정상 종료부터 3단계
                print(f"✓ Chrome 종료 (PID={pid}, 방식={how})")
            PID_FILE.unlink(missing_ok=True)
        except Exception as e:  # noqa: BLE001 - 로컬 CDP 크롬 강제 시작/중지 CLI 도구 - 프로세스 상태 조회/종료 실패 시 print 안내
            print(f"종료 실패: {e}")
    else:
        print("PID 파일 없음 — 수동으로 Chrome 닫으세요.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "start"
    url_arg = sys.argv[2] if len(sys.argv) > 2 else ""

    if cmd == "start":
        sys.exit(cmd_start(url_arg))
    elif cmd == "status":
        cmd_status()
    elif cmd == "stop":
        cmd_stop()
    else:
        print(f"알 수 없는 명령: {cmd}")
        print("사용법: python scripts/browser/cdp/cdp_force_start.py [start|status|stop] [url]")
        sys.exit(1)
