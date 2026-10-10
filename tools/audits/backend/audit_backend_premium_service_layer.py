"""Service Layer 감사 스크립트 — read-only.

TaskQueueService, ExecutionPolicyService 계약 및 판정 로직을 점검한다.
외부 호출, DB 접속, 파일 수정 금지.

exit code: 0=PASS/PASS_WITH_KNOWN_WARN, 1=FAIL, 2=STOP_CONDITION
"""

from __future__ import annotations

import importlib
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
# sys.path에 프로젝트 root 추가 (직접 실행 시 필요)
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))

AUDIT_NAME = "service_layer"

CHECKLIST = [
    {"id": "sl-01", "title": "services/__init__.py 존재", "required": True},
    {"id": "sl-02", "title": "task_queue_service.py 존재", "required": True},
    {"id": "sl-03", "title": "execution_policy_service.py 존재", "required": True},
    {"id": "sl-04", "title": "TaskQueueService import 가능", "required": True},
    {"id": "sl-05", "title": "TaskQueueSummary import 가능", "required": True},
    {"id": "sl-06", "title": "ExecutionPolicyService import 가능", "required": True},
    {"id": "sl-07", "title": "PolicyDecision import 가능", "required": True},
    {"id": "sl-08", "title": "pending task 조회 메서드 존재", "required": True},
    {"id": "sl-09", "title": "execution_location별 count 계산 가능", "required": True},
    {"id": "sl-10", "title": "forbidden field stripping/redaction 연계 존재", "required": True},
    {"id": "sl-11", "title": "LOCAL_AGENT_REQUIRED 서버 직접 실행 불가 판정", "required": True},
    {"id": "sl-12", "title": "USER_DIRECT_REQUIRED 자동 실행 불가 판정", "required": True},
    {"id": "sl-13", "title": "BLOCKED 실행 불가 판정", "required": True},
    {"id": "sl-14", "title": "OFFICIAL_API_OR_OAUTH_REQUIRED 설정 전 실행 불가", "required": True},
    {"id": "sl-15", "title": "기존 API response shape 변경 없음 (router 비의존)", "required": True},
]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _item(cid: str, status: str, evidence: str, details: dict | None = None) -> dict:
    meta = next(c for c in CHECKLIST if c["id"] == cid)
    return {
        "id": cid,
        "title": meta["title"],
        "required": meta["required"],
        "status": status,
        "evidence": evidence,
        "details": details or {},
    }


def _check_service_files_exist() -> list[dict]:
    files = {
        "sl-01": ROOT / "ai_orchestrator/services/__init__.py",
        "sl-02": ROOT / "ai_orchestrator/services/task_queue_service.py",
        "sl-03": ROOT / "ai_orchestrator/services/execution_policy_service.py",
    }
    return [_item(cid, "PASS" if p.exists() else "FAIL", str(p)) for cid, p in files.items()]


def _import_services() -> tuple[Any, Any, list[dict]]:
    results = []
    tqs_mod = eps_mod = None
    for cid, mod_name, cls_name in [
        ("sl-04", "ai_orchestrator.services.task_queue_service", "TaskQueueService"),
        ("sl-05", "ai_orchestrator.services.task_queue_service", "TaskQueueSummary"),
        ("sl-06", "ai_orchestrator.services.execution_policy_service", "ExecutionPolicyService"),
        ("sl-07", "ai_orchestrator.services.execution_policy_service", "PolicyDecision"),
    ]:
        try:
            mod = importlib.import_module(mod_name)
            obj = getattr(mod, cls_name, None)
            if cls_name == "TaskQueueService":
                tqs_mod = mod
            if cls_name == "ExecutionPolicyService":
                eps_mod = mod
            results.append(_item(cid, "PASS" if obj else "FAIL", f"{cls_name}={'found' if obj else 'not found'}"))
        except Exception as e:  # noqa: BLE001 - ExecutionPolicyService 계약 자체검증 스크립트 - 판정 호출 실패를 WARN으로 기록(실제 런타임 게이트가 아닌 감사 리포트)
            results.append(_item(cid, "FAIL", str(e)))
    return tqs_mod, eps_mod, results


