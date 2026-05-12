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
    scripts.naver     — 네이버 서비스 자동화
    scripts.google    — Google 서비스 자동화
    scripts.kakao     — 카카오 서비스
    scripts.smartstore — 스마트스토어
    scripts.explorer  — 사이트 탐색
"""
from __future__ import annotations

# 버전 정보
__version__ = "1.0.0"

# 핵심 유틸리티 — 직접 참조 허용
from scripts.logger import get_logger  # noqa: F401
from scripts.schemas import (          # noqa: F401
    RiskLevel,
    GateVerdict,
    OpStatus,
    GateResult,
    OpRecord,
    CriticalRecord,
    CdpNavEvent,
    CdpRequestEvent,
    FileChangeRecord,
    PopupEvent,
    PopupDecision,
    EumDevice,
)
from scripts.gate import (             # noqa: F401
    check as gate_check,
    gated,
    force_approved,
    GateBlocked,
    get_risk,
    register as gate_register,
)
from scripts.op_log import (           # noqa: F401
    log_op,
    op_context,
    op_logged,
    query_recent as op_query,
    query_stats as op_stats,
)
from scripts.critical_logger import (  # noqa: F401
    log_critical,
    query_recent as critical_query,
)
