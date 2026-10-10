"""중요작업 전용 로그 — 감사 추적용.

기록 대상:
  - 은행/금융 사이트 접속 및 로그인
  - 인증서 사용/관리
  - 파일 다운로드 (.exe / 인증서 등)
  - 보안 프로그램 설치
  - 메일 발송 (홍보/알림)
  - 결제/이체 등 금전 거래
  - 데이터 삭제

저장 위치:
  - data/logs/critical.log      (텍스트 — 즉시 읽기용)
  - data/cdp.db.critical_logs   (SQLite — 검색/필터링용)

사용법:
    from scripts.common.critical_logger import log_critical

    log_critical("BANK_LOGIN", "하나은행 로그인 시도", site="hanabank.com", user="skyjwshin")
    log_critical("FILE_DOWNLOAD", "Veraport 다운로드", file="veraport-g3-x64-sha2.exe", size=30041304)
    log_critical("MAIL_SEND", "통신단절 알림 발송", to="vendor@x.com", subject="...")
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Any

from ai_orchestrator.paths.runtime import data_dir
from scripts.common.app_paths import repo_root

ROOT = repo_root()
LOG_DIR = data_dir() / "logs"
CRITICAL_LOG_FILE = LOG_DIR / "critical.log"
DB_PATH = data_dir() / "cdp.db"

# 카테고리 분류 (확장 가능)
CATEGORIES = {
    # 금융
    "BANK_VISIT",
    "BANK_LOGIN",
    "BANK_LOGOUT",
    "BANK_INQUIRY",
    "BANK_TRANSFER",
    "CARD_VISIT",
    "CARD_LOGIN",
    "CARD_INQUIRY",
    "CARD_PAYMENT",
    "CARD_STATEMENT",
    "INSURANCE_VISIT",
    "INSURANCE_LOGIN",
    "INSURANCE_CLAIM",
    "FIN_REGULATOR",
    # 세무
    "TAX_VISIT",
    "TAX_LOGIN",
    "TAX_FILING",
    "TAX_PAYMENT",
    "TAX_REFUND",
    # 4대보험 (공공)
    "SOCIAL_INSURANCE",
    "SOCIAL_INSURANCE_FILING",
    # 사법/법무
    "COURT_VISIT",
    "COURT_FILING",
    "COURT_CERT_ISSUE",
    # 노동/취업
    "LABOR_VISIT",
    "LABOR_FILING",
    # 부동산/등기
    "REALESTATE_VISIT",
    "REALESTATE_FILING",
    # 특허/지적재산
    "IP_VISIT",
    "IP_FILING",
    # 자동차/교통
    "MOTOR_VISIT",
    "MOTOR_FILING",
    # 정부 부처/공공
    "GOV_MINISTRY",
    "GOV_VISIT",
    "GOV_OTHER",
    "GOV_LOGIN",
    "GOV_FILING",
    "GOV_CERT_ISSUE",
    # 인증
    "CERT_USE",
    "CERT_INSTALL",
    "CERT_DELETE",
    "CERT_COPY",
    "CERT_RENEW",
    # 파일
    "FILE_DOWNLOAD",
    "FILE_UPLOAD",
    "FILE_DELETE",
    # 보안 프로그램
    "SECU_INSTALL",
    "SECU_UNINSTALL",
    # 메일
    "MAIL_SEND",
    "MAIL_DELETE",
    # 데이터
    "DATA_DELETE",
    "DATA_EXPORT",
    "DATA_IMPORT",
    # 인증/결제
    "PAYMENT",
    "AUTH_SUCCESS",
    "AUTH_FAIL",
    # EUM (건설근로자공제회)
    "EUM_LOGIN",
    "EUM_INQUIRY",
    "EUM_REGISTER",
    "EUM_REMOVE",
    # 일반 인기 사이트 (commercial/consumer)
    "PORTAL_VISIT",
    "KAKAO_SERVICE",
    "SHOPPING_VISIT",
    "SHOPPING_ORDER",
    "SHOPPING_PAYMENT",
    "MART_VISIT",
    "DELIVERY_VISIT",
    "DELIVERY_ORDER",
    "USED_MARKET",
    "USED_LIST",
    "USED_DEAL",
    "OTT_VISIT",
    "OTT_LOGIN",
    "OTT_SUBSCRIBE",
    "MUSIC_VISIT",
    "MUSIC_LOGIN",
    "TRAVEL_VISIT",
    "TRAVEL_BOOK",
    "TRAVEL_CANCEL",
    "TELCO_VISIT",
    "TELCO_LOGIN",
    "TELCO_USAGE",
    "PAYMENT_VISIT",
    "PAYMENT_RUN",
    "GAME_VISIT",
    "GAME_LOGIN",
    "COMMUNITY_VISIT",
    "COMMUNITY_POST",
    "REALESTATE_PRIVATE",
    "REALESTATE_INQUIRY",
    "MAP_NAVIGATION",
    "MAP_SEARCH",
    "MAP_ROUTE",
    "AUTO_MARKET",
    "AUTO_INQUIRY",
    "JOB_VISIT",
    "JOB_APPLY",
    "MAIL_PORTAL",
    "MAIL_PORTAL_SEND",
    "COLLAB_VISIT",
    "EDU_VISIT",
    "EDU_PURCHASE",
    "SNS_VISIT",
    "SNS_POST",
    "NEWS_VISIT",
    # 명품/라이프스타일/디자인
    "LUXURY_FASHION",
    "LUXURY_FASHION_BUY",
    "LUXURY_PLATFORM",
    "LUXURY_PLATFORM_BUY",
    "WATCH_LUXURY",
    "JEWELRY_LUXURY",
    "AUTO_LUXURY",
    "INTERIOR_FURNITURE",
    "INTERIOR_INQUIRY",
    "LIGHTING_DESIGN",
    "DESIGN_MEDIA",
    "ART_MUSEUM",
    "ART_VISIT",
    "ART_AUCTION",
    "ART_BID",
    "LIFESTYLE_LUXURY",
    "TECH_GLOBAL",
    "FRAGRANCE_LUXURY",
    # 기타
    "OTHER",
}

_FMT = "%(asctime)s  [%(category)s]  %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"

_logger: logging.Logger | None = None


def _init() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("critical")
    logger.setLevel(logging.INFO)
    logger.propagate = False  # 일반 로거와 분리

    if not logger.handlers:
        fh = RotatingFileHandler(CRITICAL_LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
        fh.setFormatter(logging.Formatter(_FMT, datefmt=_DATE_FMT))
        logger.addHandler(fh)

        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(logging.Formatter("🔒 [%(category)s] %(message)s"))
        logger.addHandler(ch)

    _init_db()
    _logger = logger
    return logger


def _init_db() -> None:
    """critical_logs 테이블 생성 (없으면)."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS critical_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                category TEXT NOT NULL,
                message TEXT NOT NULL,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_critical_category ON critical_logs(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_critical_ts ON critical_logs(ts)")
        conn.commit()
        conn.close()
    except Exception:  # noqa: BLE001 - 로그 기록(auxiliary) 실패가 본 기능 흐름을 막아선 안 되므로 무시 — DB write는 INSERT뿐, DELETE/DROP 없음
        pass


def log_critical(category: str, message: str, **metadata: Any) -> None:
    """중요작업 로그 기록.

    Args:
        category: CATEGORIES 중 하나 (예: "BANK_LOGIN", "FILE_DOWNLOAD")
        message: 사람이 읽을 메시지
        **metadata: 추가 구조화 데이터 (site=, user=, to=, file=, size= 등)
    """
    logger = _init()
    cat = category if category in CATEGORIES else "OTHER"

    # 파일 + 콘솔 로그
    meta_str = " | ".join(f"{k}={v}" for k, v in metadata.items()) if metadata else ""
    full_msg = f"{message}  {meta_str}".strip()
    logger.info(full_msg, extra={"category": cat})

    # DB 기록
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "INSERT INTO critical_logs (ts, category, message, metadata) VALUES (?, ?, ?, ?)",
            (
                datetime.now().isoformat(timespec="seconds"),
                cat,
                message,
                json.dumps(metadata, ensure_ascii=False) if metadata else None,
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:  # noqa: BLE001 - 중요 이벤트 SQLite 로깅 유틸 — 로그 기록 자체가 실패해도 무시(pass)하거나 경고만 남김, 로깅 실패가 본 기능을 막으면 안 되는 부가 기록용 코드이며 DELETE/DROP 없음(INSERT/SELECT만)
        logger.warning(f"DB 기록 실패 (무시): {e}", extra={"category": "OTHER"})


def query_recent(category: str | None = None, limit: int = 50) -> list[dict]:
    """최근 중요작업 로그 조회."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        if category:
            rows = conn.execute(
                "SELECT * FROM critical_logs WHERE category = ? ORDER BY id DESC LIMIT ?",
                (category, limit),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM critical_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:  # noqa: BLE001 - 중요 이벤트 SQLite 로깅 유틸 — 로그 기록 자체가 실패해도 무시(pass)하거나 경고만 남김, 로깅 실패가 본 기능을 막으면 안 되는 부가 기록용 코드이며 DELETE/DROP 없음(INSERT/SELECT만)
        return []
