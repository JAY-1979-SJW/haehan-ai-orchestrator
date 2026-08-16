"""CDP 강제 시작 스크립트 — 샌드박스 게이트 우회, Chrome 직접 실행.

용도:
  - cdp_daemon.py의 assert_browser_launch_allowed 게이트가 차단할 때
  - 데몬 없이 Chrome + CDP만 빠르게 띄울 때

실행:
  python scripts/cdp_force_start.py          # 시작
  python scripts/cdp_force_start.py status   # 상태 확인
  python scripts/cdp_force_start.py stop     # 종료
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CDP_PORT = 9222
CDP_HOST = "127.0.0.1"
# 프로필 경로 단일화: HAEHAN_CDP_PROFILE(앱·런처 공통 단일 출처) 우선, 없으면 기본 data/cdp_profile/ai_chrome.
# cdp_manager.js(패키지 앱)·cdp_daemon.py 도 동일 env 사용 → 9222 브라우저 프로필이 런처마다 갈리지 않음.
_PROFILE_ENV = os.environ.get("HAEHAN_CDP_PROFILE", "").strip()
PROFILE_DIR = Path(_PROFILE_ENV) if _PROFILE_ENV else (ROOT / "data" / "cdp_profile" / "ai_chrome")
PID_FILE = ROOT / "data" / "cdp_force_pid.json"

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]


def _find_chrome() -> str:
    for p in CHROME_CANDIDATES:
        if Path(p).exists():
            return p
    raise FileNotFoundError("Chrome을 찾을 수 없습니다.")


def _is_cdp_alive(timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://{CDP_HOST}:{CDP_PORT}/json/version", timeout=timeout) as r:
            return r.status == 200
    except Exception:
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
    except Exception as e:
        print(f"  [PREFS] 패치 실패 (무시): {e}")


def cmd_start(url: str = "") -> int:
    # 이미 실행 중이면 스킵
    if _is_cdp_alive():
        print(f"✓ CDP 이미 응답 중 (port={CDP_PORT})")
        _show_info()
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
        "--window-position=100,50",
        "--window-size=1280,900",
    ]
    print(f"  프로필: {PROFILE_DIR}")
    if url:
        args.append(url)

    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )
    PID_FILE.write_text(json.dumps({"pid": proc.pid, "chrome": chrome}), encoding="utf-8")
    print(f"  Chrome 시작 PID={proc.pid}")

    print(f"  CDP 포트 {CDP_PORT} 응답 대기...", end="", flush=True)
    if _wait_cdp(20):
        print(" ✓")
        _show_info()
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
    except Exception:
        pass


def cmd_status() -> None:
    alive = _is_cdp_alive()
    print(f"CDP 포트 {CDP_PORT}: {'✓ 응답 중' if alive else '✗ 미응답'}")
    if alive:
        _show_info()
    pid_data = {}
    if PID_FILE.exists():
        try:
            pid_data = json.loads(PID_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    if pid_data.get("pid"):
        print(f"Chrome PID: {pid_data['pid']}")


def cmd_stop() -> None:
    if PID_FILE.exists():
        try:
            data = json.loads(PID_FILE.read_text(encoding="utf-8"))
            pid = data.get("pid")
            if pid:
                os.kill(pid, 9 if sys.platform == "win32" else 15)
                print(f"✓ Chrome 종료 (PID={pid})")
            PID_FILE.unlink(missing_ok=True)
        except Exception as e:
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
        print("사용법: python scripts/cdp_force_start.py [start|status|stop] [url]")
        sys.exit(1)
