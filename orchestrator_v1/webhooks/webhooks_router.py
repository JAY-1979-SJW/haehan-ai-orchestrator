"""
외부 서비스 Webhook 수신 라우트 (Flask Blueprint)

POST /api/v1/webhooks/kakaowork          — 카카오워크 Bot webhook 수신 → inbox 저장
POST /api/v1/webhooks/kakaotalk-channel  — 카카오톡 채널 범용 webhook 수신 → inbox 저장 (자동 회신 없음)
POST /api/v1/webhooks/kakaotalk-skill    — 카카오 챗봇 "스킬" 서버 (오픈빌더 연동) → 즉시 스킬 응답 반환

정책:
  - 카카오워크 / 카카오톡 채널(범용 webhook): 자동 실행·자동 회신 없음, inbox 저장만 수행
  - 카카오톡 스킬(오픈빌더): 사용자가 명시 승인한 채널 챗봇 전용 경로이므로, 고정 안내 문구로만
    즉시 응답한다 (AI 생성 답변 아님). 자유 생성형 자동회신은 여전히 금지.
  - 기존 approval/executor 파이프라인 미연결
"""

import hashlib
import hmac
import os
from datetime import UTC, datetime

from flask import Blueprint, jsonify, request

from orchestrator_v1.core import audit_logger
import inbox_store
import kakaowork_reader
from orchestrator_v1.core.logger import get_logger

log = get_logger("webhooks_router")

webhooks_bp = Blueprint("webhooks", __name__, url_prefix="/api/v1/webhooks")

_KAKAOTALK_CHANNEL_ACCOUNT = os.environ.get("KAKAOTALK_CHANNEL_ID", "kakaotalk-channel-default")

_KAKAOTALK_MAX_UTTERANCE_LEN = 4096


def _verify_kakaowork_signature(bot_key: str, req) -> tuple[bool, str]:
    """
    X-Kakaowork-Signature 헤더를 HMAC-SHA256으로 검증.
    반환: (is_valid, reason)
    """
    sig = req.headers.get("X-Kakaowork-Signature", "")
    if not sig:
        return False, "signature header missing"
    body = req.get_data()
    expected = hmac.new(bot_key.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig.lower(), expected.lower()):
        return False, "signature mismatch"
    return True, "ok"


# ── 카카오워크 Bot webhook ─────────────────────────────────────────────────────


