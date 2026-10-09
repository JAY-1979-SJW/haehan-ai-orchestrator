"""PreToolUse 훅: 유튜브 영상 업로드/공개전환 명령을 사용자 사전 승인 없이
자동 실행하지 못하도록 차단한다 (Bash/PowerShell 매처).

사고 이력 (2026-08-26): .env의 YOUTUBE_OAUTH_TOKEN_FILE 기본값(해한AI 채널)을
그대로 써서 반딧불전파사용 쇼츠를 엉뚱한 채널에 업로드한 사고 발생. 이후로는
업로드/공개전환 관련 명령이 감지되면, 어느 토큰 파일(=어느 채널)을 쓰는지
채널 소유권을 먼저 확인했는지 사용자에게 재확인받는다.
"""

from __future__ import annotations

import json
import re
import sys

TRIGGER_PATTERNS = (
    re.compile(r"_upload_with_official_api"),
    re.compile(r"execute_upload_plan"),
    re.compile(r"youtube_upload_video"),
    re.compile(r"videos\(\)\.insert"),
    re.compile(r"videos\(\)\.update"),
    re.compile(r"privacyStatus.{0,20}public", re.IGNORECASE),
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
    if "youtube" not in command.lower() and "videos()" not in command:
        return 0

    hit = next((p for p in TRIGGER_PATTERNS if p.search(command)), None)
    if not hit:
        return 0

    result = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": (
                "유튜브 업로드/공개전환 감지 — 실행 전 반드시 "
                "channels().list(part='snippet', mine=True) 로 이 토큰이 어느 채널에 "
                "연결됐는지 확인했는지, 그리고 어느 토큰 파일(해한AI vs 반딧불전파사)을 "
                "쓰는지 사용자에게 재확인 필요 (2026-08-26 오채널 업로드 사고 재발 방지)"
            ),
        }
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
