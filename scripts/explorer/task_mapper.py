"""탐색 결과 → 사이트 업무 지도 (L3/L4 어댑터, 읽기 전용).

기준서: docs/specs/2026-10-03_site_task_map.md (M1)

- 분류·병합 규칙은 `ai_orchestrator.site_work.site_task_map`(순수), 저장은 `persistence.site_task_map_store`.
- 이 모듈은 기존 탐색기 산출물(`page_snapshot.collect` 결과, `auto_explorer` 결과 JSON)을 업무 지도에 합치는 연결만 한다.
- 브라우저를 직접 열지 않는다: `record_page(page)` 는 호출자가 넘긴 현재 탭을 **읽기만** 한다(이동·클릭·제출 없음).
- 지도에는 구조만 저장한다(필드 이름·라벨·URL). 입력값·표 데이터·쿠키는 읽지도 저장하지도 않는다.
"""

from __future__ import annotations

import contextlib
import json
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ai_orchestrator.site_work import site_map_labels as lab
from ai_orchestrator.site_work import site_map_menu as menu
from ai_orchestrator.site_work import site_map_sources as sources
from ai_orchestrator.site_work import site_task_map as tm
from ai_orchestrator.site_work import site_task_map_store as store


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _has_inputs(page_rec: dict[str, Any]) -> bool:
    """폼이 있거나(forms_count) 폼 없이 버튼·편집 영역이 있는(controls_count) 화면."""
    return bool(page_rec.get("forms_count") or page_rec.get("controls_count"))


def merge_snapshots(
    host: str,
    snapshots: list[dict[str, Any]],
    *,
    auth: str = tm.AUTH_PUBLIC,
    save: bool = True,
    explored_pages: int | None = None,
) -> dict[str, Any]:
    """스냅샷 여러 장을 호스트 지도에 합친다. 다른 호스트의 스냅샷은 무시한다(같은 호스트만)."""
    now = _now()
    site_map = store.load(host, now=now)
    observed: list[dict[str, Any]] = []
    per_snapshot: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    skipped = 0
    for snap in snapshots:
        if (urlparse(str(snap.get("url") or "")).hostname or "") != site_map["host"]:
            skipped += 1
            continue
        found = tm.tasks_from_snapshot(snap, auth=auth, now=now)
        per_snapshot.append((snap, found))
        observed.extend(found)
    global_labels = [x for snap, _ in per_snapshot for x in lab.global_nav_labels(snap, risk_of=tm.risk_of)]
    observed, repeated = lab.split_by_frequency(observed)  # 여러 화면에 반복되는 읽기 이동 버튼 = 전역 메뉴(업무로 쌓지 않는다)
    merged = tm.merge_tasks(site_map, observed, now=now)
    # 메뉴 색인과 `주소 열기` 업무(M8): 링크를 따라가는 것이 핵심 조작인 사이트(카탈로그·게시판)에서 읽을 수단이 되게 한다
    menu_entries = [e for snap, _ in per_snapshot for e in menu.menu_from_snapshot(snap, risk_of=tm.risk_of, skip_fragments=tm.EXPLORE_SKIP_URL)]
    merged = menu.merge_menu(merged, menu_entries, now=now)
    if merged.get("menu") and per_snapshot:
        origin = urlparse(str(per_snapshot[0][0].get("url") or ""))
        merged = tm.merge_tasks(merged, [tm.open_page_task(merged["host"], f"{origin.scheme}://{origin.netloc}/", auth=auth, now=now)], now=now)
    if explored_pages is not None:  # 전역 메뉴 기록·예전 형식 정리는 탐색 실행에서만(한 화면 기록에서는 반복 여부를 알 수 없다)
        merged = lab.merge_global_nav(merged, [*global_labels, *repeated], now=now)
        merged, _pruned = lab.prune_legacy(merged)
        merged, _collapsed = lab.collapse_duplicate_actions(merged)  # 화면마다 쌓인 같은 쓰기 버튼(예: 장바구니 담기 21개)을 하나로
    if explored_pages is not None:  # 탐색 실행(explore_to_map)에서만: 탐색했다는 사실과 접근 구분(로그인 세션이면 '공개'로 남기지 않음)
        coverage = tm.coverage_of(per_snapshot)
        if skipped:  # 읽었지만 이 호스트 화면이 아니라 버려진 것 — 조용히 0건이 되지 않게 알린다
            coverage = dict(coverage, skipped_other_host=skipped, warning=coverage.get("warning") or f"읽은 화면 {skipped}쪽이 다른 호스트라 지도에 넣지 못했습니다 — 지도가 불완전합니다.")
        merged = tm.note_exploration(merged, pages=explored_pages, auth=auth, now=now, coverage=coverage)
    if save:
        store.save(merged)
    return {"map": merged, "observed": len(observed), "skipped_other_host": skipped}


