"""커뮤니티 리포트 알림 — 텔레그램 발송.

설정: data/community/notify_config.json {channel, telegram_token, telegram_chat_id, enabled}
토큰은 응답에 마스킹해 노출. getUpdates 로 chat_id 자동 감지.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ai_orchestrator.paths.runtime import atomic_write_text, data_dir

ROOT = Path(__file__).resolve().parents[2]
_CFG = data_dir() / "community" / "notify_config.json"
_TG = "https://api.telegram.org/bot{token}/{method}"


def load_config() -> dict:
    if not _CFG.exists():
        return {"channel": "telegram", "telegram_token": "", "telegram_chat_id": "", "enabled": False}
    try:
        return json.loads(_CFG.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 텔레그램 알림 설정 로드/전송 유틸 — 설정파일 파싱 실패 시 빈 기본 설정 반환, 전송 실패 시 ok=False 결과 반환, 자격증명(token)은 반환값에 노출하지 않음
        return {"channel": "telegram", "telegram_token": "", "telegram_chat_id": "", "enabled": False}


def save_config(cfg: dict) -> None:
    _CFG.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(_CFG, json.dumps(cfg, ensure_ascii=False, indent=2))


def public_config() -> dict:
    """토큰 마스킹한 설정(응답용)."""
    c = load_config()
    tok = c.get("telegram_token", "")
    return {
        "channel": c.get("channel", "telegram"),
        "enabled": bool(c.get("enabled")),
        "token_set": bool(tok),
        "token_masked": (tok[:6] + "…" + tok[-4:]) if len(tok) > 12 else ("설정됨" if tok else ""),
        "chat_id": c.get("telegram_chat_id", ""),
    }


def _tg_call(token: str, method: str, params: dict, timeout: int = 10) -> dict:
    url = _TG.format(token=token, method=method)
    data = urllib.parse.urlencode(params).encode() if params else None
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def detect_chat_id(token: str) -> str:
    """봇에게 보낸 최근 메시지에서 chat_id 추출. 없으면 ''."""
    try:
        res = _tg_call(token, "getUpdates", {"limit": 10})
    except Exception:  # noqa: BLE001 - 텔레그램 알림 설정 로드/전송 유틸 — 설정파일 파싱 실패 시 빈 기본 설정 반환, 전송 실패 시 ok=False 결과 반환, 자격증명(token)은 반환값에 노출하지 않음
        return ""
    if not res.get("ok"):
        return ""
    for upd in reversed(res.get("result", [])):
        msg = upd.get("message") or upd.get("edited_message") or {}
        chat = msg.get("chat") or {}
        if chat.get("id"):
            return str(chat["id"])
    return ""


def send_message(text: str, token: str = "", chat_id: str = "") -> dict:
    """텔레그램 메시지 발송. token/chat_id 미지정 시 설정에서 로드."""
    c = load_config()
    token = token or c.get("telegram_token", "")
    chat_id = chat_id or c.get("telegram_chat_id", "")
    if not token or not chat_id:
        return {"ok": False, "error": "telegram_not_configured"}
    try:
        res = _tg_call(
            token,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text[:4000],
                "disable_web_page_preview": "true",
            },
        )
        return {"ok": bool(res.get("ok")), "error": None if res.get("ok") else res.get("description")}
    except Exception as e:  # noqa: BLE001 - 텔레그램 알림 설정 로드/전송 유틸 — 설정파일 파싱 실패 시 빈 기본 설정 반환, 전송 실패 시 ok=False 결과 반환, 자격증명(token)은 반환값에 노출하지 않음
        return {"ok": False, "error": str(e)[:120]}


def _format_report(report: dict) -> str:
    lines = [
        f"📡 커뮤니티 자율 분석 ({report.get('generated_at', '')[:16]})",
        f"사이트 {report.get('site_count', 0)}개 · 성공 {report.get('ok_count', 0)}\n",
    ]
    for r in report.get("reports", [])[:6]:
        if not r.get("ok"):
            continue
        lines.append(f"▪ {r.get('site', '')}")
        if r.get("summary"):
            lines.append(f"  {r['summary'][:90]}")
        ops = r.get("opportunities") or []
        if ops:
            lines.append(f"  💰 {ops[0].get('idea', '')}")
    return "\n".join(lines)


def notify_report(report: dict) -> dict:
    """리포트 요약을 알림 채널로 발송 (enabled 일 때만)."""
    c = load_config()
    if not c.get("enabled") or not c.get("telegram_token") or not c.get("telegram_chat_id"):
        return {"ok": False, "error": "disabled_or_unconfigured", "skipped": True}
    if not report.get("reports"):
        return {"ok": False, "error": "no_reports", "skipped": True}
    return send_message(_format_report(report))


def set_token_and_detect(token: str) -> dict[str, Any]:
    """토큰 저장 + chat_id 자동 감지."""
    token = (token or "").strip()
    if not token or ":" not in token:
        return {"ok": False, "error": "토큰 형식이 올바르지 않습니다"}
    chat_id = detect_chat_id(token)
    cfg = load_config()
    cfg["channel"] = "telegram"
    cfg["telegram_token"] = token
    if chat_id:
        cfg["telegram_chat_id"] = chat_id
        cfg["enabled"] = True
    save_config(cfg)
    return {"ok": True, "chat_id": chat_id, "detected": bool(chat_id)}