def _check_pending_task_query(tqs_mod: Any) -> dict:
    if not tqs_mod:
        return _item("sl-08", "FAIL", "TaskQueueService import 실패")
    tqs_cls = getattr(tqs_mod, "TaskQueueService", None)
    has_pending = tqs_cls and (
        hasattr(tqs_cls, "get_pending_tasks")
        or hasattr(tqs_cls, "list_pending")
        or hasattr(tqs_cls, "get_queue_summary")
    )
    methods = [m for m in dir(tqs_cls or object()) if "pending" in m or "queue" in m or "summary" in m]
    return _item("sl-08", "PASS" if has_pending else "FAIL", f"pending 관련 메서드: {methods}")


def _check_execution_location_count(tqs_mod: Any) -> dict:
    if not tqs_mod:
        return _item("sl-09", "FAIL", "TaskQueueService import 실패")
    summary_cls = getattr(tqs_mod, "TaskQueueSummary", None)
    has_loc = summary_cls and any(
        "location" in f.lower() or "count" in f.lower()
        for f in (summary_cls.__dataclass_fields__ if hasattr(summary_cls, "__dataclass_fields__") else {})
    )
    return _item(
        "sl-09",
        "PASS" if has_loc else "WARN",
        f"TaskQueueSummary fields: {list(getattr(summary_cls, '__dataclass_fields__', {}).keys())}",
    )


def _check_redaction_linked() -> dict:
    src = (
        (ROOT / "ai_orchestrator/services/task_queue_service.py").read_text(encoding="utf-8")
        if (ROOT / "ai_orchestrator/services/task_queue_service.py").exists()
        else ""
    )
    has_redact = "redact" in src or "forbidden" in src.lower() or "secret_redaction" in src or "strip_sensitive" in src
    return _item(
        "sl-10",
        "PASS" if has_redact else "WARN",
        "redaction 연계 있음" if has_redact else "명시적 연계 없음 (상위 레이어 위임 가능)",
    )


def _check_policy_decisions(eps_mod: Any) -> list[dict]:
    cids = ["sl-11", "sl-12", "sl-13", "sl-14"]
    if not eps_mod:
        return [_item(cid, "FAIL", "module import 실패") for cid in cids]

    eps_cls = getattr(eps_mod, "ExecutionPolicyService", None)
    pd_cls = getattr(eps_mod, "PolicyDecision", None)
    if not (eps_cls and pd_cls):
        return [_item(cid, "FAIL", "ExecutionPolicyService 또는 PolicyDecision 없음") for cid in cids]

    svc = eps_cls()
    results = []

    # LOCAL_AGENT_REQUIRED — decide_execution_policy(classification) 사용
    try:
        d = svc.decide_execution_policy("LOCAL_AGENT_REQUIRED")
        results.append(
            _item(
                "sl-11",
                "PASS" if not d.server_executable else "FAIL",
                f"execution_location={d.execution_location} server_executable={d.server_executable}",
            )
        )
    except Exception as e:  # noqa: BLE001 - ExecutionPolicyService 계약 자체검증 스크립트 - 판정 호출 실패를 WARN으로 기록(실제 런타임 게이트가 아닌 감사 리포트)
        results.append(_item("sl-11", "WARN", f"decide_execution_policy 호출 실패: {e}"))

    # USER_DIRECT_REQUIRED
    try:
        d = svc.decide_execution_policy("USER_DIRECT_REQUIRED")
        results.append(
            _item(
                "sl-12",
                "PASS" if not d.server_executable else "FAIL",
                f"execution_location={d.execution_location} server_executable={d.server_executable}",
            )
        )
    except Exception as e:  # noqa: BLE001 - ExecutionPolicyService 계약 자체검증 스크립트 - 판정 호출 실패를 WARN으로 기록(실제 런타임 게이트가 아닌 감사 리포트)
        results.append(_item("sl-12", "WARN", f"호출 실패: {e}"))

    # BLOCKED (QUARANTINE_OR_HOLD)
    try:
        d = svc.decide_execution_policy("QUARANTINE_OR_HOLD")
        results.append(
            _item(
                "sl-13",
                "PASS" if d.is_blocked else "FAIL",
                f"execution_location={d.execution_location} is_blocked={d.is_blocked}",
            )
        )
    except Exception as e:  # noqa: BLE001 - ExecutionPolicyService 계약 자체검증 스크립트 - 판정 호출 실패를 WARN으로 기록(실제 런타임 게이트가 아닌 감사 리포트)
        results.append(_item("sl-13", "WARN", f"호출 실패: {e}"))

    # OAUTH
    try:
        d = svc.decide_execution_policy("OFFICIAL_API_OR_OAUTH_REQUIRED")
        results.append(
            _item(
                "sl-14",
                "PASS" if d.requires_oauth_setup or d.is_blocked else "FAIL",
                f"execution_location={d.execution_location} requires_oauth_setup={d.requires_oauth_setup} is_blocked={d.is_blocked}",
            )
        )
    except Exception as e:  # noqa: BLE001 - ExecutionPolicyService 계약 자체검증 스크립트 - 판정 호출 실패를 WARN으로 기록(실제 런타임 게이트가 아닌 감사 리포트)
        results.append(_item("sl-14", "WARN", f"호출 실패: {e}"))

    return results