@webhooks_bp.route("/kakaowork", methods=["POST"])
def receive_kakaowork():
    """
    카카오워크 Bot webhook 수신.
    payload 파싱 → inbox 저장 → 200 OK 반환.
    자동 회신/실행 없음.
    """
    # 서명 검증 (KAKAOWORK_BOT_KEY 설정 시 강제)
    bot_key = os.environ.get("KAKAOWORK_BOT_KEY", "")
    if bot_key:
        sig_valid, sig_reason = _verify_kakaowork_signature(bot_key, request)
        if not sig_valid:
            audit_logger.record(
                "KAKAOWORK_SIGNATURE_INVALID",
                actor="webhook",
                source_type="kakaowork",
                reason=sig_reason,
            )
            log.warning("kakaowork webhook: signature invalid: %s", sig_reason)
            return jsonify({"status": "error", "message": "unauthorized"}), 401
        audit_logger.record(
            "KAKAOWORK_SIGNATURE_VALID",
            actor="webhook",
            source_type="kakaowork",
        )
    else:
        log.warning("kakaowork webhook: KAKAOWORK_BOT_KEY not configured, signature verification skipped")

    payload = request.get_json(silent=True)

    if not payload:
        audit_logger.record(
            "KAKAOWORK_MESSAGE_FAILED",
            actor="webhook",
            note="empty or invalid JSON payload",
        )
        log.warning("kakaowork webhook: empty payload")
        return jsonify({"status": "error", "message": "invalid payload"}), 400

    try:
        msg = kakaowork_reader.parse_webhook_payload(payload)
    except ValueError as e:
        audit_logger.record(
            "KAKAOWORK_MESSAGE_FAILED",
            actor="webhook",
            note=f"parse error: {e}",
        )
        log.warning("kakaowork webhook: parse error: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 400

    result = inbox_store.save_message(
        source_type=msg["source_type"],
        external_id=msg["external_id"],
        source_account=msg["source_account"],
        sender=msg["sender"],
        title=msg["title"],
        body_raw=msg["body_raw"],
        received_at=msg["received_at"],
        metadata=msg.get("metadata"),
    )

    if result["status"] == "saved":
        audit_logger.record(
            "KAKAOWORK_MESSAGE_RECEIVED",
            actor="webhook",
            note=f"saved external_id={msg['external_id'][:20]}",
        )
        log.info("kakaowork message saved: external_id=%s", msg["external_id"][:20])
    else:
        audit_logger.record(
            "KAKAOWORK_MESSAGE_DUPLICATE",
            actor="webhook",
            note=f"duplicate external_id={msg['external_id'][:20]}",
        )
        log.info("kakaowork message duplicate: external_id=%s", msg["external_id"][:20])

    # 카카오워크 webhook은 200 OK만 반환 — 자동 회신 없음
    return jsonify({"status": result["status"]}), 200


# ── 카카오톡 채널 webhook (뼈대) ───────────────────────────────────────────────


@webhooks_bp.route("/kakaotalk-channel", methods=["POST"])
def receive_kakaotalk_channel():
    """
    카카오톡 채널 webhook 수신 (뼈대).
    채널 기반 비즈니스 webhook만 처리 — 개인 카카오톡 연동 없음.
    payload 파싱 → inbox 저장 → 200 OK 반환.
    자동 회신/실행 없음.
    """
    payload = request.get_json(silent=True)

    if not payload:
        audit_logger.record(
            "KAKAOTALK_CHANNEL_MESSAGE_FAILED",
            actor="webhook",
            note="empty or invalid JSON payload",
        )
        log.warning("kakaotalk-channel webhook: empty payload")
        return jsonify({"status": "error", "message": "invalid payload"}), 400

    try:
        msg = _parse_kakaotalk_channel_payload(payload)
    except ValueError as e:
        audit_logger.record(
            "KAKAOTALK_CHANNEL_PAYLOAD_INVALID",
            actor="webhook",
            source_type="kakaotalk_channel",
            reason=str(e),
        )
        log.warning("kakaotalk-channel webhook: payload invalid: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 400

    result = inbox_store.save_message(
        source_type="kakaotalk_channel",
        external_id=msg["external_id"],
        source_account=msg["source_account"],
        sender=msg["sender"],
        title=msg["title"],
        body_raw=msg["body_raw"],
        received_at=msg["received_at"],
        metadata=msg.get("metadata"),
    )

    if result["status"] == "saved":
        audit_logger.record(
            "KAKAOTALK_CHANNEL_MESSAGE_RECEIVED",
            actor="webhook",
            note=f"saved external_id={msg['external_id'][:20]}",
        )
        log.info("kakaotalk-channel message saved: external_id=%s", msg["external_id"][:20])
    else:
        audit_logger.record(
            "KAKAOTALK_CHANNEL_MESSAGE_DUPLICATE",
            actor="webhook",
            note=f"duplicate external_id={msg['external_id'][:20]}",
        )
        log.info("kakaotalk-channel message duplicate: external_id=%s", msg["external_id"][:20])

    # 카카오톡 채널 webhook은 200 OK만 반환 — 자동 회신 없음
    return jsonify({"status": result["status"]}), 200


# ── 카카오톡 스킬(오픈빌더) webhook ───────────────────────────────────────────

_KAKAOTALK_SKILL_FIXED_REPLY = "문의 감사합니다. 담당자가 확인 후 빠르게 답변드리겠습니다."


def _kakao_skill_text_response(text: str) -> dict:
    """카카오 오픈빌더 스킬 응답 규격(version 2.0, simpleText)으로 감싼다."""
    return {
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": text}}]},
    }


@webhooks_bp.route("/kakaotalk-skill", methods=["POST"])
def receive_kakaotalk_skill():
    """
    카카오 챗봇 관리자센터 "스킬"에 등록하는 실제 응답 엔드포인트.
    payload 파싱 → inbox 저장(기존 로직 재사용) → 고정 안내 문구로 즉시 스킬 응답.
    AI 생성형 자동 답변 아님 — 실제 문의 내용은 inbox에 남아 사람이 이어서 응대한다.
    """
    payload = request.get_json(silent=True)

    if not payload:
        audit_logger.record(
            "KAKAOTALK_CHANNEL_PAYLOAD_INVALID",
            actor="webhook",
            source_type="kakaotalk_channel",
            reason="empty or invalid JSON payload",
        )
        log.warning("kakaotalk-skill webhook: empty payload")
        return jsonify(_kakao_skill_text_response(_KAKAOTALK_SKILL_FIXED_REPLY)), 200

    try:
        msg = _parse_kakaotalk_channel_payload(payload)
    except ValueError as e:
        audit_logger.record(
            "KAKAOTALK_CHANNEL_PAYLOAD_INVALID",
            actor="webhook",
            source_type="kakaotalk_channel",
            reason=str(e),
        )
        log.warning("kakaotalk-skill webhook: payload invalid: %s", e)
        # 스킬 서버는 항상 200 + 정상 응답 포맷을 돌려줘야 카카오톡에 에러가 안 뜬다.
        return jsonify(_kakao_skill_text_response(_KAKAOTALK_SKILL_FIXED_REPLY)), 200

    result = inbox_store.save_message(
        source_type="kakaotalk_channel",
        external_id=msg["external_id"],
        source_account=msg["source_account"],
        sender=msg["sender"],
        title=msg["title"],
        body_raw=msg["body_raw"],
        received_at=msg["received_at"],
        metadata=msg.get("metadata"),
    )

    audit_logger.record(
        "KAKAOTALK_CHANNEL_MESSAGE_RECEIVED" if result["status"] == "saved" else "KAKAOTALK_CHANNEL_MESSAGE_DUPLICATE",
        actor="webhook",
        note=f"skill:{result['status']} external_id={msg['external_id'][:20]}",
    )
    log.info("kakaotalk-skill message %s: external_id=%s", result["status"], msg["external_id"][:20])

    return jsonify(_kakao_skill_text_response(_KAKAOTALK_SKILL_FIXED_REPLY)), 200


def _parse_kakaotalk_channel_payload(payload: dict) -> dict:
    """
    카카오톡 채널 webhook payload 파싱.
    채널 비즈니스 API 이벤트 기준 (https://developers.kakao.com/docs/latest/ko/message/channel-webhook).

    최소 payload 구조:
    {
        "userRequest": {
            "utterance": "안녕하세요",
            "user": { "id": "user-key-123", "type": "botUserKey" }
        },
        "bot": { "id": "bot-id-001" }
    }

    필수 필드 누락 시 ValueError 발생.
    """
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

    if len(utterance) > _KAKAOTALK_MAX_UTTERANCE_LEN:
        raise ValueError(f"utterance 최대 길이 초과 (max={_KAKAOTALK_MAX_UTTERANCE_LEN})")

    bot = payload.get("bot") or {}
    bot_id = str(bot.get("id") or _KAKAOTALK_CHANNEL_ACCOUNT)

    now_dt = datetime.now(UTC)
    now = now_dt.strftime("%Y-%m-%dT%H:%M:%S")
    # 충돌 위험 감소: hash raw에 마이크로초 포함
    raw = f"kakaotalk:{user_id}:{utterance[:30]}:{now_dt.isoformat()}"
    external_id = f"kakaotalk:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"

    title = (utterance[:50] + "...") if len(utterance) > 50 else utterance

    return {
        "external_id": external_id,
        "source_type": "kakaotalk_channel",
        "source_account": bot_id,
        "sender": user_id,
        "title": title,
        "body_raw": utterance,
        "received_at": now,
        "metadata": {
            "bot_id": bot_id,
            "user_id": user_id,
            "user_type": user.get("type", ""),
        },
    }
