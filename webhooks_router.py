"""
외부 서비스 Webhook 수신 라우트 (Flask Blueprint)

POST /api/v1/webhooks/kakaowork          — 카카오워크 Bot webhook 수신 → inbox 저장
POST /api/v1/webhooks/kakaotalk-channel  — 카카오톡 채널 webhook 수신 → inbox 저장 (뼈대)

정책:
  - 자동 실행 없음
  - 자동 회신 없음 (카카오워크/카카오톡 API에 회신 요청 금지)
  - 수집 후 inbox 저장만 수행
  - 기존 approval/executor 파이프라인 미연결
"""
import hashlib
import hmac
import os
from datetime import datetime, timezone
from typing import Optional

from flask import Blueprint, jsonify, request

import audit_logger
import inbox_store
import kakaowork_reader
from logger import get_logger

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

    now_dt = datetime.now(timezone.utc)
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