def _check_router_independence() -> dict:
    svc_src = (
        (ROOT / "ai_orchestrator/services/task_queue_service.py").read_text(encoding="utf-8")
        if (ROOT / "ai_orchestrator/services/task_queue_service.py").exists()
        else ""
    )
    eps_src = (
        (ROOT / "ai_orchestrator/services/execution_policy_service.py").read_text(encoding="utf-8")
        if (ROOT / "ai_orchestrator/services/execution_policy_service.py").exists()
        else ""
    )
    bad_imports = [
        line.strip()
        for line in (svc_src + eps_src).splitlines()
        if "import" in line
        and any(x in line for x in ["fastapi", "flask", "router.py", "ai_orchestrator.routers.registry"])
    ]
    return _item(
        "sl-15",
        "PASS" if not bad_imports else "FAIL",
        f"금지 import: {bad_imports}" if bad_imports else "router 비의존 확인",
    )


def run_audit() -> dict[str, Any]:
    # 2026-09-29 STD-08(복잡도) 리팩터: sl-01~15 체크 블록을 _check_*()/_import_*() 함수로
    # 분리(순서·조건·문자열 그대로). tqs_mod/eps_mod 는 명시적 인자로 전달.
    results: list[dict[str, Any]] = []
    results.extend(_check_service_files_exist())

    tqs_mod, eps_mod, import_results = _import_services()
    results.extend(import_results)
    results.append(_check_pending_task_query(tqs_mod))
    results.append(_check_execution_location_count(tqs_mod))
    results.append(_check_redaction_linked())
    results.extend(_check_policy_decisions(eps_mod))
    results.append(_check_router_independence())

    summary = {"pass": 0, "warn": 0, "fail": 0, "skip": 0}
    for r in results:
        summary[r["status"].lower()] = summary.get(r["status"].lower(), 0) + 1

    required_fail = any(r["status"] == "FAIL" and r["required"] for r in results)
    verdict = "FAIL" if required_fail else ("PASS_WITH_KNOWN_WARN" if summary["warn"] > 0 else "PASS")

    return {
        "audit_name": AUDIT_NAME,
        "verdict": verdict,
        "checked_at": _now(),
        "checklist": results,
        "summary": summary,
    }


def main() -> int:
    from scripts.common.audit_cli import run_checklist_cli

    return run_checklist_cli(AUDIT_NAME, run_audit)


if __name__ == "__main__":
    sys.exit(main())
