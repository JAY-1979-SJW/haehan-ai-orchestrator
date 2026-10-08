"""Google Drive API 조회 — CDP DriveAPI(scripts/google/drive_api.py) 대체.

Docs/Sheets "최근 목록"도 여기서 처리한다 — Docs API/Sheets API는 문서 "내용"을
다루는 API고, "최근 목록"은 실제로는 Drive의 파일 목록(mimeType 필터)이라 Drive API
하나로 셋 다 커버된다(공식 가이드 확인, 2026-09-29).

L3 Connectors 계층. drive.readonly 스코프(google_oauth.py 공용 자격증명).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_MIME_DOC = "application/vnd.google-apps.document"
_MIME_SHEET = "application/vnd.google-apps.spreadsheet"


def _list_files(query: str | None, limit: int) -> list[dict]:
    from ai_orchestrator.connectors.google import oauth as google_oauth

    service = google_oauth.build_service("drive", "v3")
    kwargs: dict = {
        "pageSize": limit,
        "orderBy": "modifiedTime desc",
        "fields": "files(id, name, mimeType, webViewLink, modifiedTime)",
    }
    if query:
        kwargs["q"] = query
    response = service.files().list(**kwargs).execute()
    return [
        {
            "name": f.get("name", ""),
            "id": f.get("id", ""),
            "url": f.get("webViewLink", ""),
            "modified_time": f.get("modifiedTime", ""),
        }
        for f in response.get("files", [])
    ]


def list_recent(limit: int = 20) -> list[dict]:
    """최근 파일(전체 타입)."""
    return _list_files(None, limit)


def list_recent_docs(limit: int = 15) -> list[dict]:
    """최근 Google Docs 문서 목록."""
    return _list_files(f"mimeType='{_MIME_DOC}' and trashed=false", limit)


def list_recent_sheets(limit: int = 15) -> list[dict]:
    """최근 Google Sheets 목록."""
    return _list_files(f"mimeType='{_MIME_SHEET}' and trashed=false", limit)
