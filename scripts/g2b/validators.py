"""G2B 세대 페이로드 검증기.

실제 G2B API 호출, DB 접근, 외부 네트워크 호출 없음.
입력 형식 및 보안 제약 검증만 수행.
"""

from __future__ import annotations

import re
from typing import Any

from scripts.g2b.site_profile import ALL_KNOWN_ACTIONS, BLOCKED_ACTIONS

# ── 상수 ─────────────────────────────────────────────────────────────

# 나라장터 입찰공고번호: 숫자 + 하이픈 형식 (예: 20240115123-00)
_BID_NTCE_NO_RE = re.compile(r"^\d{14,17}$|^\d{10,15}-\d{2,4}$")
_BID_NTCE_ORD_RE = re.compile(r"^\d{1,4}$")

_SECRET_KEYS = frozenset(
    {
        "password",
        "passwd",
        "pw",
        "session",
        "cookie",
        "token",
        "otp",
        "cert_password",
        "certificate_password",
        "access_token",
        "refresh_token",
    }
)

_ALLOWED_ACTION_NAMES: frozenset[str] = ALL_KNOWN_ACTIONS - BLOCKED_ACTIONS


# ── 내부 헬퍼 ────────────────────────────────────────────────────────


def _has_secret_key(payload: dict[str, Any]) -> bool:
    return bool(_SECRET_KEYS & {k.lower() for k in payload})


def _make_error(field: str, msg: str) -> dict[str, Any]:
    return {"valid": False, "field": field, "error": msg}


def _make_ok() -> dict[str, Any]:
    return {"valid": True}


def _get_dual(payload: dict[str, Any], first_key: str, second_key: str) -> Any:
    """camelCase(원본 G2B API 응답) 또는 snake_case(내부 정규화 값) 어느 쪽으로
    와도 같은 필드를 조회한다. first_key 값이 비어있으면(falsy) second_key도 본다
    — 원래 각 호출부에 있던 `payload.get(A) or payload.get(B)`와 완전히 동일한
    순서·동작(그대로 옮기기만 함, 값 자체가 falsy인 경우의 폴백까지 보존).

    2026-09-29 정정(docs/defect_index.json #21): 이 파일 곳곳에 흩어져 있던 이
    인라인 패턴을 여기 한 곳으로 모았다 — 정규화 경계가 어디에도 없다는 지적을
    "경계를 하나로 명시"하는 걸로 해결(동작은 기존과 완전히 동일, 호출부 계약
    변경 없음).
    """
    return payload.get(first_key) or payload.get(second_key)


def _has_dual(payload: dict[str, Any], first_key: str, second_key: str) -> bool:
    return first_key in payload or second_key in payload


# ── 공개 검증 함수 ────────────────────────────────────────────────────


def validate_g2b_no_secret_session_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if _has_secret_key(payload):
        return _make_error("payload", "secret/session/cookie/token 키 포함 불가")
    return _make_ok()


def validate_g2b_action_name(action: str) -> dict[str, Any]:
    if not isinstance(action, str) or not action.strip():
        return _make_error("action", "action 이름은 비어 있을 수 없습니다")
    if action in BLOCKED_ACTIONS:
        return _make_error("action", f"차단된 action: '{action}'")
    if action not in ALL_KNOWN_ACTIONS:
        return _make_error("action", f"알 수 없는 action: '{action}'")
    return _make_ok()


def validate_notice_search_payload(payload: dict[str, Any]) -> dict[str, Any]:
    secret_check = validate_g2b_no_secret_session_payload(payload)
    if not secret_check["valid"]:
        return secret_check
    return _make_ok()


def validate_notice_detail_payload(payload: dict[str, Any]) -> dict[str, Any]:
    secret_check = validate_g2b_no_secret_session_payload(payload)
    if not secret_check["valid"]:
        return secret_check
    bid_no = _get_dual(payload, "bidNtceNo", "bid_ntce_no")
    if bid_no is not None and not _BID_NTCE_NO_RE.match(str(bid_no)):
        return _make_error("bidNtceNo", f"입찰공고번호 형식 오류: '{bid_no}'")
    bid_ord = _get_dual(payload, "bidNtceOrd", "bid_ntce_ord")
    if bid_ord is not None and not _BID_NTCE_ORD_RE.match(str(bid_ord)):
        return _make_error("bidNtceOrd", f"차수 형식 오류: '{bid_ord}'")
    return _make_ok()


def validate_attachment_payload(payload: dict[str, Any]) -> dict[str, Any]:
    secret_check = validate_g2b_no_secret_session_payload(payload)
    if not secret_check["valid"]:
        return secret_check
    att_id = _get_dual(payload, "attachment_id", "attachmentId")
    att_path = _get_dual(payload, "attachment_path", "attachmentPath")
    if att_id is None and att_path is None:
        return _make_error("attachment", "attachment_id 또는 attachment_path 필요")
    return _make_ok()


def _validate_bid_no_draft_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """비밀값·세션 없음 + 입찰공고번호(bid_ntce_no/bidNtceNo) 필수 — 분석 초안·제출 초안 공용 검증."""
    secret_check = validate_g2b_no_secret_session_payload(payload)
    if not secret_check["valid"]:
        return secret_check
    if not _has_dual(payload, "bid_ntce_no", "bidNtceNo"):
        return _make_error("bidNtceNo", "입찰공고번호 필요")
    return _make_ok()


def validate_bid_analysis_draft_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return _validate_bid_no_draft_payload(payload)


def validate_submit_draft_payload(payload: dict[str, Any]) -> dict[str, Any]:
    # submit draft 자체 검증 허용, 최종 제출은 gate에서 차단
    return _validate_bid_no_draft_payload(payload)
