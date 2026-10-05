"""CDP 브라우저 감시 로그 — 탭 생성·이동·종료를 JSONL 로 기록한다(읽기 전용).

브라우저 레벨 CDP 웹소켓에서 Target 이벤트만 구독한다. 페이지에 붙지 않고 Playwright 연결도
맺지 않으므로 자동화에 간섭하지 않는다. 설계: docs/specs/2026-09-30_browser_watch_log.md

사용법:
    python scripts/ops/browser_watch.py run      # 포그라운드 감시(Ctrl+C 로 종료)
    python scripts/ops/browser_watch.py start    # 분리 기동(이미 떠 있으면 생략)
    python scripts/ops/browser_watch.py stop
    python scripts/ops/browser_watch.py status
"""

from __future__ import annotations

import collections
import contextlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[2]
CDP_PORT = 9222
LOG_PATH = ROOT / "data" / "logs" / "browser_watch.jsonl"
PID_PATH = ROOT / "data" / "browser_watch_pid.json"

LOG_MAX_BYTES = 5 * 1024 * 1024
CHAIN_WINDOW_SEC = 60.0  # 한 탭이 이 시간 안에
CHAIN_MIN_DOMAINS = 5  # 서로 다른 도메인 이 개수 이상으로 이동하면 이상
MAX_TABS = 3  # 동시에 열린 page 탭이 이 개수를 넘으면 이상
RECONNECT_SEC = 2.0


