"""디버깅 & 로그 게이트 — 전역 로거 모듈.

레벨:  DEBUG < INFO < WARN < ERROR
게이트: 환경변수 LOG_LEVEL 또는 set_level()로 런타임 변경 가능.

사용법:
    from scripts.common.logger import get_logger
    log = get_logger(__name__)

    log.debug("CDP 포트: %s", port)
    log.info("페이지 이동: %s", url)
    log.warn("버튼 못 찾음: %s", selector)
    log.error("연결 실패: %s", e)

    # 디버그 모드 켜기 (환경변수)
    # LOG_LEVEL=DEBUG python scripts/...

    # 런타임 변경
    from scripts.common.logger import set_level
    set_level("DEBUG")
"""

from __future__ import annotations

import contextlib
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler

from ai_orchestrator.paths.runtime import data_dir
from scripts.common.app_paths import repo_root

ROOT = repo_root()
LOG_DIR = data_dir() / "logs"
LOG_FILE = LOG_DIR / "app.log"


class _BlockedRotateSafeHandler(RotatingFileHandler):
    """여러 프로세스가 같은 로그 파일을 열고 있는 Windows 에서도 기록이 끊기지 않는 회전 핸들러.

    표준 RotatingFileHandler 는 회전(os.rename)이 다른 프로세스의 파일 사용 때문에 막히면(WinError 32)
    로그 한 줄마다 회전을 다시 시도하고 매번 "--- Logging error ---" 를 낸다(2026-10-04 실측: 112회).
    회전이 막히면 _RETRY_SEC 동안은 다시 시도하지 않고 기존 파일에 계속 이어 쓴다.
    """

    _RETRY_SEC = 60.0

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._blocked_until = 0.0

    def shouldRollover(self, record: logging.LogRecord) -> int:
        if time.monotonic() < self._blocked_until:
            return False
        return super().shouldRollover(record)

    def doRollover(self) -> None:
        try:
            super().doRollover()
        except OSError:
            # 회전 실패(다른 프로세스가 파일 사용 중) — 잠시 쉬고, 표준 doRollover 가 닫아 둔 스트림을 되살려 계속 기록
            self._blocked_until = time.monotonic() + self._RETRY_SEC
            if self.stream is None:
                self.stream = self._open()


# ── 포맷 ─────────────────────────────────────────────────────────────
_FMT_CONSOLE = "%(levelname)s  %(name)s │ %(message)s"
_FMT_FILE = "%(asctime)s  %(levelname)s  %(name)s │ %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"

# ── 레벨 매핑 ────────────────────────────────────────────────────────
_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARN": logging.WARNING,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}


def _resolve_level() -> int:
    raw = os.environ.get("LOG_LEVEL", "INFO").upper()
    return _LEVEL_MAP.get(raw, logging.INFO)


# ── 루트 로거 초기화 (1회만) ─────────────────────────────────────────
def _init_root() -> None:
    root = logging.getLogger("scripts")
    if root.handlers:
        return  # 이미 초기화됨

    root.setLevel(logging.DEBUG)  # 핸들러가 레벨 게이트를 담당

    # 콘솔 핸들러 (frozen exe의 cp949 stdout에서도 한글·em-dash 안전 기록)
    stream = sys.stdout
    if stream is not None:
        # 콘솔 스트림 UTF-8 인코딩 재설정 best-effort - 실패해도 로깅 자체(핸들러 등록)는 계속 진행
        with contextlib.suppress(Exception):
            # utf-8 로 강제 + 인코딩 불가 문자는 대체(크래시 방지)
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        ch = logging.StreamHandler(stream)
        ch.setLevel(_resolve_level())
        ch.setFormatter(logging.Formatter(_FMT_CONSOLE))
        root.addHandler(ch)

    # 파일 핸들러 (최대 5MB x 3개 로테이션)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fh = _BlockedRotateSafeHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    fh.setLevel(logging.DEBUG)  # 파일은 항상 전체 기록
    fh.setFormatter(logging.Formatter(_FMT_FILE, datefmt=_DATE_FMT))
    root.addHandler(fh)


_init_root()


# ── 공개 API ─────────────────────────────────────────────────────────


def get_logger(name: str) -> logging.Logger:
    """모듈별 로거 반환.

    name은 보통 __name__ 사용.
    scripts.google.common.calendar_tasks → 'google.calendar_tasks' 로 짧게 표시.
    """
    # 'scripts.' 접두사를 붙여 루트 로거 아래 계층 구조 유지
    if not name.startswith("scripts"):
        name = f"scripts.{name}"
    return logging.getLogger(name)


def set_level(level: str) -> None:
    """런타임 콘솔 출력 레벨 변경. 파일 레벨은 항상 DEBUG."""
    lvl = _LEVEL_MAP.get(level.upper(), logging.INFO)
    root = logging.getLogger("scripts")
    for h in root.handlers:
        if isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler):
            h.setLevel(lvl)


def enable_debug() -> None:
    """콘솔 디버그 모드 ON."""
    set_level("DEBUG")


def disable_debug() -> None:
    """콘솔 디버그 모드 OFF (INFO로 복귀)."""
    set_level("INFO")
