"""EUM 영업메일 엔드포인트 (/api/v1/eum/*).

흐름: 신규현장(WEBMAN370M00) 전수 수집 → 영업메일 타겟 선별/초안 생성 → 하이웍스로 1건씩 발송.
발송은 confirmed=True 필수 (외부 메일 — 자동 일괄발송 금지, 1건씩 승인).

L8 Server API 계층. 실제 수집/메일 로직은 scripts/eum, scripts/hiworks 에 위임.
"""

from __future__ import annotations

import json
import logging
import sys
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ai_orchestrator.paths import repo_root
from ai_orchestrator.paths.runtime import data_dir
from tools.gates.auth import require_role
from tools.gates.send_approval import addresses, require_send_approval

from ...audit.audit_logger import log_event

logger = logging.getLogger(__name__)

eum_router = APIRouter(prefix="/eum", tags=["eum"])

_ROOT = repo_root()
_TARGETS_LATEST = data_dir() / "eum_sales_mail_targets_latest.json"


def _ensure_root_on_path() -> None:
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))


class QuoteRequest(BaseModel):
    recipient: str
    quote_type: str  # 이동형_임대 | 벽부형_임대 | 벽부형_구매
    quantity: int = 1
    months: int | None = None


class CollectRequest(BaseModel):
    max_pages: int = 20


EUM_SALES_MAIL_CONFIRM_TEXT = "EUM_APPROVED_SALES_MAIL"


class SendRequest(BaseModel):
    to: str
    subject: str
    body: str
    confirmed: bool = False
    # 사용자가 확인 단계에서 직접 입력한 승인 문구(EUM_SALES_MAIL_CONFIRM_TEXT). 없거나 다르면 403.
    send_confirm: str | None = None


def _run_eum_query(query_fn, *, needs_login_hint: bool = True) -> dict:
    """EUM 로그인된 브라우저 페이지에서 query_fn(page)를 실행하는 공통 래퍼.

    CDP page 조작은 브라우저 전용 스레드에서(playwright sync 스레드 경계).
    """
    from scripts.browser.cdp.connection import get_page, run_on_browser_thread
    from scripts.site_engine.site_access import LoginError
    from scripts.site_engine.site_watch import StepFailure

    try:

        def _run():
            page = get_page()
            return query_fn(page)

        return run_on_browser_thread(_run, timeout=120)
    except (LoginError, StepFailure) as e:
        if needs_login_hint:
            return {"ok": False, "needs_login": True, "error": "EUM 로그인이 필요합니다."}
        raise HTTPException(status_code=500, detail=str(e)) from e


