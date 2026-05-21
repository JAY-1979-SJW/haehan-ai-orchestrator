# -*- coding: utf-8 -*-
"""AI agent → CAD command contract layer.

CAD-AGENT-CAD-CONTROL-COMMAND-CONTRACT-01.

AI 에이전트가 CAD local_bridge / AutoCAD COM 을 직접 호출하지 않고,
안전한 CAD 명령 후보를 생성·검증·승인 대기 상태로 만드는 contract 계층.

본 모듈은 schema / validator / registry 만 정의한다. 실제 실행 0건.
desktop hub route / proxy / WS action / CAD repo / local_bridge / DB
write / subprocess 일체 호출하지 않는다.

분류:
- READ_ONLY: 9 tool (local_agent/cad/tool_catalog 의 READ_ONLY_TOOLS import).
  approval 불필요.
- CANDIDATE_PAYLOAD: 4 tool (payload contract endpoint — 실행이 아니라
  payload 후보 생성). approval 불필요. 단 autoExecute=False 유지.
- MUTATING_DXF: DXF 원본 수정 가능 — approval 필수.
- MUTATING_AUTOCAD_COM: AutoCAD COM 호출 — approval 필수.

본 트랙은 MUTATING_* 명령을 실제 등록하지 않는다 (seed 0건). enum 으로
정책만 잠금. 향후 트랙에서 명시적으로 추가.
"""
from __future__ import annotations

import enum
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Tuple

from . import tool_catalog as _tool_catalog

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────

class RiskLevel(str, enum.Enum):
    READ_ONLY = "READ_ONLY"
    CANDIDATE_PAYLOAD = "CANDIDATE_PAYLOAD"
    MUTATING_DXF = "MUTATING_DXF"
    MUTATING_AUTOCAD_COM = "MUTATING_AUTOCAD_COM"


class CommandStatus(str, enum.Enum):
    PROPOSED = "PROPOSED"
    VALIDATED = "VALIDATED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    USED = "USED"
    EXPIRED = "EXPIRED"
    BLOCKED = "BLOCKED"


