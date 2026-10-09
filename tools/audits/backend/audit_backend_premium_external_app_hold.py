"""External App Hold 감사 스크립트 — read-only.

CAD/HWPX/Excel/Tax/Bid HOLD 분류, known 실패 목록을 점검한다.
실제 CAD 앱 실행 금지. 외부 호출 금지.

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

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
# sys.path에 프로젝트 root 추가 (직접 실행 시 필요)
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))

AUDIT_NAME = "external_app_hold"

# 알려진 CAD_EXTERNAL_APP_HOLD 실패 목록
KNOWN_EXTERNAL_APP_HOLD_FAILURES = [
    {
        "test": "tests/test_cad_local_agent_adapter_20260509.py::test_cad_status_lists_physical_modules",
        "reason": "실제 CAD 앱 물리 모듈 환경 의존",
        "classification": "CAD_EXTERNAL_APP_HOLD",
        "backend_impact": False,
    },
    {
        "test": "tests/test_mcp_local_cad_adapter_tools_20260509.py::test_mcp_local_cad_adapter_status_json",
        "reason": "실제 MCP CAD bridge 환경 의존",
        "classification": "CAD_EXTERNAL_APP_HOLD",
        "backend_impact": False,
    },
    {
        "test": "tests/test_mcp_local_cad_adapter_tools_20260509.py::test_mcp_local_bridge_health_json",
        "reason": "실제 MCP bridge health 환경 의존",
        "classification": "CAD_EXTERNAL_APP_HOLD",
        "backend_impact": False,
    },
    {
        "test": "tests/test_mcp_local_cad_adapter_tools_20260509.py::test_fastmcp_call_tool_invokes_local_cad_bridge_health",
        "reason": "FastMCP CAD bridge 환경 의존",
        "classification": "CAD_EXTERNAL_APP_HOLD",
        "backend_impact": False,
    },
]

CHECKLIST = [
    {"id": "eh-01", "title": "CAD_EXTERNAL_APP_HOLD 분류 존재", "required": True},
    {"id": "eh-02", "title": "HWPX_EXTERNAL_APP_HOLD 분류 존재", "required": True},
    {"id": "eh-03", "title": "OFFICE_EXTERNAL_APP_HOLD 분류 존재", "required": True},
    {"id": "eh-04", "title": "TAX USER_DIRECT_REQUIRED 분류 존재", "required": True},
    {"id": "eh-05", "title": "BID USER_DIRECT_REQUIRED 분류 존재", "required": True},
    {"id": "eh-06", "title": "DOCUMENT_AUTOMATION bridge 분류 존재", "required": True},
    {"id": "eh-07", "title": "CAD 4건 환경 의존 known hold 목록 존재", "required": True},
    {"id": "eh-08", "title": "CAD/HWPX/Excel 현재 앱 내부 구현 대상 아님", "required": True},
    {"id": "eh-09", "title": "bridge/handoff 계약만 존재", "required": True},
    {"id": "eh-10", "title": "실제 외부 앱 import/call 없음", "required": True},
    {"id": "eh-11", "title": "no_bid_auto_execute 정책 존재", "required": True},
    {"id": "eh-12", "title": "ExternalAppHandoff와 연결 가능", "required": True},
]


def _now() -> str:
    return datetime.now(UTC).isoformat()


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

    # bridge 목록 가져오기
    bridges: list[Any] = []
    try:
        adapters = importlib.import_module("ai_orchestrator.domain.model_adapters")
        bridges = adapters.get_all_bridges() if hasattr(adapters, "get_all_bridges") else []
    except Exception:  # noqa: BLE001 - 어댑터 모듈 조회 실패시 빈 목록으로 폴백(이후 개수 0으로 FAIL 반영), 개별 체크 실패는 FAIL 항목으로 명시 기록 — 읽기전용 감사
        pass

    app_type_map = {b.app_type: b for b in bridges}

    # eh-01~06: 각 앱 분류 존재
    for cid, app_type, expected_loc in [
        ("eh-01", "CAD", "LOCAL_AGENT_REQUIRED"),
        ("eh-02", "HWPX", "LOCAL_AGENT_REQUIRED"),
        ("eh-03", "OFFICE", "LOCAL_AGENT_REQUIRED"),
        ("eh-04", "TAX", "USER_DIRECT_REQUIRED"),
        ("eh-05", "BID", "USER_DIRECT_REQUIRED"),
        ("eh-06", "DOCUMENT_AUTOMATION", "LOCAL_AGENT_REQUIRED"),
    ]:
        b = app_type_map.get(app_type)
        if b:
            has_loc = expected_loc in b.execution_location
            status_ok = b.status in ("FUTURE_INTEGRATION", "EXTERNAL_APP_HOLD")
            ok = has_loc and status_ok
            results.append(
                item(cid, "PASS" if ok else "FAIL", f"{app_type}: loc={b.execution_location}, status={b.status}")
            )
        else:
            results.append(item(cid, "FAIL", f"{app_type}: bridge 없음"))

    # eh-07: known hold 목록
    results.append(
        item(
            "eh-07",
            "PASS",
            f"known failures={len(KNOWN_EXTERNAL_APP_HOLD_FAILURES)}건",
            {"failures": KNOWN_EXTERNAL_APP_HOLD_FAILURES},
        )
    )

    # eh-08: 현재 앱 내부 구현 대상 아님 (is_implemented=False)
    implemented = [b.bridge_id for b in bridges if b.is_implemented()]
    results.append(
        item(
            "eh-08",
            "PASS" if not implemented else "FAIL",
            f"is_implemented=True: {implemented}" if implemented else "전체 미구현 상태 확인",
        )
    )

    # eh-09: bridge/handoff 계약만
    # model_adapters에 실제 실행 코드 없음 확인
    adapters_src = (
        (ROOT / "ai_orchestrator/domain/model_adapters.py").read_text(encoding="utf-8")
        if (ROOT / "ai_orchestrator/domain/model_adapters.py").exists()
        else ""
    )
    real_exec_patterns = ["subprocess.run", "os.system", "open_app", "launch_app", "execute_cad"]
    exec_hits = [p for p in real_exec_patterns if p in adapters_src]
    results.append(
        item(
            "eh-09", "PASS" if not exec_hits else "FAIL", f"실행 패턴: {exec_hits}" if exec_hits else "계약만 존재 확인"
        )
    )

    # eh-10: 실제 외부 앱 import 없음
    import sys as _sys

    real_app_modules = [
        k
        for k in _sys.modules
        if any(kw in k.lower() for kw in ["autocad", "zwcad", "hwpx_sdk", "libreoffice", "bidtool"])
    ]
    results.append(
        item(
            "eh-10",
            "PASS" if not real_app_modules else "FAIL",
            f"실제 앱 모듈: {real_app_modules}" if real_app_modules else "실제 앱 import 없음",
        )
    )

    # eh-11: no_bid_auto_execute
    bid = app_type_map.get("BID")
    if bid:
        policy_str = " ".join(bid.safety_policy_ids)
        has_no_bid = "no-bid-auto-execute" in policy_str or "no_bid_auto_execute" in policy_str
        results.append(
            item("eh-11", "PASS" if has_no_bid else "FAIL", f"bid safety_policy_ids={bid.safety_policy_ids}")
        )
    else:
        results.append(item("eh-11", "FAIL", "BID bridge 없음"))

    # eh-12: ExternalAppHandoff 연결
    try:
        hf_mod = importlib.import_module("ai_orchestrator.audit_evidence.models")
        hf_cls = getattr(hf_mod, "ExternalAppHandoff", None)
        if hf_cls:
            hf = hf_cls.create(
                task_id="t_hold",
                bridge_id="cad-bridge",
                app_type="CAD",
                handoff_mode="file_drop",
                status="handoff_recorded",
                approval_required=True,
                user_direct_required=False,
            )
            results.append(item("eh-12", "PASS", f"handoff 생성 가능, status={hf.status}"))
        else:
            results.append(item("eh-12", "FAIL", "ExternalAppHandoff 없음"))
    except Exception as e:  # noqa: BLE001 - 어댑터 모듈 조회 실패시 빈 목록으로 폴백(이후 개수 0으로 FAIL 반영), 개별 체크 실패는 FAIL 항목으로 명시 기록 — 읽기전용 감사
        results.append(item("eh-12", "FAIL", str(e)))

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
        "known_external_app_hold_failures": KNOWN_EXTERNAL_APP_HOLD_FAILURES,
        "backend_impact": False,
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
        print(f"\n  known_external_app_hold_failures: {len(result['known_external_app_hold_failures'])}건")
        print(f"  backend_impact: {result['backend_impact']}")
    return 0 if result["verdict"] in ("PASS", "PASS_WITH_KNOWN_WARN", "PASS_WITH_EXTERNAL_APP_HOLD") else 1


if __name__ == "__main__":
    sys.exit(main())
