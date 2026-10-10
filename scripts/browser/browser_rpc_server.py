"""브라우저 RPC 서버 — Playwright 연결을 프로세스 간에 계속 살려둔다.

문제: 지금까지는 Bash 호출(= 매번 새 파이썬 프로세스)마다
`sync_playwright().start()` + `connect_over_cdp()`를 새로 했다.
`web_connector.py`의 캐시(`_BROWSER_CONTEXT_CACHE` 등)는 프로세스 전역
변수라서, 프로세스가 매번 새로 뜨는 이 패턴에서는 캐시 효과가 전혀 없었다
(2026-08-22 확인). 이게 "frame has been detached", 탭 유실 같은 문제의
근본 원인 중 하나.

해결: 이 서버 하나만 Playwright 연결을 한 번 맺어서 계속 들고 있고,
클라이언트(각 Bash 호출)는 로컬 TCP로 명령만 보낸다.

실행:
    python scripts/browser/browser_rpc_server.py start   # 백그라운드 시작
    python scripts/browser/browser_rpc_server.py status
    python scripts/browser/browser_rpc_server.py stop

클라이언트 사용(스크립트 안에서):
    from scripts.browser.cdp.browser_rpc_client import rpc
    rpc("goto", url="https://blog.naver.com/skyjwsin")
    text = rpc("text")["result"]
    rpc("click", selector="text=삭제")
"""

from __future__ import annotations

import json
import socket
import socketserver
import subprocess
import sys
import threading
import time
from contextlib import suppress
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.common.logger import get_logger  # noqa: E402

_log = get_logger(__name__)

RPC_HOST = "127.0.0.1"
RPC_PORT = 8899
PID_FILE = ROOT / "data" / "browser_rpc_pid.json"
LOG_FILE = ROOT / "data" / "browser_rpc_server.log"

_page_lock = threading.Lock()
_current_page = None  # 도메인 재사용 없이 단일 페이지 핸들 — get_domain_page 로 매번 교체


def _get_page(url: str | None = None):
    """web_connector의 get_domain_page/get_page 로직을 그대로 재사용."""
    global _current_page
    from scripts.browser.cdp.connection import get_page
    from scripts.browser.page.web_connector import get_domain_page

    if url:
        page = get_domain_page(url)
        page.goto(url, timeout=30000)
    else:
        page = get_page()
    _current_page = page
    return page


class _Handler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            raw = self.rfile.readline()
            if not raw:
                return
            req = json.loads(raw.decode("utf-8"))
            cmd = req.get("cmd")
            with _page_lock:
                result = self._dispatch(cmd, req)
            self.wfile.write((json.dumps(result, ensure_ascii=False) + "\n").encode("utf-8"))
        except Exception as e:  # noqa: BLE001 - 브라우저 RPC 서버 - 명령 처리 실패를 JSON 에러 응답으로 변환, 탭 재사용 실패 시 새 탭으로 대체
            with suppress(Exception):
                self.wfile.write((json.dumps({"ok": False, "error": str(e)}) + "\n").encode("utf-8"))

    @staticmethod
    def _cmd_goto(req: dict) -> dict:
        global _current_page
        url = req["url"]
        try:
            page = _get_page(url)
        except Exception as e:
            if "detached" not in str(e).lower():
                raise
            # 재사용하려던 탭이 죽어있음(2026-08-22 실측) — 새 탭으로 강제 교체.
            _log.warning("[browser-rpc] 탭 detached — 새 탭으로 재시도: %s", url)
            from scripts.browser.cdp.connection import open_page

            page = open_page(allow_new_tab=True, reason="rpc-detached-retry")
            page.goto(url, timeout=30000)
            _current_page = page
        time.sleep(float(req.get("wait", 1.5)))
        return {"ok": True, "result": page.url}

    @staticmethod
    def _cmd_page(cmd: str, req: dict) -> dict:
        page = _current_page or _get_page()
        if cmd == "text":
            return {"ok": True, "result": page.inner_text("body")}
        if cmd == "eval":
            return {"ok": True, "result": page.evaluate(req["js"])}
        if cmd == "click":
            sel = req["selector"]
            if sel.startswith("text="):
                page.get_by_text(sel[5:], exact=req.get("exact", False)).first.click(timeout=req.get("timeout", 5000))
            else:
                page.locator(sel).first.click(timeout=req.get("timeout", 5000))
            return {"ok": True, "result": "clicked"}
        if cmd == "fill":
            page.fill(req["selector"], req["value"])
            return {"ok": True, "result": "filled"}
        # screenshot
        out = req.get("path", str(ROOT / "data" / "browser_rpc_shot.png"))
        page.screenshot(path=out, timeout=req.get("timeout", 15000))
        return {"ok": True, "result": out}

    def _dispatch(self, cmd: str, req: dict) -> dict:
        try:
            if cmd == "ping":
                return {"ok": True, "result": "pong"}

            if cmd == "goto":
                return self._cmd_goto(req)

            if cmd in ("text", "eval", "click", "fill", "screenshot"):
                return self._cmd_page(cmd, req)

            return {"ok": False, "error": f"unknown cmd: {cmd}"}
        except Exception as e:  # noqa: BLE001 - 브라우저 RPC 서버 - 명령 처리 실패를 JSON 에러 응답으로 변환, 탭 재사용 실패 시 새 탭으로 대체
            return {"ok": False, "error": str(e)}


