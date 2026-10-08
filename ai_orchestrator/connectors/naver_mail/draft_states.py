"""L1 공유 계약 — 메일 AI 초안의 상태 어휘와 상태 전이 규칙(순수 값·판정, 부작용 없음).

저장소(`connectors/naver_mail/draft_store`, L7)는 L2 정책을 읽을 수 없으므로, 저장소와 정책이 함께 쓰는
상태 이름·전이표·유효 기간을 여기에 둔다. 정책(`connectors/naver_mail/draft_policy`)은 이 이름들을 그대로 다시 내보낸다.
"""

from __future__ import annotations

DRAFT_TTL_DAYS = 7

# 초안 상태
PENDING, SENDING, SENT, FAILED, UNKNOWN, CANCELLED, EXPIRED = (
    "pending",
    "sending",
    "sent",
    "failed",
    "unknown",
    "cancelled",
    "expired",
)
STATUSES = (PENDING, SENDING, SENT, FAILED, UNKNOWN, CANCELLED, EXPIRED)
OPEN_STATUSES = (PENDING, FAILED)  # 사람이 아직 처리할 수 있는 초안

# sending → unknown 은 "전송 요청이 나간 뒤 결과를 알 수 없음" — 자동 재시도 금지, 사람이 확인(중복 발송 방지)
_TRANSITIONS: dict[str, frozenset[str]] = {
    PENDING: frozenset({SENDING, CANCELLED, EXPIRED}),
    SENDING: frozenset({SENT, FAILED, UNKNOWN}),
    FAILED: frozenset({SENDING, CANCELLED, EXPIRED}),  # 명확한 실패(전송 전)는 사람이 다시 눌러 재시도할 수 있다
    SENT: frozenset(),
    UNKNOWN: frozenset(),
    CANCELLED: frozenset(),
    EXPIRED: frozenset(),
}


def can_transition(current: str, target: str) -> bool:
    return target in _TRANSITIONS.get(current, frozenset())
