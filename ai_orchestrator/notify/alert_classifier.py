"""승인 게이트 감사 결과 분류 및 알림 메시지 생성.

AlertType:
  HARD_FAIL — 즉시 알림 (만료 pending, 스토리지 실패, 보안 이슈)
  SOFT_WARN — 조건부 알림 (과다 pending, 오래된 pending, 데이터 없음)
  NONE      — 알림 없음 (PASS)

retry_candidate:
  True  — 인프라 일시 실패(STORAGE_READ_FAILED)만
  False — 승인 필요 작업·보안 이슈·만료 건 (자동 재시도 절대 금지)

보안:
  build_alert_text() 는 token/password/cookie/path 전체 일절 포함 금지.
  숫자·코드명·타임스탬프만 허용.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

AlertType = Literal["HARD_FAIL", "SOFT_WARN", "NONE"]

# 경고 코드 prefix → HARD_FAIL (즉시 알림)
_HARD_FAIL_PREFIXES: tuple[str, ...] = (
    "STORAGE_READ_FAILED",
    "SUMMARY_LEAKAGE_DETECTED",
    "EXPIRED_PENDING_EXISTS",
)

# retry_candidate=True: 인프라 일시 실패만
# 승인 필요 작업(pending/approved 계열)은 자동 재시도 절대 금지
_RETRY_CANDIDATE_PREFIXES: tuple[str, ...] = (
    "STORAGE_READ_FAILED",
)


@dataclass
class AlertClassification:
    alert_type: AlertType
    should_notify: bool      # True → 알림 활성화 시 발송 대상
    retry_candidate: bool    # True → 인프라 실패로 재시도 유의미 (자동 실행 금지)
    reasons: list[str] = field(default_factory=list)


def classify(warnings: list[str], result: str) -> AlertClassification:
    """감사 경고 목록과 결과로 알림 분류를 결정한다.

    Args:
        warnings: audit() 가 수집한 경고 코드 목록 (colon-separated)
        result: "PASS" | "WARN" | "FAIL"
    """
    if not warnings and result == "PASS":
        return AlertClassification(
            alert_type="NONE",
            should_notify=False,
            retry_candidate=False,
        )

    alert_type: AlertType = "NONE"
    reasons: list[str] = []
    retry = False

    for w in warnings:
        code = w.split(":")[0]

        if any(code.startswith(p) for p in _HARD_FAIL_PREFIXES):
            alert_type = "HARD_FAIL"
        else:
            if alert_type != "HARD_FAIL":
                alert_type = "SOFT_WARN"

        reasons.append(code)

        if any(code.startswith(p) for p in _RETRY_CANDIDATE_PREFIXES):
            retry = True

    # 중복 제거, 순서 유지
    seen: dict[str, None] = {}
    for r in reasons:
        seen[r] = None

    return AlertClassification(
        alert_type=alert_type,
        should_notify=alert_type in ("HARD_FAIL", "SOFT_WARN"),
        retry_candidate=retry,
        reasons=list(seen),
    )


def build_alert_text(
    classification: AlertClassification,
    *,
    pending_count: int = 0,
    expired_pending_count: int = 0,
    recent_executed: int = 0,
    recent_failed: int = 0,
    audit_time: str = "",
) -> str:
    """Telegram 알림 메시지 텍스트 생성.

    보안: token / password / cookie / path 전체 절대 미포함.
    숫자·코드명·ISO 타임스탬프만 포함.
    """
    if not audit_time:
        audit_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    icon = "🚨" if classification.alert_type == "HARD_FAIL" else "⚠️"
    lines = [
        f"{icon} Dev-Reg 승인 게이트 {classification.alert_type}",
        "",
        f"감지 시각: {audit_time}",
        f"알림 유형: {classification.alert_type}",
        "",
        "주요 경고:",
    ]
    for r in classification.reasons[:10]:
        lines.append(f"  - {r}")

    lines += [
        "",
        "현황:",
        f"  pending_count      : {pending_count}",
        f"  expired_pending    : {expired_pending_count}",
        f"  recent_executed    : {recent_executed}",
        f"  recent_failed      : {recent_failed}",
        "",
        "재시도 가능: "
        + ("Yes (인프라 실패)" if classification.retry_candidate else "No (수동 확인 필요)"),
    ]
    return "\n".join(lines)
