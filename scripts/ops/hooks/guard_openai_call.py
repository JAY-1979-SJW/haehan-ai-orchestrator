"""PreToolUse 훅: GPT/OpenAI 등 외부 유료 AI API 호출 명령을 사용자 사전 승인 없이
자동 실행하지 못하도록 차단한다 (Bash/PowerShell 매처).

트리거 키워드: openai_proxy_caller, call_openai_agent, call_openai_chat,
OPENAI_API_KEY, api.openai.com

정책: 이 훅이 걸리면 permissionDecision=ask 로 강제 확인을 받는다.
bypassPermissions 모드에서도 훅의 ask 결정은 우선 적용된다.
"""

from __future__ import annotations

import json
import sys

TRIGGER_KEYWORDS = (
    "openai_proxy_caller",
    "call_openai_agent",
    "call_openai_chat",
    "OPENAI_API_KEY",
    "api.openai.com",
)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001 - PreToolUse 훅 진입점(유료 OpenAI 호출 승인 게이트) — stdin JSON 파싱 실패 시 exit(0)으로 통과시키는 의도된 fail-open, 실제 차단/확인 판정은 파싱 성공 이후 로직에서 별도 수행.
        return 0

    tool_name = payload.get("tool_name", "")
    if tool_name not in ("Bash", "PowerShell"):
        return 0

    command = str((payload.get("tool_input") or {}).get("command", ""))
    hit = next((kw for kw in TRIGGER_KEYWORDS if kw in command), None)
    if not hit:
        return 0

    result = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": (
                f"GPT/OpenAI 유료 API 호출 감지({hit}) - 사용자 사전 승인 필요 "
                "(CLAUDE.md 운영규칙: 외부 유료 AI API 호출 승인제)"
            ),
        }
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
