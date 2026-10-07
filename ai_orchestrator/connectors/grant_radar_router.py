"""grant_radar_router.py — 정부 지원사업 레이더 API (Phase 1).

GET  /api/v1/grant-radar/report  — 최신 보고서 JSON 반환 (read-only)
POST /api/v1/grant-radar/scan    — 스캔+보고서 생성 트리거 (별도 헤드리스 subprocess)

L8 Server API 계층. 업무 로직은 scripts/grant_radar/* (L6/L10)에 위임.
보안: secret 미출력. mutation은 로컬 파일 생성뿐(외부 발행/제출 없음).
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from ai_orchestrator.paths.runtime import data_dir

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
# 쓰기 데이터는 영속 경로(paths.runtime.data_dir — HAEHAN_DATA_DIR/HAEHAN_DATA_ROOT), 읽기전용 프로필은 번들 configs
DATA_DIR = data_dir() / "grant_radar"
REPORT_FILE = DATA_DIR / "report_latest.json"
DRAFT_DIR = DATA_DIR / "drafts"
COMPANY_FILE = ROOT / "configs" / "grant_radar_company.json"


def _grant_cmd(task: str) -> list[str]:
    """grant_radar 서브태스크 실행 커맨드.

    `python -m scripts.grant_radar.<module>` 로 실행 (uvicorn 소스 실행 전제,
    패키징 배포 없음).
    """
    module = {"scan": "scan", "report": "report", "fill": "form_fill"}[task]
    if getattr(sys, "frozen", False):
        return [sys.executable, "--grant-task", task]
    return [sys.executable, "-m", f"scripts.grant_radar.{module}"]


grant_radar_router = APIRouter(prefix="/grant-radar", tags=["grant-radar"])

_scan_running = False

# 응답에서 가리는 민감 키 (감사/보안)
_MASK_KEYS = {"business_no", "_note"}


def _load_company() -> dict:
    try:
        return json.loads(COMPANY_FILE.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("회사 프로필 로드 실패: %s", COMPANY_FILE, exc_info=True)
        return {}


def _load_report_items() -> list[dict]:
    if not REPORT_FILE.exists():
        return []
    try:
        return json.loads(REPORT_FILE.read_text(encoding="utf-8")).get("items", [])
    except Exception:
        logger.warning("보고서 항목 로드 실패: %s", REPORT_FILE, exc_info=True)
        return []


@grant_radar_router.get("/report")
def get_report():
    """최신 지원사업 보고서 반환. 없으면 빈 결과."""
    if not REPORT_FILE.exists():
        return {"ok": False, "reason": "no_report", "items": [], "message": "아직 스캔 전입니다. 스캔을 실행하세요."}
    try:
        data = json.loads(REPORT_FILE.read_text(encoding="utf-8"))
        return data
    except Exception as e:
        logger.error("보고서 로드 실패: %s", e)
        logger.exception("보고서 로드 실패: %s", e)
        return {"ok": False, "reason": "read_error", "items": []}


@grant_radar_router.post("/scan")
def trigger_scan():
    """스캔 → 보고서 생성을 동기 실행. (별도 헤드리스 Chromium, 메인 Chrome 무관)"""
    global _scan_running
    if _scan_running:
        return {"ok": False, "reason": "already_running"}
    _scan_running = True
    try:
        scan = subprocess.run(
            _grant_cmd("scan"),
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        rep = subprocess.run(
            _grant_cmd("report"),
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        ok = scan.returncode == 0 and rep.returncode == 0
        if not ok:
            logger.warning("스캔/보고서 실패 scan=%s report=%s", scan.returncode, rep.returncode)
        return {"ok": ok, "scan_rc": scan.returncode, "report_rc": rep.returncode}
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "timeout"}
    except Exception as e:
        logger.error("스캔 실행 오류: %s", e)
        logger.exception("스캔 실행 오류: %s", e)
        return {"ok": False, "reason": "exec_error"}
    finally:
        _scan_running = False


class DraftRequest(BaseModel):
    item_index: int
    confirm: bool = False


@grant_radar_router.post("/draft")
def make_draft(body: DraftRequest):
    """신청서 초안 생성. confirm=True(사용자 승인) 시에만 LLM 생성·저장.

    외부 제출이 아닌 로컬 초안 작성. 실제 제출은 사용자 최종 단계(Phase 3).
    """
    items = _load_report_items()
    if body.item_index < 0 or body.item_index >= len(items):
        return {"ok": False, "reason": "invalid_item"}
    grant = items[body.item_index]

    # 승인 게이트: confirm 없으면 미생성, 미리보기만 반환
    if not body.confirm:
        return {
            "ok": False,
            "need_confirm": True,
            "preview": {
                "title": grant.get("title", ""),
                "deadline": grant.get("dday") or grant.get("deadline"),
                "portal": grant.get("portal_name", ""),
            },
        }

    company = _load_company()
    try:
        from ..llm.openai_client import generate_application_draft

        draft = generate_application_draft(grant, company)
    except Exception as e:
        logger.error("초안 생성 오류: %s", e)
        logger.exception("초안 생성 오류: %s", e)
        return {"ok": False, "reason": "draft_error"}

    # 저장
    DRAFT_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c for c in grant.get("title", "draft")[:40] if c.isalnum() or c in " _-").strip() or "draft"
    path = DRAFT_DIR / f"{body.item_index:03d}_{safe_name}.md"
    path.write_text(draft, encoding="utf-8")

    # 감사 로그 (외부 제출 아님, 초안 생성 기록)
    try:
        from ..audit.audit_logger import log_event

        log_event(
            event_type="GRANT_DRAFT_CREATED",
            task_id=f"grant-{body.item_index}",
            risk_level="low",
            actor="user",
            action_type="grant.draft",
            target=grant.get("title", "")[:60],
            note=f"portal={grant.get('portal')}",
        )
    except Exception as e:  # noqa: BLE001 - 정부지원사업 공고 스캔/초안생성 API - 모두 ok:False,reason 반환, 실제 신청서 제출 없음(초안 저장까지만), 감사로그 실패는 warning 으로만 무시
        logger.warning("초안 감사로그 기록 실패(무시): %s", e)

    return {"ok": True, "title": grant.get("title", ""), "draft": draft, "saved": path.name}


@grant_radar_router.get("/drafts")
def list_drafts():
    """저장된 신청서 초안 목록."""
    if not DRAFT_DIR.exists():
        return {"ok": True, "drafts": []}
    files = sorted(DRAFT_DIR.glob("*.md"))
    return {"ok": True, "drafts": [{"name": f.name, "size": f.stat().st_size} for f in files]}


class FillRequest(BaseModel):
    url_substr: str
    text: str
    confirm: bool = False
    target_index: int | None = None


@grant_radar_router.post("/fill")
def fill_form(body: FillRequest):
    """신청폼 자동입력 (로컬 CDP). confirm=False면 채울 필드 계획만 반환.

    ★ submit 미클릭 — 최종 제출은 사용자. 로컬 전용(서버엔 CDP 없음).
    """
    payload = json.dumps(
        {"url_substr": body.url_substr, "text": body.text, "confirm": body.confirm, "target_index": body.target_index},
        ensure_ascii=False,
    )
    try:
        proc = subprocess.run(
            _grant_cmd("fill"),
            cwd=str(ROOT),
            input=payload,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
        )
        out = (proc.stdout or "").strip().splitlines()
        result = json.loads(out[-1]) if out else {"ok": False, "reason": "no_output"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "timeout"}
    except Exception as e:
        logger.error("폼 입력 오류: %s", e)
        logger.exception("폼 입력 오류: %s", e)
        return {"ok": False, "reason": "exec_error"}

    if result.get("ok"):
        try:
            from ..audit.audit_logger import log_event

            log_event(
                event_type="GRANT_FORM_FILLED",
                task_id="grant-fill",
                risk_level="low",
                actor="user",
                action_type="grant.fill",
                target=body.url_substr[:60],
                note=f"filled_len={result.get('filled_len')}",
            )
        except Exception as e:  # noqa: BLE001 - 정부지원사업 공고 스캔/초안생성 API - 모두 ok:False,reason 반환, 실제 신청서 제출 없음(초안 저장까지만), 감사로그 실패는 warning 으로만 무시
            logger.warning("폼입력 감사로그 실패(무시): %s", e)
    return result
