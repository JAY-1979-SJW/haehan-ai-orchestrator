"""L8 Server API — 가비아 업무 현황 라우터.

지원 엔드포인트:
  GET  /api/v1/gabia/status        - 업무 현황 + 게이트 정책 요약
  GET  /api/v1/gabia/dns/tasks     - DNS 업무 레지스트리 목록
  POST /api/v1/gabia/login/watch   - 로그인 감지 스크립트 백그라운드 시작
  GET  /api/v1/gabia/nav-plan      - 브라우저 작업 네비게이션 계획

금지: 비밀번호/OTP/세션/쿠키 반환 금지, 결제 자동화 금지
"""

from __future__ import annotations

import subprocess
import sys

from fastapi import APIRouter
from pydantic import BaseModel

from ...paths import repo_root

gabia_router = APIRouter(prefix="/gabia", tags=["gabia"])

ROOT = repo_root()


# ── 응답 모델 ─────────────────────────────────────────────────────────────────


class GabiaOperation(BaseModel):
    name: str
    gate: str
    note: str
    user_action_required: bool


class GabiaStatusResponse(BaseModel):
    provider: str
    base_url: str
    operations: list[GabiaOperation]
    login_note: str
    dns_mgmt_url: str


class DnsTaskItem(BaseModel):
    external_work_id: str
    action_type: str
    category: str
    risk_level: str
    approval_required: bool
    description: str


class LoginWatchResponse(BaseModel):
    ok: bool
    message: str
    pid: int | None = None


class NavStep(BaseModel):
    step: int
    state: str
    actor: str
    action: str
    safe_to_auto: bool


# ── 엔드포인트 ────────────────────────────────────────────────────────────────


@gabia_router.get("/status", response_model=GabiaStatusResponse)
def get_gabia_status():
    """가비아 업무 현황 및 게이트 정책 요약."""
    operations = [
        GabiaOperation(
            name="공개 페이지 조회", gate="READ_ONLY_ALLOWED", note="로그인 없이 가능", user_action_required=False
        ),
        GabiaOperation(
            name="계정 정보 조회",
            gate="LOCAL_AGENT_REQUIRED",
            note="로컬 에이전트 + 로그인 세션 필요",
            user_action_required=True,
        ),
        GabiaOperation(
            name="로그인 / OTP",
            gate="USER_DIRECT_REQUIRED",
            note="OTP/2FA 필수 — 사용자가 직접 수행",
            user_action_required=True,
        ),
        GabiaOperation(
            name="DNS 레코드 변경",
            gate="APPROVAL_REQUIRED",
            note="AI 입력 준비 → 사용자 최종 저장",
            user_action_required=True,
        ),
        GabiaOperation(
            name="DNS 레코드 삭제",
            gate="APPROVAL_REQUIRED",
            note="비가역 작업 — 사용자 승인 필수",
            user_action_required=True,
        ),
        GabiaOperation(
            name="도메인 연장/이전",
            gate="APPROVAL_REQUIRED",
            note="비가역 — 사용자 승인 필수",
            user_action_required=True,
        ),
        GabiaOperation(
            name="호스팅/메일 설정", gate="APPROVAL_REQUIRED", note="사용자 승인 후 실행", user_action_required=True
        ),
        GabiaOperation(
            name="결제/청구", gate="BLOCKED", note="사용자가 직접 my.gabia.com 처리", user_action_required=True
        ),
    ]
    return GabiaStatusResponse(
        provider="gabia",
        base_url="https://www.gabia.com",
        operations=operations,
        login_note="가비아는 OTP/2FA 필수로 자동 로그인 불가. 브라우저에서 직접 로그인 후 AI가 세션을 재사용합니다.",
        dns_mgmt_url="https://my.gabia.com/service/domain/haehan-ai.kr/dns",
    )


@gabia_router.get("/dns/tasks", response_model=list[DnsTaskItem])
def list_dns_tasks():
    """가비아 DNS 업무 레지스트리 목록."""
    from ai_orchestrator.connectors.gabia.dns_work_registry import list_gabia_external_works

    works = list_gabia_external_works()
    return [
        DnsTaskItem(
            external_work_id=w.external_work_id,
            action_type=w.action_type,
            category=w.category,
            risk_level=w.risk_level,
            approval_required=w.approval_required,
            description=w.description,
        )
        for w in works
    ]


@gabia_router.post("/login/watch", response_model=LoginWatchResponse)
def start_login_watch():
    """가비아 로그인 감지 스크립트를 백그라운드로 시작.

    브라우저에서 사용자가 직접 로그인하면 감지 후 DNS 관리 화면으로 이동합니다.
    비밀번호/OTP는 사용자가 직접 입력합니다.
    """
    script = ROOT / "scripts" / "gabia" / "login_watch.py"
    if not script.exists():
        return LoginWatchResponse(ok=False, message="gabia/login_watch.py 스크립트를 찾을 수 없습니다")
    try:
        proc = subprocess.Popen(
            [sys.executable, str(script), "--timeout", "300"],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return LoginWatchResponse(
            ok=True,
            message="로그인 감지 시작됨. 브라우저에서 가비아 로그인을 진행하세요. (최대 5분 대기)",
            pid=proc.pid,
        )
    except Exception as e:  # noqa: BLE001 - 가비아 로그인 감지 프로세스 시작 실패를 LoginWatchResponse(ok=False, message=...)로 반환 — fail-closed, 사용자에게 실패를 알림
        return LoginWatchResponse(ok=False, message=f"시작 실패: {e}")


@gabia_router.get("/nav-plan", response_model=list[NavStep])
def get_nav_plan():
    """가비아 DNS 업무 브라우저 네비게이션 계획."""
    from ai_orchestrator.connectors.gabia.browser_task import GABIA_NAV_PLAN

    return [
        NavStep(
            step=s["step"],
            state=s["state"],
            actor=s["actor"],
            action=s["action"],
            safe_to_auto=s["safe_to_auto"],
        )
        for s in GABIA_NAV_PLAN
    ]
