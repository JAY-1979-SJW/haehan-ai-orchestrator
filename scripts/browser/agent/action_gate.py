"""브라우저 액션 게이트 — AUTO / NOTIFY / APPROVE 분류.

분류 기준
=========
APPROVE  : 6개 카테고리 (돈 이동, 법적 효력, 계정 변경, 외부 발송, 민감정보 제출, 자격증명 입력)
NOTIFY   : Intent 범위 이탈 (외부 origin), 파일 다운로드, 팝업
AUTO     : 그 외 탐색·읽기·스크린샷·클릭·스크롤·타이핑(비민감)

원칙
====
1. 자격증명(비밀번호·카드번호·주민번호·OTP 등) 입력 → 사용자 승인 후 진행(APPROVE).
2. APPROVE 키워드 매칭은 label + url + params 양쪽에서.
3. Intent가 없으면 NOTIFY (승인 없이 범위 불명확).
4. Intent가 있으면 origin 범위 검사 → 이탈 시 NOTIFY.
5. 분류 결과는 side-effect 없이 dict 반환.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from scripts.browser.agent.intent_token import (
    IntentToken,
    is_origin_allowed,
    validate_intent,
)
from ai_orchestrator.paths.runtime import data_dir

# 분류 결과 코드
GATE_AUTO = "AUTO"
GATE_NOTIFY = "NOTIFY"
GATE_APPROVE = "APPROVE"
GATE_BLOCKED = "BLOCKED"

# ── gate_policy.json 로드 ────────────────────────────────────────────────────
_POLICY_PATH = data_dir() / "gate_policy.json"


def _load_policy() -> dict:
    try:
        return json.loads(_POLICY_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - _load_policy(): gate_policy.json 로드 실패 시 빈 dict 반환 — 이후 _pt()가 각 카테고리 키워드를 코드 내 하드코딩된 전체 기본값(fallback)으로 사용하므로 정책 파일 손상 시에도 APPROVE 키워드 목록이 비지 않고 그대로 유지됨(fail-closed 유지)
        return {}


_policy = _load_policy()


def _pt(key: str, fallback: tuple) -> tuple:
    """policy에서 key를 tuple로 반환, 없으면 fallback."""
    return tuple(_policy.get(key, list(fallback)))


# APPROVE 카테고리 1: 돈 이동 (결제·입금·송금·투찰·입찰)
_APPROVE_MONEY = _pt(
    "approve_money",
    (
        "결제",
        "payment",
        "pay",
        "checkout",
        "송금",
        "transfer",
        "입금",
        "출금",
        "이체",
        "투찰",
        "입찰",
        "낙찰",
        "bid",
        "구매",
        "purchase",
        "buy",
        "주문",
        "order",
        "cart",
    ),
)

# APPROVE 카테고리 2: 법적 효력 (전자서명·제출·신청·계약)
_APPROVE_LEGAL = _pt(
    "approve_legal",
    (
        "전자서명",
        "esign",
        "e-sign",
        "서명",
        "계약",
        "contract",
        "agreement",
        "제출",
        "submit",
        "신청",
        "날인",
        "stamp",
        "공문",
        "공시",
    ),
)

# APPROVE 카테고리 3: 계정 변경 (탈퇴·비밀번호 변경·권한 변경)
_APPROVE_ACCOUNT = _pt(
    "approve_account",
    (
        "탈퇴",
        "withdraw",
        "delete account",
        "회원탈퇴",
        "비밀번호 변경",
        "password change",
        "reset password",
        "권한",
        "permission",
        "role",
        "2fa",
        "mfa",
        "인증 설정",
    ),
)

# APPROVE 카테고리 4: 외부 발송 (이메일·문자·알림 발송)
_APPROVE_SEND = _pt(
    "approve_send",
    (
        "이메일 발송",
        "send email",
        "메일 보내기",
        "문자 발송",
        "sms",
        "send message",
        "알림 발송",
        "send notification",
        "공유",
        "share",
    ),
)

# APPROVE 카테고리 5: 민감정보 제출 (주민번호·카드·여권 등)
_APPROVE_SENSITIVE_SUBMIT = _pt(
    "approve_sensitive_submit",
    (
        "주민번호",
        "rrn",
        "ssn",
        "카드번호",
        "card number",
        "여권번호",
        "passport",
        "공인인증",
        "npki",
        "otp 입력",
        "otp submit",
    ),
)

_ALL_APPROVE_KEYWORDS = _APPROVE_MONEY + _APPROVE_LEGAL + _APPROVE_ACCOUNT + _APPROVE_SEND + _APPROVE_SENSITIVE_SUBMIT

# APPROVE 카테고리 6: 자격증명 입력 (사용자 승인 후 AI 입력 가능)
_CREDENTIAL_INPUT_KEYS = _pt(
    "credential_keys",
    (
        "password",
        "passwd",
        "pwd",
        "비밀번호",
        "card_number",
        "cardnumber",
        "cvv",
        "cvc",
        "카드번호",
        "rrn",
        "주민번호",
        "otp",
        "auth_code",
        "인증번호",
        "verification_code",
        "private_key",
        "npki",
        "pin",
        "secret",
    ),
)

# 자연어 label → 이미 APPROVE인지 판단하는 최종 키워드 체크
_APPROVE_SUBMIT_ACTIONS = _pt(
    "approve_submit_actions",
    (
        "submit",
        "form_submit",
        "click_submit",
        "form_confirm",
        "confirm_and_submit",
        "sign",
        "esign",
        "bid_submit",
        "payment_confirm",
    ),
)

# NOTIFY 대상 액션 타입
_NOTIFY_ACTION_TYPES = _pt(
    "notify_action_types",
    (
        "download",
        "file_download",
        "file_upload",
        "upload",
        "popup",
        "new_window",
        "new_tab",
        "alert_accept",
        "dialog_confirm",
    ),
)


def _text_contains_approve_keyword(text: str) -> tuple[bool, str]:
    """text에 APPROVE 키워드 포함 여부 → (matched, keyword)."""
    lower = text.lower()
    for kw in _ALL_APPROVE_KEYWORDS:
        if kw in lower:
            return True, kw
    return False, ""


def _params_contain_credential_field(params: dict) -> tuple[bool, str]:
    """params에 자격증명 필드 포함 여부 → (found, field_name)."""
    for k in params:
        k_lower = k.lower()
        for cred in _CREDENTIAL_INPUT_KEYS:
            if cred in k_lower:
                return True, k
    return False, ""


@dataclass
class GateResult:
    verdict: str  # AUTO / NOTIFY / APPROVE / BLOCKED
    reason: str
    category: str = ""  # approve 카테고리명 (MONEY / LEGAL / ACCOUNT / SEND / SENSITIVE)
    blocked_field: str = ""
    matched_keyword: str = ""
    intent_ok: bool = True
    origin_allowed: bool = True

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "verdict": self.verdict,
            "reason": self.reason,
        }
        if self.category:
            d["category"] = self.category
        if self.blocked_field:
            d["blocked_field"] = self.blocked_field
        if self.matched_keyword:
            d["matched_keyword"] = self.matched_keyword
        if not self.intent_ok:
            d["intent_ok"] = False
        if not self.origin_allowed:
            d["origin_allowed"] = False
        return d


def classify_action(
    *,
    action_type: str,
    label: str = "",
    url: str = "",
    intent: IntentToken | None = None,
    params: dict | None = None,
) -> GateResult:
    """액션을 AUTO / NOTIFY / APPROVE / BLOCKED 중 하나로 분류.

    Parameters
    ----------
    action_type: CDP 액션 종류 (navigate, click, type, submit, download, …)
    label:       사람이 읽는 액션 설명 (버튼 텍스트, 폼 레이블 등)
    url:         현재/대상 URL
    intent:      현재 활성 IntentToken (없으면 NOTIFY)
    params:      액션 파라미터 (type 액션의 경우 value 포함 가능)
    """
    params = params or {}

    # 1. 자격증명 필드 → APPROVE (사용자 승인 후 입력)
    found, field = _params_contain_credential_field(params)
    if found:
        return GateResult(
            verdict=GATE_APPROVE,
            reason=f"자격증명 입력: 사용자 승인 필요 ({field})",
            category="CREDENTIAL",
            matched_keyword=field,
        )

    # 2. APPROVE 키워드 검사 (label + url + action_type 통합)
    combined_text = f"{action_type} {label} {url}"
    matched, keyword = _text_contains_approve_keyword(combined_text)
    if matched:
        category = _categorize_approve_keyword(keyword)
        return GateResult(
            verdict=GATE_APPROVE,
            reason=f"APPROVE 키워드 감지: '{keyword}'",
            category=category,
            matched_keyword=keyword,
        )

    # 3. action_type이 명시적 submit류 → APPROVE
    if action_type.lower() in _APPROVE_SUBMIT_ACTIONS:
        return GateResult(
            verdict=GATE_APPROVE,
            reason=f"APPROVE 액션 타입: {action_type}",
            category="SUBMIT",
        )

    # 4. NOTIFY 대상 액션 타입
    if action_type.lower() in _NOTIFY_ACTION_TYPES:
        return GateResult(
            verdict=GATE_NOTIFY,
            reason=f"NOTIFY 액션 타입: {action_type}",
        )

    # 5. Intent 없음 → NOTIFY
    if intent is None:
        return GateResult(
            verdict=GATE_NOTIFY,
            reason="Intent 없음: 범위 불명확",
            intent_ok=False,
        )

    # 6. Intent 유효성 검사
    val = validate_intent(intent)
    if not val["ok"]:
        return GateResult(
            verdict=GATE_NOTIFY,
            reason=f"Intent 무효: {val.get('code')}",
            intent_ok=False,
        )

    # 7. Origin 범위 검사
    if url and not is_origin_allowed(intent, url):
        return GateResult(
            verdict=GATE_NOTIFY,
            reason=f"Intent 범위 이탈: {url}",
            origin_allowed=False,
        )

    # 8. 그 외 → AUTO
    return GateResult(
        verdict=GATE_AUTO,
        reason="Intent 범위 내 자동 진행",
    )


def _categorize_approve_keyword(keyword: str) -> str:
    """keyword가 어떤 APPROVE 카테고리인지 반환."""
    kw = keyword.lower()
    if any(k in kw for k in _CREDENTIAL_INPUT_KEYS):
        return "CREDENTIAL"
    if any(k in kw for k in _APPROVE_MONEY):
        return "MONEY"
    if any(k in kw for k in _APPROVE_LEGAL):
        return "LEGAL"
    if any(k in kw for k in _APPROVE_ACCOUNT):
        return "ACCOUNT"
    if any(k in kw for k in _APPROVE_SEND):
        return "SEND"
    if any(k in kw for k in _APPROVE_SENSITIVE_SUBMIT):
        return "SENSITIVE"
    return "OTHER"


def is_auto(result: GateResult) -> bool:
    return result.verdict == GATE_AUTO


def is_blocked(result: GateResult) -> bool:
    return result.verdict == GATE_BLOCKED


def requires_approval(result: GateResult) -> bool:
    return result.verdict == GATE_APPROVE


def should_notify(result: GateResult) -> bool:
    return result.verdict == GATE_NOTIFY
