"""웹 작업 레지스트리.

provider / action_type 별 어댑터 등록 및 허용 작업 목록 조회.
등록되지 않은 작업은 실행할 수 없다.

금지 원칙:
  - 임의 provider/action_type 실행 금지
  - 등록되지 않은 작업은 404 거절
  - adapter_class 외부 직접 노출 금지 (list_entries 는 안전 필드만 반환)
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_orchestrator.sites.adapters.dev_reg_base import DevRegAdapterBase


@dataclass(frozen=True)
class WebTaskEntry:
    task_key: str  # "{provider}/{action_type}"
    provider: str
    action_type: str
    adapter_class: type[DevRegAdapterBase]
    risk_level: str  # "medium" / "high"
    requires_approval: bool
    read_only: bool
    description: str


def _build_registry() -> dict[str, WebTaskEntry]:
    # 지연 임포트 — 순환 참조 방지
    from ai_orchestrator.sites.adapters.google_dev_reg import GoogleDevRegAdapter
    from ai_orchestrator.sites.adapters.hiworks_dev_reg import HiworksDevRegAdapter
    from ai_orchestrator.sites.adapters.naver_dev_reg import NaverDevRegAdapter

    entries = [
        WebTaskEntry(
            task_key="hiworks/developer_apply",
            provider="hiworks",
            action_type="developer_apply",
            adapter_class=HiworksDevRegAdapter,
            risk_level="high",
            requires_approval=True,
            read_only=False,
            description="하이웍스 개발자 센터 앱 등록 신청",
        ),
        WebTaskEntry(
            task_key="naver/app_register",
            provider="naver",
            action_type="app_register",
            adapter_class=NaverDevRegAdapter,
            risk_level="high",
            requires_approval=True,
            read_only=False,
            description="네이버 개발자 센터 앱 등록",
        ),
        WebTaskEntry(
            task_key="google/oauth_submit",
            provider="google",
            action_type="oauth_submit",
            adapter_class=GoogleDevRegAdapter,
            risk_level="high",
            requires_approval=True,
            read_only=False,
            description="Google Cloud Console OAuth 클라이언트 등록",
        ),
    ]
    return {e.task_key: e for e in entries}


_REGISTRY: dict[str, WebTaskEntry] = _build_registry()


def get_entry(provider: str, action_type: str) -> WebTaskEntry | None:
    """provider/action_type 으로 레지스트리 조회. 미등록 시 None."""
    return _REGISTRY.get(f"{provider}/{action_type}")


def list_entries() -> list[dict]:
    """등록된 작업 목록 (adapter_class 제외한 안전 필드만 반환)."""
    return [
        {
            "task_key": e.task_key,
            "provider": e.provider,
            "action_type": e.action_type,
            "risk_level": e.risk_level,
            "requires_approval": e.requires_approval,
            "read_only": e.read_only,
            "description": e.description,
        }
        for e in _REGISTRY.values()
    ]


__all__ = ["WebTaskEntry", "get_entry", "list_entries"]
