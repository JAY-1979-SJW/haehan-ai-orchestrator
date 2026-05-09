"""discovery candidate JSON 검증 스크립트.

build_discovery_candidates_from_fixture.py의 출력을 검증한다.

Usage:
    python scripts/validate_discovery_candidates.py tmp/candidates_g2b.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_orchestrator.local_agent.browser_discovery_candidates import validate_candidate_safety


def main() -> None:
    if len(sys.argv) < 2:
        print("사용법: python scripts/validate_discovery_candidates.py <candidates_json>")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"[ERROR] 파일 없음: {path}")
        sys.exit(1)

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    site_id = data.get("site_id", "?")
    candidates = data.get("candidates", [])
    print(f"[검증] site_id={site_id}  총 {len(candidates)}건")

    all_ok = True
    for i, entry in enumerate(candidates):
        candidate = entry.get("candidate")
        if candidate is None:
            label = entry.get("visible_label", f"#{i}")
            verdict = entry.get("policy_verdict", "BLOCKED")
            print(f"  [{i+1:02d}] ⚠️  candidate 없음 (verdict={verdict})  label={label!r}")
            continue

        safety = validate_candidate_safety(candidate)
        label = candidate.get("visible_label", "?")
        ctype = candidate.get("candidate_type", "?")
        fp = candidate.get("selector_fingerprint", "?")

        if safety.get("safe", safety.get("ok", True)):
            print(f"  [{i+1:02d}] ✅  {ctype:<25} {label!r:<30} fp={fp}")
        else:
            reason = safety.get("reason", safety.get("block_reason", "unknown"))
            print(f"  [{i+1:02d}] ❌  {ctype:<25} {label!r:<30} 차단={reason}")
            all_ok = False

    print()
    if all_ok:
        print(f"✅ 전체 통과 ({len(candidates)}건)")
    else:
        print("❌ 일부 후보 검증 실패")
        sys.exit(1)


if __name__ == "__main__":
    main()
