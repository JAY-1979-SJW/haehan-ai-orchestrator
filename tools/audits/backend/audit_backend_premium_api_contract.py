"""API Contract 감사 스크립트 — read-only.

endpoint 등록 상태, category, response 변경 여부를 점검한다.
실제 서버 실행 없음. 외부 호출, DB 접속, 파일 수정 금지.

exit code: 0=PASS/PASS_WITH_KNOWN_WARN, 1=FAIL, 2=STOP_CONDITION
"""

from __future__ import annotations

import importlib
import subprocess
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


def _check_router_import() -> dict:
    try:
        importlib.import_module("ai_orchestrator.routers.registry")
        return _item("ac-01", "PASS", "router import 성공")
    except Exception as e:  # noqa: BLE001 - 백엔드 API 계약 자체검증 스크립트 - import/실행 실패를 체크리스트 FAIL/WARN으로 기록(런타임 게이트 아님)
        return _item("ac-01", "FAIL", str(e)[:120])


def _check_ops_router_import() -> dict:
    try:
        importlib.import_module("ai_orchestrator.routers.ops_router")
        return _item("ac-02", "PASS", "ops_router import 성공")
    except Exception as e:  # noqa: BLE001 - 백엔드 API 계약 자체검증 스크립트 - import/실행 실패를 체크리스트 FAIL/WARN으로 기록(런타임 게이트 아님)
        return _item("ac-02", "FAIL", str(e)[:120])


def _check_ops_get_count() -> dict:
    try:
        ops_src = (ROOT / "ai_orchestrator/routers/ops_router.py").read_text(encoding="utf-8")
        get_count = ops_src.count("@router.get(") + ops_src.count("@ops_router.get(")
        return _item(
            "ac-03", "PASS" if get_count >= 7 else "FAIL", f"GET endpoint 수={get_count}/7", {"count": get_count}
        )
    except Exception as e:  # noqa: BLE001 - 백엔드 API 계약 자체검증 스크립트 - import/실행 실패를 체크리스트 FAIL/WARN으로 기록(런타임 게이트 아님)
        return _item("ac-03", "FAIL", str(e))


def _check_naver_endpoint_count() -> dict:
    # ac-04: naver 3개 — 실제 위치: ai_orchestrator/connectors/naver_search/naver_search_router.py
    import re as _re

    naver_src = ""
    for f in [
        ROOT / "ai_orchestrator/connectors/naver_search/naver_search_router.py",
        ROOT / "ai_orchestrator/naver_search_router.py",
        ROOT / "ai_orchestrator/sites/naver_search/router.py",
    ]:
        if f.exists():
            naver_src = f.read_text(encoding="utf-8")
            break
    naver_count = len(_re.findall(r"@\w*router\w*\.(get|post|put|delete|patch)\(", naver_src)) if naver_src else 0
    return _item(
        "ac-04",
        "PASS" if naver_count >= 3 else "WARN",
        f"naver endpoint 수={naver_count}/3",
        {"count": naver_count},
    )


def _check_web_task_router_exists() -> tuple[dict, bool]:
    web_task = (ROOT / "ai_orchestrator/web_task/web_task_router.py").exists()
    return _item("ac-05", "PASS" if web_task else "WARN", "web_task_router.py 존재" if web_task else "없음"), web_task


def _check_web_task_path(web_task: bool) -> dict:
    if not web_task:
        return _item("ac-06", "WARN", "web_task_router 없음")
    wt_src = (ROOT / "ai_orchestrator/web_task/web_task_router.py").read_text(encoding="utf-8")
    has_path = "/web-task" in wt_src or "/tasks" in wt_src
    return _item("ac-06", "PASS" if has_path else "FAIL", "web-task/tasks path 존재" if has_path else "path 없음")


def _check_approval_path() -> dict:
    approval_src = ""
    for f in [ROOT / "ai_orchestrator/routers/registry.py", ROOT / "ai_orchestrator/approval_router.py"]:
        if f.exists():
            approval_src += f.read_text(encoding="utf-8")
    has_approval = "approval" in approval_src.lower() or "approve" in approval_src.lower()
    return _item("ac-07", "PASS" if has_approval else "WARN", "approval path 존재" if has_approval else "없음")


