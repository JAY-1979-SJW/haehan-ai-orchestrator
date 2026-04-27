"""로컬 에이전트 설정.

- AGENT_LOG_DIR: agent_actions.jsonl 이 저장될 디렉터리 (기본: ./storage)
- DEFAULT_GOTO_TIMEOUT_MS: page.goto 기본 타임아웃
- SNIPPET_MAX_CHARS: inspect_page snippet 최대 길이
- HEADLESS: Chromium headless 실행 여부 (운영 기본값)
"""
from __future__ import annotations

import os
from pathlib import Path

AGENT_BASE = Path(__file__).resolve().parent

_log_dir_env = os.environ.get("AGENT_LOG_DIR", "").strip()
AGENT_LOG_DIR = Path(_log_dir_env) if _log_dir_env else AGENT_BASE / "storage"
AGENT_LOG_PATH = AGENT_LOG_DIR / "agent_actions.jsonl"

# 파일 기반 action (excel 등) 입력/출력 허용 디렉터리.
# 여기 지정된 경로 밖으로는 읽기/쓰기를 허용하지 않는다.
_work_dir_env = os.environ.get("AGENT_WORK_DIR", "").strip()
AGENT_WORK_DIR = Path(_work_dir_env) if _work_dir_env else AGENT_BASE / "work"

_output_dir_env = os.environ.get("AGENT_OUTPUT_DIR", "").strip()
AGENT_OUTPUT_DIR = (
    Path(_output_dir_env) if _output_dir_env else AGENT_BASE / "output" / "reports"
)

DEFAULT_GOTO_TIMEOUT_MS = 10_000
SNIPPET_MAX_CHARS = 1000
HEADLESS = True
