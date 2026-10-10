"""PreToolUse 훅: CDP 새 탭/타깃 생성을 차단해 기존 로그인된 탭 재사용을 강제한다.

문제: `/json/new?<url>` 또는 `Target.createTarget` 을 반복 호출하면 이미 로그인된
탭을 두고 매번 새 탭(=새 세션 컨텍스트)을 여는 낭비가 발생한다. 로그인 세션은
탭이 아니라 브라우저 프로필에 귀속되므로 새 탭도 로그인은 유지되지만, 사용자
입장에서는 화면이 계속 새로 뜨는 것으로 보여 혼란을 준다.

정책: Bash/PowerShell 명령에 CDP 새 탭 생성 패턴이 보이면 ask 로 강제 확인.
기존 탭 재사용 방법: `Page.navigate` (CDP) 또는 `/json/list` 로 기존 탭 찾기.
"""

from __future__ import annotations

import json
import re
import sys

TRIGGER_PATTERNS = (
    re.compile(r"/json/new\b"),
    re.compile(r"Target\.createTarget"),
)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001 - PreToolUse 훅 진입점 — stdin JSON 파싱 자체가 실패하면(하네스가 정상 페이로드를 못 준 경우) exit(0)으로 통과시키는 의도된 fail-open. 파싱 성공 후의 실제 차단 로직은 이 except 밖에서 별도로 수행됨.
        return 0

    tool_name = payload.get("tool_name", "")
    if tool_name not in ("Bash", "PowerShell"):
        return 0

    command = str((payload.get("tool_input") or {}).get("command", ""))
    hit = next((p.pattern for p in TRIGGER_PATTERNS if p.search(command)), None)
    if not hit:
        return 0

    result = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": (
                f"CDP 새 탭 생성 감지({hit}) - 기존 탭 재사용 우선. "
                "/json/list 로 기존 탭을 찾아 Page.navigate 로 이동하세요. "
                "정말 새 탭이 필요하면 승인 후 진행."
            ),
        }
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