@eum_router.get("/devices")
def get_devices(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """단말기설치현황 전체 조회 (WEBMAN390M00)."""
    _ensure_root_on_path()
    import time as _time

    from scripts.archive.eum_legacy.eum_extract_all_devices import click_page, extract_page_devices, get_page_count

    def _query(page):
        page.goto("https://eum.cw.or.kr/web/man/WEBMAN390M00", timeout=30000)
        page.wait_for_load_state("load", timeout=5000)
        total_pages = get_page_count(page)
        all_devices = []
        for page_num in range(1, total_pages + 1):
            if page_num > 1:
                click_page(page, page_num)
                _time.sleep(1.5)
            all_devices.extend(extract_page_devices(page))
        return {"ok": True, "count": len(all_devices), "devices": all_devices}

    result = _run_eum_query(_query)
    log_event(
        "EUM_API_DEVICES",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok" if result.get("ok") else "error",
        note=f"count={result.get('count', 0)}",
    )
    return result


@eum_router.get("/monitor")
def get_monitor(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """단말기 운용 모니터링 요약(통신단절/장기설치/준공임박) — 브라우저 불필요, 캐시된 조회 결과 기반."""
    _ensure_root_on_path()
    from scripts.eum.monitor import _load_devices, analyze

    devices = _load_devices()
    if not devices:
        return {"ok": False, "error": "단말기 데이터가 없습니다. 먼저 /eum/devices 를 조회하세요."}
    result = analyze(devices)
    return {"ok": True, **result}


@eum_router.get("/labor-test")
def get_labor_test(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """근로내역테스트 조회 (WEBMAN460M00)."""
    _ensure_root_on_path()
    from scripts.eum.labor_test import fetch_labor_test

    result = _run_eum_query(
        lambda page: {"ok": True, "records": (records := fetch_labor_test(page)), "count": len(records)}
    )
    return result


@eum_router.get("/test-workers")
def get_test_workers(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """테스트근로자등록 조회 (WEBMAN470M00)."""
    _ensure_root_on_path()
    from scripts.eum.test_workers import fetch_test_workers

    result = _run_eum_query(
        lambda page: {"ok": True, "records": (records := fetch_test_workers(page)), "count": len(records)}
    )
    return result


@eum_router.get("/site-devices")
def get_site_devices(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """현장별단말기목록 조회 (WEBMAN380M00). 필드명 미매핑 — row1_cells/row2_cells 원본."""
    _ensure_root_on_path()
    from scripts.eum.site_devices import fetch_site_devices

    result = _run_eum_query(
        lambda page: {"ok": True, "records": (records := fetch_site_devices(page)), "count": len(records)}
    )
    return result


@eum_router.get("/install-targets")
def get_install_targets(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """설치안내대상 전 페이지 조회 (WEBMAN370M00)."""
    _ensure_root_on_path()
    from scripts.eum.install_targets import collect_all_install_targets

    result = _run_eum_query(lambda page: collect_all_install_targets(page))
    return result


@eum_router.get("/device-history")
def get_device_history(
    device_id: str | None = None,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """단말기 이력 조회 (WEBMAN400M00). device_id 미지정 시 전체 목록."""
    _ensure_root_on_path()
    from scripts.eum.history import fetch_history

    result = _run_eum_query(
        lambda page: {"ok": True, "records": (records := fetch_history(page, device_id)), "count": len(records)}
    )
    return result


@eum_router.post("/sales-mail/collect")
def collect_and_prepare(
    req: CollectRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """신규현장 전수 수집(WEBMAN370M00) + 영업메일 타겟 선별/초안 생성.

    EUM 로그인 세션(CDP)이 있어야 한다. 표시개수 100 + 페이지네이션으로 전수 수집.
    """
    t0 = time.monotonic()
    try:
        _ensure_root_on_path()
        from scripts.eum.install_targets import collect_all_install_targets
        from scripts.eum.sales_mail import prepare_sales_mail
        from scripts.site_engine.site_access import open_site

        page = open_site("eum")
        collected = collect_all_install_targets(page, max_pages=req.max_pages)
        prep = prepare_sales_mail()
        log_event(
            "EUM_SALES_COLLECT",
            task_id="-",
            actor=user["actor"],
            role=user["role"],
            decision="ok",
            note=f"sites={collected.get('total')} targets={prep.get('selected_targets')}",
        )
        return {
            "ok": True,
            "collected_sites": collected.get("total", 0),
            "pages_visited": collected.get("pages_visited", 0),
            "eligible_targets": prep.get("eligible_targets", 0),
            "selected_targets": prep.get("selected_targets", 0),
            "duration_ms": int((time.monotonic() - t0) * 1000),
        }
    except Exception as e:
        # 로그인 미완료/세션 없음(LoginError/StepFailure) → 500 대신 graceful 안내.
        try:
            from scripts.site_engine.site_access import LoginError
            from scripts.site_engine.site_watch import StepFailure

            login_issue = isinstance(e, (LoginError, StepFailure))
        except Exception:  # noqa: BLE001 - EUM 영업메일 API(문서에 '발송은 confirmed=True 필수, 자동 일괄발송 금지' 명시) — send_one 엔드포인트는 confirmed 검증이 try 블록 이전에 이미 끝난 뒤에만 실제 발송을 시도하며, except는 실패를 HTTPException(500) 또는 로그인필요 안내로 변환할 뿐 승인을 우회하지 않음. 견적서 로컬 사본 저장 실패는 warn 로그만 남기고 본 스트리밍 응답에는 영향 없음.
            login_issue = False
        if login_issue or "로그인" in str(e):
            logger.info("eum collect — 로그인 필요: %s", str(e)[:120])
            return {
                "ok": False,
                "needs_login": True,
                "error": "EUM 로그인이 필요합니다. EUM에 먼저 로그인한 뒤 다시 시도하세요.",
                "collected_sites": 0,
                "duration_ms": int((time.monotonic() - t0) * 1000),
            }
        logger.exception("eum collect error")
        raise HTTPException(status_code=500, detail=f"EUM 수집 실패: {e}") from e


@eum_router.get("/sales-mail/targets")
def get_targets(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """선별된 영업메일 타겟 + 초안 조회 (최신 준비 결과)."""
    if not _TARGETS_LATEST.exists():
        return {"ok": False, "error": "no_data", "hint": "먼저 수집(collect) 실행", "targets": []}
    try:
        data = json.loads(_TARGETS_LATEST.read_text(encoding="utf-8"))
        targets = data.get("targets", []) if isinstance(data, dict) else (data or [])
        return {
            "ok": True,
            "targets": targets,
            "count": len(targets),
            "prepared_at": data.get("timestamp", "") if isinstance(data, dict) else "",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"타겟 로드 실패: {e}") from e


@eum_router.post("/sales-mail/send")
def send_one(
    req: SendRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """영업메일 1건 하이웍스 발송. confirmed=True 필수 (오발송 방지)."""
    if not req.confirmed:
        raise HTTPException(status_code=400, detail="confirmed=True 필수 (외부 메일 — 1건씩 승인 발송)")
    if not req.to or "@" not in req.to:
        raise HTTPException(status_code=400, detail="수신 이메일이 올바르지 않습니다")
    # 승인 문구 + 수신거부. 브라우저를 열기 전에 403.
    require_send_approval(
        "mail_send",
        send_confirm=req.send_confirm,
        expected=EUM_SALES_MAIL_CONFIRM_TEXT,
        recipients=addresses(req.to),
        subject=req.subject[:60],
    )
    try:
        _ensure_root_on_path()
        from scripts.browser.cdp.connection import get_page, run_on_browser_thread
        from scripts.hiworks.mail import fill_compose, send_mail

        # CDP page 조작은 브라우저 전용 스레드에서(playwright sync 스레드 경계).
        def _compose_and_send():
            page = get_page()
            fill_compose(page, to=req.to, subject=req.subject, body=req.body)
            return send_mail(page)

        result = run_on_browser_thread(_compose_and_send, timeout=180)
        ok = bool(result.get("success"))
        log_event(
            "EUM_SALES_MAIL_SEND",
            task_id="-",
            actor=user["actor"],
            role=user["role"],
            decision="ok" if ok else "error",
            note=f"to={req.to} subject={req.subject[:30]}",
        )
        if ok:
            return {"ok": True, "to": req.to, **result}
        raise HTTPException(status_code=500, detail=result.get("error_msg", "발송 실패"))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("eum send error")
        raise HTTPException(status_code=500, detail=f"발송 오류: {e}") from e


@eum_router.post("/quote/generate")
def generate_quote(
    req: QuoteRequest,
    user: dict = Depends(require_role("admin", "owner")),
):
    """견적서 xlsx 생성 후 다운로드."""
    allowed_types = {"이동형_임대", "벽부형_임대", "벽부형_구매"}
    if req.quote_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"quote_type은 {allowed_types} 중 하나여야 합니다.")
    if req.quantity < 1:
        raise HTTPException(status_code=400, detail="수량은 1 이상이어야 합니다.")
    if req.quote_type in ("이동형_임대", "벽부형_임대") and not req.months:
        raise HTTPException(status_code=400, detail="임대 유형은 개월수(months)가 필요합니다.")

    try:
        _ensure_root_on_path()
        from scripts.eum.quote_generator import generate_quote_xlsx

        xlsx_bytes = generate_quote_xlsx(
            recipient=req.recipient,
            quote_type=req.quote_type,  # type: ignore[arg-type]
            quantity=req.quantity,
            months=req.months,
        )

        import io
        from datetime import date as _date

        from scripts.eum.shared.layout_schema import OUTPUT_DIR

        safe_name = req.recipient.replace(" ", "_").replace("/", "_")[:30]
        today = _date.today().strftime("%Y%m%d")
        filename = f"견적서_{safe_name}_{req.quote_type}_{today}.xlsx"
        from urllib.parse import quote as url_quote

        encoded_name = url_quote(filename, safe="")

        # 단말기 견적서 폴더에 사본 저장
        try:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            (OUTPUT_DIR / filename).write_bytes(xlsx_bytes)
        except Exception as _save_err:  # noqa: BLE001 - EUM 영업메일 API(문서에 '발송은 confirmed=True 필수, 자동 일괄발송 금지' 명시) — send_one 엔드포인트는 confirmed 검증이 try 블록 이전에 이미 끝난 뒤에만 실제 발송을 시도하며, except는 실패를 HTTPException(500) 또는 로그인필요 안내로 변환할 뿐 승인을 우회하지 않음. 견적서 로컬 사본 저장 실패는 warn 로그만 남기고 본 스트리밍 응답에는 영향 없음.
            log_event(
                "EUM_QUOTE_SAVE_FAIL",
                task_id="-",
                actor=user["actor"],
                role=user["role"],
                decision="warn",
                note=str(_save_err),
            )

        log_event(
            "EUM_QUOTE_GENERATE",
            task_id="-",
            actor=user["actor"],
            role=user["role"],
            decision="ok",
            note=f"recipient={req.recipient} type={req.quote_type} qty={req.quantity} months={req.months} saved={filename}",
        )
        return StreamingResponse(
            io.BytesIO(xlsx_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("quote generate error")
        raise HTTPException(status_code=500, detail=f"견적서 생성 실패: {e}") from e
