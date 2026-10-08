"""
action 위험 등급 정책

AUTO_ALLOWED         - 사용자 위임 없이 실행
USER_DELEGATED_PERMISSION_REQUIRED - 사용자가 권한 위임 후 실행
USER_DIRECT_REQUIRED - 사용자가 직접 수행
BLOCKED              - 권한 부여 대상 아님, 항상 차단
"""
from __future__ import annotations

GRADE_AUTO_ALLOWED = "AUTO_ALLOWED"
GRADE_USER_DELEGATED = "USER_DELEGATED_PERMISSION_REQUIRED"
GRADE_USER_DIRECT = "USER_DIRECT_REQUIRED"
GRADE_BLOCKED = "BLOCKED"

# ── AUTO_ALLOWED ───────────────────────────────────────────────────────────────

_AUTO_ALLOWED: frozenset[str] = frozenset({
    # 조회/탐색
    "read_page", "open_url", "search", "navigate", "scroll", "detect_login_status",
    # 추출
    "extract_text", "extract_table", "extract_list", "extract_metadata",
    # 캡처/요약
    "capture_screenshot", "summarize", "preview",
    # 다운로드
    "download_file",
    # 입력(비민감)
    "fill_search_field", "fill_non_sensitive",
    # 임시저장
    "save_draft",
    # 인증 대기 (값 수집 없음)
    "wait_for_user_auth",
    # 하나팩스 자동 발송 — 사용자가 수신자·제목·문서·한도를 미리 승인한 승인서의 범위 안에서만 실행한다.
    # 승인서가 없거나 범위가 바뀌면 워크플로(connectors/hanafax/send_policy)가 발송을 거부한다(fail-closed).
    "fax_send_authorized",
    # 메일 순차 대량 발송 — 같은 방식: 사용자가 수신자·내용·첨부·한도를 미리 승인한 승인서 범위 안에서만 실행한다.
    # 승인서가 없거나 범위가 바뀌거나 멈춘 상태면 connectors/naver_mail/bulk_policy 가 발송을 거부한다(fail-closed).
    "mail_send_authorized",
})

# ── USER_DELEGATED_PERMISSION_REQUIRED ────────────────────────────────────────

_USER_DELEGATED: frozenset[str] = frozenset({
    # 블로그
    "blog_publish", "blog_schedule_publish", "blog_edit", "blog_delete",
    "blog_set_visibility",
    # 카페
    "cafe_post_write", "cafe_post_edit", "cafe_post_delete",
    "cafe_comment_write", "cafe_comment_edit", "cafe_comment_delete",
    # 공개범위/첨부 포함 게시
    "set_visibility", "publish_with_attachment",
    # 폼 제출 (비금융/비법적)
    "form_submit", "click_submit",
    # 파일 업로드
    "file_upload",
    # 이메일/메시지 발송
    "send_email", "send_message",
})

# ── USER_DIRECT_REQUIRED ──────────────────────────────────────────────────────

_USER_DIRECT: frozenset[str] = frozenset({
    "login_password_input", "otp_input", "cert_password_input",
    "e_sign", "sign_document",
    "bid_final_submit", "confirm_payment", "confirm_transfer",
    "contract_confirm", "final_submit",
    "government_final_submit", "legal_final_submit",
})

# ── BLOCKED (권한 부여 불가) ───────────────────────────────────────────────────

_BLOCKED: frozenset[str] = frozenset({
    # 민감정보 저장/수집/export
    "password_save", "otp_save", "cert_password_save",
    "collect_password", "collect_otp", "collect_cookie", "collect_session",
    "cookie_export", "session_export", "cookie_dump", "session_dump",
    "token_export", "auth_header_export", "storage_state_export",
    "localStorage_dump", "sessionStorage_dump",
    # 인증서/NPKI
    "cert_file_access", "npki_access", "read_certificate_file",
    # 자동 서명/투찰/결제/송금
    "auto_sign", "auto_bid_submit", "auto_payment", "auto_transfer",
    "auto_contract_submit", "auto_final_submit", "transfer_money",
    # 우회/스팸
    "captcha_bypass", "account_restriction_bypass",
    "bulk_spam_post", "bulk_spam_comment",
    # 사용자 몰래 실행 (silent)
    "silent_execute",
})


def classify_action(action: str) -> str:
    """action을 4개 등급 중 하나로 분류한다."""
    if action in _BLOCKED:
        return GRADE_BLOCKED
    if action in _USER_DIRECT:
        return GRADE_USER_DIRECT
    if action in _USER_DELEGATED:
        return GRADE_USER_DELEGATED
    if action in _AUTO_ALLOWED:
        return GRADE_AUTO_ALLOWED
    # 미등록 action → 안전하게 USER_DELEGATED 처리
    return GRADE_USER_DELEGATED


def is_delegatable(action: str) -> bool:
    """사용자가 권한 위임 가능한 action인지 반환."""
    return classify_action(action) == GRADE_USER_DELEGATED


def is_blocked(action: str) -> bool:
    """권한 부여 불가(항상 차단) action인지 반환."""
    return classify_action(action) == GRADE_BLOCKED


def is_auto_allowed(action: str) -> bool:
    return classify_action(action) == GRADE_AUTO_ALLOWED


def is_user_direct_required(action: str) -> bool:
    return classify_action(action) == GRADE_USER_DIRECT


def get_all_delegatable_actions() -> frozenset[str]:
    return _USER_DELEGATED


def get_all_blocked_actions() -> frozenset[str]:
    return _BLOCKED
