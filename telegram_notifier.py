"""
텔레그램 승인 요청기 — 환경변수 없으면 mock 모드
이번 단계: 메시지 송신까지만 구현 (웹훅 수신 미구현)
"""

import json
import os
import time

try:
    import urllib.request

    _HAS_URLLIB = True
except ImportError:
    _HAS_URLLIB = False

from models import ExecutionPlan, RiskAssessment, TaskRequest

_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def _is_mock() -> bool:
    return not (_BOT_TOKEN and _CHAT_ID)


def _send_telegram(text: str) -> dict:
    if _is_mock():
        return {"ok": True, "mock": True, "text": text}

    url = f"https://api.telegram.org/bot{_BOT_TOKEN}/sendMessage"
    payload = json.dumps(
        {
            "chat_id": _CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
        }
    ).encode("utf-8")

    try:
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return {"ok": True, "mock": False, "response": body}
    except Exception as e:  # noqa: BLE001 - 텔레그램 알림 전송 실패를 ok=False, error 필드로 반환하는 best-effort 알림 — 실패해도 알림 못 보냈다는 결과만 리턴, 다른 승인/차단 로직에 영향 없음.
        return {"ok": False, "mock": False, "error": str(e)}


def send_approval_request(
    task: TaskRequest,
    risk: RiskAssessment,
    plan: ExecutionPlan,
    token: str | None,
) -> dict:
    lines = [
        "🔐 *[승인 요청]*",
        f"• task_id: `{task.task_id}`",
        f"• action_type: `{task.action_type}`",
        f"• target: `{task.target}`",
        f"• risk_level: *{risk.risk_level}*",
        f"• requires_approval: {risk.requires_approval}",
        f"• token_id: `{token or 'N/A'}`",
        f"• description: {task.description}",
        "",
        "_이 작업을 승인하려면 관리자에게 token_id를 전달하세요._",
        "_텔레그램 웹훅 자동 승인은 아직 미구현입니다._",
    ]
    text = "\n".join(lines)
    result = _send_telegram(text)
    return {
        "sent": result.get("ok", False),
        "mock": result.get("mock", True),
        "task_id": task.task_id,
        "token_id": token,
        "risk_level": risk.risk_level,
        "requires_approval": risk.requires_approval,
        "action_type": task.action_type,
        "target": task.target,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "error": result.get("error"),
    }


def send_status_message(text: str) -> dict:
    result = _send_telegram(text)
    return {
        "sent": result.get("ok", False),
        "mock": result.get("mock", True),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "error": result.get("error"),
    }
