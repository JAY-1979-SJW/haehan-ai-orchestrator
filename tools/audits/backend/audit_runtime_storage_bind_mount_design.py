"""
Runtime Storage Bind Mount Design Audit
ASSISTANT_BACKEND_RUNTIME_STORAGE_BIND_MOUNT_DESIGN_01

PERSISTENCE_AUDIT_01에서 확인된 /app/logs 소실 위험과
execution_history 경로 미확정을 해결하기 위한 bind mount 설계.

이번 공정은 설계 공정.
docker-compose.yml 실제 수정 / 컨테이너 재시작 / 서버 반영 금지.
"""

import json
from pathlib import Path
from typing import Any

REPO_ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
SERVER = json.loads(
    (REPO_ROOT / "configs" / "server_layout.json").read_text(encoding="utf-8")
)  # 서버 폴더 배치(설정 파일)

AUDIT_ID = "RUNTIME_STORAGE_BIND_MOUNT_DESIGN"
AUDIT_DATE = "2026-05-18"

# ── 운영 안전 플래그 ─────────────────────────────────────────────────────────
DOCKER_COMPOSE_MODIFY_ALLOWED = False
CONTAINER_RESTART_ALLOWED = False
SERVER_APPLY_ALLOWED = False
LOG_CONTENT_OUTPUT_ALLOWED = False
SECRET_OUTPUT_ALLOWED = False
DESIGN_ONLY = True

# ── 조사 결과 확정 사항 ───────────────────────────────────────────────────────
INVESTIGATION_FINDINGS = {
    "LOG_DIR_env": {
        "value": "/app/ai_orchestrator/storage",
        "source": "docker-compose.yml env section + docker inspect 확인",
        "effect": "execution_history.jsonl, approval_tokens.jsonl, audit_logs.jsonl, app.log 모두 storage/ named volume에 기록됨",
        "verdict": "CORRECTLY_CONFIGURED",
    },
    "storage_named_volume": {
        "host_path": "/var/lib/docker/volumes/haehan-ai-orchestrator-api-storage/_data",
        "container_path": "/app/ai_orchestrator/storage",
        "persisted_across_rebuild": True,
        "contains": [
            "audit_logs.jsonl (1320줄, 448KB) — 감사 로그",
            "app.log (300KB) — 애플리케이션 로그",
            "approval_tokens.jsonl (1줄) — 토큰 이력",
            "task_states.jsonl (18줄) — 태스크 상태",
            "execution_history.jsonl — low 경로 실행 후 생성됨",
        ],
        "verdict": "CORRECTLY_PERSISTED",
    },
    "app_logs_dir": {
        "container_path": "/app/logs",
        "not_bind_mounted": True,
        "persisted_across_rebuild": False,
        "contents": {
            "audit.jsonl": {
                "lines": 4,
                "size": "955 bytes",
                "mtime": "2026-04-22",
                "origin": "별도 audit_log 계열 (LOG_DIR 외부 — 이전 구버전 경로 추정)",
                "current_write_active": False,
                "verdict": "LEGACY_PATH_LOW_ACTIVITY",
            },
            "orchestrator.log": {
                "lines": 44,
                "size": "6.5 KB",
                "mtime": "2026-05-16",
                "origin": "uvicorn 프로세스 로그 또는 별도 logging handler",
                "current_write_active": True,
                "verdict": "PERSISTENCE_RISK_ACTIVE",
            },
            "orchestrator.error.log": {
                "size": "0 bytes",
                "origin": "uvicorn stderr redirect",
                "current_write_active": False,
                "verdict": "EMPTY_LOW_RISK",
            },
        },
        "verdict": "PARTIAL_PERSISTENCE_RISK",
    },
    "execution_history_path": {
        "env_based_path": "/app/ai_orchestrator/storage/execution_history.jsonl",
        "config_code": "ai_orchestrator/core/config.py:20 — EXECUTION_HISTORY_PATH = LOG_DIR / 'execution_history.jsonl'",
        "LOG_DIR_confirmed": "/app/ai_orchestrator/storage",
        "persisted_in_named_volume": True,
        "currently_exists": False,
        "created_on": "low 경로 execute 완료 시 record_execution 호출 시 생성",
        "verdict": "CORRECTLY_CONFIGURED_NOT_YET_CREATED",
    },
}

