"""타임아웃 때 자손 프로세스까지 종료하고 파이프를 놓는 subprocess 실행기.

`subprocess.run(..., capture_output=True, timeout=N)` 은 시간이 지나면 자식만 죽이고 `communicate()` 로 파이프가 닫히길 기다린다.
시험이나 import 가 CDP 데몬·Chrome 같은 **자손 프로세스를 띄워 파이프를 물고 있게 두면** 자식이 죽어도 EOF 가 오지 않아 영원히 멈춘다
(2026-10-08 PR #160 CI verify 가 90분 상한까지 출력 없이 멈춘 원인으로 추정). 이 실행기는 시간 초과 시 프로세스 트리 전체를 종료하고,
그래도 파이프가 안 닫히면 기다리지 않고 포기한 채 `TimeoutExpired` 를 올린다.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

PIPE_GRACE_S = 15  # 트리를 죽인 뒤 파이프가 닫히길 기다리는 최대 시간


def kill_tree(pid: int) -> None:
    """pid 와 그 자손을 모두 종료한다(이미 없으면 조용히 넘어간다)."""
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, timeout=30, check=False)
        else:
            os.killpg(pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass


def run_tree_killed(
    cmd: Sequence[str],
    *,
    cwd: str | Path | None = None,
    timeout: float,
    env: Mapping[str, str] | None = None,
    input: bytes | str | None = None,
    text: bool = True,
    **popen_extra: Any,
) -> subprocess.CompletedProcess:
    """`subprocess.run(capture_output=True[, text=True])` 와 같은 결과를 주되, 시간 초과 때 자손까지 죽이고 멈추지 않는다.

    text=False 면 stdout/stderr 를 bytes 로 돌려준다(input 도 bytes). popen_extra 는 Popen 에 그대로 넘긴다(creationflags 등).
    """
    kwargs: dict = {"cwd": cwd, "env": env, "stdout": subprocess.PIPE, "stderr": subprocess.PIPE, **popen_extra}
    if input is not None:
        kwargs["stdin"] = subprocess.PIPE
    if text:
        kwargs.update({"text": True, "encoding": "utf-8", "errors": "replace"})
    if os.name != "nt":
        kwargs["start_new_session"] = True  # killpg 가 이 자식의 그룹만 겨냥하게
    proc = subprocess.Popen(cmd, **kwargs)
    try:
        out, err = proc.communicate(input, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        kill_tree(proc.pid)
        try:
            out, err = proc.communicate(timeout=PIPE_GRACE_S)
        except subprocess.TimeoutExpired:
            # 파이프를 문 프로세스가 남아 있다 — 기다리지 않고 포기한다. 파이프를 닫으려 하면(stream.close()) 읽기 스레드가
            # 잡고 있는 잠금 때문에 윈도우에서 다시 멈추므로 닫지 않는다(읽기 스레드는 daemon 이라 종료를 막지 않는다).
            out, err = ("", "") if text else (b"", b"")
        raise subprocess.TimeoutExpired(cmd, timeout, output=out, stderr=err) from exc
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)
