"""External App Bridge 감사 스크립트 — read-only.

bridge registry, handoff 계약, 차단 정책을 점검한다.
실제 외부 앱 실행 금지. 외부 호출, DB 접속, 파일 수정 금지.

exit code: 0=PASS/PASS_WITH_KNOWN_WARN, 1=FAIL, 2=STOP_CONDITION
"""

from __future__ import annotations

import importlib
import re
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


def _import_bridges() -> tuple[list, dict]:
    try:
        adapters_mod = importlib.import_module("ai_orchestrator.domain.model_adapters")
        fn = getattr(adapters_mod, "get_all_bridges", None)
        if not fn:
            return [], _item("eb-01", "FAIL", "get_all_bridges 없음")
        bridges = fn()
        return bridges, _item("eb-01", "PASS", f"get_all_bridges 존재, count={len(bridges)}")
    except Exception as e:  # noqa: BLE001 - 브릿지/핸드오프 모듈 조회 실패를 FAIL 항목으로 명시 기록하는 감사 스크립트 — 성공 위장 없음, 읽기전용
        return [], _item("eb-01", "FAIL", str(e))


def _check_bridge_count(bridges: list) -> dict:
    return _item("eb-02", "PASS" if len(bridges) >= 6 else "FAIL", f"bridge 수={len(bridges)}/6")


def _check_app_types_present(app_type_map: dict) -> list[dict]:
    results = []
    for cid, app_type in [
        ("eb-03", "CAD"),
        ("eb-04", "HWPX"),
        ("eb-05", "OFFICE"),
        ("eb-06", "TAX"),
        ("eb-07", "BID"),
        ("eb-08", "DOCUMENT_AUTOMATION"),
    ]:
        found = app_type in app_type_map
        results.append(_item(cid, "PASS" if found else "FAIL", f"{app_type}: {'found' if found else 'not found'}"))
    return results


def _check_all_approval_required(bridges: list) -> dict:
    not_approved = [b.bridge_id for b in bridges if not b.approval_required]
    return _item(
        "eb-09",
        "PASS" if not not_approved else "FAIL",
        f"approval_required=False: {not_approved}" if not_approved else "전체 승인 필요",
    )


def _check_none_implemented(bridges: list) -> dict:
    implemented = [b.bridge_id for b in bridges if b.is_implemented()]
    return _item(
        "eb-10",
        "PASS" if not implemented else "FAIL",
        f"is_implemented=True: {implemented}" if implemented else "전체 미구현 상태",
    )


def _check_local_agent_required(bridges: list) -> dict:
    violations = [
        b.bridge_id
        for b in bridges
        if b.app_type in LOCAL_AGENT_TYPES and "LOCAL_AGENT_REQUIRED" not in b.execution_location
    ]
    return _item(
        "eb-11",
        "PASS" if not violations else "FAIL",
        f"위반: {violations}" if violations else "LOCAL_AGENT_REQUIRED 확인",
    )


def _check_user_direct_required(bridges: list) -> dict:
    violations2 = [
        b.bridge_id
        for b in bridges
        if b.app_type in USER_DIRECT_TYPES and "USER_DIRECT_REQUIRED" not in b.execution_location
    ]
    return _item(
        "eb-12",
        "PASS" if not violations2 else "FAIL",
        f"위반: {violations2}" if violations2 else "USER_DIRECT_REQUIRED 확인",
    )


def _check_bid_no_auto_execute(app_type_map: dict) -> dict:
    bid_bridge = app_type_map.get("BID")
    if not bid_bridge:
        return _item("eb-13", "FAIL", "BID bridge 없음")
    policy_str = " ".join(bid_bridge.safety_policy_ids)
    has_no_bid = "no-bid-auto-execute" in policy_str or "no_bid_auto_execute" in policy_str
    return _item("eb-13", "PASS" if has_no_bid else "FAIL", f"safety_policy_ids={bid_bridge.safety_policy_ids}")


