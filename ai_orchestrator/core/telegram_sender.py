"""Telegram Bot API HTTP 전송 레이어.

telegram_notifier.py 는 메시지 포맷만 담당.
이 모듈이 실제 Bot API HTTP 호출(sendMessage / sendPhoto / answerCallbackQuery)을 수행한다.

필요 환경 변수:
    TELEGRAM_BOT_TOKEN         — Bot API 토큰 (@BotFather 발급)
    TELEGRAM_APPROVER_CHAT_ID  — 승인 메시지를 받을 chat_id (개인/그룹)
"""

import json
import logging
import os
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_API_BASE = "https://api.telegram.org/bot{token}/{method}"
_TIMEOUT = 15


def _token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


def _chat_id() -> str:
    return os.environ.get("TELEGRAM_APPROVER_CHAT_ID", "")


def _url(method: str) -> str:
    return _API_BASE.format(token=_token(), method=method)


def send_message(
    text: str,
    reply_markup: dict | None = None,
    chat_id: str | None = None,
    parse_mode: str = "HTML",
) -> dict:
    """sendMessage API 호출. 성공 시 Telegram response dict 반환."""
    tok = _token()
    if not tok:
        logger.warning("TELEGRAM_BOT_TOKEN 미설정 — sendMessage 스킵")
        return {"ok": False, "skipped": True}
    cid = chat_id or _chat_id()
    if not cid:
        logger.warning("TELEGRAM_APPROVER_CHAT_ID 미설정 — sendMessage 스킵")
        return {"ok": False, "skipped": True}
    payload: dict = {"chat_id": cid, "text": text, "parse_mode": parse_mode}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        resp = httpx.post(_url("sendMessage"), json=payload, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:  # noqa: BLE001 - 텔레그램 Bot API HTTP 전송 레이어 — sendMessage/sendPhoto/answerCallbackQuery 각각 실패 시 로그와 {ok: False, error}를 반환, 토큰/chat_id 원문은 에러 메시지에 노출되지 않음.
        logger.error("sendMessage 실패: %s", e)
        return {"ok": False, "error": str(e)}


def send_photo(
    photo_path: Path,
    caption: str = "",
    reply_markup: dict | None = None,
    chat_id: str | None = None,
    parse_mode: str = "HTML",
) -> dict:
    """sendPhoto API 호출. 파일이 없으면 sendMessage fallback."""
    tok = _token()
    if not tok:
        logger.warning("TELEGRAM_BOT_TOKEN 미설정 — sendPhoto 스킵")
        return {"ok": False, "skipped": True}
    cid = chat_id or _chat_id()
    if not cid:
        logger.warning("TELEGRAM_APPROVER_CHAT_ID 미설정 — sendPhoto 스킵")
        return {"ok": False, "skipped": True}
    if not isinstance(photo_path, Path) or not photo_path.exists():
        logger.warning("스크린샷 없음 — sendMessage fallback: %s", photo_path)
        return send_message(caption, reply_markup=reply_markup, chat_id=cid, parse_mode=parse_mode)
    try:
        data: dict = {"chat_id": cid, "caption": caption, "parse_mode": parse_mode}
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
        with photo_path.open("rb") as f:
            files = {"photo": (photo_path.name, f, "image/png")}
            resp = httpx.post(_url("sendPhoto"), data=data, files=files, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:  # noqa: BLE001 - 텔레그램 Bot API HTTP 전송 레이어 — sendMessage/sendPhoto/answerCallbackQuery 각각 실패 시 로그와 {ok: False, error}를 반환, 토큰/chat_id 원문은 에러 메시지에 노출되지 않음.
        logger.error("sendPhoto 실패: %s", e)
        return {"ok": False, "error": str(e)}


def answer_callback_query(callback_query_id: str, text: str = "") -> dict:
    """answerCallbackQuery — 버튼 클릭 후 팝업 응답."""
    tok = _token()
    if not tok:
        return {"ok": False, "skipped": True}
    try:
        resp = httpx.post(
            _url("answerCallbackQuery"),
            json={
                "callback_query_id": callback_query_id,
                "text": text,
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:  # noqa: BLE001 - 텔레그램 Bot API HTTP 전송 레이어 — sendMessage/sendPhoto/answerCallbackQuery 각각 실패 시 로그와 {ok: False, error}를 반환, 토큰/chat_id 원문은 에러 메시지에 노출되지 않음.
        logger.error("answerCallbackQuery 실패: %s", e)
        return {"ok": False, "error": str(e)}