class ApprovalStatus(str, enum.Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    USED = "USED"
    EXPIRED = "EXPIRED"


# ──────────────────────────────────────────────
# Error codes (no secret 노출)
# ──────────────────────────────────────────────

ERROR_TOOL_NOT_REGISTERED = "CAD_AGENT_TOOL_NOT_REGISTERED"
ERROR_TOOL_NOT_AUTO_EXECUTABLE = "CAD_TOOL_NOT_AUTO_EXECUTABLE"
ERROR_APPROVAL_REQUIRED = "CAD_AGENT_APPROVAL_REQUIRED"
ERROR_AUTO_EXECUTE_FORBIDDEN = "CAD_AGENT_AUTO_EXECUTE_FORBIDDEN"
ERROR_INVALID_ARGS = "CAD_AGENT_INVALID_ARGS"


class CadToolNotRegistered(LookupError):
    """등록되지 않은 tool_id 호출 시."""


class CadAutoExecuteForbidden(PermissionError):
    """autoExecute=True 를 외부에서 주입하려는 경우."""


# ──────────────────────────────────────────────
# Candidate-payload tool seed (D3)
# ──────────────────────────────────────────────

# (tool_id, endpoint_path, short description)
CANDIDATE_PAYLOAD_TOOLS: Tuple[Tuple[str, str, str], ...] = (
    (
        "arch_quantity_tab.build_cards",
        "/acad/arch-quantity-tab/build-cards",
        "건축탭 9 카드 payload 빌드 (실행 아님 — payload 후보 생성)",
    ),
    (
        "drawing_inventory.analyze_drawing_inventory",
        "/acad/inventory/analyze-drawing-inventory",
        "도면 인벤토리 분석 (8 필수 필드 + 공종 분류 + 일람표 검출)",
    ),
    (
        "schedule_tables.detect",
        "/acad/schedule-tables/detect",
        "표/일람표 후보 검출 (실제 cell parse 0건 — payload only)",
    ),
    (
        "construction_sequence.plan",
        "/acad/construction-sequence/plan",
        "공사 순서 18 stage 실행계획 (계획 only — 실행 0건)",
    ),
)


# ──────────────────────────────────────────────
# Registry entry
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class CadCommandRegistryEntry:
    toolId: str
    risk: RiskLevel
    endpointPath: Optional[str]  # CAD bridge 측 경로 contract (실제 호출 0)
    description: str

    @property
    def requires_approval(self) -> bool:
        return self.risk in (
            RiskLevel.MUTATING_DXF, RiskLevel.MUTATING_AUTOCAD_COM,
        )


# ──────────────────────────────────────────────
# Registry — singleton pattern
# ──────────────────────────────────────────────

class CadCommandRegistry:
    """tool_id → RegistryEntry 매핑. 중복 등록 거부, unknown tool 차단."""

    def __init__(self) -> None:
        self._entries: Dict[str, CadCommandRegistryEntry] = {}

    def register(self, entry: CadCommandRegistryEntry) -> None:
        if entry.toolId in self._entries:
            raise ValueError(
                f"duplicate tool registration: {entry.toolId}"
            )
        self._entries[entry.toolId] = entry

    def get(self, tool_id: str) -> CadCommandRegistryEntry:
        key = _normalize(tool_id)
        if key not in self._entries:
            raise CadToolNotRegistered(
                f"tool_id not registered: {tool_id!r} ({ERROR_TOOL_NOT_REGISTERED})"
            )
        return self._entries[key]

    def has(self, tool_id: str) -> bool:
        return _normalize(tool_id) in self._entries

    def list_ids(self) -> Tuple[str, ...]:
        return tuple(sorted(self._entries))

    def list_by_risk(self, risk: RiskLevel) -> Tuple[str, ...]:
        return tuple(sorted(
            tid for tid, e in self._entries.items() if e.risk == risk
        ))


def _normalize(tool_id: str) -> str:
    return (tool_id or "").strip().lower()


def build_default_registry() -> CadCommandRegistry:
    """기본 registry — READ_ONLY 9 + CANDIDATE_PAYLOAD 4 시드.

    MUTATING_* 는 본 트랙에서 등록하지 않는다 (정책: enum 만 잠금).
    """
    reg = CadCommandRegistry()
    # READ_ONLY — tool_catalog.READ_ONLY_TOOLS 자동 import (D1)
    for tool_id in _tool_catalog.READ_ONLY_TOOLS:
        reg.register(CadCommandRegistryEntry(
            toolId=_normalize(tool_id),
            risk=RiskLevel.READ_ONLY,
            endpointPath=None,  # 실행 wiring 은 별 트랙
            description=f"read-only CAD tool: {tool_id}",
        ))
    # CANDIDATE_PAYLOAD — 4 시드 (D3)
    for tool_id, path, desc in CANDIDATE_PAYLOAD_TOOLS:
        reg.register(CadCommandRegistryEntry(
            toolId=_normalize(tool_id),
            risk=RiskLevel.CANDIDATE_PAYLOAD,
            endpointPath=path,
            description=desc,
        ))
    return reg


# 기본 싱글톤 (eager init — import 시점에 9+4 = 13 등록)
DEFAULT_REGISTRY: CadCommandRegistry = build_default_registry()


# ──────────────────────────────────────────────
# Command dataclass
# ──────────────────────────────────────────────

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class CadAgentCommand:
    """AI agent 가 제안한 단일 CAD 명령 후보 — 불변.

    autoExecute 는 dataclass field 가 아니다. 외부에서 의도적으로
    True 로 만들 수 없도록 property 로 고정 (CadAutoExecuteForbidden).

    실제 실행은 본 트랙 책임 밖.
    """
    commandId: str
    toolId: str
    args: Mapping[str, Any]
    risk: RiskLevel
    status: CommandStatus
    approvalStatus: ApprovalStatus
    approvalId: Optional[str]
    endpointPath: Optional[str]
    requiresApproval: bool
    createdAt: str = field(default_factory=_utcnow_iso)

    # autoExecute 는 항상 False — 절대 변경 불가
    @property
    def autoExecute(self) -> bool:  # noqa: N802
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "commandId": self.commandId,
            "toolId": self.toolId,
            "args": dict(self.args),
            "risk": self.risk.value,
            "status": self.status.value,
            "approvalStatus": self.approvalStatus.value,
            "approvalId": self.approvalId,
            "endpointPath": self.endpointPath,
            "requiresApproval": self.requiresApproval,
            "autoExecute": self.autoExecute,  # 항상 False
            "createdAt": self.createdAt,
        }


