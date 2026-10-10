"""CDP 프로필 세션 관리 — 진단/백업/리셋/로그인 자동 감지."""

from __future__ import annotations

import os
import shutil
import sqlite3
import time
import zipfile
from datetime import datetime
from pathlib import Path

from scripts.common.cdp_audit import L2, L3
from ai_orchestrator.paths.runtime import data_dir

PROFILE_ROOT = data_dir() / "cdp_profile"
ACTOR = "session_manager"

# 사이트별 인증 쿠키 마커 — 등장 시 로그인 완료로 판정
# 추가 사이트는 도메인:[쿠키명, ...] 형식으로 등록
LOGIN_MARKERS: dict[str, list[str]] = {
    "naver.com": ["NID_AUT", "NID_SES"],
    "blog.naver.com": ["NID_AUT", "NID_SES"],
    "cafe.naver.com": ["NID_AUT", "NID_SES"],
    "mail.naver.com": ["NID_AUT", "NID_SES"],
    "calendar.naver.com": ["NID_AUT", "NID_SES"],
    "mybox.naver.com": ["NID_AUT", "NID_SES"],
    "g2b.go.kr": ["JSESSIONID"],
    "developer.hancom.com": ["JSESSIONID"],
    "github.com": ["user_session", "logged_in"],
    "google.com": ["SID", "HSID"],
}


def get_profile_dir() -> Path:
    return PROFILE_ROOT


def is_session_initialized() -> bool:
    cookies_db = PROFILE_ROOT / "Default" / "Cookies"
    if not cookies_db.exists():
        return False
    try:
        with sqlite3.connect(f"file:{cookies_db}?mode=ro", uri=True) as con:
            cur = con.execute("SELECT COUNT(*) FROM cookies")
            return cur.fetchone()[0] > 0
    except Exception:  # noqa: BLE001 - CDP 프로필 세션 진단 -- 쿠키 개수/도메인 조회 실패 시 False/빈 리스트 반환(읽기 전용, 쿠키 값 자체를 로그·반환값에 노출하지 않음)
        return False


def get_logged_in_sites() -> list[str]:
    cookies_db = PROFILE_ROOT / "Default" / "Cookies"
    if not cookies_db.exists():
        return []
    try:
        with sqlite3.connect(f"file:{cookies_db}?mode=ro", uri=True) as con:
            cur = con.execute("SELECT DISTINCT host_key FROM cookies ORDER BY host_key")
            return [row[0].lstrip(".") for row in cur.fetchall()]
    except sqlite3.OperationalError:
        return []


def backup_session(dest_dir: Path | None = None) -> Path:
    dest_dir = dest_dir or (PROFILE_ROOT.parent / "cdp_profile_backups")
    dest_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = dest_dir / f"cdp_profile_{ts}.zip"
    size = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in PROFILE_ROOT.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(PROFILE_ROOT))
                size += p.stat().st_size
    L2("SESSION_BACKUP", ACTOR, dest=str(out), size_bytes=size)
    return out


def get_cdp_cookies(host: str = "127.0.0.1", port: int = 9222) -> list[dict]:
    """Playwright로 활성 컨텍스트의 쿠키 조회 (DB 락 회피, 실시간 반영).

    sqlite 직접 조회와 달리 Chrome 실행 중에도 안정적으로 작동.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(f"http://{host}:{port}")
            ctx = browser.contexts[0] if browser.contexts else None
            return list(ctx.cookies()) if ctx else []
    except Exception:  # noqa: BLE001 - CDP 프로필 세션 진단 -- 쿠키 개수/도메인 조회 실패 시 False/빈 리스트 반환(읽기 전용, 쿠키 값 자체를 로그·반환값에 노출하지 않음)
        return []


def is_logged_in(domain: str, host: str = "127.0.0.1", port: int = 9222) -> bool:
    """도메인 인증 쿠키 마커 등장 여부 판정.

    LOGIN_MARKERS에 등록된 쿠키 중 1개 이상이 해당 도메인으로 존재하면 True.
    """
    markers = LOGIN_MARKERS.get(domain, [])
    if not markers:
        # 마커 미등록 도메인 — 도메인의 쿠키 1개 이상 있으면 True (보수적)
        cookies = get_cdp_cookies(host, port)
        return any(domain in (c.get("domain", "") or "") for c in cookies)

    cookies = get_cdp_cookies(host, port)
    found = {c.get("name", "") for c in cookies if domain in (c.get("domain", "") or "")}
    return any(m in found for m in markers)


def wait_for_login(
    domain: str,
    timeout: int = 300,
    poll_interval: float = 2.0,
    host: str = "127.0.0.1",
    port: int = 9222,
) -> bool:
    """로그인 자동 감지 — 인증 쿠키 등장까지 폴링.

    Args:
        domain: 감시할 도메인 (예: 'naver.com')
        timeout: 최대 대기 시간 (초). 기본 5분
        poll_interval: 폴링 주기 (초)

    Returns:
        True: 로그인 감지됨 / False: 타임아웃
    """
    t0 = time.time()
    L3("LOGIN_WAIT_START", ACTOR, domain=domain, timeout=timeout)
    deadline = t0 + timeout
    last_cookie_count = 0

    while time.time() < deadline:
        if is_logged_in(domain, host, port):
            elapsed = int(time.time() - t0)
            L3("LOGIN_DETECTED", ACTOR, domain=domain, elapsed_s=elapsed)
            return True

        # 진행 상황 보고 (쿠키 수 변화 시)
        cookies = get_cdp_cookies(host, port)
        cnt = len([c for c in cookies if domain in (c.get("domain", "") or "")])
        if cnt != last_cookie_count:
            L3("LOGIN_PROGRESS", ACTOR, domain=domain, cookie_count=cnt, elapsed_s=int(time.time() - t0))
            last_cookie_count = cnt

        time.sleep(poll_interval)

    L3("LOGIN_TIMEOUT", ACTOR, domain=domain, timeout=timeout)
    return False


def reset_session(confirm: bool = True) -> None:
    if not confirm:
        raise ValueError("reset_session은 confirm=True 명시 필요")
    size_before = sum(p.stat().st_size for p in PROFILE_ROOT.rglob("*") if p.is_file()) if PROFILE_ROOT.exists() else 0
    L3("SESSION_RESET", ACTOR, confirmed_by=os.environ.get("USERNAME", ""), profile_size_before=size_before)
    if PROFILE_ROOT.exists():
        shutil.rmtree(PROFILE_ROOT)
