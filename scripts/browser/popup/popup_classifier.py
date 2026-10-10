"""팝업 분류기 — popup_classifier v1.0

룰베이스 분류로 팝업의 종류와 적정 처리 액션을 판단한다.
popup_watcher가 감지한 이벤트를 입력받아 신중하게 자동/수동/차단을 결정.

사용:
    from scripts.browser.popup.popup_classifier import classify
    decision = classify(marker="작성 중인 글", snippet="이어서 작성하시겠습니까? ...")
    # → {"category": "draft_restore", "severity": "low",
    #    "action": "auto_dismiss", "target": "취소", "confidence": 0.9}
"""
from __future__ import annotations

from typing import TypedDict, Literal


Category = Literal[
    "draft_restore",        # 임시저장 복원 안내
    "cookie_consent",       # 쿠키/GDPR 동의
    "session_expired",      # 세션 만료/재로그인
    "login_required",       # 로그인 필요
    "notification_request", # 브라우저 알림 권한 요청
    "marketing_optin",      # 마케팅/뉴스레터 권유
    "destructive_confirm",  # 삭제/전송/결제 확인 (위험)
    "two_factor",           # 2FA / OTP
    "captcha",              # 캡차
    "update_available",     # 업데이트 알림
    "generic_info",         # 단순 안내
    "access_blocked",       # 비정상 접근 차단 (자동화 감지)
    "rate_limited",         # 과도한 요청 차단
    "bot_detected",         # 봇 감지/차단
    "unknown",              # 미분류
]

Severity = Literal["low", "medium", "high", "critical"]
Action = Literal["auto_dismiss", "auto_accept", "notify_user", "block_workflow"]


class Decision(TypedDict):
    category: Category
    severity: Severity
    action: Action
    target: str | None     # 클릭할 버튼 텍스트 (auto_* 액션일 때)
    confidence: float      # 0.0 ~ 1.0
    reasoning: str


# (카테고리, severity, action, target, 매칭 키워드 set, 본문 키워드 set)
# 본문 키워드는 snippet 안에 하나라도 있어야 매칭.
_RULES: list[tuple[Category, Severity, Action, str | None, set[str], set[str]]] = [
    # ── 심각: 자동화 감지 및 접근 차단 ─────────────────────────────────────
    ("access_blocked",      "critical", "block_workflow", "확인",
     {"비정상적인 접근", "Abnormal access", "자동화 프로그램"},
     set()),
    ("bot_detected",        "critical", "block_workflow", "확인",
     {"봇으로 판단", "자동 프로그램", "bot detected", "automated access"},
     set()),
    ("access_blocked",      "critical", "block_workflow", "확인",
     {"접근 차단", "access denied", "이용이 제한", "서비스 차단"},
     {"보안", "보호", "이상 탐지", "security", "suspicious"}),
    ("rate_limited",        "high",     "block_workflow", "확인",
     {"과도한 요청", "too many requests", "요청이 많음", "rate limit"},
     set()),

    # ── 위험: 무조건 사용자에게 ─────────────────────────────────────
    ("destructive_confirm", "high",     "block_workflow", None,
     {"삭제하시겠습니까", "완전 삭제", "영구 삭제", "Delete forever", "permanently delete"},
     set()),
    ("destructive_confirm", "critical", "block_workflow", None,
     {"결제", "Payment", "Charge", "구매 확정", "Confirm purchase"},
     set()),
    ("destructive_confirm", "high",     "block_workflow", None,
     {"전송", "보내기"},
     {"외부", "수신자", "참조", "확인하지"}),

    ("two_factor",          "high",     "notify_user",    None,
     {"2단계 인증", "Two-step", "Two-factor", "OTP", "인증 코드"},
     set()),
    ("captcha",             "high",     "notify_user",    None,
     {"reCAPTCHA", "캡차", "로봇이 아닙니다", "I'm not a robot"},
     set()),

    ("login_required",      "medium",   "notify_user",    None,
     {"로그인이 필요", "로그인 후 이용", "Sign in to continue", "Please sign in"},
     set()),
    ("session_expired",     "medium",   "notify_user",    None,
     {"세션이 만료", "Session expired", "다시 로그인", "Please log in again"},
     set()),

    # ── 안전: 자동 처리 가능 ──────────────────────────────────────
    ("draft_restore",       "low",      "auto_dismiss",   "취소",
     {"작성 중인 글", "이어서 작성", "임시저장된", "Continue writing", "Restore draft"},
     set()),
    ("cookie_consent",      "low",      "auto_accept",    "동의함",
     {"cookies", "쿠키", "GDPR", "Accept all", "모두 수락", "동의함", "Manage cookies"},
     set()),
    ("notification_request","low",      "auto_dismiss",   "나중에",
     {"알림을 표시", "Show notifications", "notification"},
     {"권한", "허용", "Allow"}),
    ("marketing_optin",     "low",      "auto_dismiss",   "나중에",
     {"뉴스레터", "구독하시겠", "newsletter", "마케팅", "프로모션"},
     set()),
    ("update_available",    "low",      "auto_dismiss",   "나중에",
     {"새 버전", "업데이트가", "Update available", "새로 고침"},
     set()),
    ("generic_info",        "low",      "auto_dismiss",   "확인",
     {"안내", "info", "주의사항"},
     set()),
]


def _normalize(text: str) -> str:
    return (text or "").lower().strip()


def classify(*, marker: str, snippet: str = "") -> Decision:
    """marker와 snippet을 룰에 매칭해 Decision 반환.

    매칭 우선순위: 위험 룰 먼저 검사 → 안전 룰. 첫 매칭 채택.
    """
    marker_n = _normalize(marker)
    snippet_n = _normalize(snippet)
    combined = f"{marker_n} {snippet_n}"

    for category, severity, action, target, marker_kws, snippet_kws in _RULES:
        mk_hit = any(_normalize(kw) in combined for kw in marker_kws)
        if not mk_hit:
            continue
        if snippet_kws and not any(_normalize(kw) in snippet_n for kw in snippet_kws):
            continue
        return Decision(
            category=category,
            severity=severity,
            action=action,
            target=target,
            confidence=0.85 if snippet_kws else 0.75,
            reasoning=f"마커 매칭: '{marker}' → {category}",
        )

    return Decision(
        category="unknown",
        severity="medium",
        action="notify_user",
        target=None,
        confidence=0.0,
        reasoning=f"분류 불가: marker='{marker[:60]}'",
    )


def is_auto_handleable(decision: Decision) -> bool:
    """auto_* 액션이면서 confidence ≥ 0.7 일 때만 자동 처리 허용."""
    return decision["action"].startswith("auto_") and decision["confidence"] >= 0.7
