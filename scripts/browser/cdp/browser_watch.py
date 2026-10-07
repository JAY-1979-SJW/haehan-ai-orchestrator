"""CDP 브라우저 감시 로그 — 탭 생성·이동·종료와 브라우저 프로세스의 출현·소멸을 JSONL 로 기록한다(읽기 전용).

브라우저 레벨 CDP 웹소켓에서 Target 이벤트만 구독한다. 페이지에 붙지 않고 Playwright 연결도
맺지 않으므로 자동화에 간섭하지 않는다. 설계: docs/specs/2026-09-30_browser_watch_log.md

사용법:
    python scripts/browser/cdp/browser_watch.py run      # 포그라운드 감시(Ctrl+C 로 종료)
    python scripts/browser/cdp/browser_watch.py start    # 분리 기동(이미 떠 있으면 생략)
    python scripts/browser/cdp/browser_watch.py stop
    python scripts/browser/cdp/browser_watch.py status
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

ROOT = Path(__file__).resolve().parents[3]
CDP_PORT = 9222
LOG_PATH = ROOT / "data" / "logs" / "browser_watch.jsonl"
PID_PATH = ROOT / "data" / "browser_watch_pid.json"

LOG_MAX_BYTES = 5 * 1024 * 1024
CHAIN_WINDOW_SEC = 60.0  # 한 탭이 이 시간 안에
CHAIN_MIN_DOMAINS = 5  # 서로 다른 도메인 이 개수 이상으로 이동하면 이상
MAX_TABS = 3  # 동시에 열린 page 탭이 이 개수를 넘으면 이상
RECONNECT_SEC = 2.0
PROCESS_POLL_SEC = 1.0  # 브라우저 프로세스 점검 주기
RECENT_WINDOW_SEC = 90.0  # 브라우저가 사라지기 직전 이 시간 안에 시작된 프로세스를 기록한다(원인 후보)
RECENT_MAX = 40
CLIENT_SNAPSHOT_MIN_GAP_S = 5.0  # 탭 이동이 몰려도 연결 클라이언트 기록은 이 간격으로만 남긴다
_SCRIPT_SUFFIXES = (".py", ".js", ".cmd", ".bat", ".ps1", ".vbs")


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


# ── 브라우저 프로세스 감시 ─────────────────────────────────────────────────────
# 탭 이벤트만으로는 "브라우저가 언제·누구 때문에 사라졌는가"를 알 수 없다(2026-10-05: 검증 중 9222 Chrome 이 두 번 사라졌으나 원인 불명).
# 그래서 본체 프로세스의 출현·소멸 시각과, 소멸 직전에 시작된 프로세스(이름·스크립트 파일명만)를 같은 로그에 남긴다.


def script_name(cmdline: list[str]) -> str:
    """명령줄에서 스크립트 파일명만 뽑는다(경로·인자는 버린다 — 토큰·라이선스 같은 값이 로그에 남지 않게)."""
    for arg in cmdline[1:]:
        name = Path(arg.strip('"')).name
        if name.lower().endswith(_SCRIPT_SUFFIXES):
            return name
    return ""


def is_browser_main(cmdline: list[str], port: int) -> bool:
    """디버그 포트로 뜬 Chrome 본체(렌더러·GPU 같은 --type= 자식 제외)."""
    return any(f"--remote-debugging-port={port}" in a for a in cmdline) and not any(a.startswith("--type=") for a in cmdline)


def recent_processes(procs: list[dict], now: float, window: float = RECENT_WINDOW_SEC, limit: int = RECENT_MAX) -> list[dict]:
    """`window` 초 안에 시작된 프로세스(브라우저 자식·conhost 제외, 최신순)의 이름·스크립트 파일명만. 입출력 없는 순수 함수."""
    out = []
    for p in procs:
        cmd = p.get("cmdline") or []
        age = now - float(p.get("create_time", 0))
        name = str(p.get("name") or "")
        if age < 0 or age > window or name.lower() == "conhost.exe" or any(a.startswith("--type=") for a in cmd):
            continue
        out.append({"pid": p.get("pid"), "ppid": p.get("ppid"), "name": name, "script": script_name(cmd), "age_sec": round(age)})
    out.sort(key=lambda r: int(r["age_sec"] or 0))  # 최신(경과 시간이 짧은) 순
    return out[:limit]


class ProcessState:
    """브라우저 본체 PID 변화 → 기록 dict 목록. 입출력이 없어 단위 시험이 가능하다."""

    def __init__(self) -> None:
        self._pid: int | None = None
        self._seen = False

    def changed(self, main: dict | None) -> bool:
        """이번 점검 결과가 마지막으로 기록한 상태와 다른가(첫 점검에서 브라우저가 이미 있으면 기록 대상)."""
        pid = main["pid"] if main else None
        return pid != self._pid or (not self._seen and pid is not None)

    def observe(self, main: dict | None, procs: list[dict], now: float) -> list[dict]:
        pid = main["pid"] if main else None
        first, self._seen = not self._seen, True
        if pid == self._pid and not (first and pid is not None):
            return []
        prev, self._pid = self._pid, pid
        out: list[dict] = []
        if prev is not None:
            out.append({"event": "browser_process", "state": "vanished", "pid": prev, "recent_processes": recent_processes(procs, now)})
        if pid is not None and main is not None:
            parent = next((p for p in procs if p.get("pid") == main.get("ppid")), {})
            out.append(
                {
                    "event": "browser_process",
                    "state": "appeared",
                    "pid": pid,
                    "initial": first,
                    "parent": {"pid": main.get("ppid"), "name": parent.get("name", ""), "script": script_name(parent.get("cmdline") or [])},
                }
            )
        return out


def _snapshot_processes() -> list[dict]:
    """전체 프로세스 목록. Windows 에서 3초 안팎 걸리므로(2026-10-05 실측 360개 3.1초) 변화가 있을 때만 부른다."""
    import psutil

    procs: list[dict] = []
    for p in psutil.process_iter(["pid", "ppid", "name", "cmdline", "create_time"]):
        try:
            procs.append({**p.info, "cmdline": p.info.get("cmdline") or []})
        except psutil.Error:
            continue
    return procs


def _find_browser_main(port: int) -> dict | None:
    """가벼운 점검(평소 주기 호출): 이름이 chrome.exe/chrome 인 프로세스에서만 명령줄을 읽어 디버그 포트 본체를 찾는다(약 2ms)."""
    import psutil

    for p in psutil.process_iter(["pid", "name"]):
        try:
            if (p.info.get("name") or "").lower() not in ("chrome.exe", "chrome"):
                continue
            if is_browser_main(p.cmdline(), port):
                return {"pid": p.info["pid"], "ppid": p.ppid()}
        except psutil.Error:
            continue
    return None


def poll_process(state: ProcessState, port: int, log: RotatingLog, now: float) -> None:
    """본체 프로세스를 한 번 점검해 변화가 있을 때만(무거운) 전체 스냅샷을 찍어 기록한다. 오류는 모두 삼킨다(감시가 감시 루프를 죽이지 않게)."""
    try:
        main = _find_browser_main(port)
        if not state.changed(main):
            return
        for rec in state.observe(main, _snapshot_processes(), now):
            log.write(rec)
    except Exception:  # noqa: BLE001 - 보조 감시: 실패해도 탭 감시는 계속한다
        return


# ── 누가 이동시켰나: 탭 이동 순간의 연결 클라이언트 ────────────────────────────
# CDP 이벤트는 탭이 열리고 이동했다는 사실만 알려 주고 "누가"는 알려 주지 않는다(2026-10-05: 빈 탭이 80초 뒤 YouTube 검색으로 이동했으나 주체 불명).
# 이동이 일어난 바로 그 순간 디버그 포트에 연결돼 있는 프로세스(Playwright·자동화 스크립트)의 이름·스크립트 파일명을 같은 로그에 남긴다.


def cdp_clients(port: int, own_pid: int) -> list[dict]:
    """디버그 포트에 연결된 클라이언트 프로세스(브라우저 자신·이 감시 프로세스 제외)의 pid·이름·스크립트 파일명."""
    import psutil

    found: dict[int, dict] = {}
    try:
        conns = psutil.net_connections(kind="tcp")
    except (psutil.Error, OSError):
        return []
    for c in conns:
        if c.status != "ESTABLISHED" or not c.pid or c.pid == own_pid or not c.raddr or c.raddr.port != port:
            continue
        try:
            proc = psutil.Process(c.pid)
            name = proc.name()
            if name.lower() in ("chrome.exe", "chrome"):
                continue
            found[c.pid] = {"pid": c.pid, "name": name, "script": script_name(proc.cmdline())}
        except psutil.Error:
            continue
    return list(found.values())


def should_log_clients(records: list[dict], last_at: float, now: float, gap: float = CLIENT_SNAPSHOT_MIN_GAP_S) -> bool:
    """이번 기록에 탭 열림·이동이 있고, 마지막 클라이언트 기록 이후 gap 초가 지났는가(순수)."""
    return now - last_at >= gap and any(r.get("event") in ("opened", "navigated") for r in records)


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
    proc_state = ProcessState()
    last_poll = 0.0
    last_clients_at = 0.0
    deadline = None if stop_after is None else time.time() + stop_after
    while deadline is None or time.time() < deadline:
        poll_process(proc_state, port, log, time.time())
        last_poll = time.time()
        ws_url = _browser_ws_url(port)
        if not ws_url:
            time.sleep(RECONNECT_SEC)
            continue
        state = WatchState()  # 재접속 시 대상 목록이 다시 들어오므로 상태를 새로 시작
        try:
            ws = websocket.create_connection(ws_url, timeout=1)
            ws.send(json.dumps({"id": 1, "method": "Target.setDiscoverTargets", "params": {"discover": True}}))
            while deadline is None or time.time() < deadline:
                if time.time() - last_poll >= PROCESS_POLL_SEC:
                    poll_process(proc_state, port, log, time.time())
                    last_poll = time.time()
                try:
                    msg = json.loads(ws.recv())
                except websocket.WebSocketTimeoutException:
                    continue
                recs = state.handle(msg, time.time())
                for rec in recs:
                    log.write(rec)
                if recs and should_log_clients(recs, last_clients_at, time.time()):  # 탭이 열리거나 이동한 순간 누가 연결돼 있는지
                    last_clients_at = time.time()
                    log.write({"event": "cdp_clients", "clients": cdp_clients(port, os.getpid())})
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
    print("사용법: python scripts/browser/cdp/browser_watch.py [run|start|stop|status]")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
