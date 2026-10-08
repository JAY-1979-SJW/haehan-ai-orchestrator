"""스마트스토어 상품 일괄 등록 + 재시도 + 진행 보고 + DB 기록.

사용:
  from scripts.naver.smartstore.bulk import BulkRegister
  br = BulkRegister(page)
  result = br.register_all([
      {"name": "상품1", "price": 10000, "stock": 100},
      {"name": "상품2", "price": 20000, "stock": 50},
  ], product_type="general", save_after=False)
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from playwright.sync_api import Page

from ai_orchestrator.paths.runtime import data_dir
from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger
from scripts.common.sqlite_helpers import init_sqlite_schema
from scripts.naver.smartstore.product.models import (
    GeneralProductData,
    GroupProductData,
    RegisterResult,
    ValidationError,
)

if TYPE_CHECKING:
    from scripts.naver.smartstore.product.general_product import GeneralProductRegister
    from scripts.naver.smartstore.product.product import ProductRegister

_log = get_logger(__name__)

ROOT = (
    Path(__file__).resolve().parents[4]
)  # 2026-09-29 defect_index #39: 이 파일만 [3]으로 남아있었음(같은 폴더의 다른 파일 전부 [4] — product/ 하위로 이동 후 미반영, DB_PATH 가 scripts/data/ 로 잘못 계산되던 실버그)
DB_PATH = data_dir() / "cdp.db"


def _init_db() -> None:
    """등록 이력 테이블 초기화."""
    init_sqlite_schema(
        DB_PATH,
        (
            """
        CREATE TABLE IF NOT EXISTS smartstore_register_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            product_name TEXT NOT NULL,
            product_type TEXT,
            ok INTEGER,
            saved INTEGER,
            url TEXT,
            error TEXT,
            duration_s REAL,
            data TEXT,
            steps TEXT
        )
    """,
            "CREATE INDEX IF NOT EXISTS idx_ssreg_ts ON smartstore_register_log(ts)",
            "CREATE INDEX IF NOT EXISTS idx_ssreg_ok ON smartstore_register_log(ok)",
        ),
    )


def _save_log(result: RegisterResult, data: dict) -> None:
    """등록 결과 DB 저장."""
    try:
        _init_db()
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            """INSERT INTO smartstore_register_log
               (ts, product_name, product_type, ok, saved, url, error, duration_s, data, steps)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result.started_at or datetime.now().isoformat(timespec="seconds"),
                result.product_name,
                result.type,
                1 if result.ok else 0,
                1 if result.saved else 0,
                result.url,
                result.error,
                result.duration_s,
                json.dumps(data, ensure_ascii=False),
                json.dumps(
                    [(n, r.get("ok") if isinstance(r, dict) else None) for n, r in result.steps], ensure_ascii=False
                ),
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:  # noqa: BLE001 - 스마트스토어 상품 일괄 등록 — DB저장 실패는 로그만 남김(로컬 sqlite 등록이력 기록용, 운영 DB 아님), retry 래퍼와 register_product 예외 모두 ok=False로 표준화되어 실패가 성공으로 보고되지 않음. 진행 콜백 실패는 무시.
        _log.error("[bulk] DB 저장 실패: %s", e)


def retry(func: Callable, max_attempts: int = 3, delay_s: float = 1.0, backoff: float = 1.5) -> Any:
    """간단한 재시도 래퍼."""
    attempt = 0
    last_err = None
    while attempt < max_attempts:
        try:
            result = func()
            if isinstance(result, dict) and not result.get("ok", True):
                # ok=False도 재시도 대상
                last_err = result.get("error", "ok=False")
                attempt += 1
                if attempt < max_attempts:
                    time.sleep(delay_s * (backoff ** (attempt - 1)))
                    continue
                return result
            return result
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품 일괄 등록 — DB저장 실패는 로그만 남김(로컬 sqlite 등록이력 기록용, 운영 DB 아님), retry 래퍼와 register_product 예외 모두 ok=False로 표준화되어 실패가 성공으로 보고되지 않음. 진행 콜백 실패는 무시.
            last_err = str(e)
            attempt += 1
            if attempt < max_attempts:
                time.sleep(delay_s * (backoff ** (attempt - 1)))
            else:
                return {"ok": False, "error": last_err, "attempts": attempt}


