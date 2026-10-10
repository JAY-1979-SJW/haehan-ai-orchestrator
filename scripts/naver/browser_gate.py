"""Naver CDP browser gate.

This module keeps Naver browser automation out of the sandbox and checks
that an already-running CDP browser enters login from naver.com.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
NAVER_CDP_HOST = os.environ.get("NAVER_CDP_HOST", "127.0.0.1")
NAVER_CDP_PORT = int(os.environ.get("NAVER_CDP_PORT", "9222"))
NAVER_DEFAULT_PROFILE_DIR = Path(
    os.environ.get("NAVER_CDP_PROFILE_DIR", str(ROOT / "data" / "browser_sessions" / "naver_parallel"))
)
NAVER_START_URL = "https://www.naver.com/"
DAEMON_STATE_FILE = ROOT / "data" / "cdp_daemon_state.json"

CODE_OK = "ok"
CODE_NOT_RUNNING = "not_running"
CODE_WRONG_BROWSER = "wrong_browser_conditions"
CODE_MULTIPLE = "multiple_naver_browsers"
CODE_DIRECT_LOGIN = "direct_login_entry"
CODE_SANDBOX_BLOCKED = "sandbox_browser_launch_blocked"

from scripts.browser.session.browser_cdp_selection_gate import (  # noqa: E402
    CODE_AMBIGUOUS_DOMAIN_SESSION,
    CODE_MIXED_DOMAIN_SESSION,
    CODE_NO_CDP,
    CODE_NO_DOMAIN_SESSION,
    discover_sessions,
)
from scripts.browser.session.browser_cdp_selection_gate import (  # noqa: E402
    CODE_OK as CDP_SELECT_OK,
)
from scripts.browser.session.browser_cdp_selection_gate import (  # noqa: E402
    evaluate_sessions as evaluate_cdp_sessions,
)
from scripts.browser.session.browser_sandbox_gate import (  # noqa: E402
    assert_browser_launch_allowed,
    is_sandboxed_runtime,
)


@dataclass
class BrowserGateReport:
    ok: bool
    code: str
    messages: list[str] = field(default_factory=list)
    matched_pids: list[int] = field(default_factory=list)
    cdp_available: bool = False
    tab_urls: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "code": self.code,
            "messages": self.messages,
            "matched_pids": self.matched_pids,
            "cdp_available": self.cdp_available,
            "tab_urls": self.tab_urls,
            "port": NAVER_CDP_PORT,
            "profile_required": False,
            "start_url": NAVER_START_URL,
        }


def _extract_arg(command_line: str, name: str) -> str:
    pattern = rf"--{re.escape(name)}(?:=|\s+)(\"[^\"]+\"|'[^']+'|\S+)"
    match = re.search(pattern, command_line)
    if not match:
        return ""
    return match.group(1).strip().strip('"').strip("'")


def command_matches_naver_browser(command_line: str) -> bool:
    port = _extract_arg(command_line, "remote-debugging-port")
    return port == str(NAVER_CDP_PORT)


def _is_direct_login_only(tab_urls: Iterable[str]) -> bool:
    urls = [url for url in tab_urls if url and not url.startswith("devtools://")]
    if not urls:
        return False
    has_naver_main = any(url.startswith(NAVER_START_URL) for url in urls)
    has_direct_login = any(url.startswith("https://nid.naver.com/nidlogin.login") for url in urls)
    return has_direct_login and not has_naver_main and len(urls) == 1


def evaluate_conditions(
    process_rows: Iterable[tuple[int, str]],
    *,
    cdp_available: bool,
    tab_urls: Iterable[str] = (),
) -> BrowserGateReport:
    matched = [int(pid) for pid, command_line in process_rows if command_matches_naver_browser(command_line)]
    tabs = list(tab_urls)
    if cdp_available and _is_direct_login_only(tabs):
        return BrowserGateReport(
            ok=False,
            code=CODE_DIRECT_LOGIN,
            messages=["Only direct nid.naver.com login entry is open; start from naver.com."],
            matched_pids=matched,
            cdp_available=True,
            tab_urls=tabs,
        )
    if len(matched) > 1:
        return BrowserGateReport(
            ok=False,
            code=CODE_MULTIPLE,
            messages=["Naver CDP browser has more than one matching parent process."],
            matched_pids=matched,
            cdp_available=cdp_available,
            tab_urls=tabs,
        )
    if len(matched) == 1:
        return BrowserGateReport(
            ok=True,
            code=CODE_OK,
            messages=["Naver CDP browser is available; profile is not enforced."],
            matched_pids=matched,
            cdp_available=cdp_available,
            tab_urls=tabs,
        )
    if cdp_available:
        return BrowserGateReport(
            ok=True,
            code=CODE_OK,
            messages=["CDP endpoint is available; process profile could not be verified and is not required."],
            cdp_available=True,
            tab_urls=tabs,
        )
    return BrowserGateReport(
        ok=False,
        code=CODE_NOT_RUNNING,
        messages=["Naver CDP browser is not running."],
        cdp_available=False,
        tab_urls=tabs,
    )


def _find_chrome_exe() -> str:
    # 이 파일은 정책(L2)으로 분류돼 L4 인 scripts.browser.session.browser_paths 를 import 할 수 없다(층 위반) → 같은 후보 순서를 여기에 유지한다.
    # 경로는 Windows 가 알려 주는 환경변수로 만든다(C: 가 아닌 드라이브에 설치된 PC 도 맞음). HAEHAN_CHROME_PATH 가 있으면 최우선.
    relative = Path("Google") / "Chrome" / "Application" / "chrome.exe"
    roots = [os.environ.get(name, "") for name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
    candidates = [os.environ.get("HAEHAN_CHROME_PATH", "").strip(), *(str(Path(root) / relative) for root in roots if root)]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise FileNotFoundError("Chrome executable was not found.")


def build_launch_command(
    chrome_exe: str | None = None,
    *,
    port: int = NAVER_CDP_PORT,
    profile_dir: str | Path | None = None,
) -> list[str]:
    exe = chrome_exe or _find_chrome_exe()
    profile = Path(profile_dir) if profile_dir is not None else NAVER_DEFAULT_PROFILE_DIR
    return [
        exe,
        f"--remote-debugging-port={int(port)}",
        "--remote-allow-origins=*",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-session-crashed-bubble",
        "--hide-crash-restore-bubble",
        "--disable-features=InfoBars,SessionCrashedBubble",
        # --restore-last-session 은 값과 무관하게 "있으면 이전 세션 복원"인 스위치라 =false 를 붙여도 복원된다(2026-10-05: 재시작 때마다 예전 YouTube·Gmail 탭이 되살아남). 복원을 막으려면 스위치를 아예 빼고 exit_type=Normal 로 정리한다.
        "--start-maximized",
        NAVER_START_URL,
    ]


def _ps_single_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _cdp_json(path: str, timeout: float = 2.0) -> Any:
    with urllib.request.urlopen(
        f"http://{NAVER_CDP_HOST}:{NAVER_CDP_PORT}{path}",
        timeout=timeout,
    ) as response:
        return json.loads(response.read().decode("utf-8") or "null")


def is_cdp_available() -> bool:
    try:
        _cdp_json("/json/version", timeout=1.0)
        return True
    except (OSError, urllib.error.URLError, TimeoutError):
        return False


def list_cdp_tab_urls() -> list[str]:
    try:
        rows = _cdp_json("/json/list", timeout=1.5)
    except Exception:  # noqa: BLE001 - 네이버 CDP 브라우저 실행 상태 게이트 — 탭목록/프로세스목록 조회 실패 시 모두 빈 결과를 반환해 '실행 중 아님' 방향에 수렴하고, 실제 브라우저 실행은 샌드박스 가드(assert_browser_launch_allowed) 통과 후에만 수행되어 이 폴백이 승인 우회로 이어지지 않음.
        return []
    if not isinstance(rows, list):
        return []
    return [str(row.get("url") or "") for row in rows if isinstance(row, dict) and row.get("type") == "page"]


def _chrome_processes_via_psutil() -> list[tuple[int, str]]:
    """psutil 기반 chrome/msedge 메인 프로세스 목록(예외는 호출부에서 폴백 처리)."""
    import psutil  # type: ignore

    rows: list[tuple[int, str]] = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = str(proc.info.get("name") or "").lower()
            if "chrome" not in name and "msedge" not in name:
                continue
            command = " ".join(proc.info.get("cmdline") or [])
            if "--type=" in command:
                continue
            rows.append((int(proc.info["pid"]), command))
        except Exception:  # noqa: BLE001 - 네이버 CDP 브라우저 실행 상태 게이트 — 탭목록/프로세스목록 조회 실패 시 모두 빈 결과를 반환해 '실행 중 아님' 방향에 수렴하고, 실제 브라우저 실행은 샌드박스 가드(assert_browser_launch_allowed) 통과 후에만 수행되어 이 폴백이 승인 우회로 이어지지 않음.
            continue
    return rows


def list_chrome_processes() -> list[tuple[int, str]]:
    try:
        return _chrome_processes_via_psutil()
    except Exception:  # noqa: BLE001 - 네이버 CDP 브라우저 실행 상태 게이트 — 탭목록/프로세스목록 조회 실패 시 모두 빈 결과를 반환해 '실행 중 아님' 방향에 수렴하고, 실제 브라우저 실행은 샌드박스 가드(assert_browser_launch_allowed) 통과 후에만 수행되어 이 폴백이 승인 우회로 이어지지 않음.
        pass

    if os.name != "nt":
        return []
    try:
        command = (
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.Name -in @('chrome.exe','msedge.exe') } | "
            "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=5,
            encoding="utf-8",
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        payload = json.loads(result.stdout)
        rows = payload if isinstance(payload, list) else [payload]
        out: list[tuple[int, str]] = []
        for row in rows:
            cmd = str(row.get("CommandLine") or "")
            if "--type=" in cmd:
                continue
            out.append((int(row.get("ProcessId") or 0), cmd))
        return out
    except Exception:  # noqa: BLE001 - 네이버 CDP 브라우저 실행 상태 게이트 — 탭목록/프로세스목록 조회 실패 시 모두 빈 결과를 반환해 '실행 중 아님' 방향에 수렴하고, 실제 브라우저 실행은 샌드박스 가드(assert_browser_launch_allowed) 통과 후에만 수행되어 이 폴백이 승인 우회로 이어지지 않음.
        return []


def inspect_gate() -> BrowserGateReport:
    selection = evaluate_cdp_sessions("naver", discover_sessions())
    if selection.code in {
        CDP_SELECT_OK,
        CODE_NO_CDP,
        CODE_NO_DOMAIN_SESSION,
        CODE_MIXED_DOMAIN_SESSION,
        CODE_AMBIGUOUS_DOMAIN_SESSION,
    }:
        all_urls = [
            page.get("url", "")
            for session in selection.to_dict().get("sessions", [])
            for page in session.get("pages", [])
        ]
        if selection.ok:
            return BrowserGateReport(
                ok=True,
                code=CODE_OK,
                messages=selection.messages,
                matched_pids=[],
                cdp_available=True,
                tab_urls=all_urls,
            )
        if selection.code == CODE_NO_CDP:
            return BrowserGateReport(
                ok=False,
                code=CODE_NOT_RUNNING,
                messages=selection.messages,
                cdp_available=False,
                tab_urls=[],
            )
        if selection.code == CODE_NO_DOMAIN_SESSION:
            return BrowserGateReport(
                ok=False,
                code=CODE_WRONG_BROWSER,
                messages=selection.messages,
                cdp_available=True,
                tab_urls=all_urls,
            )
        return BrowserGateReport(
            ok=False,
            code=selection.code,
            messages=selection.messages,
            cdp_available=True,
            tab_urls=all_urls,
        )
    return evaluate_conditions(
        list_chrome_processes(),
        cdp_available=is_cdp_available(),
        tab_urls=list_cdp_tab_urls(),
    )


def sandbox_blocked_report(report: BrowserGateReport | None = None) -> BrowserGateReport:
    base = report or inspect_gate()
    return BrowserGateReport(
        ok=False,
        code=CODE_SANDBOX_BLOCKED,
        messages=[
            "Naver browser launch is blocked inside the sandbox.",
            "Start a separate Naver CDP browser outside the sandbox, then rerun --once.",
        ],
        matched_pids=base.matched_pids,
        cdp_available=base.cdp_available,
        tab_urls=base.tab_urls,
    )


def _write_compat_daemon_state(pid: int) -> None:
    DAEMON_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "running": True,
        "pid": 0,
        "chrome_pid": int(pid),
        "cdp_port": NAVER_CDP_PORT,
        "browser_context": "active",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "last_heartbeat": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "last_error": "",
        "restart_count": 0,
        "browser_kind": "chrome",
        "browser_exe": "",
        "profile_dir": str(NAVER_DEFAULT_PROFILE_DIR),
    }
    DAEMON_STATE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def launch_naver_browser() -> int:
    assert_browser_launch_allowed(component="scripts.naver.browser_gate")
    NAVER_DEFAULT_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    command = build_launch_command()
    if os.name == "nt":
        exe = command[0]
        args = [
            *command[1:3],
            f'--user-data-dir="{NAVER_DEFAULT_PROFILE_DIR}"',
            *command[4:],
        ]
        ps_args = ",".join(_ps_single_quote(arg) for arg in args)
        ps = f"$p = Start-Process -FilePath {_ps_single_quote(exe)} -ArgumentList @({ps_args}) -PassThru; $p.Id"
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
        )
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "Start-Process failed").strip())
        pid = int((result.stdout or "0").strip().splitlines()[-1])
        _write_compat_daemon_state(pid)
        return pid

    proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _write_compat_daemon_state(proc.pid)
    return int(proc.pid)


def ensure_naver_browser(timeout_s: float = 15.0) -> BrowserGateReport:
    report = inspect_gate()
    if report.ok:
        return report
    if is_sandboxed_runtime():
        return sandbox_blocked_report(report)
    if report.code not in (CODE_NOT_RUNNING,):
        return report

    launch_naver_browser()
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(0.5)
        report = inspect_gate()
        if report.ok:
            return report
    return report


def require_naver_browser() -> None:
    report = ensure_naver_browser()
    if report.ok:
        return
    raise RuntimeError("Naver browser gate failed: " + json.dumps(report.to_dict(), ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    mode = args[0] if args else "--ensure"
    if mode == "--once":
        report = inspect_gate()
    elif mode == "--ensure":
        report = ensure_naver_browser()
    else:
        print("usage: python scripts/naver/browser_gate.py [--once|--ensure]", file=sys.stderr)
        return 2
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