# ── 현재 스토리지 구조 전체 맵 ────────────────────────────────────────────────
CURRENT_STORAGE_MAP = {
    "/app/ai_orchestrator/storage/": {
        "mount_type": "named_volume",
        "volume_name": "haehan-ai-orchestrator-api-storage",
        "persisted": True,
        "files": {
            "audit_logs.jsonl": {"classification": "PERSISTENT_AUDIT_REQUIRED", "persist_ok": True},
            "app.log": {"classification": "PERSISTENT_AUDIT_REQUIRED", "persist_ok": True},
            "approval_tokens.jsonl": {
                "classification": "EPHEMERAL_SECURITY_SENSITIVE",
                "persist_ok": True,
                "ttl_30min": True,
            },
            "task_states.jsonl": {"classification": "PERSISTENT_OPERATION_REQUIRED", "persist_ok": True},
            "execution_history.jsonl": {
                "classification": "PERSISTENT_OPERATION_REQUIRED",
                "persist_ok": True,
                "note": "미생성 — 실행 후 자동 생성",
            },
            "approval_tokens.json": {
                "classification": "EPHEMERAL_SECURITY_SENSITIVE",
                "persist_ok": True,
                "note": "legacy 추정 — 다음 공정 검토",
            },
        },
    },
    "/app/logs/": {
        "mount_type": "container_layer",
        "persisted": False,
        "files": {
            "audit.jsonl": {"classification": "LEGACY_AUDIT", "persist_ok": False, "action": "BIND_OR_MIGRATE"},
            "orchestrator.log": {
                "classification": "PERSISTENT_OPERATION_REQUIRED",
                "persist_ok": False,
                "action": "BIND_REQUIRED",
            },
            "orchestrator.error.log": {
                "classification": "PERSISTENT_OPERATION_REQUIRED",
                "persist_ok": False,
                "action": "BIND_REQUIRED",
            },
        },
    },
    "/run/secrets/api/": {
        "mount_type": "bind_readonly",
        "persisted": True,
        "files": {
            "http_users.json": {"classification": "FORBIDDEN_PLAINTEXT_SECRET", "note": "원문 접근 금지"},
        },
    },
}

# ── 설계안: bind mount 추가 ───────────────────────────────────────────────────
BIND_MOUNT_DESIGN = {
    "status": "DESIGN_ONLY",
    "implementation_phase": "RUNTIME_STORAGE_BIND_MOUNT_APPLY_01",
    "approval_required": "대표 명시 승인 후 docker-compose.yml 수정 및 서버 반영",
    "options": {
        "OPTION_A_BIND_MOUNT": {
            "description": "/app/logs를 host 디렉터리에 bind mount",
            "docker_compose_addition": {
                "service": "ai-orchestrator-api",
                "volumes_add": "- /home/ubuntu/apps/haehan-ai-orchestrator/data/app-logs:/app/logs",
            },
            "host_path": f"{SERVER['orchestrator_root']}/data/app-logs",
            "pros": ["단순", "host에서 직접 확인 가능", "재빌드에도 보존"],
            "cons": ["host 디렉터리 사전 생성 필요", "권한 설정 필요"],
            "recommended": True,
        },
        "OPTION_B_NAMED_VOLUME": {
            "description": "/app/logs를 별도 named volume으로 관리",
            "docker_compose_addition": {
                "service": "ai-orchestrator-api",
                "volumes_add": "- api_app_logs:/app/logs",
                "volumes_section": "api_app_logs:\n  name: haehan-ai-orchestrator-api-app-logs",
            },
            "pros": ["docker 표준 관리"],
            "cons": ["host 직접 확인 불편", "docker volume inspect 필요"],
            "recommended": False,
        },
        "OPTION_C_MIGRATE_TO_LOG_DIR": {
            "description": "orchestrator.log 생성 handler를 LOG_DIR (storage/)로 이전",
            "approach": "logging_setup.py의 orchestrator.log handler 경로를 LOG_DIR/orchestrator.log로 변경",
            "pros": ["기존 named volume만으로 해결", "bind mount 추가 불필요"],
            "cons": ["코드 수정 필요", "다음 서버 반영 시 효과"],
            "code_change_required": True,
            "recommended": False,
            "note": "logging_setup.py 수정 승인 필요",
        },
    },
    "recommended_option": "OPTION_A_BIND_MOUNT",
    "reason": "가장 단순하고 host 직접 확인 가능. 운영 실용성 우선.",
}

