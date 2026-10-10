"""R1 게이트 — admin-web↔FastAPI 계약의 '새로' 끊긴 호출만 차단.

기존 부채(configs/r1_api_contract_baseline.json 허용 목록)는 통과시키고,
그 목록에 없는 새 끊긴 호출이 생기면 실패한다. 수리는 이 게이트의 책임이
아니다 — 목록화만(ROOT_FIX_ORDERS.md W2-R1 5번).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tools.repo_gates.audit_api_contract_frontend_backend import _call_id, load_baseline, run_audit  # noqa: E402


def main() -> int:
    report = run_audit()
    baseline = load_baseline()
    broken_ids = {_call_id(c): c for c in report.broken_calls}
    new_broken = sorted(set(broken_ids) - baseline)
    resolved = sorted(baseline - set(broken_ids))

    if resolved:
        print(
            f"[R1_GATE] 참고: 기존 끊긴 호출 중 {len(resolved)}건이 더 이상 끊기지 않음(수리됨) — 허용목록 정리 권장:"
        )
        for r in resolved:
            print(f"  - {r}")

    if new_broken:
        print(f"[R1_GATE] FAIL — 새로 끊긴 호출 {len(new_broken)}건:")
        for nid in new_broken:
            c = broken_ids[nid]
            print(f"  - {nid} ({c.file}:{c.line})")
        print("허용 목록(configs/r1_api_contract_baseline.json)에 의도적으로 추가하려면")
        print(
            "tools/repo_gates/audit_api_contract_frontend_backend.py --write-baseline 재실행 후 변경 사유를 커밋 메시지에 남기세요."
        )
        return 1

    print(f"[R1_GATE] PASS — 새로 끊긴 호출 없음(기존 부채 {len(baseline)}건은 허용목록으로 고정)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
