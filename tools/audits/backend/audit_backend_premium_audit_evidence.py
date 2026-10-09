"""Audit/Evidence 감사 스크립트 — read-only.

표준 모델 11개 필드, adapter, redaction을 점검한다.
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

AUDIT_NAME = "audit_evidence"

STANDARD_AUDIT_EVENT_FIELDS = {
    "event_id",
    "event_type",
    "task_id",
    "actor",
    "status",
    "timestamp",
    "summary",
    "safety_verdict",
    "artifact_refs",
    "metadata",
    "redaction_applied",
}

CHECKLIST = [
    {"id": "ae-01", "title": "audit_evidence 패키지 존재", "required": True},
    {"id": "ae-02", "title": "models.py 존재", "required": True},
    {"id": "ae-03", "title": "adapters.py 존재", "required": True},
    {"id": "ae-04", "title": "StandardAuditEvent import 가능", "required": True},
    {"id": "ae-05", "title": "ExecutionAttempt import 가능", "required": True},
    {"id": "ae-06", "title": "SafetyVerdict import 가능", "required": True},
    {"id": "ae-07", "title": "ExternalAppHandoff import 가능", "required": True},
    {"id": "ae-08", "title": "ArtifactEvidenceRef import 가능", "required": True},
    {"id": "ae-09", "title": "StandardAuditEvent 표준 필드 11개", "required": True},
    {"id": "ae-10", "title": "ExecutionAttempt: execution_location/policy_decision/status", "required": True},
    {"id": "ae-11", "title": "SafetyVerdict: block/hold/user_direct/oauth_required", "required": True},
    {"id": "ae-12", "title": "ExternalAppHandoff: bridge_id/handoff_mode/status", "required": True},
    {"id": "ae-13", "title": "ArtifactEvidenceRef: storage_ref만 참조", "required": True},
    {"id": "ae-14", "title": "to_safe_dict redaction 적용", "required": True},
    {"id": "ae-15", "title": "nested metadata redaction 적용", "required": True},
    {"id": "ae-16", "title": "audit_event_dict_to_standard adapter 존재", "required": True},
    {"id": "ae-17", "title": "policy_decision_to_safety_verdict adapter 존재", "required": True},
    {"id": "ae-18", "title": "evidence_dict_to_artifact_ref adapter 존재", "required": True},
    {"id": "ae-19", "title": "build_external_app_handoff adapter 존재", "required": True},
    {"id": "ae-20", "title": "기존 audit_logger 대체 없음 (adapter만 연결)", "required": True},
]

FORBIDDEN_KEYS = {
    "password",
    "token",
    "session",
    "cookie",
    "secret",
    "private_key",
    "access_token",
    "refresh_token",
    "auth_token",
    "credential",
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _check_forbidden(d: dict) -> list[str]:
    found = []
    for k, v in d.items():
        if k.lower() in FORBIDDEN_KEYS:
            found.append(k)
        if isinstance(v, dict):
            found.extend(_check_forbidden(v))
    return found


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


def _check_files_exist() -> list[dict]:
    files = {
        "ae-01": ROOT / "ai_orchestrator/audit_evidence/__init__.py",
        "ae-02": ROOT / "ai_orchestrator/audit_evidence/models.py",
        "ae-03": ROOT / "ai_orchestrator/audit_evidence/adapters.py",
    }
    return [_item(cid, "PASS" if p.exists() else "FAIL", str(p)) for cid, p in files.items()]


def _import_models_module() -> tuple[Any, list[dict]]:
    try:
        models_mod = importlib.import_module("ai_orchestrator.audit_evidence.models")
    except Exception as e:  # noqa: BLE001 - 감사 대상 모듈 import 실패시 해당 체크항목들을 FAIL로 명시 기록하는 감사 스크립트 — 성공 위장 없음, 읽기전용
        return None, [_item(cid, "FAIL", f"import 실패: {e}") for cid in ["ae-04", "ae-05", "ae-06", "ae-07", "ae-08"]]

    results = []
    for cid, name in [
        ("ae-04", "StandardAuditEvent"),
        ("ae-05", "ExecutionAttempt"),
        ("ae-06", "SafetyVerdict"),
        ("ae-07", "ExternalAppHandoff"),
        ("ae-08", "ArtifactEvidenceRef"),
    ]:
        obj = getattr(models_mod, name, None)
        results.append(_item(cid, "PASS" if obj else "FAIL", f"{name}={'found' if obj else 'not found'}"))
    return models_mod, results


def _check_standard_audit_event_fields(models_mod: Any) -> dict:
    sae = getattr(models_mod, "StandardAuditEvent", None) if models_mod else None
    if not sae:
        return _item("ae-09", "FAIL", "StandardAuditEvent 없음")
    ev = sae.create(event_type="test", task_id="t", actor="a", status="ok", summary="s")
    safe = ev.to_safe_dict()
    actual_keys = set(safe.keys())
    missing = STANDARD_AUDIT_EVENT_FIELDS - actual_keys
    ok = len(actual_keys) == 11 and not missing
    return _item(
        "ae-09",
        "PASS" if ok else "FAIL",
        f"필드={len(actual_keys)}/11, missing={missing}",
        {"fields": sorted(actual_keys)},
    )


def _check_execution_attempt_fields(models_mod: Any) -> dict:
    ea_cls = getattr(models_mod, "ExecutionAttempt", None) if models_mod else None
    if not ea_cls:
        return _item("ae-10", "FAIL", "ExecutionAttempt 없음")
    ea = ea_cls.create(
        task_id="t",
        execution_location="server",
        risk_level="low",
        status="ok",
        policy_decision="allow",
        safe_to_execute_on_server=True,
    )
    d = ea.to_safe_dict()
    has_fields = all(f in d for f in ["execution_location", "policy_decision", "status"])
    return _item(
        "ae-10", "PASS" if has_fields else "FAIL", f"필드 확인: execution_location={'execution_location' in d}"
    )


def _check_safety_verdict_fields(models_mod: Any) -> dict:
    sv_cls = getattr(models_mod, "SafetyVerdict", None) if models_mod else None
    if not sv_cls:
        return _item("ae-11", "FAIL", "SafetyVerdict 없음")
    sv = sv_cls.create(
        task_id="t",
        policy_id="p",
        decision="block",
        reason="차단",
        required_execution_location="server",
        blocked=True,
        requires_user_direct=True,
        requires_oauth_setup=True,
    )
    d = sv.to_safe_dict()
    has_fields = all(f in d for f in ["blocked", "requires_user_direct", "requires_oauth_setup"])
    return _item(
        "ae-11",
        "PASS" if has_fields else "FAIL",
        f"blocked={d.get('blocked')}, user_direct={d.get('requires_user_direct')}",
    )


def _check_external_app_handoff_fields(models_mod: Any) -> dict:
    hf_cls = getattr(models_mod, "ExternalAppHandoff", None) if models_mod else None
    if not hf_cls:
        return _item("ae-12", "FAIL", "ExternalAppHandoff 없음")
    hf = hf_cls.create(
        task_id="t",
        bridge_id="b",
        app_type="CAD",
        handoff_mode="file_drop",
        status="handoff_recorded",
        approval_required=True,
        user_direct_required=False,
    )
    d = hf.to_safe_dict()
    has_fields = all(f in d for f in ["bridge_id", "handoff_mode", "status"])
    return _item("ae-12", "PASS" if has_fields else "FAIL", f"bridge_id={d.get('bridge_id')}, status={d.get('status')}")


def _check_artifact_evidence_ref(models_mod: Any) -> dict:
    ar_cls = getattr(models_mod, "ArtifactEvidenceRef", None) if models_mod else None
    if not ar_cls:
        return _item("ae-13", "FAIL", "ArtifactEvidenceRef 없음")
    ar = ar_cls.create(
        artifact_type="log", content_type="text/plain", storage_ref="/tmp/x", safe_name="x", source_task_id="t"
    )
    d = ar.to_safe_dict()
    no_binary = "file_content" not in d and "file_bytes" not in d and "base64" not in d
    has_ref = "storage_ref" in d
    return _item(
        "ae-13", "PASS" if (no_binary and has_ref) else "FAIL", f"storage_ref={has_ref}, 바이너리 없음={no_binary}"
    )


def _check_redaction(models_mod: Any) -> tuple[dict, dict]:
    sae = getattr(models_mod, "StandardAuditEvent", None) if models_mod else None
    if not sae:
        return _item("ae-14", "FAIL", "StandardAuditEvent 없음"), _item("ae-15", "FAIL", "StandardAuditEvent 없음")
    ev = sae.create(
        event_type="t",
        task_id="t",
        actor="a",
        status="ok",
        summary="s",
        metadata={"password": "FAKE", "inner": {"token": "FAKE_TOKEN"}},
    )
    d = ev.to_safe_dict()
    forbidden = _check_forbidden(d)
    ae14 = _item(
        "ae-14", "PASS" if not forbidden else "FAIL", f"금지 필드: {forbidden}" if forbidden else "redaction 정상"
    )
    nested_ok = "token" not in d.get("metadata", {}).get("inner", {})
    ae15 = _item("ae-15", "PASS" if nested_ok else "FAIL", f"nested token 제거={'없음' if nested_ok else '남아있음'}")
    return ae14, ae15


def _import_adapters_module() -> tuple[Any, list[dict]]:
    try:
        adapter_mod = importlib.import_module("ai_orchestrator.audit_evidence.adapters")
    except Exception as e:  # noqa: BLE001 - 감사 대상 모듈 import 실패시 해당 체크항목들을 FAIL로 명시 기록하는 감사 스크립트 — 성공 위장 없음, 읽기전용
        return None, [_item(cid, "FAIL", f"import 실패: {e}") for cid in ["ae-16", "ae-17", "ae-18", "ae-19"]]

    results = []
    for cid, fn_name in [
        ("ae-16", "audit_event_dict_to_standard"),
        ("ae-17", "policy_decision_to_safety_verdict"),
        ("ae-18", "evidence_dict_to_artifact_ref"),
        ("ae-19", "build_external_app_handoff"),
    ]:
        fn = getattr(adapter_mod, fn_name, None)
        results.append(_item(cid, "PASS" if fn else "FAIL", f"{fn_name}={'found' if fn else 'not found'}"))
    return adapter_mod, results


def _check_audit_logger_not_replaced() -> dict:
    adapters_src = (
        (ROOT / "ai_orchestrator/audit_evidence/adapters.py").read_text(encoding="utf-8")
        if (ROOT / "ai_orchestrator/audit_evidence/adapters.py").exists()
        else ""
    )
    replaces_logger = "audit_logger" in adapters_src and "def log_event" in adapters_src
    return _item(
        "ae-20",
        "PASS" if not replaces_logger else "FAIL",
        "audit_logger 대체 없음 확인" if not replaces_logger else "audit_logger 재정의 감지",
    )


def run_audit() -> dict[str, Any]:
    # 2026-09-29 STD-08(복잡도) 리팩터: ae-01~20 체크 블록을 _check_*()/_import_*() 함수로
    # 분리(순서·조건·문자열 그대로). models_mod/adapter_mod 는 명시적으로 인자로 넘긴다.
    results: list[dict[str, Any]] = []
    results.extend(_check_files_exist())

    models_mod, model_import_results = _import_models_module()
    results.extend(model_import_results)
    if models_mod:
        results.append(_check_standard_audit_event_fields(models_mod))
        results.append(_check_execution_attempt_fields(models_mod))
        results.append(_check_safety_verdict_fields(models_mod))
        results.append(_check_external_app_handoff_fields(models_mod))
        results.append(_check_artifact_evidence_ref(models_mod))
        results.extend(_check_redaction(models_mod))

    _adapter_mod, adapter_import_results = _import_adapters_module()
    results.extend(adapter_import_results)

    results.append(_check_audit_logger_not_replaced())

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
