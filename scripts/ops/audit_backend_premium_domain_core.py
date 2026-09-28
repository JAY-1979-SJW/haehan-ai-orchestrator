"""Domain Core 감사 스크립트 — read-only.

모델 존재, 필드 계약, safe serialization, secret 필드 부재를 점검한다.
외부 호출, DB 접속, 파일 수정 금지.

exit code: 0=PASS/PASS_WITH_KNOWN_WARN, 1=FAIL, 2=STOP_CONDITION
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import sys
from dataclasses import fields as dc_fields
from dataclasses import is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
# sys.path에 프로젝트 root 추가 (직접 실행 시 필요)
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))

AUDIT_NAME = "domain_core"

FORBIDDEN_FIELD_NAMES = {
    "password",
    "passwd",
    "pwd",
    "otp",
    "token",
    "access_token",
    "refresh_token",
    "auth_token",
    "device_token",
    "api_key",
    "client_secret",
    "session",
    "cookie",
    "cookies",
    "credential",
    "credentials",
    "secret",
    "private_key",
    "authorization",
    "cert_password",
    "certificate_password",
    "npki",
    "npki_data",
    "approval_token",
    "final_approval_token",
    "token_hash",
}

CHECKLIST = [
    {"id": "dc-01", "title": "domain/models.py 존재", "required": True},
    {"id": "dc-02", "title": "domain/model_adapters.py 존재", "required": True},
    {"id": "dc-03", "title": "Task 모델 import 가능", "required": True},
    {"id": "dc-04", "title": "WorkTrade 모델 import 가능", "required": True},
    {"id": "dc-05", "title": "ExternalWork 모델 import 가능", "required": True},
    {"id": "dc-06", "title": "Integration 모델 import 가능", "required": True},
    {"id": "dc-07", "title": "Artifact 모델 import 가능", "required": True},
    {"id": "dc-08", "title": "SafetyPolicy 모델 import 가능", "required": True},
    {"id": "dc-09", "title": "ExternalAppBridge 모델 import 가능", "required": True},
    {"id": "dc-10", "title": "AuditEvent 또는 StandardAuditEvent 계약 연결 가능", "required": True},
    {"id": "dc-11", "title": "WorkTradeScope enum 존재", "required": True},
    {"id": "dc-12", "title": "HandoffMode enum 존재", "required": True},
    {"id": "dc-13", "title": "SafetyDecision enum 존재", "required": False},
    {"id": "dc-14", "title": "to_safe_dict 또는 safe serialization 존재", "required": True},
    {"id": "dc-15", "title": "secret/token/password/session/cookie 필드 직접 정의 없음", "required": True},
    {"id": "dc-16", "title": "external_work_registry adapter 존재 (get_all_bridges)", "required": True},
    {"id": "dc-17", "title": "CAD/HWPX/Excel/Tax/Bid EXTERNAL_APP_HOLD 표현 가능", "required": True},
    {"id": "dc-18", "title": "기존 API response에 강제 적용 없음 (domain 독립)", "required": True},
]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _check(title: str) -> dict[str, Any]:
    return {"title": title, "status": "PASS", "evidence": "", "details": {}}


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

    # dc-01
    p1 = ROOT / "ai_orchestrator/domain/models.py"
    results.append(item("dc-01", "PASS" if p1.exists() else "FAIL", str(p1), {"exists": p1.exists()}))

    # dc-02
    p2 = ROOT / "ai_orchestrator/domain/model_adapters.py"
    results.append(item("dc-02", "PASS" if p2.exists() else "FAIL", str(p2), {"exists": p2.exists()}))

    # dc-03 ~ dc-10: 모델 import
    model_checks = [
        ("dc-03", "Task"),
        ("dc-04", "WorkTrade"),
        ("dc-05", "ExternalWork"),
        ("dc-06", "Integration"),
        ("dc-07", "Artifact"),
        ("dc-08", "SafetyPolicy"),
        ("dc-09", "ExternalAppBridge"),
        ("dc-10", "AuditEvent"),
    ]
    models_mod = None
    try:
        models_mod = importlib.import_module("ai_orchestrator.domain.models")
    except Exception as e:  # noqa: BLE001 - read-only 도메인모델 감사 스크립트(문서에 '외부호출/DB접속/파일수정 금지' 명시) — 각 except는 해당 체크리스트 항목을 FAIL로 표시할 뿐 성공으로 위장하지 않으며, 감사 결과 산출일 뿐 실행 동작이 없음.
        for cid, _ in model_checks:
            results.append(item(cid, "FAIL", f"import 실패: {e}"))
    else:
        for cid, name in model_checks:
            obj = getattr(models_mod, name, None)
            if obj is None and name == "AuditEvent":
                # audit_evidence 패키지에서도 확인
                try:
                    ae_mod = importlib.import_module("ai_orchestrator.audit_evidence.models")
                    obj = getattr(ae_mod, "StandardAuditEvent", None)
                except Exception:  # noqa: BLE001 - read-only 도메인모델 감사 스크립트(문서에 '외부호출/DB접속/파일수정 금지' 명시) — 각 except는 해당 체크리스트 항목을 FAIL로 표시할 뿐 성공으로 위장하지 않으며, 감사 결과 산출일 뿐 실행 동작이 없음.
                    pass
            st = "PASS" if obj is not None else "FAIL"
            results.append(item(cid, st, f"{name}={'found' if obj else 'not found'}"))

    # dc-11, dc-12, dc-13: enum
    for cid, name in [("dc-11", "WorkTradeScope"), ("dc-12", "HandoffMode"), ("dc-13", "SafetyDecision")]:
        obj = getattr(models_mod, name, None) if models_mod else None
        st = "PASS" if obj else ("WARN" if not next(c for c in CHECKLIST if c["id"] == cid)["required"] else "FAIL")
        results.append(item(cid, st, f"{name}={'found' if obj else 'not found'}"))

    # dc-14: to_safe_dict
    found_safe = []
    if models_mod:
        for name in ["Task", "ExternalAppBridge", "AuditEvent", "Artifact"]:
            cls = getattr(models_mod, name, None)
            if cls and hasattr(cls, "to_safe_dict"):
                found_safe.append(name)
    results.append(item("dc-14", "PASS" if found_safe else "FAIL", f"to_safe_dict 보유 클래스: {found_safe}"))

    # dc-15: secret 필드 직접 정의 없음
    violations: list[str] = []
    if models_mod:
        for name, obj in inspect.getmembers(models_mod, inspect.isclass):
            if is_dataclass(obj):
                for f in dc_fields(obj):
                    if f.name.lower() in FORBIDDEN_FIELD_NAMES:
                        violations.append(f"{name}.{f.name}")
    results.append(
        item("dc-15", "PASS" if not violations else "FAIL", f"위반: {violations}" if violations else "secret 필드 없음")
    )

    # dc-16: get_all_bridges adapter
    try:
        adapters = importlib.import_module("ai_orchestrator.domain.model_adapters")
        fn = getattr(adapters, "get_all_bridges", None)
        if fn:
            bridges = fn()
            results.append(item("dc-16", "PASS", f"bridge 수={len(bridges)}", {"count": len(bridges)}))
        else:
            results.append(item("dc-16", "FAIL", "get_all_bridges 없음"))
    except Exception as e:  # noqa: BLE001 - read-only 도메인모델 감사 스크립트(문서에 '외부호출/DB접속/파일수정 금지' 명시) — 각 except는 해당 체크리스트 항목을 FAIL로 표시할 뿐 성공으로 위장하지 않으며, 감사 결과 산출일 뿐 실행 동작이 없음.
        results.append(item("dc-16", "FAIL", str(e)))

    # dc-17: EXTERNAL_APP_HOLD 표현
    try:
        adapters = importlib.import_module("ai_orchestrator.domain.model_adapters")
        bridges = adapters.get_all_bridges() if hasattr(adapters, "get_all_bridges") else []
        app_types = {b.app_type for b in bridges}
        required_types = {"CAD", "HWPX", "OFFICE", "TAX", "BID"}
        covered = required_types & app_types
        st = "PASS" if required_types <= app_types else "FAIL"
        results.append(item("dc-17", st, f"covered={covered}, missing={required_types - app_types}"))
    except Exception as e:  # noqa: BLE001 - read-only 도메인모델 감사 스크립트(문서에 '외부호출/DB접속/파일수정 금지' 명시) — 각 except는 해당 체크리스트 항목을 FAIL로 표시할 뿐 성공으로 위장하지 않으며, 감사 결과 산출일 뿐 실행 동작이 없음.
        results.append(item("dc-17", "FAIL", str(e)))

    # dc-18: domain이 router/server를 import하지 않음
    models_src = p1.read_text(encoding="utf-8") if p1.exists() else ""
    forbidden_imports = [
        line.strip()
        for line in models_src.splitlines()
        if "import" in line
        and any(x in line for x in ["fastapi", "flask", "ai_orchestrator.server", "ai_orchestrator.router"])
    ]
    results.append(
        item(
            "dc-18",
            "PASS" if not forbidden_imports else "FAIL",
            f"금지 import: {forbidden_imports}" if forbidden_imports else "독립 도메인 확인",
        )
    )

    # 집계
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
            f"pass={result['summary']['pass']} "
            f"warn={result['summary']['warn']} "
            f"fail={result['summary']['fail']}"
        )
        for r in result["checklist"]:
            icon = "✓" if r["status"] == "PASS" else ("△" if r["status"] == "WARN" else "✗")
            print(f"  {icon} [{r['id']}] {r['title']} — {r['evidence'][:80]}")

    return 0 if result["verdict"] in ("PASS", "PASS_WITH_KNOWN_WARN", "PASS_WITH_EXTERNAL_APP_HOLD") else 1


if __name__ == "__main__":
    sys.exit(main())
