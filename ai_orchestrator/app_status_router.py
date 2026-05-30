"""App Status Read-Only Router.

[APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_01]

Priority 1 read-only endpoints:
- GET /app/health/summary
- GET /app/providers
- GET /app/storage/status
- GET /app/live-summary
- GET /app/deployment-status

보기만 가능. 스위치 없음. mutation 일체 금지.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

# ── 공정 상수 ────────────────────────────────────────────────────────────────
APP_STATUS_ROUTER_PHASE = "APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_01"
READ_ONLY_API_ENABLED = True
MUTATION_ALLOWED = False
SERVER_ACTION_ALLOWED = False
SECRET_VALUE_OUTPUT_ALLOWED = False

# ── 보안/레드액션 금지 필드 (감사용) ─────────────────────────────────────────
_FORBIDDEN_RESPONSE_FIELDS = frozenset({
    "raw_token", "access_token", "refresh_token", "cookie",
    "session_secret", "password", "approval_token_raw",
    "private_key", "certificate_password", "secret_value",
    "execute_url", "deploy_url", "restart_url",
})

# ── 공통 meta ─────────────────────────────────────────────────────────────────
_META_READ_ONLY: dict[str, Any] = {
    "source": "app_status_router",
    "read_only": True,
    "mutation_allowed": False,
    "side_effect_allowed": False,
    "server_action_allowed": False,
}

app_status_router = APIRouter(prefix="/app", tags=["app-status"])


# ─────────────────────────────────────────────────────────────────────────────
# GET /app/health/summary
# ─────────────────────────────────────────────────────────────────────────────

@app_status_router.get("/health/summary")
def get_health_summary() -> dict[str, Any]:
    """Backend 상태 read-only 요약. mutation 없음."""
    return {
        "ok": True,
        "data": {
            "service": "haehan-ai-orchestrator",
            "health_status": "ok",
            "server_head": None,
            "origin_head": None,
            "sync_status": "not_checked",
            "post_tasks_dry_run_enabled": True,
            "phase1_closeout_status": "complete",
            "container_health_source": "static",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "meta": {**_META_READ_ONLY},
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /app/providers
# ─────────────────────────────────────────────────────────────────────────────

def _provider_to_dict(p: Any) -> dict[str, Any]:
    return {
        "provider_id": p.provider_id,
        "display_name": p.display_name,
        "category": p.category,
        "current_status": p.current_status,
        "risk_level": p.risk_level,
        "user_present_login_required": p.user_present_login_required,
        "desktop_app_required": p.desktop_app_required,
        "cookie_storage_allowed": False,
        "token_storage_allowed": False,
        "approval_gate_required": p.approval_gate_required,
        "automation_status": p.automation_status,
        "server_remote_login_allowed": False,
        "certificate_login_required": getattr(p, "certificate_login_required", False),
    }


@app_status_router.get("/providers")
def get_providers() -> dict[str, Any]:
    """External Site provider registry read-only 목록. 쿠키/토큰/비밀번호 없음."""
    from ai_orchestrator.external_sites.provider_registry import PROVIDER_REGISTRY

    providers = [_provider_to_dict(p) for p in PROVIDER_REGISTRY]
    return {
        "ok": True,
        "data": {
            "providers": providers,
        },
        "meta": {
            **_META_READ_ONLY,
            "provider_count": len(providers),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /app/storage/status
# ─────────────────────────────────────────────────────────────────────────────

@app_status_router.get("/live-summary")
def get_live_summary() -> dict[str, Any]:
    """실시간 운영 요약 — 헬스·DRY_RUN 게이트·Phase·스토리지 정책을 한 번에 read-only 조회.

    mutation/실행/승인 없음. secret/token 미반환. generated_at 으로 실시간성 제공.
    """
    # DRY_RUN 게이트는 현재 운영 정책상 항상 활성(True). router.py 의 상수와 동일하며,
    # router→app_status_router 순환 import 를 피하기 위해 직접 import 하지 않는다.
    # (health/summary 엔드포인트와 동일한 처리)
    return {
        "ok": True,
        "data": {
            "service": "haehan-ai-orchestrator",
            "health_status": "ok",
            "post_tasks_dry_run_enabled": True,
            "phase1_closeout_status": "complete",
            "container_health_source": "static",
            "read_only": True,
            "mutation_allowed": False,
            "storage": {
                "named_volume_status": "configured",
                "app_logs_bind_mount_status": "configured",
                "audit_log_policy": "PERSISTENT_AUDIT_REQUIRED",
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "meta": {**_META_READ_ONLY},
    }


@app_status_router.get("/deployment-status")
def get_deployment_status() -> dict[str, Any]:
    """배포 상태 read-only 조회 — 배포 SOP/상태 안내만. git 명령/빌드/배포 실행 없음.

    server_head/origin_head 비교나 배포 트리거는 하지 않는다(서버 액션 금지).
    """
    return {
        "ok": True,
        "data": {
            "server_head": None,
            "origin_head": None,
            "state": "not_checked",
            "build_required": False,
            "sop_steps": [
                "git pull origin master",
                "docker compose build",
                "docker compose up -d",
            ],
            "deploy_action_allowed": False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "meta": {**_META_READ_ONLY},
    }


@app_status_router.get("/storage/status")
def get_storage_status() -> dict[str, Any]:
    """Runtime storage 정책 read-only 조회. 파일 내용/토큰 반환 없음."""
    storage_paths = [
        {"name": "storage", "path": "/app/ai_orchestrator/storage", "type": "named_volume"},
        {"name": "app_logs", "path": "/app/logs", "type": "bind_mount"},
    ]
    return {
        "ok": True,
        "data": {
            "storage_paths": storage_paths,
            "named_volume_status": "configured",
            "app_logs_bind_mount_status": "configured",
            "app_logs_path": "/app/logs",
            "storage_path": "/app/ai_orchestrator/storage",
            "audit_log_policy": "PERSISTENT_AUDIT_REQUIRED",
            "execution_history_policy": "PERSISTENT_OPERATION_REQUIRED",
            "approval_token_policy": "EPHEMERAL_SECURITY_SENSITIVE_WITH_TTL",
            "runtime_cache_policy": "RUNTIME_CACHE_DISPOSABLE",
        },
        "meta": {**_META_READ_ONLY},
    }
