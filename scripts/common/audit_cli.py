"""읽기 전용 감사 스크립트(scripts/ops/audit_*) 공용 출력·CLI 틀.

여러 감사 스크립트가 출력 문구·토큰만 다르게 똑같이 복사해 쓰던 main()/audit()/print_report() 본문을
한 곳으로 모았다(BASELINE_AUDIT §4 N2). 스크립트별 값(결과 토큰·문서 경로·문구·판정 이름)은 호출 시점에 넘기고,
출력 문구·반환값·종료 코드는 원래 스크립트와 같다.

호출하는 감사 스크립트는 직접 실행(`python scripts/ops/audit_x.py`)될 때 맨 위에서 저장소 루트를 sys.path 에
넣으므로, 이 모듈은 함수 안에서 `from scripts.common.audit_cli import ...` 로 지연 import 한다(E402 회피).
표준 라이브러리만 쓴다.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn


def report_findings(ok: bool, findings: Sequence[str], result_token: str) -> int:
    """각 finding 을 "[PASS] …"/"[FAIL] …" 로, 마지막 줄 "RESULT=PASS_<token>"/"RESULT=FAIL_<token>" 출력. 종료 코드(0/1)."""
    for finding in findings:
        print(f"[{'PASS' if ok else 'FAIL'}] {finding}")
    print(f"RESULT={('PASS_' if ok else 'FAIL_') + result_token}")
    return 0 if ok else 1


@dataclass(frozen=True)
class BaselineRefSpec:
    """audit_baseline_with_module_ref 입력 — 모듈 기준서와 MODULE_BASELINE 의 경로·필수 문구·실패/성공 문구."""

    baseline: Path
    baseline_missing: str
    baseline_phrases: tuple[str, ...]
    baseline_fail_prefix: str
    module_baseline: Path
    module_missing: str
    module_phrases: tuple[str, ...]
    module_fail_prefix: str
    success: list[str]


def audit_baseline_with_module_ref(
    spec: BaselineRefSpec, missing_phrases: Callable[[str, tuple[str, ...]], list[str]]
) -> tuple[bool, list[str]]:
    """모듈 기준서(baseline)와 MODULE_BASELINE 의 필수 문구를 확인한다.

    문서가 없으면 (False, [<missing 문구>]), 빠진 문구가 있으면 (False, [<prefix> + 빠진 문구 목록]),
    모두 있으면 (True, success).
    """
    failures: list[str] = []
    if not spec.baseline.exists():
        return False, [spec.baseline_missing]
    if not spec.module_baseline.exists():
        return False, [spec.module_missing]

    baseline_text = spec.baseline.read_text(encoding="utf-8", errors="replace")
    module_text = spec.module_baseline.read_text(encoding="utf-8", errors="replace")

    missing_baseline = missing_phrases(baseline_text, spec.baseline_phrases)
    if missing_baseline:
        failures.append(spec.baseline_fail_prefix + ", ".join(missing_baseline))

    missing_module_refs = missing_phrases(module_text, spec.module_phrases)
    if missing_module_refs:
        failures.append(spec.module_fail_prefix + ", ".join(missing_module_refs))

    return not failures, failures or spec.success


def run_json_or_report_cli(
    description: str,
    run_audit: Callable[[], dict],
    print_report: Callable[[dict], None],
    ok_key: str,
) -> NoReturn:
    """--json 이면 감사 결과 JSON, 아니면 print_report 출력. audit[ok_key] 가 참이면 종료 코드 0, 아니면 1."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    audit = run_audit()
    if args.json:
        print(json.dumps(audit, ensure_ascii=False, indent=2))
    else:
        print_report(audit)
    sys.exit(0 if audit[ok_key] else 1)


_CHECKLIST_PASS_VERDICTS = ("PASS", "PASS_WITH_KNOWN_WARN", "PASS_WITH_EXTERNAL_APP_HOLD")


def run_checklist_cli(audit_name: str, run_audit: Callable[[], dict[str, Any]]) -> int:
    """backend_premium 계열 체크리스트 감사 CLI — --json 이면 JSON, 아니면 요약 1줄 + 항목별 아이콘 줄. PASS 계열이면 0."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run_audit()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"[{audit_name}] verdict={result['verdict']} "
            f"pass={result['summary']['pass']} warn={result['summary']['warn']} fail={result['summary']['fail']}"
        )
        for r in result["checklist"]:
            icon = "✓" if r["status"] == "PASS" else ("△" if r["status"] == "WARN" else "✗")
            print(f"  {icon} [{r['id']}] {r['title']} — {r['evidence'][:80]}")
    return 0 if result["verdict"] in _CHECKLIST_PASS_VERDICTS else 1


def print_check_report(
    title: str,
    checks: Sequence[tuple[str, bool, str]],
    verdicts: tuple[str, str, str],
    warn_max_failed: int,
    total_label: str = "개 검사",
) -> str:
    """(이름, 통과여부, 상세) 검사 목록 보고서 출력 후 판정 반환.

    verdicts = (READY, WARN, BLOCKED): 실패 0 이면 READY, warn_max_failed 이하면 WARN, 그보다 많으면 BLOCKED.
    """
    passed = sum(1 for _, r, _ in checks if r)
    failed = sum(1 for _, r, _ in checks if not r)

    print(f"\n{'=' * 64}")
    print(title)
    print(f"{'=' * 64}")
    for name, result, detail in checks:
        status = "PASS" if result else "FAIL"
        line = f"  [{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print(f"{'=' * 64}")
    print(f"  총 {len(checks)}{total_label}: PASS={passed}, FAIL={failed}")

    ready, warn, blocked = verdicts
    if failed == 0:
        verdict = ready
    elif failed <= warn_max_failed:
        verdict = warn
    else:
        verdict = blocked

    print(f"  최종 판정: {verdict}")
    print(f"{'=' * 64}\n")
    return verdict
