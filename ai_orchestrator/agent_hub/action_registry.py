"""Action Registry — 등록된 액션 스펙 + 실행 핸들러 매핑."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ai_orchestrator.agent_hub.action_schemas import (
    ActionSpec,
    all_specs,
)

# 실행 핸들러는 actions/ 모듈에서 등록
_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {}


def get_action_spec(name: str) -> ActionSpec | None:
    """이름으로 액션 스펙 조회."""
    return all_specs().get(name)


def list_action_names() -> list[str]:
    return sorted(all_specs().keys())


def list_actions_by_grade(grade: str) -> list[str]:
    return sorted(name for name, spec in all_specs().items() if spec.risk_grade == grade)


def list_implemented_actions() -> list[str]:
    return sorted(name for name, spec in all_specs().items() if spec.implemented)


def list_pending_actions() -> list[str]:
    return sorted(name for name, spec in all_specs().items() if not spec.implemented)


def list_pair_actions(prepare_name: str) -> str | None:
    """prepare 액션의 짝(execute)을 반환."""
    spec = get_action_spec(prepare_name)
    return spec.pair_with if spec and spec.is_pair else None


def register_handler(name: str, handler: Callable[..., dict[str, Any]]) -> None:
    """액션 실행 핸들러 등록 (actions/ 모듈에서 호출)."""
    spec = get_action_spec(name)
    if not spec:
        raise ValueError(f"등록되지 않은 액션: {name}")
    if not spec.implemented:
        raise ValueError(f"미구현(implemented=False) 액션의 핸들러 등록 시도: {name}")
    _HANDLERS[name] = handler


def get_handler(name: str) -> Callable[..., dict[str, Any]] | None:
    return _HANDLERS.get(name)


def has_handler(name: str) -> bool:
    return name in _HANDLERS


def requires_user_approval(name: str) -> bool:
    spec = get_action_spec(name)
    return bool(spec and spec.requires_user_approval)


def requires_pre_execution_summary(name: str) -> bool:
    spec = get_action_spec(name)
    return bool(spec and spec.requires_pre_execution_summary)
