"""탐색 결과 → 사이트 업무 지도 (L3/L4 어댑터, 읽기 전용).

기준서: docs/specs/2026-10-03_site_task_map.md (M1)

- 분류·병합 규칙은 `ai_orchestrator.domain.site_task_map`(순수), 저장은 `persistence.site_task_map_store`.
- 이 모듈은 기존 탐색기 산출물(`page_snapshot.collect` 결과, `auto_explorer` 결과 JSON)을 업무 지도에 합치는 연결만 한다.
- 브라우저를 직접 열지 않는다: `record_page(page)` 는 호출자가 넘긴 현재 탭을 **읽기만** 한다(이동·클릭·제출 없음).
- 지도에는 구조만 저장한다(필드 이름·라벨·URL). 입력값·표 데이터·쿠키는 읽지도 저장하지도 않는다.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ai_orchestrator.domain import site_task_map as tm
from ai_orchestrator.persistence import site_task_map_store as store


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def merge_snapshots(host: str, snapshots: list[dict[str, Any]], *, auth: str = tm.AUTH_PUBLIC, save: bool = True) -> dict[str, Any]:
    """스냅샷 여러 장을 호스트 지도에 합친다. 다른 호스트의 스냅샷은 무시한다(같은 호스트만)."""
    now = _now()
    site_map = store.load(host, now=now)
    observed: list[dict[str, Any]] = []
    skipped = 0
    for snap in snapshots:
        if (urlparse(str(snap.get("url") or "")).hostname or "") != site_map["host"]:
            skipped += 1
            continue
        observed.extend(tm.tasks_from_snapshot(snap, auth=auth, now=now))
    merged = tm.merge_tasks(site_map, observed, now=now)
    if save:
        store.save(merged)
    return {"map": merged, "observed": len(observed), "skipped_other_host": skipped}


def record_page(page: Any, *, auth: str = tm.AUTH_PUBLIC, save: bool = True) -> dict[str, Any]:
    """현재 탭 한 장을 읽어 지도에 합친다(읽기 전용)."""
    from scripts.explorer.page_snapshot import collect  # 지연 import: 브라우저 연결 모듈을 시험·변환 경로에서 끌어오지 않는다

    snap = collect(page)
    host = urlparse(str(snap.get("url") or "")).hostname or ""
    if not host:
        raise ValueError("현재 탭의 주소를 알 수 없습니다")
    return merge_snapshots(host, [snap], auth=auth, save=save)


def import_auto_sitemap(path: str | Path, *, auth: str = tm.AUTH_PUBLIC, save: bool = True) -> dict[str, Any]:
    """`auto_explorer` 결과 JSON(`data/sitemap/*_auto_*.json`)을 가져온다.

    이 결과에는 입력창 이름이 없고 폼 요약(의도·역할·제출 선택자)만 있어, 폼이 있는 화면을
    **분류 미정(unclassified) 업무**로만 올린다. 구체 필드는 `record_page` 로 그 화면을 한 번 읽을 때 채워진다.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    host = str(data.get("host") or "")
    now = _now()
    site_map = store.load(host, now=now)
    observed = []
    for p in data.get("pages", []):
        if "error" in p or not p.get("forms_count"):
            continue
        url = str(p.get("url") or "")
        summary = p.get("form_summary") or {}
        risk = tm.risk_of([urlparse(url).path, str(summary.get("submit") or "")])
        observed.append(
            {
                "id": f"{tm.slug(urlparse(url).path)}#page",
                "name": str(p.get("title") or url)[:80],
                "category": "unclassified",
                "purpose": "",
                "risk": risk,
                "auth": auth,
                "state": tm.STATE_OBSERVED,
                "url": url,
                "host": host,
                "fields": [],
                "control": "",
                "outputs": [],
                "steps": [{"type": "navigate", "url": url}],
                "fingerprint": tm.fingerprint([]),
                "observed_at": now,
                "verified_at": "",
                "failures": 0,
                "changes": [],
            }
        )
    merged = tm.merge_tasks(site_map, observed, now=now)
    if save and host:
        store.save(merged)
    return {"map": merged, "observed": len(observed)}


