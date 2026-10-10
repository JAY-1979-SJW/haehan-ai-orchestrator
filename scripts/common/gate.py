"""경량 위험 게이트 — 호환 shim.

게이트 핵심은 `tools/gates/gate_core.py` 로 옮겼다(R2d-2 설계서 §4: `ai_orchestrator/gates ↔ scripts` 순환 해소).
이 모듈은 기존 `from scripts.common.gate import check, gated, GateBlocked, ...` 호출자(29곳+)를 위한 shim 이고,
`sys.modules` 를 바꿔치기해 **같은 모듈 객체**를 돌려준다(모듈 전역 상태 `_RISK_REGISTRY`·`_force_local` 공유, 시험의 patch 도 그대로 동작).

게이트 판정의 감사 기록(op_log)은 핵심이 `scripts` 를 import 하지 않도록 싱크 주입으로 연결한다 — 여기서 등록한다.
"""

from __future__ import annotations

import importlib as _il
import sys as _sys
from typing import Any as _Any

from tools.gates.gate_core import (  # noqa: F401 - 정적 분석(mypy)이 속성을 볼 수 있게 명시 재수출
    CONFIRM_TEXTS,
    GateBlocked,
    add_opt_out,
    check,
    force_approved,
    gated,
    get_risk,
    is_opted_out,
    list_registry,
    opt_out_list,
    register,
    require_approved,
    require_side_effect,
    set_audit_sink,
)


def _audit(name: str, **fields: _Any) -> None:
    """게이트 판정을 op_log 에 기록(지연 import — 기존 동작과 같다)."""
    from scripts.common.op_log import log_op

    log_op(name, **fields)


set_audit_sink(_audit)

# 호환 shim: 실제 모듈은 tools/gates/gate_core.py (docs/architecture/R2D2_HUMAN_APPROVAL_PLAN.md §4)
_sys.modules[__name__] = _il.import_module("tools.gates.gate_core")