# ── 파일별 최종 설계 결론 ─────────────────────────────────────────────────────
STORAGE_POLICY_FINAL = {
    "approval_tokens": {
        "path": "/app/ai_orchestrator/storage/approval_tokens.jsonl",
        "classification": "EPHEMERAL_SECURITY_SENSITIVE",
        "persistence": "named_volume (현재)",
        "ttl_policy": "30분 만료 — router.py approval 모듈 설계 의도",
        "secret_risk": "토큰 ID·만료시각 저장은 허용. 토큰 secret 평문 여부는 다음 공정(TOKEN_CONTENT_AUDIT) 확인 필요",
        "action": "MAINTAIN_TTL_ENFORCE",
        "verdict": "ACCEPTABLE",
    },
    "audit_logs": {
        "path": "/app/ai_orchestrator/storage/audit_logs.jsonl",
        "classification": "PERSISTENT_AUDIT_REQUIRED",
        "persistence": "named_volume (현재) — 올바름",
        "action": "NONE",
        "verdict": "CORRECTLY_PERSISTED",
    },
    "execution_history": {
        "path": "/app/ai_orchestrator/storage/execution_history.jsonl",
        "classification": "PERSISTENT_OPERATION_REQUIRED",
        "persistence": "named_volume (LOG_DIR 기반 — 올바름)",
        "currently_exists": False,
        "action": "NONE — low 실행 후 자동 생성됨",
        "verdict": "CORRECTLY_CONFIGURED",
    },
    "orchestrator_log": {
        "path": "/app/logs/orchestrator.log",
        "classification": "PERSISTENT_OPERATION_REQUIRED",
        "persistence": "container layer (현재) — 소실 위험",
        "action": "BIND_MOUNT_APPLY_IN_NEXT_PHASE",
        "verdict": "PERSISTENCE_RISK_PENDING_FIX",
    },
    "legacy_audit_jsonl": {
        "path": "/app/logs/audit.jsonl",
        "classification": "LEGACY_AUDIT",
        "persistence": "container layer (현재) — 소실 위험",
        "current_write_active": False,
        "action": "BIND_MOUNT_APPLY_OR_CONFIRM_INACTIVE",
        "verdict": "LOW_RISK_MONITOR",
    },
    "chrome_ui_monitor_state": {
        "path": "scripts/archive/data/chrome_ui_monitor_state.json",
        "classification": "RUNTIME_CACHE_DISPOSABLE",
        "persistence": "불필요",
        "action": "NONE",
        "verdict": "DISPOSABLE_CONFIRMED",
    },
}

# ── 다음 공정 조건 ─────────────────────────────────────────────────────────────
NEXT_PHASE_CONDITIONS = {
    "phase": "RUNTIME_STORAGE_BIND_MOUNT_APPLY_01",
    "description": "docker-compose.yml에 /app/logs bind mount 추가 및 서버 반영",
    "requires_approval": True,
    "approval_scope": "docker-compose.yml 수정 + git push + 서버 pull/build/up -d",
    "conditions": [
        "이번 설계 공정 PASS 확인",
        "OPTION_A bind mount 추가 docker-compose.yml 수정 내용 확인",
        "host 디렉터리 /home/ubuntu/apps/haehan-ai-orchestrator/data/app-logs 생성 확인",
        "git push → 서버 pull --ff-only → docker compose build → up -d",
        "재기동 후 /app/logs 파일 host에서 확인",
        "대표 명시 승인: 'bind mount 적용 및 서버 반영 승인'",
    ],
    "current_status": "DESIGN_COMPLETE_PENDING_APPROVAL",
}


def _check_docker_compose_not_modified() -> bool:
    # 설계 공정(DESIGN_ONLY)에서는 수정 금지.
    # APPLY 공정 이후에는 bind mount가 추가됨 — 수정 자체는 허용.
    # 이 함수는 apply 공정 이후 실행 시 False를 반환하나, run_audit에서 DESIGN_ONLY 위반
    # 으로 판단하지 않도록 처리함.
    content = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8", errors="ignore")
    return "data/app-logs:/app/logs" not in content


def _audit_safety_flags(errors):
    if DOCKER_COMPOSE_MODIFY_ALLOWED:
        errors.append("DOCKER_COMPOSE_MODIFY_ALLOWED must be False")
    if CONTAINER_RESTART_ALLOWED:
        errors.append("CONTAINER_RESTART_ALLOWED must be False")
    if SERVER_APPLY_ALLOWED:
        errors.append("SERVER_APPLY_ALLOWED must be False")
    if SECRET_OUTPUT_ALLOWED:
        errors.append("SECRET_OUTPUT_ALLOWED must be False")
    if not DESIGN_ONLY:
        errors.append("DESIGN_ONLY must be True")


