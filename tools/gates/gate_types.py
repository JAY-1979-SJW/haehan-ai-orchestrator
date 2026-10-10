"""게이트 결과 타입(RiskLevel·GateVerdict·GateResult) — `scripts` 에 의존하지 않는 말단 모듈.

게이트 핵심(`gate_core`)이 `scripts` 패키지를 import 하지 않도록(순환 해소, R2d-2 설계서 §4) 이 타입을 여기에 둔다.
`scripts/common/schemas.py` 가 같은 객체를 재수출하므로 기존 `from scripts.common.schemas import GateResult` 는 그대로 동작한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RiskLevel(str, Enum):  # noqa: UP042
    """작업 위험 등급.

    AUTO   — 자동 실행 허용 (조회/탐색/읽기 등)
    NOTIFY — 실행하되 로그에 경고 기록 (파일 쓰기, URL 이동 등)
    APPROVE — 사용자 직접 승인 필요 (메일 발송, 결제 등)
    BLOCK  — 실행 금지 (민감정보 삭제, 인증서 조작 등)
    """

    AUTO = "auto"
    NOTIFY = "notify"
    APPROVE = "approve"
    BLOCK = "block"


class GateVerdict(str, Enum):  # noqa: UP042
    ALLOWED = "allowed"  # 통과
    NOTIFIED = "notified"  # 통과 + 경고 기록
    PENDING = "pending"  # 승인 대기 (외부 처리 필요)
    BLOCKED = "blocked"  # 차단


@dataclass
class GateResult:
    """gate.check() 반환값."""

    verdict: GateVerdict
    risk: RiskLevel
    op_name: str
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.verdict in (GateVerdict.ALLOWED, GateVerdict.NOTIFIED)

    @property
    def blocked(self) -> bool:
        return self.verdict == GateVerdict.BLOCKED
