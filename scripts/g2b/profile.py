"""G2B (나라장터/조달청) 세대 사이트 프로필.

실제 G2B 접속, 로그인, 투찰, 전자서명 구현 없음.
골격 정책 선언만 포함.
"""
from __future__ import annotations

# ── action 분류 상수 ──────────────────────────────────────────────────

READ_ONLY_ACTIONS: frozenset[str] = frozenset({
    "search_notice",
    "read_notice_detail",
    "inspect_attachment",
    "collect_openapi_notice",
})

DOWNLOAD_ACTIONS: frozenset[str] = frozenset({
    "download_public_attachment",
})

DRAFT_ACTIONS: frozenset[str] = frozenset({
    "create_bid_analysis_draft",
    "create_submit_draft",
})

LOCAL_AGENT_REQUIRED_ACTIONS: frozenset[str] = frozenset({
    "login",
})

USER_DIRECT_REQUIRED_ACTIONS: frozenset[str] = frozenset({
    "certificate_auth",
    "otp",
})

BLOCKED_ACTIONS: frozenset[str] = frozenset({
    "submit_bid",
    "e_sign",
    "final_send",
    "payment_or_fee_related_action",
    "extract_password",
    "extract_session",
    "extract_cookie",
    "extract_token",
    "server_side_login_browser",
})

ALL_KNOWN_ACTIONS: frozenset[str] = (
    READ_ONLY_ACTIONS
    | DOWNLOAD_ACTIONS
    | DRAFT_ACTIONS
    | LOCAL_AGENT_REQUIRED_ACTIONS
    | USER_DIRECT_REQUIRED_ACTIONS
    | BLOCKED_ACTIONS
)

# ── 세대 구조 gate 정책 ───────────────────────────────────────────────

ROOM_GATE_POLICY: dict[str, str] = {
    "public-notice":        "READ_ONLY_ALLOWED",
    "notice-detail":        "READ_ONLY_ALLOWED",
    "attachment-download":  "LOCAL_AGENT_REQUIRED",
    "openapi-collector":    "READ_ONLY_ALLOWED",
    "login-restricted":     "LOCAL_AGENT_REQUIRED",
    "bid-analysis":         "DRAFT_ALLOWED",
    "bid-submit":           "USER_DIRECT_REQUIRED",
    "e-sign":               "BLOCKED",
    "evidence-report":      "READ_ONLY_ALLOWED",
}

# ── evidence/report warehouse 정책 ───────────────────────────────────

EVIDENCE_WAREHOUSE_POLICY: dict[str, str] = {
    "warehouse_root":       "data/g2b/",
    "public_notice_cache":  "data/g2b/public_notices/",
    "attachment_store":     "data/g2b/attachments/",
    "bid_analysis_drafts":  "data/g2b/bid_analysis/",
    "submit_drafts":        "data/g2b/submit_drafts/",
    "audit_logs":           "data/g2b/audit/",
    "report_root":          "docs/reports/",
    "access_mode":          "LOCAL_ONLY",
    "server_write":         "BLOCKED",
}

# ── 사이트 프로필 선언 ────────────────────────────────────────────────

G2B_SITE_PROFILE: dict[str, object] = {
    "key":                "g2b",
    "base_url":           "https://www.g2b.go.kr",
    "display_name":       "나라장터(G2B)",
    "status":             "ACTIVE",
    "description":        "조달청 전자조달 나라장터. Read-Only 공고 탐색 허용, 로그인/투찰/전자서명 BLOCKED.",
    "login_domain_hints": ("g2b.go.kr",),
    "openapi_collector_boundary": "SEPARATE",
    "allowed_actions":    sorted(READ_ONLY_ACTIONS | DOWNLOAD_ACTIONS | DRAFT_ACTIONS),
    "local_agent_actions": sorted(LOCAL_AGENT_REQUIRED_ACTIONS),
    "user_direct_actions": sorted(USER_DIRECT_REQUIRED_ACTIONS),
    "blocked_actions":    sorted(BLOCKED_ACTIONS),
    "room_gate_policy":   ROOM_GATE_POLICY,
    "evidence_warehouse": EVIDENCE_WAREHOUSE_POLICY,
}