def _check_external_app_handoff() -> list[dict]:
    try:
        hf_mod = importlib.import_module("ai_orchestrator.audit_evidence.models")
        hf_cls = getattr(hf_mod, "ExternalAppHandoff", None)
        if not hf_cls:
            return [_item(cid, "FAIL", "ExternalAppHandoff 없음") for cid in ["eb-14", "eb-15", "eb-16"]]
        hf = hf_cls.create(
            task_id="t_audit",
            bridge_id="cad-bridge",
            app_type="CAD",
            handoff_mode="file_drop",
            status="handoff_recorded",
            approval_required=True,
            user_direct_required=False,
            input_artifact_refs=("ar_001",),
            auto_execute_allowed=False,
        )
        eb14 = _item("eb-14", "PASS", f"status={hf.status}")
        eb15 = _item(
            "eb-15",
            "PASS" if "ar_001" in hf.input_artifact_refs else "FAIL",
            f"input_artifact_refs={hf.input_artifact_refs}",
        )
        eb16 = _item(
            "eb-16",
            "PASS" if hf.output_artifact_refs == () else "FAIL",
            f"output_artifact_refs={hf.output_artifact_refs}",
        )
        return [eb14, eb15, eb16]
    except Exception as e:  # noqa: BLE001 - 브릿지/핸드오프 모듈 조회 실패를 FAIL 항목으로 명시 기록하는 감사 스크립트 — 성공 위장 없음, 읽기전용
        return [_item(cid, "FAIL", str(e)) for cid in ["eb-14", "eb-15", "eb-16"]]


def _check_safe_dict_forbidden(bridges: list) -> dict:
    violations_sec = []
    for b in bridges:
        forbidden = _check_forbidden(b.to_safe_dict())
        if forbidden:
            violations_sec.append(f"{b.bridge_id}: {forbidden}")
    return _item(
        "eb-17",
        "PASS" if not violations_sec else "FAIL",
        f"위반: {violations_sec}" if violations_sec else "secret 미포함 확인",
    )


def _load_bridge_source() -> str:
    bridge_src = ""
    for fp in [ROOT / "ai_orchestrator/domain/model_adapters.py", ROOT / "ai_orchestrator/domain/models.py"]:
        if fp.exists():
            bridge_src += fp.read_text(encoding="utf-8")
    return bridge_src


def _check_no_real_app_imports(bridge_src: str) -> dict:
    real_imports = [k for k in FORBIDDEN_REAL_IMPORTS if k in bridge_src.lower()]
    return _item(
        "eb-18",
        "PASS" if not real_imports else "FAIL",
        f"실제 앱 import 감지: {real_imports}" if real_imports else "실제 앱 import 없음",
    )


def _check_no_hardcoded_paths(bridge_src: str) -> dict:
    hardcoded = []
    for line in bridge_src.splitlines():
        if any(
            re.search(pat, line) for pat in [r"C:[\\/]Program Files", r"/Applications/", r"autocad\.exe", r"hwpx\.exe"]
        ):
            hardcoded.append(line.strip()[:80])
    return _item(
        "eb-19", "PASS" if not hardcoded else "FAIL", f"하드코딩: {hardcoded}" if hardcoded else "절대경로 없음"
    )


def _check_future_integration_status(bridges: list) -> dict:
    non_future = [b.bridge_id for b in bridges if b.status not in ("FUTURE_INTEGRATION", "EXTERNAL_APP_HOLD")]
    return _item(
        "eb-20",
        "PASS" if not non_future else "FAIL",
        f"비정상 status: {non_future}" if non_future else "전체 FUTURE_INTEGRATION/HOLD 상태",
    )


def run_audit() -> dict[str, Any]:
    # 2026-09-29 STD-08(복잡도) 리팩터: eb-01~20 체크 블록을 _check_*()/_import_*() 함수로
    # 분리(순서·조건·문자열 그대로). bridges/app_type_map/bridge_src 는 명시적 인자로 전달.
    results: list[dict[str, Any]] = []
    bridges, eb01 = _import_bridges()
    results.append(eb01)
    results.append(_check_bridge_count(bridges))

    app_type_map = {b.app_type: b for b in bridges}
    results.extend(_check_app_types_present(app_type_map))
    results.append(_check_all_approval_required(bridges))
    results.append(_check_none_implemented(bridges))
    results.append(_check_local_agent_required(bridges))
    results.append(_check_user_direct_required(bridges))
    results.append(_check_bid_no_auto_execute(app_type_map))
    results.extend(_check_external_app_handoff())
    results.append(_check_safe_dict_forbidden(bridges))

    bridge_src = _load_bridge_source()
    results.append(_check_no_real_app_imports(bridge_src))
    results.append(_check_no_hardcoded_paths(bridge_src))
    results.append(_check_future_integration_status(bridges))

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
