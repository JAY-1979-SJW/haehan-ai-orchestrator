"""L1 Shared Contracts — 신규 사이트 사전 조사 규칙: robots.txt 해석·sitemap 주소 추출·진행/차단 판정 (순수, 입출력 없음).

기준서: docs/specs/2026-10-05_new_site_onboarding_pipeline.md (M10)

- 조회(네트워크)는 이 모듈 밖(L3 `scripts/explorer/preflight_fetch.py`)에서 한다. 여기는 받은 글자만 해석한다.
- 저장·반환은 구조만(경로 접두사·판정·이유). 응답 본문 전체는 남기지 않는다.
- 판정: `proceed`(진행) | `use_api`(공식 API 로 개발 권장 — 등록은 막지 않고 안내) | `blocked`(탐색 중단).
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

PROCEED, USE_API, BLOCKED = "proceed", "use_api", "blocked"
VERDICTS = (PROCEED, USE_API, BLOCKED)

ROBOTS_OK, ROBOTS_MISSING, ROBOTS_UNAVAILABLE = "ok", "missing", "unavailable"
EXCLUDE_MAX = 50
SITEMAP_PATHS_MAX = 30
CRAWL_DELAY_TOP = 30.0
_LIVE_API = ("available", "registered")
_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.IGNORECASE)


def _fields(text: str):
    """주석을 떼고 `이름: 값` 줄만 (소문자 이름, 값)으로 내놓는다."""
    for raw in str(text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" in line:
            field, value = (part.strip() for part in line.split(":", 1))
            yield field.lower(), value


def _crawl_delay(value: str) -> float | None:
    try:
        return min(max(float(value), 0.0), CRAWL_DELAY_TOP)
    except ValueError:
        return None


def _read_groups(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    groups: list[dict[str, Any]] = []
    sitemaps: list[str] = []
    current: dict[str, Any] | None = None
    reading_agents = False
    for field, value in _fields(text):
        if field == "sitemap":
            sitemaps.extend([value] if value else [])
        elif field == "user-agent":
            if not reading_agents or current is None:
                current = {"agents": [], "rules": [], "crawl_delay": None}
                groups.append(current)
            current["agents"].append(value.lower())
            reading_agents = True
        elif current is not None:
            reading_agents = False
            if field in ("allow", "disallow") and value:  # 빈 Disallow 는 "모두 허용" — 규칙으로 두지 않는다
                current["rules"].append((field, value))
            elif field == "crawl-delay":
                current["crawl_delay"] = _crawl_delay(value)
    return groups, sitemaps


def parse_robots(text: str, agent: str = "*") -> dict[str, Any]:
    """robots.txt 를 해석한다. 지정한 에이전트 그룹이 있으면 그것을, 없으면 `*` 그룹을 쓴다(RFC 9309)."""
    groups, sitemaps = _read_groups(text)
    wanted = agent.lower()
    chosen = next((g for g in groups if wanted in g["agents"]), None) or next(
        (g for g in groups if "*" in g["agents"]), None
    )
    return {
        "rules": list(chosen["rules"]) if chosen else [],
        "crawl_delay": chosen["crawl_delay"] if chosen else None,
        "sitemaps": sitemaps[:5],
    }


def _pattern(path_rule: str) -> re.Pattern[str]:
    anchored = path_rule.endswith("$")
    body = re.escape(path_rule[:-1] if anchored else path_rule).replace(r"\*", ".*")
    return re.compile("^" + body + ("$" if anchored else ""))


def is_allowed(rules: list[tuple[str, str]], path: str) -> bool:
    """가장 긴 일치 규칙이 이긴다. 같은 길이면 허용이 이긴다. 일치하는 규칙이 없으면 허용."""
    target = path if path.startswith("/") else "/" + path
    best_len, allowed = -1, True
    for kind, rule in rules:
        if _pattern(rule).match(target) and (len(rule) > best_len or (len(rule) == best_len and kind == "allow")):
            best_len, allowed = len(rule), kind == "allow"
    return allowed


def fully_blocked(rules: list[tuple[str, str]]) -> bool:
    """사이트 첫 화면까지 막혀 있고 풀어 주는 규칙도 없으면 사이트 전체 금지로 본다."""
    return not is_allowed(rules, "/") and not any(kind == "allow" for kind, _ in rules)


def exclude_prefixes(rules: list[tuple[str, str]]) -> list[str]:
    """탐색에서 제외할 경로 접두사(와일드카드 없는 Disallow 만, 더 긴 Allow 가 풀어 주는 것은 제외)."""
    out: list[str] = []
    for kind, rule in rules:
        if kind != "disallow" or any(ch in rule for ch in "*$") or rule == "/":
            continue
        if any(k == "allow" and a.startswith(rule) for k, a in rules):
            continue
        if rule not in out:
            out.append(rule)
    return out[:EXCLUDE_MAX]


def sitemap_paths(xml_text: str, host: str) -> list[str]:
    """sitemap.xml 의 `<loc>` 중 같은 호스트의 경로만(쿼리·조각 제거, 중복 제거). 다른 호스트 주소는 버린다."""
    paths: list[str] = []
    for loc in _LOC.findall(str(xml_text or "")):
        parsed = urlparse(loc)
        if (parsed.hostname or "").lower() != host.lower() or not parsed.path:
            continue
        if parsed.path not in paths:
            paths.append(parsed.path)
        if len(paths) >= SITEMAP_PATHS_MAX:
            break
    return paths


def _api_state(official_api: dict[str, Any]) -> tuple[bool, bool]:
    """(공식 API 가 이미 연결돼 있나, 목록에 없어 조사가 필요한가)."""
    if not official_api.get("checked"):
        return False, True
    vendors = official_api.get("vendors") or []
    live = any(v.get("status") in _LIVE_API for v in vendors)
    return live, not vendors


def decide(
    *,
    robots_status: str,
    robots: dict[str, Any] | None,
    official_api: dict[str, Any],
    compliance: dict[str, Any] | None,
) -> dict[str, Any]:
    """사전 조사 종합 판정. 차단 사유가 하나라도 있으면 blocked, 공식 API 가 연결돼 있으면 use_api, 아니면 proceed.

    compliance 는 안내로 싣는다(미지의 사이트 기본 정책이 '승인 필요'라 하드 차단에 쓰면 새 사이트가 전부 막힌다).
    하드 차단은 정책이 `AUTOMATION_BLOCKED` 로 명시한 경우와 robots 전체 금지·조회 불가뿐이다.
    """
    parsed = robots or {"rules": [], "crawl_delay": None, "sitemaps": []}
    reasons: list[str] = []
    verdict = PROCEED
    if robots_status == ROBOTS_UNAVAILABLE:
        verdict = BLOCKED
        reasons.append("robots.txt 를 읽지 못했습니다(서버 오류·접속 불가) — 잠시 뒤 다시 조사해 주세요")
    elif fully_blocked(parsed["rules"]):
        verdict = BLOCKED
        reasons.append("robots.txt 가 사이트 전체를 금지합니다")
    if (compliance or {}).get("capability") == "AUTOMATION_BLOCKED":
        verdict = BLOCKED
        reasons.append(str((compliance or {}).get("message_ko") or "정책상 자동화가 금지된 사이트입니다")[:120])
    live_api, research_needed = _api_state(official_api)
    if verdict == PROCEED and live_api:
        verdict = USE_API
        reasons.append("공식 API 가 연결돼 있습니다 — 화면 조작보다 API 로 개발하세요")
    if compliance and compliance.get("block_reason") and verdict != BLOCKED:
        reasons.append(str(compliance.get("message_ko") or compliance["block_reason"])[:120])
    return {
        "verdict": verdict,
        "reasons": reasons,
        "research_needed": research_needed and verdict != BLOCKED,
        "robots_status": robots_status,
        "exclude_prefixes": exclude_prefixes(parsed["rules"]),
        "crawl_delay": parsed["crawl_delay"],
    }
