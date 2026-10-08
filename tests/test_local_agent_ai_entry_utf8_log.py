"""local-agent-ai.exe 진입점은 stdout/stderr 를 UTF-8 로 고정해야 한다 (2026-10-08).

PyInstaller 번들 exe 는 stdout/stderr 가 파이프로 리다이렉트될 때 콘솔 코드페이지(cp949 등)로
떨어져 local-agent-ai.log 의 한글 로그가 깨진다. scripts/local_agent_ai_entry.py 가 모듈 import
시점에 reconfigure(encoding="utf-8")를 호출하는지 정적 검사하고, 실제로 한글을 기록한 뒤 UTF-8로
다시 읽어 바이트가 깨지지 않는지 서브프로세스로 재현한다.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "scripts" / "local_agent_ai_entry.py"


def _calls_reconfigure_utf8(tree: ast.AST, attr_target: str) -> bool:
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "reconfigure"
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == attr_target
            and any(
                kw.arg == "encoding" and isinstance(kw.value, ast.Constant) and kw.value.value == "utf-8"
                for kw in node.keywords
            )
        ):
            return True
    return False


def test_entry_forces_utf8_stdout_and_stderr():
    tree = ast.parse(ENTRY.read_text(encoding="utf-8"))
    assert _calls_reconfigure_utf8(tree, "stdout"), "local_agent_ai_entry.py: sys.stdout.reconfigure(utf-8) 누락"
    assert _calls_reconfigure_utf8(tree, "stderr"), "local_agent_ai_entry.py: sys.stderr.reconfigure(utf-8) 누락"


def test_korean_log_round_trips_as_utf8(tmp_path):
    """콘솔 코드페이지가 cp949 인 환경을 흉내내도 로그에 한글이 깨지지 않아야 한다.

    PYTHONIOENCODING/PYTHONUTF8 을 끈 자식 프로세스에서 entry 와 같은 reconfigure 를 적용한 뒤
    한글을 stdout 에 쓰고, 그 바이트를 UTF-8 로 다시 읽어 원문과 같은지 확인한다.
    """
    message = "로컬 에이전트 연결 중 — 한글 로그 인코딩 확인"
    script = textwrap.dedent(
        f"""
        import contextlib
        import sys
        with contextlib.suppress(Exception):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        with contextlib.suppress(Exception):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        print({message!r})
        """
    )
    import os

    # 부모 환경을 그대로 물려주되 UTF-8 강제 변수만 빼서, frozen exe 에서 그 변수들이
    # 전달되지 않는 상황(이번 결함의 실제 원인)을 재현한다.
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    log_file = tmp_path / "local-agent-ai.log"
    with log_file.open("wb") as fh:
        subprocess.run(
            [sys.executable, "-c", script],
            stdout=fh,
            stderr=subprocess.STDOUT,
            check=True,
            timeout=30,
            env=env,
        )
    content = log_file.read_text(encoding="utf-8")
    assert message in content
