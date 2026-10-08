"""scripts/ops/desktop_fresh_run.ps1 — '빈 PC처럼' 실행 도구 시험 (Windows PowerShell 필요, 없으면 건너뜀).

실제 앱 대신 가짜 앱(8401 포트를 잠깐 여는 파이썬)으로 전체 흐름을 확인한다: 임시 userData 로 실행 → 서버 감지 → 종료 감지 → 요약.
"""

from __future__ import annotations

import shutil
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ops" / "desktop_fresh_run.ps1"
PS = shutil.which("powershell") or shutil.which("pwsh")

pytestmark = pytest.mark.skipif(PS is None or sys.platform != "win32", reason="Windows PowerShell 이 필요하다")


def run_ps(*args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(PS), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def make_user_data(root: Path) -> Path:
    ud = root / "userData"
    (ud / "storage").mkdir(parents=True)
    (ud / "data").mkdir()
    (ud / "mcp" / "20261008-abc1234").mkdir(parents=True)
    (ud / "mcp" / "20261008-abc1234" / "haehan-mcp.exe").write_bytes(b"x")
    (ud / "logs").mkdir()
    (ud / "logs" / "fastapi.log").write_text("INFO ok\nERROR boom\n", encoding="utf-8")
    (ud / "data" / "a.json").write_text("{}", encoding="utf-8")
    secret = "s3cr3t" * 12
    (ud / "config.json").write_text(
        '{"jwt_secret": "'
        + secret
        + '", "auth_token": "tok-abc", "owner_mode": true, "claude_mcp": {"prompted": true}}',
        encoding="utf-8",
    )
    con = sqlite3.connect(str(ud / "storage" / "users.db"))
    con.execute(
        "create table users(id text, email text, name text, password_hash text, role text, plan text, created_at text, enabled int, last_session_at text)"
    )
    con.execute("insert into users values('1','hong@example.com','홍길동','x','owner','free','2026',1,'2026-10-07')")
    con.commit()
    con.close()
    return ud


def test_summary_only_reports_everything_and_never_prints_secrets(tmp_path):
    make_user_data(tmp_path)
    r = run_ps("-SummaryOnly", "-WorkDir", str(tmp_path))
    out = r.stdout
    assert r.returncode == 0, r.stderr
    assert "jwt_secret" in out and "(설정됨, 72자)" in out  # 값이 아니라 설정 여부와 길이만
    assert "s3cr3t" not in out and "tok-abc" not in out
    assert "owner_mode" in out and "True" in out
    assert "data  (업무 데이터)" in out and "a.json" in out
    assert "계정 1명" in out and "h***@example.com" in out and "role=owner" in out  # 이메일은 마스킹
    assert "hong@example.com" not in out and "홍길동" not in out
    assert "20261008-abc1234" in out and "exe 있음" in out  # mcp 고정 폴더
    assert "오류성 줄 1개" in out and "ERROR boom" in out
    assert "config.json.corrupt-*" in out and "없음" in out


def test_summary_flags_corrupt_config_and_leftover_pid(tmp_path):
    ud = make_user_data(tmp_path)
    (ud / "config.json.corrupt-2026-10-07T00-00-00-000Z").write_text("{broken", encoding="utf-8")
    (ud / "run").mkdir()
    (ud / "run" / "fastapi.pid").write_text("{}", encoding="utf-8")
    out = run_ps("-SummaryOnly", "-WorkDir", str(tmp_path)).stdout
    assert "config.json.corrupt-2026" in out and "⚠" in out
    assert "남아 있음: fastapi.pid" in out


def test_dry_run_prints_plan_and_creates_nothing(tmp_path):
    exe = tmp_path / "HaehanAI-20261008-abc1234-portable.exe"
    exe.write_bytes(b"MZ")
    work = tmp_path / "work"
    r = run_ps("-ExePath", str(exe), "-WorkDir", str(work), "-DryRun")
    assert r.returncode == 0, r.stderr
    assert "--user-data-dir=" in r.stdout and str(work / "userData") in r.stdout
    assert "건드리지 않음" in r.stdout and "막음(동의 창 미표시)" in r.stdout
    assert not work.exists()  # 실행도 폴더 생성도 하지 않는다


def test_real_claude_mode_is_labelled_dangerous_in_plan(tmp_path):
    exe = tmp_path / "app.exe"
    exe.write_bytes(b"MZ")
    out = run_ps("-ExePath", str(exe), "-WorkDir", str(tmp_path / "w"), "-DryRun", "-RealClaude").stdout
    assert "실제 Claude 설정을 바꿀 수 있음" in out


def test_missing_exe_is_rejected(tmp_path):
    r = run_ps("-ExePath", str(tmp_path / "nope.exe"), "-WorkDir", str(tmp_path / "w"))
    assert r.returncode != 0 and "exe 를 찾을 수 없습니다" in (r.stdout + r.stderr)
    assert not (tmp_path / "w").exists()


def _port_free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


@pytest.mark.skipif(not _port_free(8401), reason="8401 포트가 이미 사용 중")
def test_full_flow_with_fake_app_uses_temp_user_data_and_summarizes(tmp_path):
    fake_py = tmp_path / "fake_app.py"
    fake_py.write_text(
        "import sys, http.server, socketserver, threading, time, pathlib\n"
        "ud = [a for a in sys.argv[1:] if a.startswith('--user-data-dir=')][0].split('=', 1)[1].strip('\"')\n"
        "p = pathlib.Path(ud); (p / 'storage').mkdir(parents=True, exist_ok=True)\n"
        "(p / 'storage' / 'audit_logs.jsonl').write_text('{}\\n')\n"
        "class H(http.server.BaseHTTPRequestHandler):\n"
        "    def do_GET(self):\n"
        "        self.send_response(200); self.end_headers()\n"
        "srv = socketserver.TCPServer(('127.0.0.1', 8401), H)\n"
        "threading.Thread(target=srv.serve_forever, daemon=True).start()\n"
        "time.sleep(15)\n",  # 점검 스크립트는 2초 간격으로 포트를 확인한다 — 느린 러너에서도 한 번은 보이게 충분히 떠 있는다
        encoding="utf-8",
    )
    fake_cmd = tmp_path / "fake.cmd"
    fake_cmd.write_bytes(f'@echo off\r\n"{sys.executable}" "{fake_py}" %*\r\n'.encode())
    work = tmp_path / "work"
    r = run_ps("-ExePath", str(fake_cmd), "-WorkDir", str(work), timeout=180)
    assert r.returncode == 0, r.stderr
    assert "서버가 떴습니다(8401)" in r.stdout and "앱이 종료되었습니다" in r.stdout
    assert (work / "userData" / "storage" / "audit_logs.jsonl").is_file()  # 임시 userData 에만 쓴다
    # 격리 모드는 'Claude 연결' 동의 창을 막는 설정을 임시 config.json 에 미리 넣는다
    assert '"prompted":true' in (work / "userData" / "config.json").read_text(encoding="utf-8-sig").replace(" ", "")
    assert "audit_logs.jsonl" in r.stdout  # 요약에 보인다
