"""Premium Backend 통합 감사 Runner — read-only.

9개 감사 스크립트를 직렬 실행하고 통합 verdict를 출력한다.
파일 생성 금지. 외부 호출 금지. DB 접속 금지. 서버 접속 금지.

사용법:
  python tools/audits/backend/audit_backend_premium_integrated_runner.py
  python tools/audits/backend/audit_backend_premium_integrated_runner.py --json
  python tools/audits/backend/audit_backend_premium_integrated_runner.py --fail-fast

exit code: 0=PASS/PASS_WITH_KNOWN_WARN, 1=FAIL, 2=STOP_CONDITION
"""

from __future__ import annotations

import argparse
import importlib.util
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

SCRIPTS_OPS = ROOT / "scripts/ops"

AUDIT_MODULES_ORDERED = [
    ("domain_core", "audit_backend_premium_domain_core"),
    ("service_layer", "audit_backend_premium_service_layer"),
    ("policy_layer", "audit_backend_premium_policy_layer"),
    ("audit_evidence", "audit_backend_premium_audit_evidence"),
    ("external_app_bridge", "audit_backend_premium_external_app_bridge"),
    ("api_contract", "audit_backend_premium_api_contract"),
    ("endpoint_inventory", "audit_backend_premium_endpoint_inventory"),
    ("security_boundary", "audit_backend_premium_security_boundary"),
    ("external_app_hold", "audit_backend_premium_external_app_hold"),
]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _load_module(name: str) -> Any:
    """스크립트 파일을 동적 로드한다."""
    path = SCRIPTS_OPS / f"{name}.py"
    if not path.exists():
        raise FileNotFoundError(f"감사 스크립트 없음: {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _determine_integrated_verdict(audit_results: list[dict]) -> str:
    verdicts = [r["verdict"] for r in audit_results]
    if any(v == "STOP" for v in verdicts):
        return "STOP"
    if any(v == "FAIL" for v in verdicts):
        return "FAIL"
    if any(v in ("PASS_WITH_EXTERNAL_APP_HOLD",) for v in verdicts):
        return "PASS_WITH_EXTERNAL_APP_HOLD"
    if any(v in ("PASS_WITH_KNOWN_WARN", "WARN") for v in verdicts):
        return "PASS_WITH_KNOWN_WARN"
    return "PASS"


def run_integrated_audit(fail_fast: bool = False) -> dict[str, Any]:
    audit_results: list[dict] = []
    errors: list[str] = []

    for audit_name, module_name in AUDIT_MODULES_ORDERED:
        try:
            mod = _load_module(module_name)
            result = mod.run_audit()
            audit_results.append(result)
        except Exception as e:  # noqa: BLE001 - 여러 감사 모듈을 순회 실행하는 통합 러너 — 개별 감사 모듈 로드/실행 실패를 verdict=FAIL 결과로 변환하는 fail-closed 경로.
            err_result = {
                "audit_name": audit_name,
                "verdict": "FAIL",
                "checked_at": _now(),
                "checklist": [],
                "summary": {"pass": 0, "warn": 0, "fail": 1, "skip": 0},
                "error": str(e),
            }
            audit_results.append(err_result)
            errors.append(f"{audit_name}: {e}")

        if fail_fast and audit_results[-1]["verdict"] == "FAIL":
            break

    integrated_verdict = _determine_integrated_verdict(audit_results)

    total_summary = {"pass": 0, "warn": 0, "fail": 0, "skip": 0}
    for r in audit_results:
        for k, v in r.get("summary", {}).items():
            total_summary[k] = total_summary.get(k, 0) + v

    return {
        "runner": "audit_backend_premium_integrated_runner",
        "verdict": integrated_verdict,
        "checked_at": _now(),
        "audit_order": [name for name, _ in AUDIT_MODULES_ORDERED],
        "audit_results": audit_results,
        "total_summary": total_summary,
        "errors": errors,
        "fail_fast_triggered": fail_fast
        and integrated_verdict == "FAIL"
        and len(audit_results) < len(AUDIT_MODULES_ORDERED),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Premium Backend 통합 감사 Runner")
    parser.add_argument("--json", action="store_true", help="JSON stdout 출력")
    parser.add_argument("--fail-fast", action="store_true", help="첫 FAIL에서 중단")
    parser.add_argument("--continue-on-fail", action="store_true", default=True, help="FAIL 후 계속 진행 (기본값)")
    args = parser.parse_args()

    result = run_integrated_audit(fail_fast=args.fail_fast)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("=" * 70)
        print("  Premium Backend 통합 감사 Runner")
        print(f"  통합 verdict: {result['verdict']}")
        print(f"  checked_at:  {result['checked_at']}")
        print("=" * 70)
        for r in result["audit_results"]:
            icon = "✓" if r["verdict"] in ("PASS", "PASS_WITH_KNOWN_WARN", "PASS_WITH_EXTERNAL_APP_HOLD") else "✗"
            s = r.get("summary", {})
            print(
                f"  {icon} [{r['audit_name']:28s}] verdict={r['verdict']:32s} "
                f"pass={s.get('pass', 0):3d} warn={s.get('warn', 0):2d} fail={s.get('fail', 0):2d}"
            )
        print("-" * 70)
        ts = result["total_summary"]
        print(f"  총계: pass={ts.get('pass', 0)} warn={ts.get('warn', 0)} fail={ts.get('fail', 0)}")
        print(f"  최종 verdict: {result['verdict']}")
        if result["errors"]:
            print(f"  오류: {result['errors']}")
        print("=" * 70)

    return 0 if result["verdict"] in ("PASS", "PASS_WITH_KNOWN_WARN", "PASS_WITH_EXTERNAL_APP_HOLD") else 1


if __name__ == "__main__":
    sys.exit(main())
