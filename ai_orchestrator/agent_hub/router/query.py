"""local_agent 조회 라우트군 (list / diagnostics) — read-only leaf 서브라우터.

local_agent_router.py(컴포지션 루트)가 include_router 로 관리한다.
sibling leaf 를 직접 import 하지 않는다. [docs/module_separation_standard.md]
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..registry import diagnostics as local_agent_diagnostics
from tools.gates.auth import require_role

query_router = APIRouter()


@query_router.get("/diagnostics")
def get_local_agents_diagnostics(
    user: dict = Depends(require_role("admin", "owner", "viewer")),
):
    """Local agent 운영 진단 정보 (read-only).

    agent/task 상태 집계, 민감정보 제외 (token_id, raw params, raw audit, raw html/url/secret 등).
    allowlist field만 반환 (counts, status, timestamps).

    2026-09-29 실측 확인한 치명적 버그 수정(defect_index 신규 항목): 여기서 _reg._lock 을
    잡은 채로 build_local_agent_diagnostics() 를 호출했는데, 그 내부가 부르는
    get_agent_status()→get_active_task_count() 가 같은 _reg._lock 을 다시 획득하려 한다
    (threading.Lock 은 비재진입 — 같은 스레드가 두 번째로 acquire() 하면 영구 교착).
    이 엔드포인트 요청 하나만으로 그 워커 스레드가 영원히 멈추는 게 아니라 서버 전체가
    응답을 멈췄다(GET /api/v1/health 조차 5초 타임아웃 반복 실측 확인) — 이 진단 엔드포인트를
    호출하는 순간 전체 API가 마비되는 치명적 결함이었다. build_local_agent_diagnostics()
    내부 함수들이 이미 각자 필요한 지점에서 개별적으로 락을 잡고 있어(세밀한 락킹) 바깥의
    통짜 락은 애초에 불필요했다 — 제거.
    """
    return local_agent_diagnostics.build_local_agent_diagnostics()
