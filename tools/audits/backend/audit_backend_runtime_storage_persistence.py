"""
Backend Runtime Storage Persistence Audit
ASSISTANT_BACKEND_RUNTIME_STORAGE_PERSISTENCE_AUDIT_01

컨테이너 재생성 시 사라지는 파일 vs 반드시 보존돼야 하는 파일 분류.
실제 docker-compose 수정 / volume 변경 / 컨테이너 재시작 / 서버 반영 전면 금지.
파일 경로·존재 여부·크기·민감도 확인만 수행.
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

AUDIT_ID = "BACKEND_RUNTIME_STORAGE_PERSISTENCE_AUDIT"
AUDIT_DATE = "2026-05-18"

# ── 운영 안전 플래그 ─────────────────────────────────────────────────────────
SERVER_APPLY_ALLOWED = False
DOCKER_MODIFICATION_ALLOWED = False
CONTAINER_RESTART_ALLOWED = False
SECRET_VALUE_OUTPUT_ALLOWED = False
READ_ONLY_AUDIT = True

# ── 분류 코드 ─────────────────────────────────────────────────────────────────
EPHEMERAL_SECURITY_SENSITIVE = "EPHEMERAL_SECURITY_SENSITIVE"
PERSISTENT_AUDIT_REQUIRED = "PERSISTENT_AUDIT_REQUIRED"
PERSISTENT_OPERATION_REQUIRED = "PERSISTENT_OPERATION_REQUIRED"
RUNTIME_CACHE_DISPOSABLE = "RUNTIME_CACHE_DISPOSABLE"
FORBIDDEN_PLAINTEXT_SECRET = "FORBIDDEN_PLAINTEXT_SECRET"

# ── docker mount 현황 (컨테이너 inspect 결과 기준) ───────────────────────────
DOCKER_MOUNTS_SUMMARY: dict[str, Any] = {
    "container": "haehan-ai-orchestrator-api",
    "image": "haehan-ai-orchestrator-api:local",
    "source_type": "baked_in_image",
    "note": "Python 소스(/app/ai_orchestrator/)는 이미지에 baked-in. git pull 후 반드시 docker compose build 필요.",
    "mounts": [
        {
            "type": "bind",
            "source": f"{SERVER['orchestrator_root']}/secrets/api",
            "destination": "/run/secrets/api",
            "mode": "ro",
            "persisted_on_host": True,
            "purpose": "secrets (read-only)",
            "contains_secret": True,
            "note": "secret 파일 read-only bind — 원문 출력 금지",
        },
        {
            "type": "volume",
            "source": "haehan-ai-orchestrator-api-storage",
            "destination": "/app/ai_orchestrator/storage",
            "mode": "rw",
            "persisted_on_host": True,
            "purpose": "runtime 영속 저장소 (approval tokens, audit logs, task states)",
            "contains_secret": False,
            "note": "named volume — 컨테이너 재생성에도 보존됨",
        },
    ],
    "not_mounted": [
        {
            "path": "/app/logs",
            "persisted_on_host": False,
            "note": "컨테이너 내부 레이어. 재생성 시 초기화.",
        },
        {
            "path": "/app/data",
            "persisted_on_host": False,
            "note": "컨테이너 내부 레이어. 재생성 시 초기화.",
        },
    ],
}

# ── 파일별 분류 matrix ────────────────────────────────────────────────────────
STORAGE_CLASSIFICATION = {
    "approval_tokens_jsonl": {
        "path_container": "/app/ai_orchestrator/storage/approval_tokens.jsonl",
        "path_host": "N/A (named volume)",
        "exists_container": True,
        "bind_mounted": True,
        "persisted_across_rebuild": True,
        "current_lines": 1,
        "current_size_approx": "442 bytes",
        "current_classification": EPHEMERAL_SECURITY_SENSITIVE,
        "sensitivity": "HIGH",
        "contains_secret_risk": True,
        "should_persist": False,
        "should_be_ephemeral": True,
        "recommended_storage": "named_volume (현재) — 단기 TTL 30분 후 자동 만료가 설계 의도. volume 보존은 감사 목적으로 허용 가능하나 원문 secret 저장 금지 확인 필요.",
        "action_required": "REVIEW_TTL_AND_TOKEN_CONTENT_IN_NEXT_PHASE",
        "verdict": "ACCEPTABLE_WITH_TTL_ENFORCEMENT",
        "note": "토큰 ID·만료시각 저장은 허용. 토큰 secret 값 평문 저장 여부는 다음 공정에서 확인.",
    },
    "approval_tokens_json": {
        "path_container": "/app/ai_orchestrator/storage/approval_tokens.json",
        "exists_container": True,
        "bind_mounted": True,
        "persisted_across_rebuild": True,
        "current_size_approx": "1.4 KB",
        "current_classification": EPHEMERAL_SECURITY_SENSITIVE,
        "sensitivity": "HIGH",
        "contains_secret_risk": True,
        "should_persist": False,
        "should_be_ephemeral": True,
        "recommended_storage": "legacy 파일로 보임. 내용 확인 없이 민감도 HIGH 처리.",
        "action_required": "VERIFY_CONTENT_TYPE_IN_NEXT_PHASE",
        "verdict": "FLAGGED_FOR_REVIEW",
    },
    "audit_logs_jsonl": {
        "path_container": "/app/ai_orchestrator/storage/audit_logs.jsonl",
        "exists_container": True,
        "bind_mounted": True,
        "persisted_across_rebuild": True,
        "current_lines": 1320,
        "current_size_approx": "448 KB",
        "current_classification": PERSISTENT_AUDIT_REQUIRED,
        "sensitivity": "MEDIUM",
        "contains_secret_risk": False,
        "should_persist": True,
        "should_be_ephemeral": False,
        "recommended_storage": "named_volume (현재) — 올바른 위치. 감사 목적 파일은 재생성에도 보존되어야 함.",
        "action_required": "NONE",
        "verdict": "CORRECTLY_PERSISTED",
    },
    "app_log": {
        "path_container": "/app/ai_orchestrator/storage/app.log",
        "exists_container": True,
        "bind_mounted": True,
        "persisted_across_rebuild": True,
        "current_size_approx": "300 KB",
        "current_classification": PERSISTENT_AUDIT_REQUIRED,
        "sensitivity": "MEDIUM",
        "contains_secret_risk": False,
        "should_persist": True,
        "should_be_ephemeral": False,
        "recommended_storage": "named_volume (현재) — 올바른 위치.",
        "action_required": "NONE",
        "verdict": "CORRECTLY_PERSISTED",
    },
    "task_states_jsonl": {
        "path_container": "/app/ai_orchestrator/storage/task_states.jsonl",
        "exists_container": True,
        "bind_mounted": True,
        "persisted_across_rebuild": True,
        "current_lines": 18,
        "current_size_approx": "8.4 KB",
        "current_classification": PERSISTENT_OPERATION_REQUIRED,
        "sensitivity": "LOW",
        "contains_secret_risk": False,
        "should_persist": True,
        "should_be_ephemeral": False,
        "recommended_storage": "named_volume (현재) — 올바른 위치.",
        "action_required": "NONE",
        "verdict": "CORRECTLY_PERSISTED",
    },
    "logs_audit_jsonl": {
        "path_container": "/app/logs/audit.jsonl",
        "exists_container": True,
        "bind_mounted": False,
        "persisted_across_rebuild": False,
        "current_lines": 4,
        "current_size_approx": "955 bytes",
        "current_classification": PERSISTENT_AUDIT_REQUIRED,
        "sensitivity": "MEDIUM",
        "contains_secret_risk": False,
        "should_persist": True,
        "should_be_ephemeral": False,
        "recommended_storage": "/app/logs 는 bind mount 없음 — 재생성 시 소실 위험. 후속 공정에서 bind mount 추가 권장.",
        "action_required": "ADD_BIND_MOUNT_IN_NEXT_PHASE",
        "verdict": "PERSISTENCE_RISK",
    },
    "logs_orchestrator_log": {
        "path_container": "/app/logs/orchestrator.log",
        "exists_container": True,
        "bind_mounted": False,
        "persisted_across_rebuild": False,
        "current_lines": 44,
        "current_size_approx": "6.5 KB",
        "current_classification": PERSISTENT_OPERATION_REQUIRED,
        "sensitivity": "LOW",
        "contains_secret_risk": False,
        "should_persist": True,
        "should_be_ephemeral": False,
        "recommended_storage": "/app/logs bind mount 없음 — 소실 위험.",
        "action_required": "ADD_BIND_MOUNT_IN_NEXT_PHASE",
        "verdict": "PERSISTENCE_RISK",
    },
    "logs_orchestrator_error_log": {
        "path_container": "/app/logs/orchestrator.error.log",
        "exists_container": True,
        "bind_mounted": False,
        "persisted_across_rebuild": False,
        "current_size_approx": "0 bytes (empty)",
        "current_classification": PERSISTENT_OPERATION_REQUIRED,
        "sensitivity": "LOW",
        "contains_secret_risk": False,
        "should_persist": True,
        "should_be_ephemeral": False,
        "recommended_storage": "현재 비어있으나 /app/logs bind mount 추가 필요.",
        "action_required": "ADD_BIND_MOUNT_IN_NEXT_PHASE",
        "verdict": "PERSISTENCE_RISK",
    },
    "chrome_ui_monitor_state": {
        "path_local": "scripts/archive/data/chrome_ui_monitor_state.json",
        "path_container": "N/A (로컬 런타임 상태 파일)",
        "exists_container": False,
        "bind_mounted": False,
        "persisted_across_rebuild": False,
        "current_classification": RUNTIME_CACHE_DISPOSABLE,
        "sensitivity": "LOW",
        "contains_secret_risk": False,
        "should_persist": False,
        "should_be_ephemeral": True,
        "recommended_storage": "git tracking 불필요. .gitignore 추가 또는 archive/data/ 유지.",
        "action_required": "CONFIRM_GITIGNORE_OR_KNOWN_BASELINE",
        "verdict": "DISPOSABLE_CONFIRMED",
    },
    "execution_history_jsonl": {
        "path_container": "N/A (현재 미존재 — 재생성 후 초기화)",
        "exists_container": False,
        "bind_mounted": False,
        "persisted_across_rebuild": False,
        "current_classification": PERSISTENT_OPERATION_REQUIRED,
        "sensitivity": "LOW",
        "contains_secret_risk": False,
        "should_persist": True,
        "should_be_ephemeral": False,
        "recommended_storage": "현재 미존재. 생성 시 storage/ named volume 경로에 저장되도록 코드 확인 필요.",
        "action_required": "VERIFY_WRITE_PATH_IN_NEXT_PHASE",
        "verdict": "MISSING_VERIFY_WRITE_PATH",
    },
}

# ── 후속 bind mount 설계 권장안 ───────────────────────────────────────────────
RECOMMENDED_BIND_MOUNT_PLAN: dict[str, Any] = {
    "status": "DESIGN_ONLY",
    "implementation_allowed_this_phase": False,
    "current_protected": [
        "/app/ai_orchestrator/storage → named volume haehan-ai-orchestrator-api-storage (올바름)",
        "/run/secrets/api → host secrets/api (read-only, 올바름)",
    ],
    "recommended_additions": [
        {
            "host": f"{SERVER['orchestrator_root']}/data/logs",
            "container": "/app/logs",
            "mode": "rw",
            "reason": "/app/logs (orchestrator.log, audit.jsonl) 현재 미보존 — 재생성 시 소실",
        },
    ],
    "not_recommended": [
        "/app/ai_orchestrator/storage/approval_tokens.jsonl 별도 분리 — 현재 named volume으로 충분",
    ],
    "next_phase": "RUNTIME_STORAGE_BIND_MOUNT_DESIGN_01",
    "approval_required": "docker-compose.yml 수정 및 서버 반영 시 대표 명시 승인 필요",
}

# ── 보안 판정 ─────────────────────────────────────────────────────────────────
SECURITY_FINDINGS = {
    "plaintext_secret_detected": False,
    "token_value_output": False,
    "cookie_value_output": False,
    "password_value_output": False,
    "flagged_for_review": ["approval_tokens_jsonl", "approval_tokens_json"],
    "reason": "토큰 파일에 secret 값 평문 저장 여부는 내용 확인 없이 이번 공정에서 단정 불가. 다음 공정에서 token record 구조 확인 필요.",
}


def _check_safety_flags() -> list[str]:
    """1. 운영 안전 플래그."""
    errors = []
    if SERVER_APPLY_ALLOWED:
        errors.append("SERVER_APPLY_ALLOWED must be False")
    if DOCKER_MODIFICATION_ALLOWED:
        errors.append("DOCKER_MODIFICATION_ALLOWED must be False")
    if CONTAINER_RESTART_ALLOWED:
        errors.append("CONTAINER_RESTART_ALLOWED must be False")
    if SECRET_VALUE_OUTPUT_ALLOWED:
        errors.append("SECRET_VALUE_OUTPUT_ALLOWED must be False")
    if not READ_ONLY_AUDIT:
        errors.append("READ_ONLY_AUDIT must be True")
    return errors


def _check_no_plaintext_secret_output() -> list[str]:
    """2. 보안 — 평문 secret 출력 없음."""
    errors = []
    if SECURITY_FINDINGS["plaintext_secret_detected"]:
        errors.append("FORBIDDEN: 평문 secret 감지됨 — 즉시 STOP")
    if SECURITY_FINDINGS["token_value_output"]:
        errors.append("FORBIDDEN: token 원문 출력됨")
    if SECURITY_FINDINGS["cookie_value_output"]:
        errors.append("FORBIDDEN: cookie 원문 출력됨")
    return errors


def _check_required_classification_keys() -> list[str]:
    """3. 필수 분류 항목 존재."""
    required_keys = [
        "approval_tokens_jsonl",
        "execution_history_jsonl",
        "audit_logs_jsonl",
        "chrome_ui_monitor_state",
        "task_states_jsonl",
    ]
    return [f"분류 누락: {k}" for k in required_keys if k not in STORAGE_CLASSIFICATION]


def _check_classification_accuracy() -> list[str]:
    """4. 분류 정확성."""
    sc = STORAGE_CLASSIFICATION
    errors = []
    if sc.get("audit_logs_jsonl", {}).get("current_classification") != PERSISTENT_AUDIT_REQUIRED:
        errors.append("audit_logs는 PERSISTENT_AUDIT_REQUIRED여야 함")
    if sc.get("task_states_jsonl", {}).get("current_classification") != PERSISTENT_OPERATION_REQUIRED:
        errors.append("task_states는 PERSISTENT_OPERATION_REQUIRED여야 함")
    if sc.get("chrome_ui_monitor_state", {}).get("current_classification") != RUNTIME_CACHE_DISPOSABLE:
        errors.append("chrome_ui_monitor_state는 RUNTIME_CACHE_DISPOSABLE이어야 함")
    if sc.get("approval_tokens_jsonl", {}).get("current_classification") != EPHEMERAL_SECURITY_SENSITIVE:
        errors.append("approval_tokens_jsonl는 EPHEMERAL_SECURITY_SENSITIVE여야 함")
    if sc.get("execution_history_jsonl", {}).get("current_classification") != PERSISTENT_OPERATION_REQUIRED:
        errors.append("execution_history는 PERSISTENT_OPERATION_REQUIRED여야 함")
    return errors


def _check_persistence_risks() -> list[str]:
    """5. persistence_risk 항목 — warning."""
    return [
        f"PERSISTENCE_RISK: {key} → {item.get('recommended_storage', '')}"
        for key, item in STORAGE_CLASSIFICATION.items()
        if item.get("verdict") == "PERSISTENCE_RISK"
    ]


def _check_docker_mounts_and_followup() -> list[str]:
    """6. docker mount 요약 존재, 7. 후속 설계 존재."""
    errors = []
    if not DOCKER_MOUNTS_SUMMARY.get("mounts"):
        errors.append("docker mount 요약 없음")
    if not RECOMMENDED_BIND_MOUNT_PLAN.get("next_phase"):
        errors.append("후속 공정 정의 없음")
    if RECOMMENDED_BIND_MOUNT_PLAN.get("implementation_allowed_this_phase"):
        errors.append("이번 공정에서 docker-compose 구현 금지")
    return errors


def run_audit() -> dict:
    # 2026-09-29 STD-08(복잡도) 리팩터: 원본 주석의 1.~7. 번호 섹션을 _check_*() 함수로
    # 분리(순서·조건·문자열 그대로) — #48/#49/#51 과 같은 계열.
    errors: list[str] = []
    warnings: list[str] = []
    errors.extend(_check_safety_flags())
    errors.extend(_check_no_plaintext_secret_output())
    errors.extend(_check_required_classification_keys())
    errors.extend(_check_classification_accuracy())
    warnings.extend(_check_persistence_risks())
    errors.extend(_check_docker_mounts_and_followup())

    if errors:
        verdict = "RUNTIME_STORAGE_PERSISTENCE_AUDIT_BLOCKED"
    elif warnings:
        verdict = "RUNTIME_STORAGE_PERSISTENCE_AUDIT_WITH_WARN"
    else:
        verdict = "RUNTIME_STORAGE_PERSISTENCE_AUDIT_READY"

    # 분류 통계
    classification_counts: dict[Any, Any] = {}
    for item in STORAGE_CLASSIFICATION.values():
        c = item.get("current_classification", "UNKNOWN")
        classification_counts[c] = classification_counts.get(c, 0) + 1

    return {
        "audit_id": AUDIT_ID,
        "audit_date": AUDIT_DATE,
        "verdict": verdict,
        "read_only_audit": READ_ONLY_AUDIT,
        "docker_compose_modified": False,
        "container_restarted": False,
        "secret_value_output": False,
        "docker_mounts": {
            "bind_count": len([m for m in DOCKER_MOUNTS_SUMMARY["mounts"] if m["type"] == "bind"]),
            "volume_count": len([m for m in DOCKER_MOUNTS_SUMMARY["mounts"] if m["type"] == "volume"]),
            "storage_persisted": True,
            "logs_not_persisted": True,
        },
        "classification_counts": classification_counts,
        "persistence_risks": [k for k, v in STORAGE_CLASSIFICATION.items() if v.get("verdict") == "PERSISTENCE_RISK"],
        "correctly_persisted": [
            k for k, v in STORAGE_CLASSIFICATION.items() if v.get("verdict") == "CORRECTLY_PERSISTED"
        ],
        "flagged_for_review": SECURITY_FINDINGS["flagged_for_review"],
        "recommended_bind_mount_additions": len(RECOMMENDED_BIND_MOUNT_PLAN["recommended_additions"]),
        "next_phase": RECOMMENDED_BIND_MOUNT_PLAN["next_phase"],
        "errors": errors,
        "warnings": warnings,
    }


if __name__ == "__main__":
    result = run_audit()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"\n=== Runtime Storage Persistence Audit: {result['verdict']} ===")
    for e in result["errors"]:
        print(f"  ERROR: {e}")
    for w in result["warnings"]:
        print(f"  WARN:  {w}")
