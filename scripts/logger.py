"""디버깅 & 로그 게이트 — 전역 로거 모듈.

레벨:  DEBUG < INFO < WARN < ERROR
게이트: 환경변수 LOG_LEVEL 또는 set_level()로 런타임 변경 가능.

사용법:
    from scripts.logger import get_logger
    log = get_logger(__name__)

    log.debug("CDP 포트: %s", port)
    log.info("페이지 이동: %s", url)
    log.warn("버튼 못 찾음: %s", selector)
    log.error("연결 실패: %s", e)

    # 디버그 모드 켜기 (환경변수)
    # LOG_LEVEL=DEBUG python scripts/...

    # 런타임 변경
    from scripts.logger import set_level
    set_level("DEBUG")
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "data" / "logs"
LOG_FILE = LOG_DIR / "app.log"

# ── 포맷 ─────────────────────────────────────────────────────────────
_FMT_CONSOLE = "%(levelname)s  %(name)s │ %(message)s"
_FMT_FILE    = "%(asctime)s  %(levelname)s  %(name)s │ %(message)s"
_DATE_FMT    = "%Y-%m-%d %H:%M:%S"

# ── 레벨 매핑 ────────────────────────────────────────────────────────
_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO":  logging.INFO,
    "WARN":  logging.WARNING,
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

    # 콘솔 핸들러
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(_resolve_level())
    ch.setFormatter(logging.Formatter(_FMT_CONSOLE))
    root.addHandler(ch)

    # 파일 핸들러 (최대 5MB × 3개 로테이션)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fh = RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)  # 파일은 항상 전체 기록
    fh.setFormatter(logging.Formatter(_FMT_FILE, datefmt=_DATE_FMT))
    root.addHandler(fh)


_init_root()


# ── 공개 API ─────────────────────────────────────────────────────────

def get_logger(name: str) -> logging.Logger:
    """모듈별 로거 반환.

    name은 보통 __name__ 사용.
    scripts.google.calendar → 'google.calendar' 로 짧게 표시.
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
