"""네이버 메일 엔드포인트 (/api/v1/naver-mail/*).

- GET  /inbox      : 받은편지함 목록 (read-only, 브라우저 불필요 — DB/파일 캐시)
- POST /compose    : 메일 작성 준비 (브라우저 자동화, 사용자 승인 필요)
- POST /send       : 작성된 메일 발송 (사용자 명시 승인 + 추가 확인 필수)

보안 원칙:
  - /compose, /send 는 매번 사용자 명시 승인 필요 (CLAUDE.md 메일 전송 정책)
  - cookie/session 값 응답 금지
  - dry_run=True(기본) 이면 브라우저 자동화 미실행, 작성 정보만 반환
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ai_orchestrator.audit.audit_logger import log_event
from tools.gates.auth import require_role

logger = logging.getLogger(__name__)

naver_mail_router = APIRouter(prefix="/naver-mail", tags=["naver-mail"])


# ── 스키마 ────────────────────────────────────────────────────────────────────


class MailComposeRequest(BaseModel):
    to: str  # 수신인 (콤마 구분 다중)
    cc: str | None = None
    subject: str = ""
    body: str = ""
    dry_run: bool = True  # True=자동화 미실행, False=실제 브라우저 실행


class MailComposeResponse(BaseModel):
    ok: bool
    dry_run: bool
    to: str
    cc: str | None
    subject: str
    body_preview: str  # 본문 앞 100자
    detail: str = ""
    requires_send_approval: bool = True


# ── 엔드포인트 ────────────────────────────────────────────────────────────────


@naver_mail_router.post("/compose")
def api_compose(
    req: MailComposeRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> MailComposeResponse:
    """메일 작성 준비.

    dry_run=True(기본): 브라우저 미실행, 작성 정보만 검증·반환.
    dry_run=False: 네이버 메일 작성 페이지에 실제로 필드를 채워 준비 상태로 대기.
    발송(send)은 별도 /send 엔드포인트 + 사용자 명시 승인 필요.
    """
    body_preview = req.body[:100] if req.body else ""

    log_event(
        "NAVER_MAIL_COMPOSE_REQUESTED",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok" if req.dry_run else "pending_browser",
        note=f"to={req.to} subject={req.subject[:30]} dry_run={req.dry_run}",
    )

    if req.dry_run:
        return MailComposeResponse(
            ok=True,
            dry_run=True,
            to=req.to,
            cc=req.cc,
            subject=req.subject,
            body_preview=body_preview,
            detail="dry_run=True: 브라우저 자동화 미실행. 실행하려면 dry_run=False로 재요청.",
            requires_send_approval=True,
        )

    # dry_run=False: 실제 브라우저 자동화
    # 2026-09-29 정정(docs/defect_index.json #37): 예전엔 여기서 scripts.naver.mail의
    # compose()/send_mail()을 import 했는데, 그 함수들은 이 저장소 히스토리 전체를 뒤져도
    # 존재한 적이 없다(2026-09-23에 지워진 scripts/naver_mail 구 호환 패키지도 2줄짜리
    # 재노출 shim이었을 뿐, 실제 구현은 처음부터 없었음 — 이 라우터가 아직 없는 기능을
    # 미리 가정하고 쓰여 있던 것). scripts.naver.mail 패키지 자체도 "발송/답장/삭제/이동
    # 금지"를 모듈 docstring에 명시한 읽기전용 설계라, 그 자리에 억지로 send 함수를
    # 끼워넣는 대신 아직 미구현임을 정직하게 알린다. 실제 발송 자동화(Gmail 라우터처럼
    # CDP로 작성창을 직접 조작하는 방식)는 별도 기준서로 새로 설계해야 한다.
    raise HTTPException(
        status_code=501,
        detail=(
            "네이버메일 브라우저 자동 작성(dry_run=False)은 아직 구현되지 않았습니다. "
            "dry_run=True 로 초안 검증만 가능합니다."
        ),
    )


class MailSendRequest(BaseModel):
    confirmed: bool = False  # 사용자가 UI에서 "발송 확인" 버튼을 눌렀는지 여부


@naver_mail_router.post("/send")
def api_send(
    req: MailSendRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """현재 브라우저에 열려 있는 작성 메일 발송.

    반드시 /compose (dry_run=False) 이후에 호출해야 함.
    confirmed=True 여야 실제 발송 진행.
    """
    if not req.confirmed:
        raise HTTPException(
            status_code=400,
            detail="confirmed=True 로 사용자 명시 승인 후 재요청하세요.",
        )

    log_event(
        "NAVER_MAIL_SEND_REQUESTED",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note="user confirmed send",
    )

    # 2026-09-29 정정(docs/defect_index.json #37): /compose 와 같은 이유로 아직 미구현.
    raise HTTPException(
        status_code=501,
        detail="네이버메일 자동 발송은 아직 구현되지 않았습니다.",
    )
