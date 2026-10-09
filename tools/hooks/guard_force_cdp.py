"""PreToolUse 훅: claude-in-chrome MCP 확장 도구 호출을 차단하고 CDP 방식을
쓰도록 강제한다 (matcher: mcp__claude-in-chrome__.*).

사유: 이 프로젝트는 scripts/browser/cdp/cdp_force_start.py + scripts/browser/cdp/cdp_helper.py 로
Chrome을 CDP(9222)로 직접 띄워 조작하는 방식이 표준이다(cdp-browser-automation
스킬 참조). claude-in-chrome 확장은 이 환경에 설치/연결되어 있지 않아 매번
연결 실패로 시간을 낭비하게 되므로, 아예 시도 자체를 차단하고 CDP 경로로
유도한다.
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001 - PreToolUse 훅 진입점 — stdin JSON 파싱 실패 시 exit(0)으로 통과시키는 의도된 fail-open, 실제 차단 판정은 파싱 성공 이후 로직에서 별도 수행.
        return 0

    tool_name = payload.get("tool_name", "")
    if not tool_name.startswith("mcp__claude-in-chrome__"):
        return 0

    result = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                "claude-in-chrome MCP 도구는 이 프로젝트에서 사용 금지 — 확장이 연결되어 있지 않다. "
                "대신 scripts/browser/cdp/cdp_force_start.py 로 CDP(9222) 상태를 확인/시작하고 "
                "scripts/browser/cdp/cdp_helper.py 의 CDP 클래스(또는 Playwright connect_over_cdp)로 조작할 것. "
                "(cdp-browser-automation 스킬 참조)"
            ),
        }
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