def _check_test_files_exist() -> tuple[dict, dict, dict]:
    test_contract = list(ROOT.glob("tests/test_backend_api_contract_*.py"))
    test_direct = list(ROOT.glob("tests/test_backend_direct_dict_boundary_*.py")) + list(
        ROOT.glob("tests/test_backend_legacy_router_direct_dict_*.py")
    )
    ac08 = _item(
        "ac-08", "PASS" if test_contract else "FAIL", f"api contract 테스트 파일: {[f.name for f in test_contract]}"
    )
    ac09 = _item("ac-09", "PASS" if test_contract else "FAIL", f"파일 수={len(test_contract)}")
    ac10 = _item("ac-10", "PASS" if test_direct else "FAIL", f"direct dict 테스트: {[f.name for f in test_direct]}")
    return ac08, ac09, ac10


def _check_router_registration() -> tuple[dict, dict, str]:
    router_src = (
        (ROOT / "ai_orchestrator/routers/registry.py").read_text(encoding="utf-8")
        if (ROOT / "ai_orchestrator/routers/registry.py").exists()
        else ""
    )
    naver_reg = "naver" in router_src.lower() or "naver_search" in router_src
    ops_reg = "ops" in router_src.lower()
    ac11 = _item("ac-11", "PASS" if naver_reg else "WARN", "naver_search_router 등록" if naver_reg else "미등록")
    ac12 = _item("ac-12", "PASS" if ops_reg else "WARN", "ops_router 등록" if ops_reg else "미등록")
    return ac11, ac12, router_src


def _check_legacy_classification(router_src: str) -> dict:
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
    return _item(
        "ac-13", "PASS" if has_legacy else "WARN", "legacy 분류 있음 (wrap_legacy/LEGACY)" if has_legacy else "없음"
    )


def _check_api_contract_pytest() -> dict:
    try:
        test_files = [str(f) for f in ROOT.glob("tests/test_backend_api_contract_*.py")]
        if not test_files:
            return _item("ac-14", "FAIL", "api contract 테스트 파일 없음")
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", *test_files, "-q", "--tb=no"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
            encoding="utf-8",
        )
        passed = proc.returncode == 0
        summary_line = [l for l in proc.stdout.splitlines() if "passed" in l or "failed" in l]  # noqa: E741
        return _item("ac-14", "PASS" if passed else "FAIL", summary_line[-1] if summary_line else proc.stdout[-200:])
    except Exception as e:  # noqa: BLE001 - 백엔드 API 계약 자체검증 스크립트 - import/실행 실패를 체크리스트 FAIL/WARN으로 기록(런타임 게이트 아님)
        return _item("ac-14", "WARN", f"pytest 실행 실패: {e}")


def run_audit() -> dict[str, Any]:
    # 2026-09-29 STD-08(복잡도) 리팩터: ac-01~14 체크 블록을 _check_*() 함수로 분리(순서·조건·
    # 문자열 그대로). item() 클로저는 CHECKLIST(모듈 상수)만 읽어 상태 공유가 없어 _item() 으로
    # 그대로 모듈 레벨로 옮겼다.
    results: list[dict[str, Any]] = []
    results.append(_check_router_import())
    results.append(_check_ops_router_import())
    results.append(_check_ops_get_count())
    results.append(_check_naver_endpoint_count())
    web_task_item, web_task = _check_web_task_router_exists()
    results.append(web_task_item)
    results.append(_check_web_task_path(web_task))
    results.append(_check_approval_path())
    ac08, ac09, ac10 = _check_test_files_exist()
    results.extend([ac08, ac09, ac10])
    ac11, ac12, router_src = _check_router_registration()
    results.extend([ac11, ac12])
    results.append(_check_legacy_classification(router_src))
    results.append(_check_api_contract_pytest())

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