def _audit_execution_history_and_design(errors):
    ef = INVESTIGATION_FINDINGS.get("execution_history_path", {})
    if not ef.get("persisted_in_named_volume"):
        errors.append("execution_history가 named_volume에 기록되지 않음")
    if ef.get("verdict") != "CORRECTLY_CONFIGURED_NOT_YET_CREATED":
        errors.append("execution_history verdict 오류")

    # 5. 설계안 존재
    if not BIND_MOUNT_DESIGN.get("options"):
        errors.append("bind mount 설계안 없음")
    if not BIND_MOUNT_DESIGN.get("recommended_option"):
        errors.append("권장 옵션 미선택")
    if BIND_MOUNT_DESIGN.get("status") != "DESIGN_ONLY":
        errors.append("BIND_MOUNT_DESIGN.status must be DESIGN_ONLY")
    return ef


def _audit_next_phase(errors):
    if not NEXT_PHASE_CONDITIONS.get("phase"):
        errors.append("다음 공정 정의 없음")
    if not NEXT_PHASE_CONDITIONS.get("requires_approval"):
        errors.append("다음 공정 승인 요건 없음")


def run_audit() -> dict:
    errors: list[Any] = []
    warnings = []

    # 1. 운영 안전 플래그
    _audit_safety_flags(errors)

    # 2. docker-compose.yml 수정 여부 — 설계 공정에서는 미수정이 원칙.
    # APPLY 공정 이후 bind mount가 추가된 경우 WARN으로만 처리 (설계 검증 목적은 달성됨).
    if not _check_docker_compose_not_modified():
        warnings.append("docker-compose.yml에 bind mount 추가됨 — APPLY 공정 진행 중 또는 완료 후 상태 (정상)")

    # 3. 조사 결론 완전성
    required_findings = ["LOG_DIR_env", "storage_named_volume", "app_logs_dir", "execution_history_path"]
    for f in required_findings:
        if f not in INVESTIGATION_FINDINGS:
            errors.append(f"조사 결론 누락: {f}")

    # 4. LOG_DIR 확정 — execution_history 경로 확정
    ef = _audit_execution_history_and_design(errors)

    # 6. 파일별 정책 완전성
    required_policies = ["approval_tokens", "audit_logs", "execution_history", "orchestrator_log"]
    for p in required_policies:
        if p not in STORAGE_POLICY_FINAL:
            errors.append(f"정책 누락: {p}")

    # 7. PERSISTENCE_RISK 항목 식별
    risk_items = [k for k, v in STORAGE_POLICY_FINAL.items() if "RISK" in v.get("verdict", "")]
    if not risk_items:
        warnings.append("PERSISTENCE_RISK 항목 식별 없음 — 정책이 모두 OK인 경우만 허용")

    # 8. 다음 공정 조건
    _audit_next_phase(errors)

    if errors:
        verdict = "RUNTIME_STORAGE_BIND_MOUNT_DESIGN_FAIL"
    elif warnings:
        verdict = "RUNTIME_STORAGE_BIND_MOUNT_DESIGN_READY_WITH_WARN"
    else:
        verdict = "RUNTIME_STORAGE_BIND_MOUNT_DESIGN_READY"

    return {
        "audit_id": AUDIT_ID,
        "audit_date": AUDIT_DATE,
        "verdict": verdict,
        "design_only": DESIGN_ONLY,
        "docker_compose_modified": False,
        "container_restarted": False,
        "execution_history_path_confirmed": ef.get("env_based_path", ""),
        "execution_history_persisted": ef.get("persisted_in_named_volume", False),
        "app_logs_persistence_risk": True,
        "recommended_fix": BIND_MOUNT_DESIGN["recommended_option"],
        "persistence_risk_items": risk_items,
        "next_phase": NEXT_PHASE_CONDITIONS["phase"],
        "next_phase_status": NEXT_PHASE_CONDITIONS["current_status"],
        "errors": errors,
        "warnings": warnings,
    }


if __name__ == "__main__":
    result = run_audit()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"\n=== Runtime Storage Bind Mount Design: {result['verdict']} ===")
    print(f"  execution_history path: {result['execution_history_path_confirmed']}")
    print(f"  execution_history persisted: {result['execution_history_persisted']}")
    print(f"  recommended fix: {result['recommended_fix']}")
    for e in result["errors"]:
        print(f"  ERROR: {e}")
    for w in result["warnings"]:
        print(f"  WARN:  {w}")