def record_page(page: Any, *, auth: str = tm.AUTH_PUBLIC, save: bool = True) -> dict[str, Any]:
    """현재 탭 한 장을 읽어 지도에 합친다(읽기 전용)."""
    from scripts.explorer.page_snapshot import (
        collect,  # 지연 import: 브라우저 연결 모듈을 시험·변환 경로에서 끌어오지 않는다
    )

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
        if "error" in p or not _has_inputs(p):
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


def _default_explore() -> Callable[..., dict[str, Any]]:
    from scripts.explorer.auto_explorer import (
        explore_site,  # 지연 import: 브라우저 모듈을 시험·변환 경로에서 끌어오지 않는다
    )

    return explore_site


def _default_recorder() -> Any:
    from scripts.explorer.data_sources import ResponseRecorder

    return ResponseRecorder()


def _default_collect() -> Callable[[Any], dict[str, Any]]:
    from scripts.explorer.page_snapshot import collect

    return collect


def _note_redirect(requested: str, actual: str, *, auth: str) -> None:
    """요청한 호스트의 지도에 '실제 탐색은 다른 호스트에서 했다'를 남겨, 요청 호스트로 조회해도 어디를 봐야 하는지 알게 한다."""
    now = _now()
    note = {"pages": 0, "redirected_to": actual, "warning": f"{requested} 는 {actual} 로 이동합니다 — 업무는 {actual} 지도에 있습니다(sitemap.lookup 에 {actual} 를 넣으세요)."}
    store.save(tm.note_exploration(store.load(requested, now=now), pages=0, auth=auth, now=now, coverage=note))


