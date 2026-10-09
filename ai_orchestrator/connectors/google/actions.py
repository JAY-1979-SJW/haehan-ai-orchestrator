"""Google 도구 버튼 액션 API — CDP 세션 기반 실제 실행."""

from __future__ import annotations

import contextlib
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from tools.gates.auth import require_role

from ._helpers import audit, duration_ms

logger = logging.getLogger(__name__)

router = APIRouter()


def _cdp_call(fn, *, reason: str = "google-tools-action"):
    """공유 CDP 연결로 새 탭을 열어 fn(page) 실행 → 탭 정리.

    2026-09-29 완전 재작성: 기존엔 이 함수를 부를 때마다 독자적으로
    sync_playwright().start() + connect_over_cdp() 를 새로 맺었다. 실측 결과
    이 핸드셰이크가(웹소켓 자체는 즉시 연결되는데도 — <ws connected> 로그 확인)
    Playwright 내부 타겟 핸드셰이크 단계에서 반복적으로 정확히 180000ms(고정값)
    멈추는 현상을 확인(원시 CDP HTTP /json 은 항상 0.5초 이내 응답 — 브라우저
    자체는 정상, "매 호출마다 새로 연결"하는 방식 자체가 문제). Gmail(gmail_cdp_
    reader.py)은 처음부터 scripts.browser.page.web_connector 의 공유·캐시된 단일 연결
    (run_on_browser_thread, 프로세스 생애주기 동안 1회만 connect_over_cdp)을
    써서 이 세션 내내 이 문제를 한 번도 겪지 않았다 — 동일 패턴으로 통일.
    (CLAUDE.md '반복 실수' 참고.)
    """
    from scripts.browser.cdp.connection import open_page, run_on_browser_thread

    def _work():
        page = open_page(allow_new_tab=True, reason=reason)
        try:
            return fn(page), None
        except Exception as e:  # noqa: BLE001 - Google 서비스(Gmail/Calendar/YouTube Studio 등) CDP 브라우저 자동화 헬퍼 - 연결/액션 실패 시 None 또는 에러 메시지(200자 절단)를 반환하는 best-effort 폴백, 인증 우회나 정책 판정 없음
            return None, str(e)[:200]
        finally:
            with contextlib.suppress(Exception):
                page.close()

    try:
        return run_on_browser_thread(_work)
    except Exception as e:  # noqa: BLE001 - Google 서비스(Gmail/Calendar/YouTube Studio 등) CDP 브라우저 자동화 헬퍼 - 연결/액션 실패 시 None 또는 에러 메시지(200자 절단)를 반환하는 best-effort 폴백, 인증 우회나 정책 판정 없음
        return None, str(e)[:200]


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
        with contextlib.suppress(Exception):
            new.bring_to_front()
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
        from ai_orchestrator.connectors.google.gmail_reader import fetch_recent_emails

        items = fetch_recent_emails(max_results=limit, hours=72)
        if items:
            audit("GOOGLE_GMAIL_INBOX", user, status="ok", note=f"count={len(items)} source=oauth")
            return {"ok": True, "source": "oauth", "items": items, "count": len(items), "duration_ms": duration_ms(t0)}
    except Exception as exc:  # noqa: BLE001
        logger.debug("Gmail OAuth 조회(CDP 폴백) 실패: %s", type(exc).__name__)
        pass

    # CDP 폴백
    def _fn(page):
        from scripts.google.common.gmail_api import GmailAPI

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
        from scripts.google.common.gmail_api import GmailAPI

        return GmailAPI(page).search(query=query, limit=limit)

    items, err = _cdp_call(_fn)
    if err:
        return {"ok": False, "error": err, "duration_ms": duration_ms(t0)}
    audit("GOOGLE_GMAIL_SEARCH", user, status="ok", note=f"query={query[:60]}")
    return {"ok": True, "items": items, "count": len(items), "query": query, "duration_ms": duration_ms(t0)}


# ── Google Calendar ───────────────────────────────────────────────────────────


