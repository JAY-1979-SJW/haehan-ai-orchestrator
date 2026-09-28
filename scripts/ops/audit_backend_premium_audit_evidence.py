"""Audit/Evidence 감사 스크립트 — read-only.

표준 모델 11개 필드, adapter, redaction을 점검한다.
외부 호출, DB 접속, 파일 수정 금지.

exit code: 0=PASS/PASS_WITH_KNOWN_WARN, 1=FAIL, 2=STOP_CONDITION
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
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


def run_audit() -> dict[str, Any]:
    results: list[dict[str, Any]] = []

    def item(cid: str, status: str, evidence: str, details: dict | None = None) -> dict:
        meta = next(c for c in CHECKLIST if c["id"] == cid)
        return {
            "id": cid,
            "title": meta["title"],
            "required": meta["required"],
            "status": status,
            "evidence": evidence,
            "details": details or {},
        }

    # ae-01~03: 파일 존재
    files = {
        "ae-01": ROOT / "ai_orchestrator/audit_evidence/__init__.py",
        "ae-02": ROOT / "ai_orchestrator/audit_evidence/models.py",
        "ae-03": ROOT / "ai_orchestrator/audit_evidence/adapters.py",
    }
    for cid, p in files.items():
        results.append(item(cid, "PASS" if p.exists() else "FAIL", str(p)))

    # ae-04~08: import
    models_mod = None
    try:
        models_mod = importlib.import_module("ai_orchestrator.audit_evidence.models")
    except Exception as e:  # noqa: BLE001 - 감사 대상 모듈 import 실패시 해당 체크항목들을 FAIL로 명시 기록하는 감사 스크립트 — 성공 위장 없음, 읽기전용
        for cid in ["ae-04", "ae-05", "ae-06", "ae-07", "ae-08"]:
            results.append(item(cid, "FAIL", f"import 실패: {e}"))

    if models_mod:
        for cid, name in [
            ("ae-04", "StandardAuditEvent"),
            ("ae-05", "ExecutionAttempt"),
            ("ae-06", "SafetyVerdict"),
            ("ae-07", "ExternalAppHandoff"),
            ("ae-08", "ArtifactEvidenceRef"),
        ]:
            obj = getattr(models_mod, name, None)
            results.append(item(cid, "PASS" if obj else "FAIL", f"{name}={'found' if obj else 'not found'}"))

    # ae-09: StandardAuditEvent 필드 11개
    if models_mod:
        sae = getattr(models_mod, "StandardAuditEvent", None)
        if sae:
            ev = sae.create(event_type="test", task_id="t", actor="a", status="ok", summary="s")
            safe = ev.to_safe_dict()
            actual_keys = set(safe.keys())
            missing = STANDARD_AUDIT_EVENT_FIELDS - actual_keys
            ok = len(actual_keys) == 11 and not missing
            results.append(
                item(
                    "ae-09",
                    "PASS" if ok else "FAIL",
                    f"필드={len(actual_keys)}/11, missing={missing}",
                    {"fields": sorted(actual_keys)},
                )
            )
        else:
            results.append(item("ae-09", "FAIL", "StandardAuditEvent 없음"))

    # ae-10: ExecutionAttempt 필드
    if models_mod:
        ea_cls = getattr(models_mod, "ExecutionAttempt", None)
        if ea_cls:
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
            results.append(
                item(
                    "ae-10",
                    "PASS" if has_fields else "FAIL",
                    f"필드 확인: execution_location={'execution_location' in d}",
                )
            )
        else:
            results.append(item("ae-10", "FAIL", "ExecutionAttempt 없음"))

    # ae-11: SafetyVerdict 필드
    if models_mod:
        sv_cls = getattr(models_mod, "SafetyVerdict", None)
        if sv_cls:
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
            results.append(
                item(
                    "ae-11",
                    "PASS" if has_fields else "FAIL",
                    f"blocked={d.get('blocked')}, user_direct={d.get('requires_user_direct')}",
                )
            )
        else:
            results.append(item("ae-11", "FAIL", "SafetyVerdict 없음"))

    # ae-12: ExternalAppHandoff 필드
    if models_mod:
        hf_cls = getattr(models_mod, "ExternalAppHandoff", None)
        if hf_cls:
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
            results.append(
                item(
                    "ae-12",
                    "PASS" if has_fields else "FAIL",
                    f"bridge_id={d.get('bridge_id')}, status={d.get('status')}",
                )
            )
        else:
            results.append(item("ae-12", "FAIL", "ExternalAppHandoff 없음"))

    # ae-13: ArtifactEvidenceRef (storage_ref만, 바이너리 없음)
    if models_mod:
        ar_cls = getattr(models_mod, "ArtifactEvidenceRef", None)
        if ar_cls:
            ar = ar_cls.create(
                artifact_type="log", content_type="text/plain", storage_ref="/tmp/x", safe_name="x", source_task_id="t"
            )
            d = ar.to_safe_dict()
            no_binary = "file_content" not in d and "file_bytes" not in d and "base64" not in d
            has_ref = "storage_ref" in d
            results.append(
                item(
                    "ae-13",
                    "PASS" if (no_binary and has_ref) else "FAIL",
                    f"storage_ref={has_ref}, 바이너리 없음={no_binary}",
                )
            )
        else:
            results.append(item("ae-13", "FAIL", "ArtifactEvidenceRef 없음"))

    # ae-14~15: redaction
    if models_mod:
        sae = getattr(models_mod, "StandardAuditEvent", None)
        if sae:
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
            results.append(
                item(
                    "ae-14",
                    "PASS" if not forbidden else "FAIL",
                    f"금지 필드: {forbidden}" if forbidden else "redaction 정상",
                )
            )
            nested_ok = "token" not in d.get("metadata", {}).get("inner", {})
            results.append(
                item(
                    "ae-15", "PASS" if nested_ok else "FAIL", f"nested token 제거={'없음' if nested_ok else '남아있음'}"
                )
            )
        else:
            results.append(item("ae-14", "FAIL", "StandardAuditEvent 없음"))
            results.append(item("ae-15", "FAIL", "StandardAuditEvent 없음"))

    # ae-16~19: adapter
    adapter_mod = None
    try:
        adapter_mod = importlib.import_module("ai_orchestrator.audit_evidence.adapters")
    except Exception as e:  # noqa: BLE001 - 감사 대상 모듈 import 실패시 해당 체크항목들을 FAIL로 명시 기록하는 감사 스크립트 — 성공 위장 없음, 읽기전용
        for cid in ["ae-16", "ae-17", "ae-18", "ae-19"]:
            results.append(item(cid, "FAIL", f"import 실패: {e}"))

    if adapter_mod:
        for cid, fn_name in [
            ("ae-16", "audit_event_dict_to_standard"),
            ("ae-17", "policy_decision_to_safety_verdict"),
            ("ae-18", "evidence_dict_to_artifact_ref"),
            ("ae-19", "build_external_app_handoff"),
        ]:
            fn = getattr(adapter_mod, fn_name, None)
            results.append(item(cid, "PASS" if fn else "FAIL", f"{fn_name}={'found' if fn else 'not found'}"))

    # ae-20: audit_logger 대체 없음
    adapters_src = (
        (ROOT / "ai_orchestrator/audit_evidence/adapters.py").read_text(encoding="utf-8")
        if (ROOT / "ai_orchestrator/audit_evidence/adapters.py").exists()
        else ""
    )
    replaces_logger = "audit_logger" in adapters_src and "def log_event" in adapters_src
    results.append(
        item(
            "ae-20",
            "PASS" if not replaces_logger else "FAIL",
            "audit_logger 대체 없음 확인" if not replaces_logger else "audit_logger 재정의 감지",
        )
    )

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
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run_audit()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"[{AUDIT_NAME}] verdict={result['verdict']} "
            f"pass={result['summary']['pass']} warn={result['summary']['warn']} fail={result['summary']['fail']}"
        )
        for r in result["checklist"]:
            icon = "✓" if r["status"] == "PASS" else ("△" if r["status"] == "WARN" else "✗")
            print(f"  {icon} [{r['id']}] {r['title']} — {r['evidence'][:80]}")
    return 0 if result["verdict"] in ("PASS", "PASS_WITH_KNOWN_WARN", "PASS_WITH_EXTERNAL_APP_HOLD") else 1


if __name__ == "__main__":
    sys.exit(main())
