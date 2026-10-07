"""카카오 챗봇 "스킬"(오픈빌더) webhook 수신 API (L8).

POST /kakao/skill/kakaotalk-skill — 카카오 챗봇 관리자센터의 스킬 URL에 등록하는 실제 응답 엔드포인트.

정책:
  - 자유 생성형 AI 자동 답변 아님 — 기존 규칙기반 분류기(message_classifier, AI 미사용)로
    카테고리를 판정해 카테고리별 고정 안내 문구로 즉시 응답한다. 외부 유료 API 미사용.
  - 실제 문의 내용은 inbox에 저장되어 사람이 이어서 응대한다.
  - 이 라우터는 카카오가 호출하는 외부 webhook이므로 JWT 인증 대상이 아니다
    (instagram_dm_router 등 다른 웹훅 커넥터와 동일 컨벤션).
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ai_orchestrator.core import telegram_sender

from ...paths import repo_root
from ...tasks.inbox import create_inbox_item, exists_by_external_id

_ROOT = repo_root()
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from orchestrator_v1.inbox.message_classifier import classify_message  # noqa: E402 - 규칙기반(AI 미사용)

logger = logging.getLogger(__name__)

kakao_skill_router = APIRouter(prefix="/kakao/skill", tags=["kakao-skill"])

_MAX_UTTERANCE_LEN = 4096

_FIXED_REPLY = "문의 감사합니다. 담당자가 확인 후 빠르게 답변드리겠습니다."

# 카테고리별 안내 문구 — message_classifier.classify_message()의 category 값에 대응.
# AI 생성 아님, 고정 템플릿. general/미분류는 _FIXED_REPLY로 폴백.
# 전화번호 등 개인 연락처는 노출하지 않는다.
_CATEGORY_REPLIES: dict[str, str] = {
    "support": "문의 주셔서 감사합니다. 담당자가 확인 후 빠르게 안내드리겠습니다.",
    "sales": "견적/영업 문의 감사합니다. 담당자가 확인 후 견적 및 상담 내용을 안내드리겠습니다.",
    "bidding": "입찰/조달 관련 문의 감사합니다. 담당자가 확인 후 회신드리겠습니다.",
    "accounting": "정산/청구 관련 문의 감사합니다. 담당 부서에서 확인 후 답변드리겠습니다.",
    "development": "기술/개발 관련 문의 감사합니다. 담당자가 확인 후 답변드리겠습니다.",
    "operations": "문의 내용 확인했습니다. 담당자가 최대한 빠르게 확인해 드리겠습니다.",
}


def _reply_for_category(category: str) -> str:
    return _CATEGORY_REPLIES.get(category, _FIXED_REPLY)


def _notify_new_inquiry(category: str, title: str) -> None:
    """새 카톡 문의를 텔레그램으로 알림 (best-effort, 실패해도 스킬 응답은 계속 진행).

    챗봇이 카카오 스킬로 자동응답하면 카카오는 "이미 응답 완료"로 처리해
    채널 관리자 앱에 모바일 푸시를 보내지 않는다 — 그 공백을 메우기 위한 알림.
    """
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_APPROVER_CHAT_ID")
    if not chat_id:
        return
    text = f"[카카오톡 문의] 카테고리: {category}\n{title}"
    try:
        telegram_sender.send_message(text, chat_id=chat_id)
    except Exception as e:  # 알림 실패가 스킬 응답을 막으면 안 됨  # noqa: BLE001 - 카카오톡 오픈빌더 스킬 웹훅 -- 텔레그램 알림 실패가 스킬 응답을 막지 않도록 로깅만 하고 진행, payload 파싱 실패는 고정 응답으로 폴백
        logger.warning("kakaotalk-skill telegram 알림 실패: %s", e)


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
    except Exception as exc:  # noqa: BLE001 - 카카오톡 오픈빌더 스킬 웹훅 -- 텔레그램 알림 실패가 스킬 응답을 막지 않도록 로깅만 하고 진행, payload 파싱 실패는 고정 응답으로 폴백
        logger.debug("카카오 스킬 요청 본문 JSON 파싱 실패(무시): %s", type(exc).__name__)
        payload = None

    if not payload:
        logger.warning("kakaotalk-skill webhook: empty payload")
        return JSONResponse(_skill_response(_FIXED_REPLY))

    try:
        msg = _parse_payload(payload)
    except ValueError as e:
        logger.warning("kakaotalk-skill webhook: payload invalid: %s", e)
        return JSONResponse(_skill_response(_FIXED_REPLY))

    classification = classify_message(
        {
            "source_type": "kakaotalk_channel",
            "title": msg["title"],
            "body_raw": msg["body_raw"],
            "sender": msg["sender"],
        }
    )
    category = classification.get("category", "general")
    reply_text = _reply_for_category(category)  # 고정 안내 문구(유료 AI 호출 없음 — 2026-09-24 제거)

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
            metadata={**msg["metadata"], "classification": classification},
        )
        logger.info(
            "kakaotalk-skill message saved: external_id=%s category=%s",
            msg["external_id"][:24],
            category,
        )
        _notify_new_inquiry(category, msg["title"])

    return JSONResponse(_skill_response(reply_text))