@router.get("/calendar/today")
def get_calendar_today(
    source: str = "api",  # "api"(기본, OAuth Calendar API) | "cdp"(구 CDP 화면 스크래핑)
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """오늘 일정. 2026-09-29: 기본을 Gmail과 동일한 OAuth API로 전환(2단계) — CDP는
    fallback으로 유지."""
    t0 = time.monotonic()

    if source == "api":
        try:
            from ai_orchestrator.connectors.google.calendar_reader import list_today

            events = list_today()
        except Exception as e:  # noqa: BLE001 - Google 서비스 CDP/API 공용 헬퍼 - 연결/액션 실패 시 error 메시지 반환, 인증 우회 없음
            return {"ok": False, "error": str(e)[:300], "duration_ms": duration_ms(t0)}
        audit("GOOGLE_CALENDAR_TODAY", user, status="ok", note=f"source=api count={len(events)}")
        return {"ok": True, "events": events, "count": len(events), "duration_ms": duration_ms(t0), "source": "api"}

    def _fn(page):
        from scripts.google.calendar_api import CalendarAPI

        return CalendarAPI(page).list_today()

    events, err = _cdp_call(_fn)
    if err:
        return {"ok": False, "error": err, "duration_ms": duration_ms(t0)}
    audit("GOOGLE_CALENDAR_TODAY", user, status="ok", note=f"source=cdp count={len(events)}")
    return {"ok": True, "events": events, "count": len(events), "duration_ms": duration_ms(t0), "source": "cdp"}


@router.get("/calendar/week")
def get_calendar_week(
    source: str = "api",
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """이번 주 일정. 2026-09-29: 기본을 OAuth API로 전환(2단계) — CDP는 fallback."""
    t0 = time.monotonic()

    if source == "api":
        try:
            from ai_orchestrator.connectors.google.calendar_reader import list_week

            events = list_week()
        except Exception as e:  # noqa: BLE001 - Google 서비스 CDP/API 공용 헬퍼 - 연결/액션 실패 시 error 메시지 반환, 인증 우회 없음
            return {"ok": False, "error": str(e)[:300], "duration_ms": duration_ms(t0)}
        audit("GOOGLE_CALENDAR_WEEK", user, status="ok", note=f"source=api count={len(events)}")
        return {"ok": True, "events": events, "count": len(events), "duration_ms": duration_ms(t0), "source": "api"}

    def _fn(page):
        from scripts.google.calendar_api import CalendarAPI

        return CalendarAPI(page).list_week()

    events, err = _cdp_call(_fn)
    if err:
        return {"ok": False, "error": err, "duration_ms": duration_ms(t0)}
    audit("GOOGLE_CALENDAR_WEEK", user, status="ok", note=f"source=cdp count={len(events)}")
    return {"ok": True, "events": events, "count": len(events), "duration_ms": duration_ms(t0), "source": "cdp"}


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
    source: str = "api",
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """Drive 최근 파일 목록. 2026-09-29: 기본을 OAuth Drive API로 전환(2단계) — CDP는 fallback."""
    t0 = time.monotonic()

    if source == "api":
        try:
            from ai_orchestrator.connectors.google.drive_reader import list_recent

            files = list_recent(limit=limit)
        except Exception as e:  # noqa: BLE001 - Google 서비스 CDP/API 공용 헬퍼 - 연결/액션 실패 시 error 메시지 반환, 인증 우회 없음
            return {"ok": False, "error": str(e)[:300], "duration_ms": duration_ms(t0)}
        audit("GOOGLE_DRIVE_RECENT", user, status="ok", note=f"source=api count={len(files)}")
        return {"ok": True, "files": files, "count": len(files), "duration_ms": duration_ms(t0), "source": "api"}

    def _fn(page):
        from scripts.google.drive_api import DriveAPI

        return DriveAPI(page).list_recent(limit=limit)

    files, err = _cdp_call(_fn)
    if err:
        return {"ok": False, "error": err, "duration_ms": duration_ms(t0)}
    audit("GOOGLE_DRIVE_RECENT", user, status="ok", note=f"source=cdp count={len(files)}")
    return {"ok": True, "files": files, "count": len(files), "duration_ms": duration_ms(t0), "source": "cdp"}


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
    source: str = "api",
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """최근 Google Docs 목록. 2026-09-29: 기본을 OAuth Drive API로 전환(2단계, Docs
    "목록"은 실제로는 Drive API의 mimeType 필터 — 공식 가이드 확인). CDP는 fallback."""
    t0 = time.monotonic()

    if source == "api":
        try:
            from ai_orchestrator.connectors.google.drive_reader import list_recent_docs

            docs = list_recent_docs(limit=limit)
        except Exception as e:  # noqa: BLE001 - Google 서비스 CDP/API 공용 헬퍼 - 연결/액션 실패 시 error 메시지 반환, 인증 우회 없음
            return {"ok": False, "error": str(e)[:300], "duration_ms": duration_ms(t0)}
        audit("GOOGLE_DOCS_RECENT", user, status="ok", note=f"source=api count={len(docs)}")
        return {"ok": True, "docs": docs, "count": len(docs), "duration_ms": duration_ms(t0), "source": "api"}

    def _fn(page):
        from scripts.google.docs_api import DocsAPI

        return DocsAPI(page).recent(limit=limit)

    docs, err = _cdp_call(_fn)
    if err:
        return {"ok": False, "error": err, "duration_ms": duration_ms(t0)}
    audit("GOOGLE_DOCS_RECENT", user, status="ok", note=f"source=cdp count={len(docs)}")
    return {"ok": True, "docs": docs, "count": len(docs), "duration_ms": duration_ms(t0), "source": "cdp"}


# ── Google Sheets ─────────────────────────────────────────────────────────────


@router.get("/sheets/recent")
def get_sheets_recent(
    limit: int = 15,
    source: str = "api",
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """최근 Google Sheets 목록. 2026-09-29: 기본을 OAuth Drive API로 전환(2단계). CDP는 fallback."""
    t0 = time.monotonic()

    if source == "api":
        try:
            from ai_orchestrator.connectors.google.drive_reader import list_recent_sheets

            sheets = list_recent_sheets(limit=limit)
        except Exception as e:  # noqa: BLE001 - Google 서비스 CDP/API 공용 헬퍼 - 연결/액션 실패 시 error 메시지 반환, 인증 우회 없음
            return {"ok": False, "error": str(e)[:300], "duration_ms": duration_ms(t0)}
        audit("GOOGLE_SHEETS_RECENT", user, status="ok", note=f"source=api count={len(sheets)}")
        return {"ok": True, "sheets": sheets, "count": len(sheets), "duration_ms": duration_ms(t0), "source": "api"}

    def _fn(page):
        from scripts.google.sheets_api import SheetsAPI

        return SheetsAPI(page).recent(limit=limit)

    sheets, err = _cdp_call(_fn)
    if err:
        return {"ok": False, "error": err, "duration_ms": duration_ms(t0)}
    audit("GOOGLE_SHEETS_RECENT", user, status="ok", note=f"source=cdp count={len(sheets)}")
    return {"ok": True, "sheets": sheets, "count": len(sheets), "duration_ms": duration_ms(t0), "source": "cdp"}


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
    except Exception as e:  # noqa: BLE001 - Google 서비스(Gmail/Calendar/YouTube Studio 등) CDP 브라우저 자동화 헬퍼 - 연결/액션 실패 시 None 또는 에러 메시지(200자 절단)를 반환하는 best-effort 폴백, 인증 우회나 정책 판정 없음
        return {"ok": False, "error": str(e)[:200], "duration_ms": duration_ms(t0)}


# ── GCP Console ───────────────────────────────────────────────────────────────


@router.get("/gcp/status")
def get_gcp_status(
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """GCP 프로젝트 상태 요약 (CDP)."""
    t0 = time.monotonic()

    def _fn(page):
        # GCP 콘솔은 백그라운드 폴링이 끊이지 않는 SPA라 기본 wait_until="load" 가
        # 절대 안 끝나 매번 20s 타임아웃(2026-09-29 실측 확인) — DOM 로드 시점까지만 대기.
        page.goto("https://console.cloud.google.com/?project=haehan-ai", timeout=45000, wait_until="domcontentloaded")
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
