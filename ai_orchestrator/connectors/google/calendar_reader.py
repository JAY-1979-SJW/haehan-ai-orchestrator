"""Google Calendar API 조회 — CDP CalendarAPI(scripts/google/calendar_api.py) 대체.

L3 Connectors 계층. calendar.readonly 스코프(google_oauth.py 공용 자격증명, project
haehan-ai). 읽기전용만 — 이벤트 생성/수정은 여기 없음(그건 여전히 사람 승인 필요한
쓰기 작업이라 별도로 설계).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)


def _list_events(time_min: str, time_max: str, max_results: int = 20) -> list[dict]:
    from ai_orchestrator.connectors.google import oauth as google_oauth

    service = google_oauth.build_service("calendar", "v3")
    # timeMin/timeMax는 RFC3339(시간대 오프셋 포함) 필수, singleEvents=True 여야
    # orderBy='startTime' 사용 가능(반복 일정을 개별 인스턴스로 펼침) — 공식
    # 레퍼런스 확인(2026-09-29).
    response = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    items = []
    for ev in response.get("items", []):
        start = ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date", "")
        items.append(
            {
                "title": ev.get("summary", "(제목 없음)"),
                "start": start,
                "id": ev.get("id", ""),
                "html_link": ev.get("htmlLink", ""),
            }
        )
    return items


def _list_days(days: int) -> list[dict]:
    """오늘 0시(UTC)부터 days 일 일정(list_today/list_week 공통)."""
    now = datetime.now(UTC)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=days)
    return _list_events(start.isoformat(), end.isoformat())


def list_today() -> list[dict]:
    """오늘 일정."""
    return _list_days(1)


def list_week() -> list[dict]:
    """이번 주(오늘부터 7일) 일정."""
    return _list_days(7)
