"""텔레그램 송신 포맷 모듈 (전송 자체는 수행하지 않음).

버튼 callback_data 포맷 정의와 파싱/메시지 빌더만 담당.
실제 Bot API HTTP 호출은 추후 별도 레이어에서 수행.
"""

from typing import Optional

# callback_data 포맷: "<action>|<task_id>|<token_id>"
# Telegram 제한(64바이트) 내 유지하려면 task_id 는 짧게 유지 권장.
CALLBACK_SEP = "|"
_VALID_ACTIONS = ("approve", "reject")


def build_callback_data(action: str, task_id: str, token_id: str) -> str:
    if action not in _VALID_ACTIONS:
        raise ValueError(f"unknown action: {action}")
    data = f"{action}{CALLBACK_SEP}{task_id}{CALLBACK_SEP}{token_id}"
    if len(data.encode("utf-8")) > 64:
        raise ValueError(f"callback_data too long ({len(data)} bytes > 64): {data}")
    return data


def parse_callback_data(data: str) -> Optional[dict]:
    """callback_data 문자열 → {action, task_id, token_id}. 형식 오류시 None."""
    if not data:
        return None
    parts = data.split(CALLBACK_SEP)
    if len(parts) != 3:
        return None
    action, task_id, token_id = parts
    if action not in _VALID_ACTIONS or not task_id or not token_id:
        return None
    return {"action": action, "task_id": task_id, "token_id": token_id}


def build_approval_message(task_id: str, risk_level: str, token_id: str,
                           description: str = "") -> dict:
    """승인 요청 메시지 구조(전송 전 포맷). 실제 sendMessage 에 그대로 넣을 수 있는 dict."""
    lines = [
        f"[승인 요청] task={task_id}",
        f"risk={risk_level}",
    ]
    if description:
        lines.append(f"- {description}")
    return {
        "text": "\n".join(lines),
        "reply_markup": {
            "inline_keyboard": [[
                {"text": "승인", "callback_data": build_callback_data("approve", task_id, token_id)},
                {"text": "거절", "callback_data": build_callback_data("reject", task_id, token_id)},
            ]],
        },
    }


def build_result_text(action: str, status: str, actor: str = "", reason: str = "") -> str:
    """처리 결과를 텔레그램에 회신할 한 줄 메시지로 포맷."""
    if action == "approve" and status == "approved":
        return f"승인 완료: {actor}"
    if action == "reject" and status == "rejected":
        tail = f" ({reason})" if reason else ""
        return f"거절 완료: {actor}{tail}"
    mapping = {
        "not_found": "토큰을 찾을 수 없습니다",
        "task_mismatch": "task_id 불일치",
        "already_used": "이미 처리된 토큰입니다",
        "expired": "만료된 토큰입니다",
        "forbidden": "권한이 없습니다",
        "rate_limited": "요청이 너무 많습니다",
        "user_not_found": "등록되지 않은 사용자입니다",
        "invalid_action": "알 수 없는 action",
        "invalid_payload": "잘못된 payload",
    }
    return f"처리 실패: {mapping.get(status, status)}"