# ──────────────────────────────────────────────
# Validator
# ──────────────────────────────────────────────

class CadCommandValidator:
    """tool_id 검증 + risk 분류 + approval 요구 판정.

    실제 실행 / endpoint 호출 0건. 본 트랙은 schema layer 만.
    """

    def __init__(self, registry: Optional[CadCommandRegistry] = None) -> None:
        self._registry = registry or DEFAULT_REGISTRY

    @property
    def registry(self) -> CadCommandRegistry:
        return self._registry

    def is_approval_required(self, risk: RiskLevel) -> bool:
        return risk in (
            RiskLevel.MUTATING_DXF, RiskLevel.MUTATING_AUTOCAD_COM,
        )

    def propose(
        self,
        tool_id: str,
        args: Optional[Mapping[str, Any]] = None,
        *,
        auto_execute: bool = False,
    ) -> CadAgentCommand:
        """tool_id + args → CadAgentCommand (PROPOSED / APPROVAL_REQUIRED).

        auto_execute 인자가 True 면 CadAutoExecuteForbidden 발생.
        외부 호출자가 자동 실행을 우회하지 못하도록 명시 가드.
        """
        if auto_execute:
            raise CadAutoExecuteForbidden(
                "auto_execute=True is forbidden by policy "
                f"({ERROR_AUTO_EXECUTE_FORBIDDEN})"
            )

        if args is not None and not isinstance(args, Mapping):
            raise TypeError(
                f"args must be a mapping, got {type(args).__name__}"
            )

        entry = self._registry.get(tool_id)
        requires_approval = entry.requires_approval

        if requires_approval:
            status = CommandStatus.APPROVAL_REQUIRED
            approval_status = ApprovalStatus.PENDING
        else:
            status = CommandStatus.VALIDATED
            approval_status = ApprovalStatus.NOT_REQUIRED

        return CadAgentCommand(
            commandId=uuid.uuid4().hex[:16],
            toolId=entry.toolId,
            args=dict(args or {}),
            risk=entry.risk,
            status=status,
            approvalStatus=approval_status,
            approvalId=None,  # approval 모듈에서 생성 시 채워짐
            endpointPath=entry.endpointPath,
            requiresApproval=requires_approval,
        )

    def mark_blocked_unknown_tool(
        self, tool_id: str, args: Optional[Mapping[str, Any]] = None,
    ) -> CadAgentCommand:
        """unknown tool 차단 — BLOCKED 상태 명령 반환 (실행 0건)."""
        return CadAgentCommand(
            commandId=uuid.uuid4().hex[:16],
            toolId=_normalize(tool_id),
            args=dict(args or {}),
            risk=RiskLevel.READ_ONLY,  # default — 실행되지 않음
            status=CommandStatus.BLOCKED,
            approvalStatus=ApprovalStatus.NOT_REQUIRED,
            approvalId=None,
            endpointPath=None,
            requiresApproval=False,
        )


__all__ = [
    "RiskLevel",
    "CommandStatus",
    "ApprovalStatus",
    "ERROR_TOOL_NOT_REGISTERED",
    "ERROR_TOOL_NOT_AUTO_EXECUTABLE",
    "ERROR_APPROVAL_REQUIRED",
    "ERROR_AUTO_EXECUTE_FORBIDDEN",
    "ERROR_INVALID_ARGS",
    "CadToolNotRegistered",
    "CadAutoExecuteForbidden",
    "CANDIDATE_PAYLOAD_TOOLS",
    "CadCommandRegistryEntry",
    "CadCommandRegistry",
    "build_default_registry",
    "DEFAULT_REGISTRY",
    "CadAgentCommand",
    "CadCommandValidator",
]
