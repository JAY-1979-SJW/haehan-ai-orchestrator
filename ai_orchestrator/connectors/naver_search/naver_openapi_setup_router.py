"""L8 — 네이버 개발자센터 등록 앱의 Client ID/Secret 조회 (설정화면 자동입력용).

새 앱을 등록하는 게 아니라 이미 등록된 앱의 키를 CDP로 읽어와, 다른 PC에 설치한
데스크톱 앱의 설정화면(userData/.env)에 그대로 재사용하기 위한 헬퍼.

POST /api/v1/naver/openapi-setup/lookup-keys
  body: {app_id: str, confirm_secret_reveal: bool}
  - confirm_secret_reveal=False: Client ID만 반환 (민감값 아님)
  - confirm_secret_reveal=True : 개발자센터 "보기" 버튼을 클릭해 Client Secret도 반환
    → 호출자(프론트)는 반드시 실행 직전 사용자에게 확인을 받은 뒤에만 True로 호출한다.
  - 응답값은 로그에 남기지 않는다(log_event 에도 값 자체는 기록하지 않음).
"""

from __future__ import annotations

import logging
import sys

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from tools.gates.auth import require_role

from ...audit.audit_logger import log_event
from ai_orchestrator.paths import repo_root

ROOT = repo_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logger = logging.getLogger(__name__)

naver_openapi_setup_router = APIRouter(prefix="/naver/openapi-setup", tags=["naver-openapi-setup"])


class LookupKeysRequest(BaseModel):
    app_id: str
    confirm_secret_reveal: bool = False


@naver_openapi_setup_router.post("/lookup-keys")
def lookup_keys(body: LookupKeysRequest, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    from scripts.naver.openapi_key_lookup import lookup_naver_openapi_keys

    result = lookup_naver_openapi_keys(body.app_id, confirm_secret_reveal=body.confirm_secret_reveal)
    log_event(
        "NAVER_OPENAPI_KEY_LOOKUP",
        task_id="-",
        actor=user["actor"],
        target=body.app_id,
        note=f"secret_revealed={bool(body.confirm_secret_reveal)} ok={bool(result.get('ok'))}",
    )
    return result
