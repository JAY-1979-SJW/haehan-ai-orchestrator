"""PreToolUse 훅: 인스타그램 실제 발행(--confirmed / publish_case(confirmed=True))
명령을 사용자 사전 승인 없이 자동 실행하지 못하도록 차단한다 (Bash/PowerShell 매처).

정책: 외부 공개 발행은 매번 재확인 필수(CLAUDE.md). bypassPermissions 모드에서도
훅의 ask 결정은 우선 적용된다.
"""

from __future__ import annotations

import json
import re
import sys

TRIGGER_PATTERNS = (
    re.compile(r"ig_batch\.py.*--confirmed"),
    re.compile(r"publish_case\([^)]*confirmed\s*=\s*True"),
)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001 - PreToolUse 훅 진입점 — stdin JSON 파싱 실패 시 exit(0)으로 통과시키는 의도된 fail-open, 실제 차단 판정은 파싱 성공 이후 로직에서 별도 수행.
        return 0

    tool_name = payload.get("tool_name", "")
    if tool_name not in ("Bash", "PowerShell"):
        return 0

    command = str((payload.get("tool_input") or {}).get("command", ""))
    hit = next((p for p in TRIGGER_PATTERNS if p.search(command)), None)
    if not hit:
        return 0

    result = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": (
                "인스타그램 실제 발행(공유하기) 감지 — 사용자 사전 승인 필요 "
                "(CLAUDE.md 운영규칙: 외부 공개 발행은 매번 재확인)"
            ),
        }
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
