"""External App Bridge 감사 스크립트 — read-only.

bridge registry, handoff 계약, 차단 정책을 점검한다.
실제 외부 앱 실행 금지. 외부 호출, DB 접속, 파일 수정 금지.

exit code: 0=PASS/PASS_WITH_KNOWN_WARN, 1=FAIL, 2=STOP_CONDITION
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
# sys.path에 프로젝트 root 추가 (직접 실행 시 필요)
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))

AUDIT_NAME = "external_app_bridge"

REQUIRED_APP_TYPES = {"CAD", "HWPX", "OFFICE", "TAX", "BID", "DOCUMENT_AUTOMATION"}
LOCAL_AGENT_TYPES = {"CAD", "HWPX", "OFFICE", "DOCUMENT_AUTOMATION"}
USER_DIRECT_TYPES = {"TAX", "BID"}
FORBIDDEN_REAL_IMPORTS = {"autocad", "zwcad", "libreoffice", "hwpx_sdk", "bidtool"}

CHECKLIST = [
    {"id": "eb-01", "title": "bridge registry 존재 (model_adapters.get_all_bridges)", "required": True},
    {"id": "eb-02", "title": "bridge registry 6개 포함", "required": True},
    {"id": "eb-03", "title": "CAD bridge 존재", "required": True},
    {"id": "eb-04", "title": "HWPX bridge 존재", "required": True},
    {"id": "eb-05", "title": "OFFICE bridge 존재", "required": True},
    {"id": "eb-06", "title": "TAX bridge 존재", "required": True},
    {"id": "eb-07", "title": "BID bridge 존재", "required": True},
    {"id": "eb-08", "title": "DOCUMENT_AUTOMATION bridge 존재", "required": True},
    {"id": "eb-09", "title": "모든 bridge approval_required=True", "required": True},
    {"id": "eb-10", "title": "모든 bridge auto_execute_allowed=False (is_implemented=False)", "required": True},
    {"id": "eb-11", "title": "CAD/HWPX/OFFICE/DOC_AUTO: LOCAL_AGENT_REQUIRED", "required": True},
    {"id": "eb-12", "title": "TAX/BID: USER_DIRECT_REQUIRED", "required": True},
    {"id": "eb-13", "title": "BID: no_bid_auto_execute 정책 포함", "required": True},
    {"id": "eb-14", "title": "ExternalAppHandoff 생성 가능", "required": True},
    {"id": "eb-15", "title": "input_artifact_refs 표현 가능", "required": True},
    {"id": "eb-16", "title": "output_artifact_refs 실행 전 비어 있음", "required": True},
    {"id": "eb-17", "title": "safe dict에 secret/token/password/session/cookie 없음", "required": True},
    {"id": "eb-18", "title": "실제 외부 앱 import/call 없음", "required": True},
    {"id": "eb-19", "title": "다른 앱 절대경로 하드코딩 없음", "required": True},
    {"id": "eb-20", "title": "is_implemented=False 또는 FUTURE_INTEGRATION 상태", "required": True},
]

FORBIDDEN_KEYS = {
    "password", "token", "session", "cookie", "secret", "private_key",
    "access_token", "refresh_token", "auth_token", "credential",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        return {"id": cid, "title": meta["title"], "required": meta["required"],
                "status": status, "evidence": evidence, "details": details or {}}

    # eb-01: get_all_bridges 존재
    adapters_mod = None
    bridges = []
    try:
        adapters_mod = importlib.import_module("ai_orchestrator.domain.model_adapters")
        fn = getattr(adapters_mod, "get_all_bridges", None)
        if fn:
            bridges = fn()
            results.append(item("eb-01", "PASS", f"get_all_bridges 존재, count={len(bridges)}"))
        else:
            results.append(item("eb-01", "FAIL", "get_all_bridges 없음"))
    except Exception as e:
        results.append(item("eb-01", "FAIL", str(e)))

    # eb-02: 6개
    results.append(item("eb-02", "PASS" if len(bridges) >= 6 else "FAIL",
                         f"bridge 수={len(bridges)}/6"))

    # eb-03~08: 개별 app_type 존재
    app_type_map = {b.app_type: b for b in bridges}
    for cid, app_type in [
        ("eb-03", "CAD"), ("eb-04", "HWPX"), ("eb-05", "OFFICE"),
        ("eb-06", "TAX"), ("eb-07", "BID"), ("eb-08", "DOCUMENT_AUTOMATION"),
    ]:
        found = app_type in app_type_map
        results.append(item(cid, "PASS" if found else "FAIL",
                             f"{app_type}: {'found' if found else 'not found'}"))

    # eb-09: approval_required=True
    not_approved = [b.bridge_id for b in bridges if not b.approval_required]
    results.append(item("eb-09", "PASS" if not not_approved else "FAIL",
                         f"approval_required=False: {not_approved}" if not_approved else "전체 승인 필요"))

    # eb-10: is_implemented=False
    implemented = [b.bridge_id for b in bridges if b.is_implemented()]
    results.append(item("eb-10", "PASS" if not implemented else "FAIL",
                         f"is_implemented=True: {implemented}" if implemented else "전체 미구현 상태"))

    # eb-11: LOCAL_AGENT_REQUIRED
    violations = [b.bridge_id for b in bridges
                  if b.app_type in LOCAL_AGENT_TYPES and "LOCAL_AGENT_REQUIRED" not in b.execution_location]
    results.append(item("eb-11", "PASS" if not violations else "FAIL",
                         f"위반: {violations}" if violations else "LOCAL_AGENT_REQUIRED 확인"))

    # eb-12: USER_DIRECT_REQUIRED
    violations2 = [b.bridge_id for b in bridges
                   if b.app_type in USER_DIRECT_TYPES and "USER_DIRECT_REQUIRED" not in b.execution_location]
    results.append(item("eb-12", "PASS" if not violations2 else "FAIL",
                         f"위반: {violations2}" if violations2 else "USER_DIRECT_REQUIRED 확인"))

    # eb-13: BID no_bid_auto_execute
    bid_bridge = app_type_map.get("BID")
    if bid_bridge:
        policy_str = " ".join(bid_bridge.safety_policy_ids)
        has_no_bid = "no-bid-auto-execute" in policy_str or "no_bid_auto_execute" in policy_str
        results.append(item("eb-13", "PASS" if has_no_bid else "FAIL",
                             f"safety_policy_ids={bid_bridge.safety_policy_ids}"))
    else:
        results.append(item("eb-13", "FAIL", "BID bridge 없음"))

    # eb-14~16: ExternalAppHandoff
    try:
        hf_mod = importlib.import_module("ai_orchestrator.audit_evidence.models")
        hf_cls = getattr(hf_mod, "ExternalAppHandoff", None)
        if hf_cls:
            hf = hf_cls.create(task_id="t_audit", bridge_id="cad-bridge", app_type="CAD",
                                handoff_mode="file_drop", status="handoff_recorded",
                                approval_required=True, user_direct_required=False,
                                input_artifact_refs=("ar_001",), auto_execute_allowed=False)
            results.append(item("eb-14", "PASS", f"status={hf.status}"))
            results.append(item("eb-15", "PASS" if "ar_001" in hf.input_artifact_refs else "FAIL",
                                 f"input_artifact_refs={hf.input_artifact_refs}"))
            results.append(item("eb-16", "PASS" if hf.output_artifact_refs == () else "FAIL",
                                 f"output_artifact_refs={hf.output_artifact_refs}"))
        else:
            for cid in ["eb-14", "eb-15", "eb-16"]:
                results.append(item(cid, "FAIL", "ExternalAppHandoff 없음"))
    except Exception as e:
        for cid in ["eb-14", "eb-15", "eb-16"]:
            results.append(item(cid, "FAIL", str(e)))

    # eb-17: safe dict forbidden
    violations_sec = []
    for b in bridges:
        forbidden = _check_forbidden(b.to_safe_dict())
        if forbidden:
            violations_sec.append(f"{b.bridge_id}: {forbidden}")
    results.append(item("eb-17", "PASS" if not violations_sec else "FAIL",
                         f"위반: {violations_sec}" if violations_sec else "secret 미포함 확인"))

    # eb-18: 실제 외부 앱 import 없음
    bridge_src = ""
    for fp in [ROOT / "ai_orchestrator/domain/model_adapters.py",
               ROOT / "ai_orchestrator/domain/models.py"]:
        if fp.exists():
            bridge_src += fp.read_text(encoding="utf-8")
    real_imports = [k for k in FORBIDDEN_REAL_IMPORTS if k in bridge_src.lower()]
    results.append(item("eb-18", "PASS" if not real_imports else "FAIL",
                         f"실제 앱 import 감지: {real_imports}" if real_imports else "실제 앱 import 없음"))

    # eb-19: 절대경로 하드코딩 없음
    hardcoded = []
    for line in bridge_src.splitlines():
        if any(pat in line for pat in [r"C:\Program Files", "/Applications/", "autocad.exe", "hwpx.exe"]):
            hardcoded.append(line.strip()[:80])
    results.append(item("eb-19", "PASS" if not hardcoded else "FAIL",
                         f"하드코딩: {hardcoded}" if hardcoded else "절대경로 없음"))

    # eb-20: FUTURE_INTEGRATION 상태
    non_future = [b.bridge_id for b in bridges
                  if b.status not in ("FUTURE_INTEGRATION", "EXTERNAL_APP_HOLD")]
    results.append(item("eb-20", "PASS" if not non_future else "FAIL",
                         f"비정상 status: {non_future}" if non_future else "전체 FUTURE_INTEGRATION/HOLD 상태"))

    summary = {"pass": 0, "warn": 0, "fail": 0, "skip": 0}
    for r in results:
        summary[r["status"].lower()] = summary.get(r["status"].lower(), 0) + 1

    required_fail = any(r["status"] == "FAIL" and r["required"] for r in results)
    verdict = "FAIL" if required_fail else ("PASS_WITH_KNOWN_WARN" if summary["warn"] > 0 else "PASS")

    return {"audit_name": AUDIT_NAME, "verdict": verdict, "checked_at": _now(),
            "checklist": results, "summary": summary}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run_audit()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"[{AUDIT_NAME}] verdict={result['verdict']} "
              f"pass={result['summary']['pass']} warn={result['summary']['warn']} fail={result['summary']['fail']}")
        for r in result["checklist"]:
            icon = "✓" if r["status"] == "PASS" else ("△" if r["status"] == "WARN" else "✗")
            print(f"  {icon} [{r['id']}] {r['title']} — {r['evidence'][:80]}")
    return 0 if result["verdict"] in ("PASS", "PASS_WITH_KNOWN_WARN", "PASS_WITH_EXTERNAL_APP_HOLD") else 1


if __name__ == "__main__":
    sys.exit(main())
