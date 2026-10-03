"""탐색 결과 → 사이트 업무 지도 (L3/L4 어댑터, 읽기 전용).

기준서: docs/specs/2026-10-03_site_task_map.md (M1)

- 분류·병합 규칙은 `ai_orchestrator.domain.site_task_map`(순수), 저장은 `persistence.site_task_map_store`.
- 이 모듈은 기존 탐색기 산출물(`page_snapshot.collect` 결과, `auto_explorer` 결과 JSON)을 업무 지도에 합치는 연결만 한다.
- 브라우저를 직접 열지 않는다: `record_page(page)` 는 호출자가 넘긴 현재 탭을 **읽기만** 한다(이동·클릭·제출 없음).
- 지도에는 구조만 저장한다(필드 이름·라벨·URL). 입력값·표 데이터·쿠키는 읽지도 저장하지도 않는다.
"""

from __future__ import annotations

import json
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
