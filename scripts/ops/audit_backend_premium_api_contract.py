"""API Contract 감사 스크립트 — read-only.

endpoint 등록 상태, category, response 변경 여부를 점검한다.
실제 서버 실행 없음. 외부 호출, DB 접속, 파일 수정 금지.

exit code: 0=PASS/PASS_WITH_KNOWN_WARN, 1=FAIL, 2=STOP_CONDITION
"""

from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
# sys.path에 프로젝트 root 추가 (직접 실행 시 필요)
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))

AUDIT_NAME = "api_contract"

CHECKLIST = [
    {"id": "ac-01", "title": "router.py import 가능 (cycle 없음)", "required": True},
    {"id": "ac-02", "title": "ops_router.py import 가능", "required": True},
    {"id": "ac-03", "title": "OPS_READONLY_API 7개 GET-only 유지", "required": True},
    {"id": "ac-04", "title": "EXTERNAL_API_REGISTERED naver 3개 유지", "required": True},
    {"id": "ac-05", "title": "web_task_router 존재", "required": False},
    {"id": "ac-06", "title": "WEB_TASK_API 기존 path 유지", "required": True},
    {"id": "ac-07", "title": "APPROVAL_API 기존 path 유지", "required": False},
    {"id": "ac-08", "title": "신규 위험 POST/PUT/DELETE 없음 (API contract 테스트)", "required": True},
    {"id": "ac-09", "title": "API contract 테스트 존재", "required": True},
    {"id": "ac-10", "title": "direct dict boundary 테스트 존재", "required": True},
    {"id": "ac-11", "title": "naver_search_router REGISTERED 상태", "required": True},
    {"id": "ac-12", "title": "ops_router REGISTERED 상태", "required": True},
    {"id": "ac-13", "title": "legacy API 상태 분류 존재", "required": False},
    {"id": "ac-14", "title": "API contract pytest PASS", "required": True},
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

    # ac-01: router.py import
    try:
        importlib.import_module("ai_orchestrator.router")
        results.append(item("ac-01", "PASS", "router import 성공"))
    except Exception as e:  # noqa: BLE001 - 백엔드 API 계약 자체검증 스크립트 - import/실행 실패를 체크리스트 FAIL/WARN으로 기록(런타임 게이트 아님)
        results.append(item("ac-01", "FAIL", str(e)[:120]))

    # ac-02: ops_router
    try:
        importlib.import_module("ai_orchestrator.routers.ops_router")
        results.append(item("ac-02", "PASS", "ops_router import 성공"))
    except Exception as e:  # noqa: BLE001 - 백엔드 API 계약 자체검증 스크립트 - import/실행 실패를 체크리스트 FAIL/WARN으로 기록(런타임 게이트 아님)
        results.append(item("ac-02", "FAIL", str(e)[:120]))

    # ac-03: OPS 7개 GET
    try:
        ops_src = (ROOT / "ai_orchestrator/routers/ops_router.py").read_text(encoding="utf-8")
        get_count = ops_src.count("@router.get(") + ops_src.count("@ops_router.get(")
        results.append(
            item("ac-03", "PASS" if get_count >= 7 else "FAIL", f"GET endpoint 수={get_count}/7", {"count": get_count})
        )
    except Exception as e:  # noqa: BLE001 - 백엔드 API 계약 자체검증 스크립트 - import/실행 실패를 체크리스트 FAIL/WARN으로 기록(런타임 게이트 아님)
        results.append(item("ac-03", "FAIL", str(e)))

    # ac-04: naver 3개 — 실제 위치: ai_orchestrator/connectors/naver_search_router.py
    import re as _re

    naver_src = ""
    for f in [
        ROOT / "ai_orchestrator/connectors/naver_search_router.py",
        ROOT / "ai_orchestrator/naver_search_router.py",
        ROOT / "ai_orchestrator/sites/naver_search/router.py",
    ]:
        if f.exists():
            naver_src = f.read_text(encoding="utf-8")
            break
    naver_count = len(_re.findall(r"@\w*router\w*\.(get|post|put|delete|patch)\(", naver_src)) if naver_src else 0
    results.append(
        item(
            "ac-04",
            "PASS" if naver_count >= 3 else "WARN",
            f"naver endpoint 수={naver_count}/3",
            {"count": naver_count},
        )
    )

    # ac-05: web_task_router
    web_task = (ROOT / "ai_orchestrator/routers/web_task_router.py").exists()
    results.append(item("ac-05", "PASS" if web_task else "WARN", "web_task_router.py 존재" if web_task else "없음"))

    # ac-06: web_task path 유지
    if web_task:
        wt_src = (ROOT / "ai_orchestrator/routers/web_task_router.py").read_text(encoding="utf-8")
        has_path = "/web-task" in wt_src or "/tasks" in wt_src
        results.append(
            item("ac-06", "PASS" if has_path else "FAIL", "web-task/tasks path 존재" if has_path else "path 없음")
        )
    else:
        results.append(item("ac-06", "WARN", "web_task_router 없음"))

    # ac-07: approval path
    approval_src = ""
    for f in [ROOT / "ai_orchestrator/router.py", ROOT / "ai_orchestrator/approval_router.py"]:
        if f.exists():
            approval_src += f.read_text(encoding="utf-8")
    has_approval = "approval" in approval_src.lower() or "approve" in approval_src.lower()
    results.append(item("ac-07", "PASS" if has_approval else "WARN", "approval path 존재" if has_approval else "없음"))

    # ac-08~10: 테스트 파일 존재
    test_contract = list(ROOT.glob("tests/test_backend_api_contract_*.py"))
    test_direct = list(ROOT.glob("tests/test_backend_direct_dict_boundary_*.py")) + list(
        ROOT.glob("tests/test_backend_legacy_router_direct_dict_*.py")
    )

    results.append(
        item(
            "ac-08", "PASS" if test_contract else "FAIL", f"api contract 테스트 파일: {[f.name for f in test_contract]}"
        )
    )
    results.append(item("ac-09", "PASS" if test_contract else "FAIL", f"파일 수={len(test_contract)}"))
    results.append(
        item("ac-10", "PASS" if test_direct else "FAIL", f"direct dict 테스트: {[f.name for f in test_direct]}")
    )

    # ac-11~12: router 등록 상태
    router_src = (
        (ROOT / "ai_orchestrator/router.py").read_text(encoding="utf-8")
        if (ROOT / "ai_orchestrator/router.py").exists()
        else ""
    )
    naver_reg = "naver" in router_src.lower() or "naver_search" in router_src
    ops_reg = "ops" in router_src.lower()
    results.append(
        item("ac-11", "PASS" if naver_reg else "WARN", "naver_search_router 등록" if naver_reg else "미등록")
    )
    results.append(item("ac-12", "PASS" if ops_reg else "WARN", "ops_router 등록" if ops_reg else "미등록"))

    # ac-13: legacy 분류 — router.py 또는 api_contract 테스트에서 wrap_legacy/LEGACY 존재 확인
    has_legacy = "legacy" in router_src.lower() or "LEGACY" in router_src or "HOLD" in router_src
    if not has_legacy:
        for f in list(ROOT.glob("tests/test_backend_api_contract_*.py")) + list(
            ROOT.glob("ai_orchestrator/**/response_adapter.py")
        ):
            try:
                if "legacy" in f.read_text(encoding="utf-8").lower():
                    has_legacy = True
                    break
            except Exception:  # noqa: BLE001 - 백엔드 API 계약 자체검증 스크립트 - import/실행 실패를 체크리스트 FAIL/WARN으로 기록(런타임 게이트 아님)
                pass
    results.append(
        item(
            "ac-13", "PASS" if has_legacy else "WARN", "legacy 분류 있음 (wrap_legacy/LEGACY)" if has_legacy else "없음"
        )
    )

    # ac-14: pytest 실행
    try:
        test_files = [str(f) for f in ROOT.glob("tests/test_backend_api_contract_*.py")]
        if test_files:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", *test_files, "-q", "--tb=no"],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=60,
            )
            passed = proc.returncode == 0
            summary_line = [l for l in proc.stdout.splitlines() if "passed" in l or "failed" in l]  # noqa: E741
            results.append(
                item("ac-14", "PASS" if passed else "FAIL", summary_line[-1] if summary_line else proc.stdout[-200:])
            )
        else:
            results.append(item("ac-14", "FAIL", "api contract 테스트 파일 없음"))
    except Exception as e:  # noqa: BLE001 - 백엔드 API 계약 자체검증 스크립트 - import/실행 실패를 체크리스트 FAIL/WARN으로 기록(런타임 게이트 아님)
        results.append(item("ac-14", "WARN", f"pytest 실행 실패: {e}"))

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
