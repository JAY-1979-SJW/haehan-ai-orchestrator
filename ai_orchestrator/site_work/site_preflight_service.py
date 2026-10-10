"""L6 Business Workflows — 신규 사이트 사전 조사: 공식 API·robots.txt·sitemap.xml·정책을 모아 진행/차단을 판정한다.

기준서: docs/specs/2026-10-05_new_site_onboarding_pipeline.md (M10)

- 조회 실행기(`fetcher`)는 라우터가 주입한다 — 이 모듈은 네트워크·브라우저를 모른다(없으면 조사를 건너뛴다).
- 읽기 전용이다: robots.txt·sitemap.xml 단순 GET 과 목록 조회뿐, 로그인·쿠키·입력과 무관하다.
- 결과는 등록 레코드의 `preflight` 키에 구조만 저장한다(응답 본문·값 없음).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from ai_orchestrator.browser_tool.policy.site_compliance_policy import get_site_compliance_policy

from ..vendor_directory import vendor_directory_service as vendors
from . import site_preflight as sp
from . import site_registry as sr
from . import site_registry_store as store

Fetcher = Callable[[str], dict[str, Any]]
_fetcher_ref: list[Fetcher | None] = [None]  # 한 칸짜리 보관소 — `global` 로 다시 대입하지 않는다


def configure_fetcher(fetcher: Fetcher | None) -> None:
    _fetcher_ref[0] = fetcher


def is_configured() -> bool:
    return _fetcher_ref[0] is not None


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _official_api(host: str) -> dict[str, Any]:
    try:
        found = vendors.lookup(host)
    except ValueError as e:
        return {"checked": False, "error": str(e)}
    items = [{k: v.get(k) for k in ("name", "status", "docs", "cost")} for v in found.get("vendors", [])]
    return {"checked": True, "found": bool(items), "vendors": items}


def _robots(fetch: Fetcher, host: str) -> tuple[str, dict[str, Any]]:
    """robots.txt → (상태, 해석). 404 등 4xx 는 '제한 없음', 5xx·접속 불가는 RFC 9309 에 따라 '조회 불가'."""
    got = fetch(f"https://{host}/robots.txt")
    status = int(got.get("status") or 0)
    if got.get("error") or status >= 500 or status == 0:
        return sp.ROBOTS_UNAVAILABLE, sp.parse_robots("")
    if status >= 400:
        return sp.ROBOTS_MISSING, sp.parse_robots("")
    return sp.ROBOTS_OK, sp.parse_robots(str(got.get("text") or ""))


def _sitemap_paths(fetch: Fetcher, host: str, listed: list[str]) -> list[str]:
    """robots.txt 가 알려 준 sitemap(같은 호스트만), 없으면 /sitemap.xml 에서 같은 호스트의 경로를 모은다."""
    candidates = [u for u in listed if sp.sitemap_paths(f"<loc>{u}</loc>", host)] or [f"https://{host}/sitemap.xml"]
    got = fetch(candidates[0])
    if got.get("error") or not 200 <= int(got.get("status") or 0) < 300:
        return []
    return sp.sitemap_paths(str(got.get("text") or ""), host)


def _run(host: str) -> dict[str, Any]:
    fetch = _fetcher_ref[0]
    if fetch is None:
        raise ValueError("사전 조사 실행기가 설정되지 않았습니다")
    host = sr.normalize_host(host)
    robots_status, robots = _robots(fetch, host)
    official = _official_api(host)
    compliance = get_site_compliance_policy(host)
    result = sp.decide(robots_status=robots_status, robots=robots, official_api=official, compliance=compliance)
    result.update(
        {
            "host": host,
            "checked_at": _now(),
            "official_api": official,
            "compliance": {k: compliance.get(k) for k in ("capability", "site_type", "block_reason", "message_ko")},
            "sitemap_paths": _sitemap_paths(fetch, host, robots["sitemaps"]) if result["verdict"] != sp.BLOCKED else [],
        }
    )
    return result


def run(host: str) -> dict[str, Any]:
    """사전 조사를 실행해 결과를 돌려준다(등록 레코드가 있으면 거기에도 구조만 저장). 실행기가 없으면 ValueError."""
    result = _run(host)
    record = store.get(result["host"])
    if record is not None and record["state"] != sr.DEREGISTERED:
        store.put({**record, "preflight": result, "updated_at": result["checked_at"]})
    return result


def latest(host: str) -> dict[str, Any] | None:
    """등록 레코드에 저장된 마지막 사전 조사 결과(없으면 None)."""
    record = store.get(sr.normalize_host(host))
    return (record or {}).get("preflight")


def run_for_registration(host: str) -> dict[str, Any] | None:
    """등록 직전 사전 조사. 실행기가 없으면 None(조사를 건너뜀). 등록 레코드는 아직 없으므로 저장하지 않고 돌려준다."""
    if _fetcher_ref[0] is None:
        return None
    return _run(host)
