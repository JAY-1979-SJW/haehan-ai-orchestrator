"""표시 이름(가입·데스크톱 첫 설정) 입력 검증의 정본 — 두 요청 모델이 같은 규칙을 한 곳에서 쓴다.

user_auth_router.SignupRequest 와 desktop_session_router.DesktopSetupRequest 가 같은 구조의 검증기를 각각 갖고 있었다
(구조 동일 중복 — G12 기준선 감사, 2026-10-07). 규칙은 그대로이고 한 함수로 합쳤다.
"""

from __future__ import annotations

MAX_DISPLAY_NAME_LEN = 50


def validate_display_name(value: str) -> str:
    """공백을 다듬고, 비었거나 최대 길이를 넘으면 ValueError(pydantic 이 422 로 바꾼다)."""
    value = value.strip()
    if not value:
        raise ValueError("이름을 입력하세요")
    if len(value) > MAX_DISPLAY_NAME_LEN:
        raise ValueError(f"이름은 최대 {MAX_DISPLAY_NAME_LEN}자입니다")
    return value