class BulkRegister:
    """상품 일괄 등록."""

    def __init__(self, page: Page):
        self.page = page

    def _register_one(
        self, data: dict, product_type: str = "general", save_after: bool = False, require_confirm: bool = False
    ) -> RegisterResult:
        """단일 상품 등록 + 결과 표준화."""
        started = datetime.now()

        # 1. 데이터 검증
        try:
            pd: GeneralProductData | GroupProductData
            if product_type == "general":
                pd = GeneralProductData.from_dict(data)
            else:
                pd = GroupProductData.from_dict(data)
            validated = pd.to_dict()
        except ValidationError as e:
            return RegisterResult(
                ok=False,
                product_name=data.get("name", ""),
                type=product_type,
                saved=False,
                steps=[],
                error=f"validation_error: {e}",
                started_at=started.isoformat(timespec="seconds"),
                finished_at=datetime.now().isoformat(timespec="seconds"),
                duration_s=0,
            )

        # 2. 등록 실행
        register: GeneralProductRegister | ProductRegister
        if product_type == "general":
            from scripts.naver.smartstore.product.general_product import GeneralProductRegister

            register = GeneralProductRegister(self.page)
        else:
            from scripts.naver.smartstore.product.product import ProductRegister

            register = ProductRegister(self.page)

        try:
            r = register.register_product(validated, save_after=save_after, require_confirm=require_confirm)
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품 일괄 등록 — DB저장 실패는 로그만 남김(로컬 sqlite 등록이력 기록용, 운영 DB 아님), retry 래퍼와 register_product 예외 모두 ok=False로 표준화되어 실패가 성공으로 보고되지 않음. 진행 콜백 실패는 무시.
            r = {"ok": False, "error": str(e)[:200], "steps": []}

        finished = datetime.now()
        duration = (finished - started).total_seconds()

        return RegisterResult(
            ok=r.get("ok", False),
            product_name=pd.name,
            type=product_type,
            saved=r.get("saved", False),
            steps=r.get("steps", []),
            error=r.get("error"),
            url=self.page.url,
            started_at=started.isoformat(timespec="seconds"),
            finished_at=finished.isoformat(timespec="seconds"),
            duration_s=round(duration, 2),
        )

    def register_all(  # noqa: PLR0913 - 공개 API 시그니처 유지(호출부 다수)
        self,
        products: list[dict],
        product_type: str = "general",
        save_after: bool = False,
        require_confirm: bool = False,
        max_retries: int = 2,
        stop_on_error: bool = False,
        on_progress: Callable[[int, int, RegisterResult], None] | None = None,
    ) -> dict:
        """여러 상품 일괄 등록.

        Args:
            products: 상품 데이터 dict 리스트
            product_type: "general" / "group"
            save_after: True면 등록 후 저장
            require_confirm: 저장 전 사용자 확인
            max_retries: 실패 시 재시도 횟수
            stop_on_error: True면 첫 실패에서 중단
            on_progress(i, total, result): 진행 콜백

        Returns:
            {ok, total, success, failed, results, db_logged}
        """
        log_critical(
            "OTHER",
            f"스마트스토어 일괄 등록 시작: {len(products)}개",
            count=len(products),
            type=product_type,
            mode="bulk_start",
        )

        results = []
        success = 0
        failed = 0

        for i, p in enumerate(products, 1):
            _log.info("[bulk] [%d/%d] %s", i, len(products), p.get("name", "?")[:40])

            # 재시도
            result = self._register_one(p, product_type, save_after, require_confirm)
            attempts = 1
            while not result.ok and attempts < max_retries:
                attempts += 1
                _log.warning("[bulk] 재시도 %d/%d: %s", attempts, max_retries, result.error)
                time.sleep(2)
                result = self._register_one(p, product_type, save_after, require_confirm)

            # DB 저장
            _save_log(result, p)

            # 결과 누적
            results.append(result)
            if result.ok:
                success += 1
            else:
                failed += 1

            # 진행 콜백
            if on_progress:
                # 진행 콜백 실패는 무시 — 등록 자체 성공/실패는 result.ok로 이미 표준화되어 보고됨
                with contextlib.suppress(Exception):
                    on_progress(i, len(products), result)

            if stop_on_error and not result.ok:
                _log.warning("[bulk] 실패로 중단 (stop_on_error=True)")
                break

        summary = {
            "ok": failed == 0,
            "total": len(products),
            "success": success,
            "failed": failed,
            "results": [r.to_dict() for r in results],
            "db_logged": True,
        }
        log_critical(
            "OTHER",
            f"스마트스토어 일괄 등록 완료: {success}/{len(products)}",
            success=success,
            failed=failed,
            mode="bulk_done",
        )
        return summary


def get_register_history(limit: int = 50, ok_only: bool = False) -> list[dict]:
    """DB에서 등록 이력 조회."""
    _init_db()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    where = "WHERE ok = 1" if ok_only else ""
    rows = conn.execute(f"SELECT * FROM smartstore_register_log {where} ORDER BY id DESC LIMIT ?", (limit,)).fetchall()  # nosec B608 - 테이블명은 모듈 상수, 조건/정렬은 고정 조각이고 값은 ? 바인딩(사용자 입력 미결합)
    conn.close()
    return [dict(r) for r in rows]
