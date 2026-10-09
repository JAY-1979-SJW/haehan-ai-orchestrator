from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

_BOOT = Path(__file__).resolve().parents[2]  # 정본을 import 하기 전 sys.path 부트스트랩(G5 예외: scripts/ 독립 실행)
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from core.agent_runtime.connection.network_bypass import urlopen_for_server  # noqa: E402
from scripts.common.app_paths import repo_root  # noqa: E402

ROOT = repo_root()
SERVER_URL = "https://haehan-ai.kr/orchestrator"
SERVER_HEALTH_URL = SERVER_URL + "/api/v1/health"
OUT_OF_SCOPE = {
    "scripts/archive/data/chrome_ui_monitor_state.json",
    "scripts/ops/check_naver_mail.py",
    "scripts/ops/check_remote_browser.py",
    "scripts/ops/naver_login_and_mail.py",
    "scripts/ops/verify_remote_browser.py",
}


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def pass_(self, name: str, detail: str = "") -> None:
        self.rows.append(("PASS", name, detail))

    def warn(self, name: str, detail: str = "") -> None:
        self.rows.append(("WARN", name, detail))

    def fail(self, name: str, detail: str = "") -> None:
        self.rows.append(("FAIL", name, detail))

    def result(self) -> str:
        if any(level == "FAIL" for level, _, _ in self.rows):
            return "FAIL_LOCAL_RUNTIME_DRY_RUN"
        if any(level == "WARN" for level, _, _ in self.rows):
            return "WARN_LOCAL_RUNTIME_DRY_RUN"
        return "PASS_LOCAL_RUNTIME_DRY_RUN"

    def print(self) -> None:
        for level, name, detail in self.rows:
            suffix = f" - {detail}" if detail else ""
            print(f"[{level}] {name}{suffix}")
        print(f"RESULT={self.result()}")


def _run(args: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: UP022
        args,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def _first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "")


def check_git(report: Report) -> None:
    staged = _run(["git", "diff", "--cached", "--name-only"])
    if staged.returncode != 0:
        report.warn("git staged check", "git unavailable")
        return
    staged_files = {line.strip().replace("\\", "/") for line in staged.stdout.splitlines()}
    leaked = sorted(staged_files & OUT_OF_SCOPE)
    if leaked:
        report.fail("OUT_OF_SCOPE not staged", ", ".join(leaked))
    else:
        report.pass_("OUT_OF_SCOPE not staged")


def check_portable_files(report: Report) -> None:
    for name in ("install.bat", "start.bat", "diagnostics.bat", "uninstall.bat"):
        if (ROOT / name).exists():
            report.pass_(f"portable file exists: {name}")
        else:
            report.fail(f"portable file missing: {name}")


def check_diagnostics_bat(report: Report) -> None:
    proc = _run(["cmd", "/c", str(ROOT / "diagnostics.bat")], timeout=60)
    if proc.returncode == 0:
        report.pass_("diagnostics.bat", _first_line(proc.stdout))
    else:
        report.fail("diagnostics.bat", _first_line(proc.stderr or proc.stdout))


def check_desktop_shortcut(report: Report) -> None:
    ps = (
        "$desktop=[Environment]::GetFolderPath('Desktop'); "
        "$lnk=Join-Path $desktop 'HaehanAI Desktop.lnk'; "
        "if (-not (Test-Path -LiteralPath $lnk)) { 'exists=False'; exit 0 }; "
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($lnk); "
        "'exists=True'; "
        "'target=' + $s.TargetPath; "
        "'working=' + $s.WorkingDirectory"
    )
    proc = _run(["powershell", "-NoProfile", "-Command", ps], timeout=30)
    if proc.returncode != 0:
        report.warn("desktop shortcut", "shortcut query failed")
        return
    lines = proc.stdout.splitlines()
    if "exists=True" not in lines:
        report.warn("desktop shortcut", "HaehanAI Desktop.lnk not found")
        return
    target = next((line[7:] for line in lines if line.startswith("target=")), "")
    if Path(target).name.lower() == "start.bat":
        report.pass_("desktop shortcut", "target=start.bat")
    else:
        report.warn("desktop shortcut", "target is not start.bat")


