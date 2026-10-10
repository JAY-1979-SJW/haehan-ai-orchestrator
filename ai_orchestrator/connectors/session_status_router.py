"""L8 — 앱별 로그인 세션 현황 API.

GET  /api/v1/sessions/status   — 최신 파일 읽기 (빠름)
POST /api/v1/sessions/refresh  — 모니터 스크립트 즉시 실행 후 결과 반환
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from ai_orchestrator.paths.runtime import data_dir

logger = logging.getLogger(__name__)

session_status_router = APIRouter(prefix="/sessions", tags=["sessions"])

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = data_dir() / "login_session_monitor_latest.json"

# 사이트별 메타 (아이콘, 색상)
_SITE_META: dict[str, dict] = {
    "naver": {"icon": "N", "color": "#03C75A", "label": "네이버"},
    "google": {"icon": "G", "color": "#4285F4", "label": "Google"},
    "smartstore": {"icon": "S", "color": "#F97316", "label": "스마트스토어"},
    "gabia": {"icon": "가", "color": "#1D4ED8", "label": "가비아"},
    "eum": {"icon": "공", "color": "#7C3AED", "label": "EUM"},
    "youtube_studio": {"icon": "YT", "color": "#DC2626", "label": "YouTube Studio"},
    "kakao": {"icon": "K", "color": "#FEE500", "label": "카카오"},
    "hiworks": {"icon": "H", "color": "#374151", "label": "하이웍스"},
    "dataportal": {"icon": "공", "color": "#0891B2", "label": "공공데이터포털"},
}


class SiteStatus(BaseModel):
    key: str
    label: str
    icon: str
    color: str
    status: str  # LOGGED_IN | SESSION_EXPIRED | LOGIN_REQUIRED | CHALLENGE | ERROR | NO_TAB
    detail: str
    href: str
    has_session_cookie: bool
    checked_at: str
    login_url: str


class SessionStatusResponse(BaseModel):
    checked_at: str
    cdp_available: bool
    sites: list[SiteStatus]


_LOGIN_URLS: dict[str, str] = {
    "naver": "https://nid.naver.com/nidlogin.login",
    "google": "https://accounts.google.com/signin",
    "smartstore": "https://sell.smartstore.naver.com/",
    "gabia": "https://account.gabia.com/gabia/login",
    "eum": "https://eum.cw.or.kr/web/log/WEBLOG400M00",
    "youtube_studio": "https://studio.youtube.com/",
    "kakao": "https://accounts.kakao.com/login",
    "hiworks": "https://www.hiworks.com/login",
    "dataportal": "https://www.data.go.kr/login/loginForm.do",
}


def _load_file() -> dict | None:
    if not DATA_PATH.exists():
        return None
    try:
        return json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 세션 상태 조회 라우터 -- 읽기 전용, 파일 파싱 실패는 None, 프로버 실패는 마지막 저장 결과 파일로 폴백
        return None


def _build_response(data: dict) -> SessionStatusResponse:
    sites_raw = data.get("sites", [])
    sites = []
    for s in sites_raw:
        key = s.get("key", "")
        meta = _SITE_META.get(key, {"icon": "?", "color": "#6B7280", "label": s.get("label", key)})
        sites.append(
            SiteStatus(
                key=key,
                label=meta["label"],
                icon=meta["icon"],
                color=meta["color"],
                status=s.get("status", "ERROR"),
                detail=s.get("detail", ""),
                href=s.get("href", ""),
                has_session_cookie=bool(s.get("has_session_cookie")),
                checked_at=s.get("checked_at", ""),
                login_url=_LOGIN_URLS.get(key, ""),
            )
        )

    # 파일에 없는 사이트 채우기 (아직 실행 안 된 경우)
    existing_keys = {s.key for s in sites}
    for key, meta in _SITE_META.items():
        if key not in existing_keys:
            sites.append(
                SiteStatus(
                    key=key,
                    label=meta["label"],
                    icon=meta["icon"],
                    color=meta["color"],
                    status="UNKNOWN",
                    detail="아직 확인 안 됨 — 새로고침을 눌러주세요",
                    href="",
                    has_session_cookie=False,
                    checked_at="",
                    login_url=_LOGIN_URLS.get(key, ""),
                )
            )

    return SessionStatusResponse(
        checked_at=data.get("checked_at", ""),
        cdp_available=bool(data.get("cdp_available")),
        sites=sites,
    )


@session_status_router.get("/status", response_model=SessionStatusResponse)
def get_session_status():
    """최신 세션 파일 반환 (빠름, 파일 없으면 UNKNOWN)."""
    data = _load_file()
    if not data:
        now = datetime.now(UTC).isoformat()
        empty: dict = {"checked_at": now, "cdp_available": False, "sites": []}
        return _build_response(empty)
    return _build_response(data)


@session_status_router.post("/refresh", response_model=SessionStatusResponse)
def refresh_session_status():
    """모든 사이트를 즉시 능동 점검하고 결과 반환.

    frozen exe 에서는 sys.executable 이 python 이 아니라 subprocess 로 모니터를 못 돌리므로,
    in-process 프로버(session_probe.probe_all)로 직접 점검한다.
    """
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        from tools.runtime.session_probe import probe_all

        data = probe_all()
    except Exception as exc:  # noqa: BLE001 - 세션 상태 조회 라우터 -- 읽기 전용, 파일 파싱 실패는 None, 프로버 실패는 마지막 저장 결과 파일로 폴백
        logger.warning("세션 프로버 실행(파일 폴백) 실패: %s", type(exc).__name__)
        # 프로버 실패 시 마지막 결과 파일로 폴백
        data = _load_file() or {"checked_at": "", "cdp_available": False, "sites": []}
    return _build_response(data)
