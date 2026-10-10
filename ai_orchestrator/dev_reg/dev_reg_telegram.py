"""개발자 등록 승인 텔레그램 메시지·callback_data (전송은 하지 않음).

알림 모듈(notify/telegram_notifier)에서 옮겨 왔다 — 개발자 등록 기능의 메시지 포맷은 이 기능 폴더가 소유하고,
텔레그램 웹훅(notify)이 이 파일의 parse 함수를 부른다(notify → dev_reg 한 방향).
"""

# notify/telegram_notifier.CALLBACK_SEP 와 같은 값("|") — 알림 모듈을 import 하지 않으려고 따로 둔다(시험이 같은 값인지 확인)
CALLBACK_SEP = "|"

# 개발자 등록 신청 전용 callback_data 포맷: "dr_a|{token_id}" / "dr_r|{token_id}"
# UUID(36) + prefix 4 + sep 1 = 41 bytes — 64 바이트 제한 충족.
_DR_APPROVE = "dr_a"
_DR_REJECT = "dr_r"
_DR_ACTIONS = {_DR_APPROVE, _DR_REJECT}


def build_dev_reg_callback_data(action: str, token_id: str) -> str:
    """개발자 등록 승인용 callback_data. "dr_a|{token_id}" 또는 "dr_r|{token_id}" 형식."""
    prefix = _DR_APPROVE if action == "approve" else _DR_REJECT
    data = f"{prefix}{CALLBACK_SEP}{token_id}"
    if len(data.encode("utf-8")) > 64:
        raise ValueError(f"callback_data too long ({len(data)} bytes > 64): {data}")
    return data


def parse_dev_reg_callback_data(data: str) -> dict | None:
    """개발자 등록 callback_data 파싱 → {"action": "approve"/"reject", "token_id": str}. 실패 시 None."""
    if not data:
        return None
    parts = data.split(CALLBACK_SEP)
    if len(parts) != 2:
        return None
    raw_action, token_id = parts
    if raw_action not in _DR_ACTIONS or not token_id:
        return None
    return {"action": "approve" if raw_action == _DR_APPROVE else "reject", "token_id": token_id}


def build_dev_reg_message(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수, 인자 묶음 변경 시 API 영향)
    task_id: str,
    provider: str,
    action_type: str,
    summary: str,
    risk_level: str,
    target_url: str,
    expires_at: str,
    token_id: str,
) -> dict:
    """개발자 등록 승인 요청 메시지 구조 (전송 전 포맷).

    스크린샷은 telegram_sender.send_photo() 의 caption 으로 포함.
    Returns: {"text": str, "reply_markup": dict}
    """
    lines = [
        "<b>[개발자 등록 승인 요청]</b>",
        f"서비스: {provider}",
        f"신청 유형: {action_type}",
        f"위험도: {risk_level}",
        f"대상 URL: {target_url}",
        f"만료: {expires_at}",
        f"task: {task_id}",
        "",
        "<b>입력 요약:</b>",
        summary,
    ]
    return {
        "text": "\n".join(lines),
        "reply_markup": {
            "inline_keyboard": [
                [
                    {"text": "✅ 승인", "callback_data": build_dev_reg_callback_data("approve", token_id)},
                    {"text": "❌ 거절", "callback_data": build_dev_reg_callback_data("reject", token_id)},
                ]
            ],
        },
    }