def explore_to_map(  # noqa: PLR0913 - 깊이·쪽수·간격·인증 + 시험용 주입 3개는 모두 호출부가 정하는 독립 옵션
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
    recorder_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """시작 주소부터 같은 호스트의 화면을 **주소 이동(GET)만으로** 돌며 업무 지도를 만든다.

    1) `auto_explorer.explore_site` 로 방문 목록을 얻는다(같은 호스트·위험 주소 회피·봇 감지 시 중단).
    2) 입력창이 있는 화면만 다시 열어 `page_snapshot.collect` 로 필드 구조를 읽어 지도에 합친다.
    클릭·입력·제출은 하지 않는다. 입력값·표 데이터는 읽지 않는다.
    """
    explore = explore_fn or _default_explore()
    collect = collect_fn or _default_collect()
    recorder_factory = recorder_factory or _default_recorder

    requested_host = urlparse(start_url).hostname or ""
    recorder = recorder_factory()  # 쪽이 로드되는 동안 데이터 소스 구조와 사이트 선언 도구를 관측한다(읽기 전용, 값 불저장)
    recorder.attach(page)
    try:
        result = explore(
            page,
            depth=depth,
            max_pages=max_pages,
            save=False,
            same_host_only=True,
            bot_check_each_page=True,
            skip_url_patterns=tm.EXPLORE_SKIP_URL,
            delay_s=delay_s,
            on_page=recorder.flush,
        )
    # 시작 주소가 다른 호스트로 이동하면(blog.naver.com → section.blog.naver.com) 실제로 탐색한 호스트의 지도에 담는다
        host = str(result.get("host") or requested_host)
        if host != requested_host and requested_host:
            _note_redirect(requested_host, host, auth=auth)
        form_pages = [p["url"] for p in result.get("pages", []) if _has_inputs(p) and "error" not in p]
        snapshots: list[dict[str, Any]] = []
        for url in form_pages:
            if result.get("aborted_reason"):
                break
            sleep_fn(delay_s)
            try:
                page.goto(url, timeout=20000)
                snapshots.append(collect(page))
                recorder.flush(page)
            except Exception as e:  # noqa: BLE001 - 한 화면의 읽기 실패가 전체 탐색을 막지 않게 기록만 하고 계속한다
                result.setdefault("snapshot_errors", []).append({"url": url, "error": str(e)[:120]})
    finally:
        recorder.detach(page)
    pages_visited = int(result.get("visited_count", len(result.get("pages", []))))
    merged = merge_snapshots(host, snapshots, auth=auth, explored_pages=pages_visited)
    now = _now()
    enriched = sources.merge_tools(sources.merge_sources(merged["map"], recorder.sources, now=now), recorder.tools, now=now)
    if enriched is not merged["map"]:  # 새로 관측한 데이터 소스·선언 도구가 있을 때만 다시 저장한다
        store.save(enriched)
        merged = {**merged, "map": enriched}
    return {
        "host": host,
        "pages": int(result.get("visited_count", len(result.get("pages", [])))),
        "form_pages": len(form_pages),
        "tasks": len(merged["map"]["tasks"]),
        "aborted_reason": str(result.get("aborted_reason") or ""),
        "snapshot_errors": len(result.get("snapshot_errors", [])),
        "data_sources": len(merged["map"].get("data_sources") or []),
        "declared_tools": len(merged["map"].get("declared_tools") or []),
    }


def _target_id(context: Any, page: Any) -> str:
    """Playwright 페이지가 가리키는 CDP 대상 id (`cdp_tabs` 가 돌려주는 탭 id 와 같은 값)."""
    session = context.new_cdp_session(page)
    try:
        return str(session.send("Target.getTargetInfo")["targetInfo"]["targetId"])
    finally:
        with contextlib.suppress(Exception):
            session.detach()


def page_for_tab(context: Any, tab_id: str, *, timeout_s: float = 10.0, sleep_fn: Callable[[float], None] = time.sleep) -> Any:
    """`cdp_tabs.open_tab` 으로 만든 탭의 Playwright 페이지를 찾는다. 새 탭이 Playwright 에 나타날 때까지 잠깐 기다린다."""
    waited = 0.0
    while True:
        for page in list(context.pages):
            with contextlib.suppress(Exception):  # 닫히는 중인 탭은 건너뛴다
                if _target_id(context, page) == tab_id:
                    return page
        if waited >= timeout_s:
            raise LookupError(f"탭 {tab_id[:6]} 의 Playwright 페이지를 {timeout_s:g}초 안에 찾지 못했습니다")
        sleep_fn(0.3)
        waited += 0.3


def open_private_tab(
    context: Any,
    start_url: str,
    *,
    opener: Callable[..., Any] | None = None,
    closer: Callable[[Any], None] | None = None,
    finder: Callable[[Any, str], Any] = page_for_tab,
) -> tuple[Any, Any]:
    """탐색 전용 **새 탭**을 만들어 (Playwright 페이지, 탭 핸들) 을 돌려준다. 같은 호스트의 사용자 탭은 재사용하지 않는다.

    탭은 이 저장소가 검증해 둔 경로인 `cdp_tabs.open_tab`(HTTP 로 주소와 함께 만들고 도착까지 확인)으로 만든다.
    `ctx.new_page()+goto` 는 쓰지 않는다 — 환경에 따라 goto 가 멈추는 것이 실측됐고(cdp_tabs 문서, 2026-10-03 localhost 화면),
    `get_task_page` 는 같은 호스트의 기존 탭을 재사용해 사용자 탭을 이동시킨다. 페이지를 못 찾으면 만든 탭을 닫고 오류를 낸다.
    """
    from scripts.browser.cdp import cdp_tabs

    opener = opener or cdp_tabs.open_tab
    closer = closer or cdp_tabs.close_tab
    handle = opener(start_url, reason="사이트 업무 지도 탐색")
    try:
        return finder(context, handle.tab_id), handle
    except Exception:
        with contextlib.suppress(Exception):
            closer(handle)
        raise


def run_request(request: dict[str, Any]) -> dict[str, Any]:
    """승인된 탐색 요청 실행기(서비스에 주입). 새 전용 탭에서 탐색하고, 끝나면 **그 탭만** 닫는다. 사용자 탭은 건드리지 않는다."""
    from scripts.browser.cdp import cdp_tabs
    from scripts.browser.cdp.connection import get_context, run_on_browser_thread

    def work() -> dict[str, Any]:
        page, handle = open_private_tab(get_context(), request["start_url"])
        try:
            return explore_to_map(page, request["start_url"], depth=request["depth"], max_pages=request["max_pages"], auth=request.get("auth", tm.AUTH_PUBLIC))
        finally:
            with contextlib.suppress(Exception):  # 닫기 실패는 탐색 결과를 가리지 않는다
                cdp_tabs.close_tab(handle)

    return run_on_browser_thread(work, timeout=1800)
