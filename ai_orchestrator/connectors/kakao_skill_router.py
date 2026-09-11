"""카카오 챗봇 "스킬"(오픈빌더) webhook 수신 API (L8).

POST /kakao/skill/kakaotalk-skill — 카카오 챗봇 관리자센터의 스킬 URL에 등록하는 실제 응답 엔드포인트.

정책:
  - 자유 생성형 AI 자동 답변 아님 — 고정 안내 문구로 즉시 응답한다.
  - 실제 문의 내용은 inbox에 저장되어 사람이 이어서 응대한다.
  - 이 라우터는 카카오가 호출하는 외부 webhook이므로 JWT 인증 대상이 아니다
    (instagram_dm_router 등 다른 webhook 커넥터와 동일 컨벤션).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..inbox import create_inbox_item, exists_by_external_id

logger = logging.getLogger(__name__)

kakao_skill_router = APIRouter(prefix="/kakao/skill", tags=["kakao-skill"])

_MAX_UTTERANCE_LEN = 4096

_FIXED_REPLY = (
    "문의 감사합니다. 담당자가 확인 후 빠르게 답변드리겠습니다. 급하신 내용은 010-7378-6635로 문자 남겨주세요."
)


def _skill_response(text: str) -> dict:
    """카카오 오픈빌더 스킬 응답 규격(version 2.0, simpleText)."""
    return {
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": text}}]},
    }


def _parse_payload(payload: dict) -> dict:
    """카카오 오픈빌더 스킬 payload 파싱. 필수 필드 누락 시 ValueError."""
    if not isinstance(payload, dict):
        raise ValueError("payload는 dict이어야 합니다")

    user_request = payload.get("userRequest")
    if not isinstance(user_request, dict):
        raise ValueError("userRequest 누락 또는 형식 오류")

    user = user_request.get("user") or {}
    utterance = str(user_request.get("utterance") or "").strip()
    user_id = str(user.get("id") or "")

    if not user_id:
        raise ValueError("userRequest.user.id 누락")
    if not utterance:
        raise ValueError("utterance 누락 또는 빈 문자열")
    if len(utterance) > _MAX_UTTERANCE_LEN:
        raise ValueError(f"utterance 최대 길이 초과 (max={_MAX_UTTERANCE_LEN})")

    bot = payload.get("bot") or {}
    bot_id = str(bot.get("id") or "kakaotalk-skill-default")

    now_dt = datetime.now(UTC)
    raw = f"kakaotalk-skill:{user_id}:{utterance[:30]}:{now_dt.isoformat()}"
    external_id = f"kakaotalk-skill:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"

    title = (utterance[:50] + "...") if len(utterance) > 50 else utterance

    return {
        "external_id": external_id,
        "source_account": bot_id,
        "sender": user_id,
        "title": title,
        "body_raw": utterance,
        "metadata": {"bot_id": bot_id, "user_id": user_id, "user_type": user.get("type", "")},
    }


@kakao_skill_router.post("/kakaotalk-skill")
async def receive_kakaotalk_skill(request: Request):
    """
    카카오 챗봇 스킬 응답 엔드포인트.
    payload 파싱 → inbox 저장(중복 시 skip) → 고정 안내 문구로 즉시 스킬 응답.
    payload가 비었거나 잘못돼도 항상 200 + 정상 스킬 응답 포맷을 반환한다
    (카카오톡 쪽에 에러 화면이 뜨지 않도록).
    """
    try:
        payload = await request.json()
    except Exception:
        payload = None

    if not payload:
        logger.warning("kakaotalk-skill webhook: empty payload")
        return JSONResponse(_skill_response(_FIXED_REPLY))

    try:
        msg = _parse_payload(payload)
    except ValueError as e:
        logger.warning("kakaotalk-skill webhook: payload invalid: %s", e)
        return JSONResponse(_skill_response(_FIXED_REPLY))

    if exists_by_external_id(msg["external_id"], source_type="kakaotalk_channel"):
        logger.info("kakaotalk-skill message duplicate: external_id=%s", msg["external_id"][:24])
    else:
        create_inbox_item(
            source_type="kakaotalk_channel",
            source_account=msg["source_account"],
            external_id=msg["external_id"],
            sender=msg["sender"],
            title=msg["title"],
            body_raw=msg["body_raw"],
            metadata=msg["metadata"],
        )
        logger.info("kakaotalk-skill message saved: external_id=%s", msg["external_id"][:24])

    return JSONResponse(_skill_response(_FIXED_REPLY))
