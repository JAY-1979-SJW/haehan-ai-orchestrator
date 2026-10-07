"""사용자 브라우저 액션 감사 로그 (JSONL).

저장 경로
========
data/audit/user_browser_cdp_YYYYMMDD.jsonl

원칙
====
1. 모든 액션은 무조건 기록 (성공/실패/차단 무관).
2. 민감 정보는 자동 마스킹 (password, card, ssn, otp, token, cookie).
3. JSONL 1줄 = 1 액션 (append-only, 수정/삭제 안 함).
4. 시각은 UTC ISO8601.

사용 예
======
    from scripts.browser.agent.audit_log import log_action

    log_action(
        action="navigate",
        url="https://developer.hancom.com/",
        intent_id="intent_xxx",
        result="ok",
        title="한컴디벨로퍼",
    )
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_orchestrator.paths import repo_root

# 이동해도 값이 안 바뀌게 __file__ 상대 계산 대신 repo_root() 기준으로 고정(T4 C1).
# 지금 값과 완전히 동일(ai_orchestrator/data/audit) — 저장소 루트 data/는 기존 결함으로
# 쓰지 않음, 전환은 별도 커밋(D4).
_AUDIT_DIR = repo_root() / "ai_orchestrator" / "data" / "audit"

# 마스킹 대상 키 (대소문자 무관 부분 매칭)
_SENSITIVE_KEY_PATTERNS = (
    "password",
    "passwd",
    "pwd",
    "card",
    "cvc",
    "cvv",
    "ssn",
    "rrn",
    "주민",
    "otp",
    "auth_code",
    "verification_code",
    "token",
    "secret",
    "api_key",
    "apikey",
    "cookie",
    "session",
    "storage_state",
    "private_key",
    "npki",
    "계좌",
    "account_number",
)

# 마스킹 대상 값 패턴
_RRN_PATTERN = re.compile(r"\b\d{6}-?[1-4]\d{6}\b")  # 주민번호
_CARD_PATTERN = re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")  # 카드번호
_OTP_PATTERN = re.compile(r"\b\d{6}\b")  # 6자리 숫자 (단순 휴리스틱, 너무 광범위하니 상황별)


def _is_sensitive_key(key: str) -> bool:
    k = key.lower()
    return any(pat in k for pat in _SENSITIVE_KEY_PATTERNS)


def _mask_value(value: Any) -> Any:
    """값을 마스킹. dict/list 재귀."""
    if isinstance(value, str):
        # 주민번호/카드번호 패턴 마스킹
        masked = _RRN_PATTERN.sub("[RRN_REDACTED]", value)
        masked = _CARD_PATTERN.sub("[CARD_REDACTED]", masked)
        return masked
    if isinstance(value, dict):
        return mask_sensitive_data(value)
    if isinstance(value, list):
        return [_mask_value(v) for v in value]
    return value


def mask_sensitive_data(data: dict) -> dict:
    """dict의 민감 키를 마스킹한 새 dict 반환."""
    masked = {}
    for k, v in data.items():
        if _is_sensitive_key(k):
            masked[k] = "[REDACTED]"
        else:
            masked[k] = _mask_value(v)
    return masked


def get_audit_path(date: str | None = None) -> Path:
    """오늘 날짜의 감사 로그 파일 경로."""
    if date is None:
        date = datetime.now(UTC).strftime("%Y%m%d")
    _AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    return _AUDIT_DIR / f"user_browser_cdp_{date}.jsonl"


def log_action(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    action: str,
    *,
    url: str = "",
    intent_id: str = "",
    result: str = "ok",
    risk_level: str = "AUTO",
    approval_id: str = "",
    selector: str = "",
    params: dict | None = None,
    extra: dict | None = None,
    error: str = "",
    audit_path: Path | None = None,
) -> dict:
    """액션 1건 기록. 반환: 기록된 entry."""
    entry: dict[str, Any] = {
        "ts": datetime.now(UTC).isoformat(),
        "action": action,
        "url": url[:500],  # URL이 너무 길면 truncate
        "intent_id": intent_id,
        "result": result,
        "risk_level": risk_level,
    }
    if approval_id:
        entry["approval_id"] = approval_id
    if selector:
        entry["selector"] = selector[:200]
    if params is not None:
        entry["params"] = mask_sensitive_data(params)
    if extra is not None:
        entry["extra"] = mask_sensitive_data(extra)
    if error:
        entry["error"] = error[:500]

    path = audit_path or get_audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_log(date: str | None = None, audit_path: Path | None = None) -> list[dict]:
    """감사 로그 읽어 리스트로 반환."""
    path = audit_path or get_audit_path(date)
    if not path.exists():
        return []
    entries = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def summarize_log(date: str | None = None, audit_path: Path | None = None) -> dict:
    """감사 로그 요약: 액션 종류별/risk_level별 카운트."""
    entries = read_log(date, audit_path)
    by_action: dict[str, int] = {}
    by_risk: dict[str, int] = {}
    by_result: dict[str, int] = {}
    for e in entries:
        by_action[e.get("action", "?")] = by_action.get(e.get("action", "?"), 0) + 1
        by_risk[e.get("risk_level", "?")] = by_risk.get(e.get("risk_level", "?"), 0) + 1
        by_result[e.get("result", "?")] = by_result.get(e.get("result", "?"), 0) + 1
    return {
        "total": len(entries),
        "by_action": by_action,
        "by_risk_level": by_risk,
        "by_result": by_result,
    }