def check_desktop_exe(report: Report) -> None:
    exe = ROOT / "dist" / "HaehanAI-Desktop" / "HaehanAI-Desktop.exe"
    if not exe.exists():
        report.warn("desktop exe", "not found; portable start requires exe")
        return
    version = _run([str(exe), "--version"], timeout=30)
    if version.returncode == 0:
        report.pass_("desktop exe --version", _first_line(version.stdout))
    else:
        report.fail("desktop exe --version", _first_line(version.stderr or version.stdout))
        return
    diagnostics = _run([str(exe), "--diagnostics"], timeout=60)
    if diagnostics.returncode != 0:
        report.fail("desktop exe --diagnostics", _first_line(diagnostics.stderr or diagnostics.stdout))
        return
    try:
        data = json.loads(diagnostics.stdout)
    except json.JSONDecodeError:
        report.warn("desktop exe --diagnostics", "non-json output")
        return
    server = data.get("server", {}) if isinstance(data, dict) else {}
    heartbeat = data.get("heartbeat", {}) if isinstance(data, dict) else {}
    detail = f"server={server.get('url_redacted', '')} heartbeat={heartbeat.get('state', '')}"
    report.pass_("desktop exe --diagnostics", detail.strip())


def check_server(report: Report, *, live_server: bool) -> None:
    try:
        with socket.create_connection(("haehan-ai.kr", 443), timeout=5):
            report.pass_("server tcp 443", "haehan-ai.kr reachable")
    except OSError as exc:
        report.warn("server tcp 443", type(exc).__name__)

    if not live_server:
        report.pass_("server http health", "skipped in static mode; pass --live-server to check")
        return
    try:
        req = urllib.request.Request(SERVER_HEALTH_URL, method="GET")
        with urlopen_for_server(SERVER_URL, req, timeout=10) as resp:
            if resp.status == 200:
                report.pass_("server http health", "status=200")
            else:
                report.warn("server http health", f"status={resp.status}")
    except urllib.error.HTTPError as exc:
        report.warn("server http health", f"status={exc.code}")
    except urllib.error.URLError as exc:
        report.warn("server http health", type(exc.reason).__name__)
    except OSError as exc:
        report.warn("server http health", type(exc).__name__)


def check_playwright(report: Report) -> None:
    from core.agent_runtime.runtime.playwright.playwright_bootstrap import check_playwright_status

    status = check_playwright_status()
    state = status.get("status")
    version = status.get("package_version")
    if state == "PLAYWRIGHT_READY":
        report.pass_("playwright", f"version={version} browser_available=True")
    else:
        report.warn("playwright", f"{state}: {status.get('message_ko', '')}")


def check_asyncio_subprocess(report: Report) -> None:
    code = (
        "import asyncio, sys\n"
        "async def main():\n"
        "    p = await asyncio.create_subprocess_exec("
        "sys.executable, '-c', 'print(123)', "
        "stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)\n"
        "    out, err = await p.communicate()\n"
        "    print(p.returncode)\n"
        "asyncio.run(main())\n"
    )
    proc = _run([sys.executable, "-c", code], timeout=30)
    output = proc.stdout + "\n" + proc.stderr
    if proc.returncode == 0:
        report.pass_("python asyncio subprocess")
        return
    if "WinError 5" in output or "PermissionError" in output:
        report.warn("python asyncio subprocess", "PERMISSION_DENIED")
        return
    report.warn("python asyncio subprocess", _first_line(proc.stderr or proc.stdout) or f"exit_code={proc.returncode}")


def check_agent_ws_auth(report: Report) -> None:
    proc = _run(
        [
            sys.executable,
            "verify_agent_ws_auth.py",
            "--server",
            SERVER_URL,
            "--timeout",
            "15",
        ],
        timeout=45,
    )
    output = proc.stdout + "\n" + proc.stderr
    if "RESULT=PASS_AGENT_WS_AUTH" in output:
        status = next(
            (line for line in proc.stdout.splitlines() if line.startswith("ws_auth_status=")), "ws_auth_status=AUTH_OK"
        )
        report.pass_("agent websocket auth", status.split("=", 1)[1])
    else:
        status = next(
            (line for line in output.splitlines() if line.startswith("ws_auth_status=")), "ws_auth_status=UNKNOWN"
        )
        report.warn("agent websocket auth", status.split("=", 1)[1])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-server", action="store_true")
    parser.add_argument("--skip-playwright", action="store_true")
    args = parser.parse_args(argv)

    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    report = Report()
    check_git(report)
    check_portable_files(report)
    check_diagnostics_bat(report)
    check_desktop_shortcut(report)
    check_desktop_exe(report)
    check_server(report, live_server=args.live_server)
    if args.skip_playwright:
        report.pass_("playwright", "skipped; verified by release runtime gate")
    else:
        check_asyncio_subprocess(report)
        check_playwright(report)
    check_agent_ws_auth(report)
    report.print()
    return 1 if report.result().startswith("FAIL") else 0


if __name__ == "__main__":
    raise SystemExit(main())
