"""
인증 완료 감지기

사용자가 직접 인증을 완료했는지 페이지 상태 변화로 감지한다.

감지 기준:
- 로그인 화면에서 업무 화면으로 이동
- 인증창 종료 후 페이지 상태 변경
- URL host 유지 + title 변화
- 로그인/인증 필요 문구 사라짐

금지:
- 비밀번호 input 값 읽기
- OTP input 값 읽기
- 인증서 비밀번호 값 읽기
- cookie/session/localStorage/sessionStorage dump
- 인증서 파일 접근
- NPKI 접근
"""
from __future__ import annotations

from typing import Any

# ── 인증 필요 패턴 (존재하면 아직 인증 미완료) ──────────────────────────────

_AUTH_REQUIRED_PATTERNS: tuple[str, ...] = (
    "로그인", "login", "sign in", "signin",
    "인증이 필요", "로그인이 필요", "please log in",
    "인증서", "certificate", "공인인증", "공동인증",
    "otp", "일회용 비밀번호", "보안카드",
    "npki",
)

# ── 인증 완료 패턴 (존재하면 업무 화면으로 판단) ────────────────────────────

_AUTH_CLEARED_INDICATORS: tuple[str, ...] = (
    "마이페이지", "my page", "내 정보", "로그아웃", "logout",
    "sign out", "signout", "업무", "메인", "대시보드", "dashboard",
    "홈", "home",
)


def _has_auth_required(text: str) -> bool:
    lower = text.lower()
    return any(p in lower for p in _AUTH_REQUIRED_PATTERNS)


def _has_auth_cleared(text: str) -> bool:
    lower = text.lower()
    return any(p in lower for p in _AUTH_CLEARED_INDICATORS)


def check_auth_completed_from_page_state(
    current_title: str,
    current_url: str,
    body_text_sample: str,
    prev_title: str = "",
    prev_url: str = "",
) -> dict[str, Any]:
    """
    페이지 텍스트/URL/title 변화로 인증 완료 여부를 판단한다.

    입력값(password/OTP/cert password)은 읽지 않는다.
    cookie/session/localStorage/sessionStorage는 접근하지 않는다.
    인증서/NPKI 파일은 접근하지 않는다.

    반환:
      auth_completed: bool
      status: "AUTH_COMPLETED" | "WAITING_USER_AUTH"
      safe_to_resume: bool
      signals_cleared: list[str]
      sensitive_data_collected: bool  # 항상 false
    """
    combined = current_title + "\n" + body_text_sample

    still_needs_auth = _has_auth_required(combined)
    shows_cleared = _has_auth_cleared(combined)

    # title 변화 감지 (prev가 있을 때만)
    title_changed = bool(prev_title) and (current_title != prev_title)

    # URL 변화 감지 (host는 유지되어야 함)
    url_changed = bool(prev_url) and (current_url != prev_url)

    signals_cleared: list[str] = []
    auth_completed = False

    if not still_needs_auth and (shows_cleared or title_changed or url_changed):
        auth_completed = True
        signals_cleared = _infer_cleared_signals(prev_title, body_text_sample)

    return {
        "auth_completed": auth_completed,
        "status": "AUTH_COMPLETED" if auth_completed else "WAITING_USER_AUTH",
        "safe_to_resume": auth_completed,
        "signals_cleared": signals_cleared,
        "sensitive_data_collected": False,
    }


def check_auth_completed_from_dict(page_state: dict[str, Any]) -> dict[str, Any]:
    """
    page_state dict를 받아 인증 완료 여부를 판단한다.
    page_state 예시: {"title": ..., "url": ..., "body_text": ...,
                       "prev_title": ..., "prev_url": ...}
    """
    return check_auth_completed_from_page_state(
        current_title=page_state.get("title", ""),
        current_url=page_state.get("url", ""),
        body_text_sample=page_state.get("body_text", ""),
        prev_title=page_state.get("prev_title", ""),
        prev_url=page_state.get("prev_url", ""),
    )


def _infer_cleared_signals(prev_title: str, body_text: str) -> list[str]:
    """이전 상태를 바탕으로 어떤 인증 신호가 해소됐는지 추론한다."""
    cleared = []
    lower_prev = prev_title.lower()
    if any(p in lower_prev for p in ("로그인", "login", "sign in")):
        cleared.append("login_required")
    if any(p in lower_prev for p in ("인증서", "certificate", "npki", "공동인증")):
        cleared.append("cert_auth_required")
    if any(p in lower_prev for p in ("otp", "일회용")):
        cleared.append("otp_required")
    if not cleared:
        cleared.append("auth_required")
    return cleared