def mask_url(url: str) -> str:
    """쿼리스트링 값을 가린다(토큰·인증코드 보호). 경로까지만 원문, fragment 는 버린다."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url[:300]
    query = urlencode([(k, "***") for k, _ in parse_qsl(parts.query, keep_blank_values=True)], safe="*")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))[:300]


def mask_title(title: str) -> str:
    """로드 전 탭 제목은 브라우저가 URL 문자열(스킴 없이)을 넣는다 — 그 경우 URL 과 같은 방식으로 가린다."""
    title = str(title)[:80]
    if " " not in title and ("?" in title or "/" in title):
        return mask_url("//" + title)[2:]
    return title


def _netloc(url: str) -> str:
    try:
        return urlsplit(url).netloc.lower()
    except ValueError:
        return ""


class WatchState:
    """CDP 이벤트 → 기록 dict 목록. 입출력이 없어 단위 시험이 가능하다."""

    def __init__(self) -> None:
        self._last_url: dict[str, str] = {}
        self._visits: dict[str, collections.deque[tuple[float, str]]] = {}
        self._chain_alerted_at: dict[str, float] = {}
        self._tabs_alerted = False

    def handle(self, msg: dict, now: float) -> list[dict]:
        method = msg.get("method", "")
        params = msg.get("params") or {}
        if method == "Target.targetDestroyed":
            tid = params.get("targetId", "")
            if tid not in self._last_url:  # page 가 아닌 대상(iframe·worker)은 기록하지 않는다
                return []
            for table in (self._last_url, self._visits, self._chain_alerted_at):
                table.pop(tid, None)
            return [{"event": "closed", "target_id": tid}]

        info = params.get("targetInfo") or {}
        if info.get("type") != "page" or method not in ("Target.targetCreated", "Target.targetInfoChanged"):
            return []
        tid, url = info.get("targetId", ""), info.get("url", "")
        opened = method == "Target.targetCreated"
        if not opened and self._last_url.get(tid) == url:
            return []  # 제목만 바뀐 경우
        self._last_url[tid] = url
        rec = {
            "event": "opened" if opened else "navigated",
            "target_id": tid,
            "url": mask_url(url),
            "title": mask_title(info.get("title", "")),
            "opener_id": info.get("openerId"),
        }
        out = [rec]
        out += self._check_tabs() if opened else []
        out += self._check_chain(tid, url, now)
        return out

    def _check_tabs(self) -> list[dict]:
        count = len(self._last_url)
        if count > MAX_TABS and not self._tabs_alerted:
            self._tabs_alerted = True
            return [{"event": "anomaly", "kind": "many_tabs", "tabs": count}]
        if count <= MAX_TABS:
            self._tabs_alerted = False
        return []

    def _check_chain(self, tid: str, url: str, now: float) -> list[dict]:
        host = _netloc(url)
        if not host:
            return []
        visits = self._visits.setdefault(tid, collections.deque())
        visits.append((now, host))
        while visits and now - visits[0][0] > CHAIN_WINDOW_SEC:
            visits.popleft()
        hosts = sorted({h for _, h in visits})
        if len(hosts) < CHAIN_MIN_DOMAINS:
            return []
        last = self._chain_alerted_at.get(tid)
        if last is not None and now - last <= CHAIN_WINDOW_SEC:
            return []
        self._chain_alerted_at[tid] = now
        return [{"event": "anomaly", "kind": "chain_navigation", "target_id": tid, "domains": hosts}]


class RotatingLog:
    """JSONL 기록기 — 한도를 넘으면 `.1` 로 회전(1세대만 유지)."""

    def __init__(self, path: Path, max_bytes: int = LOG_MAX_BYTES) -> None:
        self.path = path
        self.max_bytes = max_bytes

    def write(self, rec: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and self.path.stat().st_size >= self.max_bytes:
            self.path.replace(self.path.with_name(self.path.name + ".1"))
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **rec}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _browser_ws_url(port: int) -> str | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=3) as resp:
            return json.loads(resp.read()).get("webSocketDebuggerUrl")
    except Exception:  # noqa: BLE001 - 브라우저가 없거나 재시작 중이면 다음 주기에 재시도
        return None


def run(port: int = CDP_PORT, log_path: Path = LOG_PATH, stop_after: float | None = None) -> None:
    """감시 루프. 브라우저가 죽으면 조용히 재접속을 반복한다. stop_after 는 시험용 시간 제한(초)."""
    import websocket

    log = RotatingLog(log_path)
    deadline = None if stop_after is None else time.time() + stop_after
    while deadline is None or time.time() < deadline:
        ws_url = _browser_ws_url(port)
        if not ws_url:
            time.sleep(RECONNECT_SEC)
            continue
        state = WatchState()  # 재접속 시 대상 목록이 다시 들어오므로 상태를 새로 시작
        try:
            ws = websocket.create_connection(ws_url, timeout=1)
            ws.send(json.dumps({"id": 1, "method": "Target.setDiscoverTargets", "params": {"discover": True}}))
            while deadline is None or time.time() < deadline:
                try:
                    msg = json.loads(ws.recv())
                except websocket.WebSocketTimeoutException:
                    continue
                for rec in state.handle(msg, time.time()):
                    log.write(rec)
        except (websocket.WebSocketException, OSError, ValueError):
            time.sleep(RECONNECT_SEC)


def _read_pid() -> int | None:
    try:
        return int(json.loads(PID_PATH.read_text(encoding="utf-8"))["pid"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def is_running() -> bool:
    """PID 파일의 프로세스가 살아 있고 실제로 이 감시 프로세스인지(PID 재사용 방지) 확인."""
    import psutil

    pid = _read_pid()
    if pid is None or not psutil.pid_exists(pid):
        return False
    try:
        # 인자 중 파일 이름이 정확히 browser_watch.py 인 것이 있어야 한다(pytest tests/test_browser_watch.py 같은 우연 일치 배제)
        return any(Path(arg).name == "browser_watch.py" for arg in psutil.Process(pid).cmdline())
    except psutil.Error:  # NoSuchProcess(확인 사이 종료)·AccessDenied 모두 "확인 불가 = 아님"
        return False


def start() -> bool:
    """분리 기동. 이미 떠 있으면 False."""
    if is_running():
        return False
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "run"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
        cwd=str(ROOT),
    )
    PID_PATH.parent.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(json.dumps({"pid": proc.pid, "started_at": time.time()}), encoding="utf-8")
    return True


def stop() -> bool:
    """감시 프로세스 종료. 종료할 것이 없으면 False."""
    running = is_running()
    pid = _read_pid()
    if running and pid is not None:
        os.kill(pid, 9 if sys.platform == "win32" else 15)
    PID_PATH.unlink(missing_ok=True)
    return running


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "status"
    if cmd == "run":
        with contextlib.suppress(KeyboardInterrupt):
            run()
        return 0
    if cmd == "start":
        print("감시 시작" if start() else "이미 실행 중")
        return 0
    if cmd == "stop":
        print("감시 종료" if stop() else "실행 중이 아님")
        return 0
    if cmd == "status":
        print(f"browser_watch: {'실행 중' if is_running() else '중지'} (log={LOG_PATH})")
        return 0
    print("사용법: python scripts/ops/browser_watch.py [run|start|stop|status]")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
