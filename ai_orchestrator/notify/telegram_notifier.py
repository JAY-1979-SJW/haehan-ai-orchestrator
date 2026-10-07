"""텔레그램 송신 포맷 모듈 (전송 자체는 수행하지 않음).

버튼 callback_data 포맷 정의와 파싱/메시지 빌더만 담당.
실제 Bot API HTTP 호출은 telegram_sender 모듈에서 수행.
"""

# callback_data 포맷: "<action>|<task_id>|<token_id>"
# Telegram 제한(64바이트) 내 유지하려면 task_id 는 짧게 유지 권장.
CALLBACK_SEP = "|"
_VALID_ACTIONS = ("approve", "reject")

# 개발자 등록 승인 메시지·callback_data 는 dev_reg/dev_reg_telegram.py 로 옮겼다(알림 모듈이 기능 폴더를 import 하지 않게).


def build_callback_data(action: str, task_id: str, token_id: str) -> str:
    if action not in _VALID_ACTIONS:
        raise ValueError(f"unknown action: {action}")
    data = f"{action}{CALLBACK_SEP}{task_id}{CALLBACK_SEP}{token_id}"
    if len(data.encode("utf-8")) > 64:
        raise ValueError(f"callback_data too long ({len(data)} bytes > 64): {data}")
    return data


def parse_callback_data(data: str) -> dict | None:
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


def build_approval_message(task_id: str, risk_level: str, token_id: str, description: str = "") -> dict:
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
            "inline_keyboard": [
                [
                    {"text": "승인", "callback_data": build_callback_data("approve", task_id, token_id)},
                    {"text": "거절", "callback_data": build_callback_data("reject", task_id, token_id)},
                ]
            ],
        },
    }


# ── capture_screenshot 전용 승인 메시지 ────────────────────────────
#
# 핵심 원칙:
#   - callback_data 는 기존 "approve|task_id|token_id" / "reject|..." 포맷 그대로 사용.
#     → 하위호환 유지. handle_telegram_update 의 기존 파서가 그대로 처리한다.
#   - 버튼 text 와 본문 텍스트만 dry-run 여부로 분기한다.
#   - 텍스트에는 token 원문/파일명/로컬 경로/민감값 절대 포함하지 않는다 (아래 빌더 내부에서
#     reason/note 는 축약만 수행 — 민감 키 제거 로직을 거친 값이 입력된다는 전제).

_CAP_RISK_LABEL = "HIGH"
_CAP_DRY_GUIDANCE = "이미지 파일을 생성하지 않고 환경만 점검합니다."
_CAP_REAL_GUIDANCE = "승인 시 로컬 PC에서 1회 화면 캡처가 실행되며, 서버에는 이미지가 업로드되지 않습니다."


def _truncate_memo(text: str, limit: int = 80) -> str:
    """reason/note 축약. 개행 제거 + 길이 제한. None/비문자열은 빈 문자열."""
    if not text:
        return ""
    s = str(text).replace("\r", " ").replace("\n", " ").strip()
    if len(s) > limit:
        s = s[: limit - 1] + "…"
    return s


def build_capture_screenshot_approval_message(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수, 인자 묶음 변경 시 API 영향)
    task_id: str,
    agent_id: str,
    token_id: str,
    *,
    dry_run: bool,
    risk_level: str = "high",
    requested_by: str = "",
    role: str = "",
    reason: str = "",
    note: str = "",
) -> dict:
    """capture_screenshot 승인 요청 메시지 (전송 전 포맷).

    - dry_run=True  → "사전 점검" 라벨, 버튼: "사전 점검 승인" / "거절"
    - dry_run=False → "실제 화면 캡처" 라벨, 버튼: "1회 캡처 승인" / "거절"
    - 본문과 버튼 모두 token 원문 / 파일명 / 로컬 경로를 포함하지 않는다.
    - callback_data 는 기존 "approve|task_id|token_id" 포맷 재사용 → 기존 승인 webhook
      (`handle_telegram_update` 형식 1) 경로로 그대로 처리 가능.
    """
    exec_type = "사전 점검" if dry_run else "실제 화면 캡처"
    guidance = _CAP_DRY_GUIDANCE if dry_run else _CAP_REAL_GUIDANCE

    lines = [
        "[승인 요청] 작업: capture_screenshot",
        f"실행 유형: {exec_type}",
        f"위험도: {(risk_level or 'high').upper()}",
        f"agent: {agent_id}",
        f"task: {task_id}",
    ]
    if requested_by or role:
        who_parts = []
        if requested_by:
            who_parts.append(str(requested_by)[:40])
        if role:
            who_parts.append(f"role={str(role)[:20]}")
        lines.append("요청자: " + " / ".join(who_parts))

    reason_short = _truncate_memo(reason)
    if reason_short:
        lines.append(f"사유: {reason_short}")
    note_short = _truncate_memo(note)
    if note_short:
        lines.append(f"메모: {note_short}")

    lines.append("")
    lines.append(guidance)

    approve_label = "사전 점검 승인" if dry_run else "1회 캡처 승인"
    return {
        "text": "\n".join(lines),
        "reply_markup": {
            "inline_keyboard": [
                [
                    {"text": approve_label, "callback_data": build_callback_data("approve", task_id, token_id)},
                    {"text": "거절", "callback_data": build_callback_data("reject", task_id, token_id)},
                ]
            ],
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
