"""CI 전용 — codebase_layer_audit.py 결과에서 CLAUDE.md가 명시한 3개 하드 블로커만 판정.

codebase_layer_audit.py 자체 종료코드는 "unknown layer 파일 수" 같은 별도
threshold까지 포함해 실패할 수 있다(이 저장소에 이미 있던 문제, 이 파일이
검사하는 3개 지표와는 무관). CLAUDE.md "게이트 실행 의무"에 명시된
FORBIDDEN_IMPORT > 0 / SECURITY_PATTERN > 0 / CIRCULAR_IMPORT > 0 세 가지만
CI 차단 조건으로 삼는다.

사용: python tools/repo_gates/codebase_layer_audit.py; python tools/repo_gates/ci_layer_gate_check.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
REPORT = _ROOT / "data" / "codebase_layer_audit_latest.json"


def main() -> int:
    if not REPORT.exists():
        print(f"FAIL: {REPORT} 없음 — codebase_layer_audit.py 를 먼저 실행했는지 확인")
        return 1

    try:
        data = json.loads(REPORT.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"FAIL: {REPORT} JSON 파싱 실패: {e}")
        return 1

    gate_results = data.get("gate_results", {})
    cycle_count = data.get("circular_imports", {}).get("cycle_count", 0)
    forbidden_imports = gate_results.get("forbidden_imports", 0)
    security_patterns = gate_results.get("security_patterns", 0)

    print(f"gate_results: {gate_results} | circular_imports.cycle_count: {cycle_count}")

    if forbidden_imports or security_patterns or cycle_count:
        print(
            f"FAIL: forbidden_imports={forbidden_imports} security_patterns={security_patterns} "
            f"cycle_count={cycle_count}"
        )
        return 1

    print("PASS: forbidden_imports=0, security_patterns=0, cycle_count=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