class _Server(socketserver.TCPServer):
    # Playwright sync API는 그걸 만든 스레드에서만 써야 한다("cannot switch to
    # a different thread" 예외, 2026-08-22 실측). ThreadingTCPServer는 연결마다
    # 새 스레드를 만들어서 이 제약을 깬다 — 반드시 단일 스레드(순차 처리)로 돌린다.
    allow_reuse_address = True


def _run_server():
    srv = _Server((RPC_HOST, RPC_PORT), _Handler)
    _log.info("[browser-rpc] 서버 시작 %s:%s", RPC_HOST, RPC_PORT)
    srv.serve_forever()


def _is_alive() -> bool:
    try:
        with socket.create_connection((RPC_HOST, RPC_PORT), timeout=2) as s:
            s.sendall((json.dumps({"cmd": "ping"}) + "\n").encode())
            resp = s.recv(4096)
            return b"pong" in resp
    except Exception:  # noqa: BLE001 - 브라우저 RPC 서버 - 명령 처리 실패를 JSON 에러 응답으로 변환, 탭 재사용 실패 시 새 탭으로 대체
        return False


def cmd_start():
    if _is_alive():
        print(f"✓ 이미 실행 중 (port={RPC_PORT})")
        return
    log_f = LOG_FILE.open("a", encoding="utf-8")
    args = [sys.executable, str(Path(__file__).resolve()), "_run"]
    broke_away = False
    if sys.platform == "win32":
        # DETACHED_PROCESS만으로는 샌드박스 Job Object에 묶여 있으면 부모(Claude
        # Code 세션)가 끝날 때 같이 죽는다(2026-08-22). CREATE_BREAKAWAY_FROM_JOB로
        # 탈출을 시도하고, Job이 허용 안 하면(WinError 5) 플래그 없이 재시도한다 —
        # 이 성공/실패 자체가 "정말 살아남는지"의 실측 근거가 된다.
        try:
            proc = subprocess.Popen(
                args,
                stdout=log_f,
                stderr=log_f,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.DETACHED_PROCESS
                | subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.CREATE_BREAKAWAY_FROM_JOB,
            )
            broke_away = True
        except OSError as e:
            print(f"  [경고] Job 탈출 실패({e}) — 일반 DETACHED_PROCESS로 재시도")
            proc = subprocess.Popen(
                args,
                stdout=log_f,
                stderr=log_f,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
    else:
        proc = subprocess.Popen(args, stdout=log_f, stderr=log_f, stdin=subprocess.DEVNULL, start_new_session=True)
    print(f"  Job 탈출: {'성공' if broke_away else '실패(부모 세션 종료 시 같이 죽을 수 있음)'}")
    PID_FILE.write_text(json.dumps({"pid": proc.pid, "broke_away": broke_away}), encoding="utf-8")
    for _ in range(20):
        if _is_alive():
            print(f"✓ 시작됨 PID={proc.pid} port={RPC_PORT}")
            return
        time.sleep(0.5)
    print("✗ 시작 실패 — 로그 확인:", LOG_FILE)


def cmd_status():
    if _is_alive():
        print(f"✓ 응답 중 (port={RPC_PORT})")
    else:
        print("✗ 응답 없음")


def cmd_stop():
    import os

    if not PID_FILE.exists():
        print("PID 파일 없음 — 이미 정지 상태일 수 있음")
        return
    data = json.loads(PID_FILE.read_text(encoding="utf-8"))
    try:
        os.kill(data["pid"], 9 if sys.platform == "win32" else 15)
        print(f"정지됨 PID={data['pid']}")
    except Exception as e:  # noqa: BLE001 - 브라우저 RPC 서버 - 명령 처리 실패를 JSON 에러 응답으로 변환, 탭 재사용 실패 시 새 탭으로 대체
        print(f"정지 실패(무시): {e}")
    PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "start"
    if action == "_run":
        _run_server()
    elif action == "start":
        cmd_start()
    elif action == "status":
        cmd_status()
    elif action == "stop":
        cmd_stop()
    else:
        print("사용: python scripts/browser/browser_rpc_server.py [start|status|stop]")
