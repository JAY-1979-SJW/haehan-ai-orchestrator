"""로컬 에이전트 API 응답 빌더.

API 응답 구조를 표준화하고 응답 생성을 중앙화한다.
"""

from __future__ import annotations

from typing import Any

# ── Agent 등록 응답 ─────────────────────────────────────────────────────────


def make_register_agent_response(
    agent_id: str,
    device_token: str,
    host: str,
    os_name: str,
    version: str,
    registered_at: str,
) -> dict[str, Any]:
    """에이전트 등록 응답 생성.

    device_token은 register 응답에서만 1회 노출된다.
    """
    return {
        "agent_id": agent_id,
        "device_token": device_token,
        "host": host,
        "os_name": os_name,
        "version": version,
        "registered_at": registered_at,
    }


# ── Agent 목록 응답 ─────────────────────────────────────────────────────────


def make_list_agents_response(agents: list[dict]) -> dict[str, Any]:
    """에이전트 목록 응답 생성.

    Args:
        agents: 에이전트 dict 목록

    Returns: {"agents": [...]}
    """
    return {
        "agents": agents,
    }


# ── Registration Code 목록 응답 ─────────────────────────────────────────────


def make_list_codes_response(codes: list[dict]) -> dict[str, Any]:
    """등록 코드 목록 응답 생성.

    Args:
        codes: 등록 코드 dict 목록

    Returns: {"codes": [...]}
    """
    return {
        "codes": codes,
    }


# ── Task 목록 응답 ──────────────────────────────────────────────────────────


def make_list_tasks_response(tasks: list[dict]) -> dict[str, Any]:
    """태스크 목록 응답 생성.

    Args:
        tasks: 태스크 dict 목록

    Returns: {"tasks": [...]}
    """
    return {
        "tasks": tasks,
    }


# ── Task 조회 응답 ──────────────────────────────────────────────────────────


def make_get_task_response(task: dict) -> dict[str, Any]:
    """단일 태스크 조회 응답 생성.

    Args:
        task: 태스크 dict

    Returns: 태스크 dict 또는 래핑된 응답
    """
    # 태스크는 그대로 반환 (래핑 안 함)
    return task
