"""L1 Shared Contracts — 등록 사이트(사이트 온보딩) 규칙: 상태 전이·정책 검증·탐색 결과 반영 (순수, 입출력 없음).

기준서: docs/specs/2026-10-05_site_task_map_m7_onboarding_auto_prepare.md (F1)

- 사람이 호스트를 명시해 등록한 사이트만 다룬다(브라우저 탭을 훑어 찾지 않는다).
- 저장은 구조만(호스트·상태·정책·시각). 쿠키·토큰·입력값·결과 값은 다루지 않는다.
- 로그인·로그아웃·쿠키는 이 모듈과 무관하다.
"""

from __future__ import annotations

from typing import Any

from . import site_task_map as tm

VERSION = 1

REGISTERED, EXPLORING, READY, INCOMPLETE, NEEDS_LOGIN, BLOCKED, DEREGISTERED = (
    "registered",
    "exploring",
    "ready",
    "incomplete",
    "needs_login",
    "blocked",
    "deregistered",
)
STATES = (REGISTERED, EXPLORING, READY, INCOMPLETE, NEEDS_LOGIN, BLOCKED, DEREGISTERED)

ASK, AUTO = "ask", "auto"
AUTO_MODES = (ASK, AUTO)

DAILY_MAX_DEFAULT, DAILY_MAX_TOP = 1, 24

# 허용 전이. 한 번 blocked(캡차·봇 감지)가 되면 사람이 다시 탐색을 승인해야 풀린다(자동 경로 없음).
_ALLOWED: dict[str, tuple[str, ...]] = {
    REGISTERED: (EXPLORING, BLOCKED, DEREGISTERED),  # 사전 조사(robots 전체 금지 등)로 탐색 전에 막힐 수 있다
    EXPLORING: (READY, INCOMPLETE, NEEDS_LOGIN, BLOCKED, REGISTERED, DEREGISTERED),  # 탐색 도중에도 사람이 해제할 수 있다
    READY: (EXPLORING, DEREGISTERED),
    INCOMPLETE: (EXPLORING, DEREGISTERED),
    NEEDS_LOGIN: (EXPLORING, DEREGISTERED),
    BLOCKED: (EXPLORING, DEREGISTERED),
    DEREGISTERED: (REGISTERED,),
}


def normalize_host(raw: str) -> str:
    """'https://x.com/a', 'X.com' 같은 입력을 호스트 이름으로. 내부망·로컬·IP·인증정보가 든 주소는 거부(탐색 요청과 같은 규칙)."""
    text = str(raw or "").strip()
    if not text:
        raise ValueError("호스트를 입력해 주세요")
    if "://" not in text:
        text = "https://" + text
    return tm.validate_explore_request({"start_url": text})["host"]


def validate_policy(raw: dict[str, Any]) -> dict[str, Any]:
    """정책 정규화. 잘못되면 ValueError."""
    mode = raw.get("auto_explore", ASK)
    if mode not in AUTO_MODES:
        raise ValueError("auto_explore 는 ask 또는 auto 여야 합니다")
    try:
        daily = int(raw.get("daily_explore_max", DAILY_MAX_DEFAULT))
        pages = int(raw.get("max_pages", tm.EXPLORE_DEFAULT_PAGES))
    except (TypeError, ValueError) as e:
        raise ValueError("daily_explore_max·max_pages 는 정수여야 합니다") from e
    if not 1 <= daily <= DAILY_MAX_TOP:
        raise ValueError(f"daily_explore_max 는 1~{DAILY_MAX_TOP} 사이여야 합니다")
    if not 1 <= pages <= tm.EXPLORE_PAGES_MAX:
        raise ValueError(f"max_pages 는 1~{tm.EXPLORE_PAGES_MAX} 사이여야 합니다")
    return {"auto_explore": mode, "daily_explore_max": daily, "max_pages": pages}


def new_record(host: str, *, actor: str, now: str, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "version": VERSION,
        "host": host,
        "state": REGISTERED,
        "policy": validate_policy(policy or {}),
        "registered_by": actor,
        "registered_at": now,
        "updated_at": now,
        "last_explored_at": "",
        "explored_host": "",  # 사이트가 다른 호스트로 넘긴 경우 실제로 탐색한 호스트(예: cafe.naver.com → section.cafe.naver.com)
        "explore_request_id": "",
        "note": "",
        "history": [{"at": now, "state": REGISTERED, "by": actor}],
    }


def validate_record(data: Any) -> dict[str, Any]:
    """저장된 레코드 검증. 형식이 다르면 ValueError(조용히 덮어쓰지 않는다)."""
    if not isinstance(data, dict) or data.get("version") != VERSION:
        raise ValueError("등록 사이트 레코드 형식이 올바르지 않습니다")
    if data.get("state") not in STATES or not isinstance(data.get("host"), str):
        raise ValueError("등록 사이트 레코드의 상태·호스트가 올바르지 않습니다")
    validate_policy(data.get("policy") or {})
    return data


def transition(record: dict[str, Any], state: str, *, now: str, by: str = "", note: str = "") -> dict[str, Any]:
    """허용된 전이만 한다. 같은 상태로의 전이는 변화 없이 돌려준다."""
    current = record["state"]
    if state == current:
        return record
    if state not in _ALLOWED.get(current, ()):
        raise ValueError(f"'{current}' 에서 '{state}' 로 바꿀 수 없습니다")
    history = [*(record.get("history") or [])[-49:], {"at": now, "state": state, "by": by or "system", "note": note[:120]}]
    return {**record, "state": state, "updated_at": now, "note": note[:200], "history": history}


def state_after_exploration(result: dict[str, Any], *, tasks: int, login_only: bool = False) -> tuple[str, str]:
    """탐색 결과 → (새 상태, 메모). `tasks`·`login_only` 는 **실제로 탐색한 호스트**의 지도 기준이다.

    - 캡차·봇 감지 → blocked(사람이 사이트에서 확인해야 풀린다)
    - 업무 0건 → incomplete: 시작 주소가 업무 화면이 아니거나 로그인이 풀렸을 수 있다(원인을 단정하지 않는다). 사용 가능(ready)이라고 말하지 않는다.
    - 로그인 화면만 찾음 → needs_login
    """
    reason = str(result.get("aborted_reason") or "")
    if reason.startswith("bot_flagged"):
        return BLOCKED, f"봇·보안 확인 감지로 중단({reason[:60]}) — 사람이 사이트에서 확인한 뒤 다시 탐색해 주세요"
    if tasks == 0:
        return INCOMPLETE, "업무를 찾지 못했습니다 — 시작 주소가 업무 화면이 아니거나 로그인이 풀렸을 수 있습니다. 업무가 있는 화면의 주소(예: 특정 카페 주소)로 다시 등록해 탐색해 주세요"
    if login_only:
        return NEEDS_LOGIN, "로그인 화면만 찾았습니다 — 로그인을 확인한 뒤 다시 탐색해 주세요"
    return READY, f"업무 {tasks}건"
