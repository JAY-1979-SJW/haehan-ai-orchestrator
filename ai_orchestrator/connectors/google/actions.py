"""Google 도구 버튼 액션 API — CDP 세션 기반 실제 실행."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ai_orchestrator.gates.auth import require_role

from ._helpers import audit, duration_ms

router = APIRouter()

_CDP_PORT = 9222


def _cdp_page():
    """CDP 세션에서 첫 번째 page 반환. 실패 시 None."""
    try:
        from playwright.sync_api import sync_playwright

        pw = sync_playwright().start()
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{_CDP_PORT}")
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        return pw, browser, page
    except Exception:
        return None, None, None


def _cdp_call(fn):
    """CDP 세션 연결 → fn(page) 실행 → 정리."""
    pw, _browser, page = _cdp_page()
    if not page:
        return None, "CDP 브라우저 미연결 — 먼저 브라우저를 실행하세요."
    try:
        result = fn(page)
        return result, None
    except Exception as e:
        return None, str(e)[:200]
    finally:
        try:
            pw.stop()
        except Exception:  # noqa: S110
            pass


# ── 서비스 열기 (로그인된 CDP 브라우저에서) ──────────────────────────────────


class OpenServiceRequest(BaseModel):
    url: str


@router.post("/open")
def open_service(
    body: OpenServiceRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """구글 서비스 URL 을 로그인된 CDP 브라우저의 새 탭으로 연다.

    앱에서 window.open 으로 시스템 브라우저를 열면 미로그인 상태라 로그인 요청이
    뜨던 문제 해결 — CDP 브라우저는 구글에 상시 로그인되어 있다.
    """
    url = (body.url or "").strip()
    if not url.startswith("http"):
        return {"ok": False, "error": "invalid_url"}

    def _fn(page):
        new = page.context.new_page()
        new.goto(url, wait_until="domcontentloaded", timeout=20000)
        try:
            new.bring_to_front()
        except Exception:  # noqa: S110
            pass
        return {"ok": True, "url": new.url}

    result, err = _cdp_call(_fn)
    if err:
        return {"ok": False, "error": err}
    return result or {"ok": False, "error": "unknown"}


# ── Gmail ────────────────────────────────────────────────────────────────────


@router.get("/gmail/inbox")
def get_gmail_inbox(
    limit: int = 15,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """Gmail 받은편지함 목록 (CDP)."""
    t0 = time.monotonic()

    # gmail_reader(OAuth) 우선 시도
    try:
        from ai_orchestrator.sites.gmail_reader import fetch_recent_emails

        items = fetch_recent_emails(max_results=limit, hours=72)
        if items:
            audit("GOOGLE_GMAIL_INBOX", user, status="ok", note=f"count={len(items)} source=oauth")
            return {"ok": True, "source": "oauth", "items": items, "count": len(items), "duration_ms": duration_ms(t0)}
    except Exception:  # noqa: S110
        pass

    # CDP 폴백
    def _fn(page):
        from scripts.google.gmail_api import GmailAPI

        return GmailAPI(page).list_inbox(limit=limit)

    items, err = _cdp_call(_fn)
    if err:
        return {"ok": False, "error": err, "duration_ms": duration_ms(t0)}
    audit("GOOGLE_GMAIL_INBOX", user, status="ok", note=f"count={len(items)} source=cdp")
    return {"ok": True, "source": "cdp", "items": items, "count": len(items), "duration_ms": duration_ms(t0)}


@router.get("/gmail/search")
def search_gmail(
    query: str,
    limit: int = 10,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """Gmail 검색 (CDP)."""
    t0 = time.monotonic()

    def _fn(page):
        from scripts.google.gmail_api import GmailAPI

        return GmailAPI(page).search(query=query, limit=limit)

    items, err = _cdp_call(_fn)
    if err:
        return {"ok": False, "error": err, "duration_ms": duration_ms(t0)}
    audit("GOOGLE_GMAIL_SEARCH", user, status="ok", note=f"query={query[:60]}")
    return {"ok": True, "items": items, "count": len(items), "query": query, "duration_ms": duration_ms(t0)}


# ── Google Calendar ───────────────────────────────────────────────────────────


@router.get("/calendar/today")
def get_calendar_today(
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """오늘 일정 (CDP)."""
    t0 = time.monotonic()

    def _fn(page):
        from scripts.google.calendar_api import CalendarAPI

        return CalendarAPI(page).list_today()

    events, err = _cdp_call(_fn)
    if err:
        return {"ok": False, "error": err, "duration_ms": duration_ms(t0)}
    audit("GOOGLE_CALENDAR_TODAY", user, status="ok", note=f"count={len(events)}")
    return {"ok": True, "events": events, "count": len(events), "duration_ms": duration_ms(t0)}


@router.get("/calendar/week")
def get_calendar_week(
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """이번 주 일정 (CDP)."""
    t0 = time.monotonic()

    def _fn(page):
        from scripts.google.calendar_api import CalendarAPI

        return CalendarAPI(page).list_week()

    events, err = _cdp_call(_fn)
    if err:
        return {"ok": False, "error": err, "duration_ms": duration_ms(t0)}
    audit("GOOGLE_CALENDAR_WEEK", user, status="ok", note=f"count={len(events)}")
    return {"ok": True, "events": events, "count": len(events), "duration_ms": duration_ms(t0)}


class CreateEventRequest(BaseModel):
    title: str
    when: str  # "YYYY-MM-DD HH:MM"
    duration_min: int = 60
    location: str = ""
    description: str = ""


@router.post("/calendar/create-event")
def create_calendar_event(
    body: CreateEventRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """캘린더 이벤트 생성 (CDP, 승인 필요)."""
    t0 = time.monotonic()

    def _fn(page):
        from scripts.google.calendar_api import CalendarAPI

        return CalendarAPI(page).create_event(
            title=body.title,
            when=body.when,
            duration_min=body.duration_min,
            location=body.location,
            description=body.description,
        )

    result, err = _cdp_call(_fn)
    if err:
        return {"ok": False, "error": err, "duration_ms": duration_ms(t0)}
    audit("GOOGLE_CALENDAR_CREATE_EVENT", user, status=result.get("status", "ok"), note=f"title={body.title[:60]}")
    return {**result, "duration_ms": duration_ms(t0)}


# ── Google Drive ─────────────────────────────────────────────────────────────


@router.get("/drive/recent")
def get_drive_recent(
    limit: int = 20,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """Drive 최근 파일 목록 (CDP)."""
    t0 = time.monotonic()

    def _fn(page):
        from scripts.google.drive_api import DriveAPI

        return DriveAPI(page).list_recent(limit=limit)

    files, err = _cdp_call(_fn)
    if err:
        return {"ok": False, "error": err, "duration_ms": duration_ms(t0)}
    audit("GOOGLE_DRIVE_RECENT", user, status="ok", note=f"count={len(files)}")
    return {"ok": True, "files": files, "count": len(files), "duration_ms": duration_ms(t0)}


@router.get("/drive/search")
def search_drive(
    query: str,
    limit: int = 20,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """Drive 파일 검색 (CDP)."""
    t0 = time.monotonic()

    def _fn(page):
        from scripts.google.drive_api import DriveAPI

        return DriveAPI(page).search(query=query, limit=limit)

    files, err = _cdp_call(_fn)
    if err:
        return {"ok": False, "error": err, "duration_ms": duration_ms(t0)}
    audit("GOOGLE_DRIVE_SEARCH", user, status="ok", note=f"query={query[:60]}")
    return {"ok": True, "files": files, "count": len(files), "query": query, "duration_ms": duration_ms(t0)}


# ── Google Docs ───────────────────────────────────────────────────────────────


@router.get("/docs/recent")
def get_docs_recent(
    limit: int = 15,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """최근 Google Docs 목록 (CDP)."""
    t0 = time.monotonic()

    def _fn(page):
        from scripts.google.docs_api import DocsAPI

        return DocsAPI(page).recent(limit=limit)

    docs, err = _cdp_call(_fn)
    if err:
        return {"ok": False, "error": err, "duration_ms": duration_ms(t0)}
    audit("GOOGLE_DOCS_RECENT", user, status="ok", note=f"count={len(docs)}")
    return {"ok": True, "docs": docs, "count": len(docs), "duration_ms": duration_ms(t0)}


# ── Google Sheets ─────────────────────────────────────────────────────────────


@router.get("/sheets/recent")
def get_sheets_recent(
    limit: int = 15,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """최근 Google Sheets 목록 (CDP)."""
    t0 = time.monotonic()

    def _fn(page):
        from scripts.google.sheets_api import SheetsAPI

        return SheetsAPI(page).recent(limit=limit)

    sheets, err = _cdp_call(_fn)
    if err:
        return {"ok": False, "error": err, "duration_ms": duration_ms(t0)}
    audit("GOOGLE_SHEETS_RECENT", user, status="ok", note=f"count={len(sheets)}")
    return {"ok": True, "sheets": sheets, "count": len(sheets), "duration_ms": duration_ms(t0)}


# ── YouTube (Data API) ────────────────────────────────────────────────────────


@router.get("/youtube/search")
def search_youtube(
    query: str,
    max_results: int = 5,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """YouTube 영상 검색 (Data API)."""
    t0 = time.monotonic()
    from scripts.youtube.research import search_videos

    result, path = search_videos(query, max_results=max_results)
    result["report_path"] = str(path)
    result["duration_ms"] = duration_ms(t0)
    audit("GOOGLE_YOUTUBE_SEARCH", user, status=result.get("status", "ok"), note=f"query={query[:60]}")
    return result


@router.get("/youtube/studio/status")
def get_youtube_studio_status(
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """YouTube Studio 채널 상태 (OAuth)."""
    t0 = time.monotonic()
    import json
    import urllib.parse
    import urllib.request

    from ai_orchestrator.connectors.youtube._helpers import token_path

    p = token_path()
    if not p:
        return {"ok": False, "status": "no_token", "duration_ms": duration_ms(t0)}
    try:
        t = json.loads(p.read_text(encoding="utf-8"))
        data = urllib.parse.urlencode(
            {
                "client_id": t["client_id"],
                "client_secret": t["client_secret"],
                "refresh_token": t["refresh_token"],
                "grant_type": "refresh_token",
            }
        ).encode()
        req = urllib.request.Request(  # noqa: S310
            t.get("token_uri", "https://oauth2.googleapis.com/token"),
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        access = json.loads(urllib.request.urlopen(req, timeout=10).read()).get("access_token", "")  # noqa: S310
        channel = {}
        if access:
            req2 = urllib.request.Request(
                "https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics&mine=true&maxResults=1",
                headers={"Authorization": f"Bearer {access}"},
            )
            d = json.loads(urllib.request.urlopen(req2, timeout=10).read())  # noqa: S310
            items = d.get("items", [])
            if items:
                snip = items[0]["snippet"]
                stats = items[0].get("statistics", {})
                channel = {
                    "id": items[0]["id"],
                    "title": snip["title"],
                    "subscriber_count": stats.get("subscriberCount", "?"),
                    "video_count": stats.get("videoCount", "?"),
                    "view_count": stats.get("viewCount", "?"),
                }
        audit("GOOGLE_YOUTUBE_STUDIO_STATUS", user, status="ok")
        return {"ok": True, "channel": channel, "has_upload_scope": True, "duration_ms": duration_ms(t0)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "duration_ms": duration_ms(t0)}


# ── GCP Console ───────────────────────────────────────────────────────────────


@router.get("/gcp/status")
def get_gcp_status(
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """GCP 프로젝트 상태 요약 (CDP)."""
    t0 = time.monotonic()

    def _fn(page):
        page.goto("https://console.cloud.google.com/?project=haehan-ai", timeout=20000)
        import time as _t

        _t.sleep(4)
        return page.evaluate("""
        () => {
            const project = document.querySelector('[data-project-id], [aria-label*="haehan"]')?.textContent?.trim()
                         || document.title;
            const alerts = Array.from(document.querySelectorAll('[class*="alert"],[class*="warning"]'))
                .map(el => el.innerText.trim().substring(0,80)).filter(t=>t).slice(0,5);
            return {project, alerts, url: location.href.substring(0,80)};
        }
        """)

    result, err = _cdp_call(_fn)
    if err:
        return {"ok": False, "error": err, "duration_ms": duration_ms(t0)}
    audit("GOOGLE_GCP_STATUS", user, status="ok")
    return {"ok": True, **result, "duration_ms": duration_ms(t0)}
