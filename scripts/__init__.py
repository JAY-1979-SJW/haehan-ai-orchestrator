"""scripts 패키지 — haehan-ai-orchestrator 브라우저 자동화 레이어.

핵심 모듈 익스포트:

    로깅:
        from scripts import op_log          # 작업 단위 로그
        from scripts import critical_logger # 감사 추적 로그

    게이트:
        from scripts import gate            # 위험 등급 체크
        from scripts.gate import check, gated, force_approved, GateBlocked

    스키마:
        from scripts import schemas
        from scripts.schemas import GateResult, RiskLevel, OpRecord, ...

    브라우저:
        from scripts import navigator       # 페이지 이동 / 클릭 / 입력
        from scripts import cdp_daemon      # CDP 데몬 관리
        from scripts import cdp_event_monitor  # 이벤트 상시 감시

    로거:
        from scripts.logger import get_logger

하위 패키지:
    scripts.naver      — 네이버 서비스 자동화
    scripts.google     — Google 서비스 자동화
    scripts.kakao      — 카카오 서비스
    scripts.eum        — 건설공제회 단말기 관리
    scripts.naver.smartstore — 스마트스토어
    scripts.g2b        — 나라장터 G2B
    scripts.local_agent — 정부/민원 로컬 에이전트
    scripts.explorer   — 사이트 탐색
"""

from __future__ import annotations

# 버전 정보
__version__ = "1.0.0"

# 핵심 유틸리티 — 직접 참조 허용
from scripts.critical_logger import (  # noqa: F401
    log_critical,
)
from scripts.critical_logger import (
    query_recent as critical_query,
)
from scripts.gate import (
    GateBlocked,
    force_approved,
    gated,
    get_risk,
)
from scripts.gate import (  # noqa: F401
    check as gate_check,
)
from scripts.gate import (
    register as gate_register,
)
from scripts.logger import get_logger  # noqa: F401
from scripts.op_log import (  # noqa: F401
    log_op,
    op_context,
    op_logged,
)
from scripts.op_log import (
    query_recent as op_query,
)
from scripts.op_log import (
    query_stats as op_stats,
)
from scripts.schemas import (  # noqa: F401
    CdpNavEvent,
    CdpRequestEvent,
    CriticalRecord,
    EumDevice,
    ExplorePageResult,
    FileChangeRecord,
    G2bNotice,
    GateResult,
    GateVerdict,
    LocalAgentTask,
    OpRecord,
    OpStatus,
    PopupDecision,
    PopupEvent,
    RiskLevel,
)

# 위 임포트 중 이름이 겹쳐 `x as x` 형태(ruff 권장 재수출 표기)를 쓸 수 없는 것들
# (critical_logger 와 op_log 가 같은 이름 query_recent/query_stats 를 가짐)과, 별칭 없이
# 그대로 재수출하는 것들을 __all__ 로 명시해 F401(미사용 임포트)을 해소한다.
__all__ = [
    "GateBlocked",
    "critical_query",
    "force_approved",
    "gate_register",
    "gated",
    "get_risk",
    "op_query",
    "op_stats",
]
