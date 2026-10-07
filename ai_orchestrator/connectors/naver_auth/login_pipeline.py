"""네이버 로그인 파이프라인 (L6 Business Workflow).

1단계(우선): 로그인 → 브라우저 세션(쿠키/스토리지) 저장
2단계: 세션 상태 메타 저장 (status JSON)

세션은 기존 auth_session.save_session() 체계로 저장됩니다.
  저장: data/sessions/naver.com.json  (Fernet 암호화)
  복원: from scripts.auth.auth_session import restore_session
        restore_session('naver.com', page)
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from ai_orchestrator.paths.runtime import data_dir  # noqa: E402
from scripts.common.logger import get_logger  # noqa: E402

log = get_logger(__name__)

CDP_HOST = "127.0.0.1"
CDP_PORT = 9222

NAVER_SESSION_HOST = "naver.com"
SESSION_STATUS_FILE = data_dir() / "naver_session_state.json"

# 서브도메인별 개별 저장 대상 (각 도메인 쿠키를 분리 보관)
NAVER_SUBDOMAINS = [
    "naver.com",
    "nid.naver.com",
    "mail.naver.com",
    "cafe.naver.com",
    "smartstore.naver.com",
    "shopping.naver.com",
    "news.naver.com",
    "developers.naver.com",
    "smartplace.naver.com",
]


# ── 공개 인터페이스 ──────────────────────────────────────────────────────────


def load_session_status() -> dict:
    """저장된 세션 상태 메타를 반환합니다."""
    if not SESSION_STATUS_FILE.exists():
        return {"logged_in": False, "user": None, "checked_at": None}
    try:
        return json.loads(SESSION_STATUS_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 네이버 로그인 파이프라인 - 세션은 저장만 하고 로그아웃/쿠키삭제 없음, 실패시 _fail() 로 명확히 실패 반환
        return {"logged_in": False, "user": None, "checked_at": None}


def has_saved_browser_session() -> bool:
    """auth_session 저장소에 naver.com 세션이 있는지 확인합니다."""
    from scripts.auth.auth_session import list_sessions

    return any(s["host"] == NAVER_SESSION_HOST for s in list_sessions())


def list_naver_sessions() -> list[dict]:
    """저장된 네이버 서브도메인 세션 목록을 반환합니다."""
    from scripts.auth.auth_session import list_sessions

    saved = {s["host"]: s for s in list_sessions()}
    result = []
    for host in NAVER_SUBDOMAINS:
        if host in saved:
            result.append(saved[host])
    # 목록에 없는 추가 저장분도 포함 (동적으로 감지된 서브도메인)
    for s in list_sessions():
        if "naver.com" in s["host"] and s["host"] not in [r["host"] for r in result]:
            result.append(s)
    return result


def run_naver_login_pipeline(naver_id: str | None = None) -> dict:
    """CDP 시작 → 로그인 → 브라우저 세션 저장 → 상태 저장.

    우선순위: 로그인 성공 직후 실제 쿠키/스토리지를 먼저 저장하고,
    이후 상태 메타를 기록합니다.

    Returns:
        {"ok": bool, "logged_in": bool, "user": str|None, "message": str}
    """
    log.info("[naver_login_pipeline] 시작")

    # ── Step 1: CDP 시작 ────────────────────────────────────────────────────
    if not _is_cdp_alive():
        log.info("[naver_login_pipeline] CDP 미실행 — 시작 시도")
        try:
            _start_cdp()
        except Exception as e:  # noqa: BLE001 - 네이버 로그인 파이프라인 - 세션은 저장만 하고 로그아웃/쿠키삭제 없음, 실패시 _fail() 로 명확히 실패 반환
            return _fail(f"CDP 브라우저 시작 실패: {e}")

    # ── Step 2: 브라우저 연결 ────────────────────────────────────────────────
    pw, page, err = _connect_page()
    if err:
        return err

    # ── Step 3: 현재 로그인 상태 확인 (계정 전환 요청이면 건너뜀) ──────────────
    if not naver_id:
        early = _check_existing_login(page)
        if early:
            pw.stop()
            return early

    # ── Step 4: 네이버 로그인 ────────────────────────────────────────────────
    try:
        from scripts.naver.common.auth import login_naver

        result = login_naver(page, naver_id=naver_id)
    except Exception as e:  # noqa: BLE001 - 네이버 로그인 파이프라인 - 세션은 저장만 하고 로그아웃/쿠키삭제 없음, 실패시 _fail() 로 명확히 실패 반환
        pw.stop()
        return _fail(f"로그인 함수 오류: {e}")

    return _finish_login(pw, page, result)


# ── 내부 헬퍼 ────────────────────────────────────────────────────────────────


def _is_cdp_alive(timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://{CDP_HOST}:{CDP_PORT}/json/version", timeout=timeout) as r:
            return r.status == 200
    except Exception as exc:  # noqa: BLE001 - 네이버 로그인 파이프라인 - 세션은 저장만 하고 로그아웃/쿠키삭제 없음, 실패시 _fail() 로 명확히 실패 반환
        log.debug("CDP 가동 확인 실패: %s", type(exc).__name__)
        return False


def _start_cdp() -> None:
    from scripts.browser.cdp.cdp_force_start import cmd_start

    if cmd_start() != 0:
        raise RuntimeError("CDP 브라우저 시작 실패")


def _save_browser_session(page) -> None:
    """네이버 전체 쿠키를 통합 저장 + 서브도메인별 분리 저장."""
    from scripts.auth.auth_session import save_session

    # 1. naver.com 통합 저장 (전체 네이버 쿠키)
    save_session(NAVER_SESSION_HOST, page, host_filter=True)

    # 2. 브라우저에 실제 존재하는 서브도메인별 분리 저장
    ctx = page.context
    all_cookies = ctx.cookies()
    found_domains: set[str] = set()
    for c in all_cookies:
        d = (c.get("domain") or "").lstrip(".")
        if "naver.com" in d:
            found_domains.add(d)

    for subdomain in found_domains:
        if subdomain == NAVER_SESSION_HOST:
            continue  # 통합본과 중복 스킵
        try:
            save_session(subdomain, page, host_filter=True)
            log.info("[naver_login_pipeline] 서브도메인 세션 저장: %s", subdomain)
        except Exception as e:  # noqa: BLE001 - 네이버 로그인 파이프라인 - 세션은 저장만 하고 로그아웃/쿠키삭제 없음, 실패시 _fail() 로 명확히 실패 반환
            log.warning("[naver_login_pipeline] 서브도메인 세션 저장 실패 %s: %s", subdomain, e)


def _save_status(state: dict) -> None:
    SESSION_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_STATUS_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _connect_page():
    """CDP 브라우저에 연결해 (playwright, page, 오류결과) 를 돌려준다. 성공 시 오류결과는 None."""
    try:
        from playwright.sync_api import sync_playwright

        pw = sync_playwright().start()
        browser = pw.chromium.connect_over_cdp(f"http://{CDP_HOST}:{CDP_PORT}")

        ctx = None
        for _ in range(10):
            if browser.contexts:
                ctx = browser.contexts[0]
                break
            time.sleep(1)

        if not ctx:
            pw.stop()
            return None, None, _fail("브라우저 컨텍스트 없음")

        return pw, (ctx.pages[0] if ctx.pages else ctx.new_page()), None

    except Exception as e:  # noqa: BLE001 - 네이버 로그인 파이프라인 - 세션은 저장만 하고 로그아웃/쿠키삭제 없음, 실패시 _fail() 로 명확히 실패 반환
        return None, None, _fail(f"브라우저 연결 실패: {e}")


def _finish_login(pw, page, result: dict | None) -> dict:
    """로그인 결과 처리: CAPTCHA 대기 기록 → 세션 저장 → 상태 메타 저장 → 결과 반환."""
    logged_in = bool(result and result.get("ok"))
    user = result.get("user") if result else None

    # CAPTCHA — 세션 저장 불가, 대기 상태 기록
    if not logged_in and result and result.get("captcha_required"):
        _save_status({"logged_in": False, "user": None, "checked_at": _now(), "pending_captcha": True})
        pw.stop()
        return {
            "ok": False,
            "logged_in": False,
            "user": None,
            "captcha": True,
            "message": "CAPTCHA/2FA 감지 — 브라우저에서 직접 완료 후 다시 실행하세요",
        }

    # ── Step 5: 세션 저장 (로그인 성공 시 최우선) ─────────────────────────────
    if logged_in:
        try:
            _save_browser_session(page)
            log.info("[naver_login_pipeline] 브라우저 세션 저장 완료: data/sessions/naver.com.json")
        except Exception as e:  # noqa: BLE001 - 네이버 로그인 파이프라인 - 세션은 저장만 하고 로그아웃/쿠키삭제 없음, 실패시 _fail() 로 명확히 실패 반환
            log.warning("[naver_login_pipeline] 브라우저 세션 저장 실패: %s", e)

    # ── Step 6: 상태 메타 저장 ────────────────────────────────────────────────
    status = {
        "logged_in": logged_in,
        "user": user,
        "checked_at": _now(),
        "source": "login",
        "browser_session_saved": logged_in and has_saved_browser_session(),
    }
    if not logged_in:
        status["error"] = result.get("reason", "로그인 실패") if result else "로그인 실패"
    _save_status(status)

    log.info("[naver_login_pipeline] 완료: logged_in=%s user=%s", logged_in, user)
    pw.stop()

    return {
        "ok": logged_in,
        "logged_in": logged_in,
        "user": user,
        "message": f"로그인 성공, 세션 저장 완료: {user}" if logged_in else status.get("error", "로그인 실패"),
    }


def _check_existing_login(page) -> dict | None:
    """이미 로그인됨 → 성공 결과, 판정 불가(쿠키는 있는데 화면 근거 충돌) → 실패 결과, 그 외 None(로그인 진행)."""
    try:
        from scripts.auth.login_detector import detect_login_state

        current = detect_login_state(page)
        if current.get("logged_in"):
            user = current.get("user")
            log.info("[naver_login_pipeline] 이미 로그인됨: %s — 세션 저장", user)
            _save_browser_session(page)
            _save_status({"logged_in": True, "user": user, "checked_at": _now(), "source": "existing"})
            return {
                "ok": True,
                "logged_in": True,
                "user": user,
                "message": f"이미 로그인됨: {user} — 세션 저장 완료",
            }
        evidence = current.get("evidence") or {}
        if current.get("state") == "unknown" and evidence.get("session_cookie") is True:
            # 세션 쿠키는 있는데 화면 근거가 없거나 충돌 — 새로 로그인하면 기존 세션을 흔들 수 있어 멈추고 보고
            return _fail(f"로그인 상태 확인 불가(세션 쿠키는 있으나 화면 근거 충돌): {evidence}")
    except Exception as exc:  # noqa: BLE001 - 상태 확인 실패는 로그인 진행으로 넘김(종전 동작)
        log.warning("로그인 상태 사전 확인 실패: %s", type(exc).__name__)
        pass
    return None


def _fail(msg: str) -> dict:
    log.error("[naver_login_pipeline] %s", msg)
    _save_status({"logged_in": False, "user": None, "checked_at": _now(), "error": msg})
    return {"ok": False, "logged_in": False, "user": None, "message": msg}


def _now() -> str:
    return datetime.now(UTC).isoformat()
