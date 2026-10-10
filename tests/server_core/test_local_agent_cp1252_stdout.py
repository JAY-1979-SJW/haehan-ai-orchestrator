"""결함 2026-10-10(GitHub 데스크톱 빌드 E2E) — 영문 로케일 Windows(cp1252 등)에서
stdout 이 파이프면 그 로케일 인코딩으로 쓰이는데, local_agent.py 의 한글 print
(예: "[에이전트] 서버 연결 중: ...")가 UnicodeEncodeError 로 죽어
PyInstaller 번들이 "Failed to execute script" 로 크래시했다. 이 PC(cp949)에선
안 드러나 실측하려면 PYTHONIOENCODING=cp1252 로 감싼 자식 프로세스가 필요하다."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())


def _run_agent_briefly(env_overrides: dict[str, str]) -> str:
    """main 시작부(서버 연결 중 출력) 까지 실행하고 바로 죽인다 — 연결 자체는 안 봄."""
    import os

    env = {**os.environ, **env_overrides, "PYTHONUTF8": "0", "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "core.agent_runtime.runtime.local_agent",
            "--license",
            "test-license",
            "--server",
            "ws://127.0.0.1:1",  # 아무도 안 듣는 포트 — 연결 실패해도 상관없음, 첫 print 만 본다
            "--retry",
            "60",
        ],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        out = proc.stdout.readline()  # "[에이전트] 서버 연결 중: ..." 한 줄만 보면 충분
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    return out


def test_cp1252_stdout_does_not_crash_on_startup_print():
    out = _run_agent_briefly({"PYTHONIOENCODING": "cp1252"})
    assert "UnicodeEncodeError" not in out
    assert "Traceback" not in out
    assert "에이전트" in out  # reconfigure(errors="replace") 가 아니라 utf-8 로 정상 출력돼야 함


def test_default_encoding_still_works():
    out = _run_agent_briefly({})
    assert "UnicodeEncodeError" not in out
    assert "에이전트" in out