def explore_to_map(
    page: Any,
    start_url: str,
    *,
    depth: int = tm.EXPLORE_DEFAULT_DEPTH,
    max_pages: int = tm.EXPLORE_DEFAULT_PAGES,
    delay_s: float = tm.EXPLORE_DEFAULT_DELAY_S,
    auth: str = tm.AUTH_PUBLIC,
    explore_fn: Callable[..., dict[str, Any]] | None = None,
    collect_fn: Callable[[Any], dict[str, Any]] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """시작 주소부터 같은 호스트의 화면을 **주소 이동(GET)만으로** 돌며 업무 지도를 만든다.

    1) `auto_explorer.explore_site` 로 방문 목록을 얻는다(같은 호스트·위험 주소 회피·봇 감지 시 중단).
    2) 입력창이 있는 화면만 다시 열어 `page_snapshot.collect` 로 필드 구조를 읽어 지도에 합친다.
    클릭·입력·제출은 하지 않는다. 입력값·표 데이터는 읽지 않는다.
    """
    if explore_fn is None:
        from scripts.explorer.auto_explorer import explore_site as explore_fn  # 지연 import: 브라우저 모듈을 시험·변환 경로에서 끌어오지 않는다
    if collect_fn is None:
        from scripts.explorer.page_snapshot import collect as collect_fn

    host = urlparse(start_url).hostname or ""
    result = explore_fn(
        page,
        depth=depth,
        max_pages=max_pages,
        save=False,
        same_host_only=True,
        bot_check_each_page=True,
        skip_url_patterns=tm.EXPLORE_SKIP_URL,
        delay_s=delay_s,
    )
    form_pages = [p["url"] for p in result.get("pages", []) if p.get("forms_count") and "error" not in p]
    snapshots: list[dict[str, Any]] = []
    for url in form_pages:
        if result.get("aborted_reason"):
            break
        sleep_fn(delay_s)
        try:
            page.goto(url, timeout=20000)
            snapshots.append(collect_fn(page))
        except Exception as e:  # noqa: BLE001 - 한 화면의 읽기 실패가 전체 탐색을 막지 않게 기록만 하고 계속한다
            result.setdefault("snapshot_errors", []).append({"url": url, "error": str(e)[:120]})
    merged = merge_snapshots(host, snapshots, auth=auth)
    return {
        "pages": int(result.get("visited_count", len(result.get("pages", [])))),
        "form_pages": len(form_pages),
        "tasks": len(merged["map"]["tasks"]),
        "aborted_reason": str(result.get("aborted_reason") or ""),
        "snapshot_errors": len(result.get("snapshot_errors", [])),
    }


def open_private_tab(context: Any, start_url: str) -> Any:
    """탐색 전용 **새 탭**을 만든다. 같은 호스트의 기존 탭(사용자가 로그인해 둔 탭 포함)은 재사용하지 않는다.

    `get_task_page` 는 허용 호스트가 같은 기존 탭을 재사용해 그 탭을 이동시켜 버리므로 쓰지 않는다
    (2026-10-03 실측: 탐색 후 사용자 탭의 주소가 바뀌었다). 열기에 실패하면 만든 탭을 닫고 오류를 낸다.
    """
    page = context.new_page()
    try:
        page.goto(start_url, timeout=30000)
    except Exception:
        page.close()
        raise
    return page


def run_request(request: dict[str, Any]) -> dict[str, Any]:
    """승인된 탐색 요청 실행기(서비스에 주입). 새 전용 탭에서 탐색하고, 끝나면 **그 탭만** 닫는다. 사용자 탭은 건드리지 않는다."""
    from scripts.web_connector import get_context, run_on_browser_thread

    def work() -> dict[str, Any]:
        page = open_private_tab(get_context(), request["start_url"])
        try:
            return explore_to_map(page, request["start_url"], depth=request["depth"], max_pages=request["max_pages"], auth=request.get("auth", tm.AUTH_PUBLIC))
        finally:
            try:
                page.close()
            except Exception:  # noqa: BLE001 - 닫기 실패는 탐색 결과를 가리지 않는다(다음 정리 때 남은 빈 탭으로 처리)
                pass

    return run_on_browser_thread(work, timeout=1800)
