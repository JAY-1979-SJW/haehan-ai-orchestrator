"""브라우저·미디어 도구 실행 파일 위치 탐색 — 후보 목록의 단일 정본 (결함 #17).

설계: docs/specs/2026-10-01_hardcoded_paths_consolidation.md

여기서는 **위치만 찾는다**. 브라우저 실행(`assert_browser_launch_allowed` 등 게이트)은 호출부의 책임이다.
후보 순서는 기존 코드와 같다: Program Files → Program Files (x86) → %LOCALAPPDATA%.
"""

from __future__ import annotations

import glob
import os
import shutil
from collections.abc import Iterable
from pathlib import Path

CHROME_CANDIDATES: tuple[str, ...] = (
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
)

EDGE_CANDIDATES: tuple[str, ...] = (
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe",
)

# winget 으로 설치한 ffmpeg 의 패키지 폴더(계정·버전 이름이 들어 있어 glob 으로 찾는다)
_WINGET_FFMPEG_GLOB = r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\ffmpeg-*\bin\ffmpeg.exe"


def first_existing(candidates: Iterable[str]) -> str | None:
    """환경변수(%VAR%)를 펼친 뒤 처음으로 실제 존재하는 경로를 반환한다. 없으면 None."""
    for candidate in candidates:
        expanded = os.path.expandvars(candidate)
        if Path(expanded).exists():
            return expanded
    return None


def find_chrome() -> str | None:
    """Chrome 실행 파일. 환경변수 HAEHAN_CHROME_PATH(비표준 위치에 설치한 PC 용) → Program Files → x86 → %LOCALAPPDATA% 순."""
    configured = os.environ.get("HAEHAN_CHROME_PATH", "").strip()
    if configured and Path(configured).exists():
        return configured
    return first_existing(CHROME_CANDIDATES)


def find_edge() -> str | None:
    return first_existing(EDGE_CANDIDATES)


def find_ffmpeg() -> str | None:
    """ffmpeg 실행 파일: 환경변수 FFMPEG_PATH → PATH 의 ffmpeg → winget 패키지 폴더(가장 새 버전) 순."""
    env_path = os.environ.get("FFMPEG_PATH", "").strip()
    if env_path and Path(env_path).exists():
        return env_path
    on_path = shutil.which("ffmpeg")
    if on_path:
        return on_path
    matches = sorted(glob.glob(os.path.expandvars(_WINGET_FFMPEG_GLOB)))
    return matches[-1] if matches else None
