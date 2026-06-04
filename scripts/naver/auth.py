"""네이버 ID/PW 자동 로그인 모듈.

네이버는 자동화 봇 감지가 강하므로:
  - 사람처럼 천천히 타이핑
  - 캡차/2차인증 감지 시 사용자에게 위임
  - 보안문자 등장 시 즉시 중단 + 사용자 알림

자격증명 우선순위:
  1. 함수 파라미터 (id, pw)
  2. 환경변수 (NAVER_ID, NAVER_PW)
  3. .env 파일 (data/.env_naver)

사용:
  from scripts.naver.auth import login_naver
  from scripts.web_connector import get_page

  page = get_page()
  result = login_naver(page)  # 환경변수/파일 사용
  # 또는: login_naver(page, naver_id="...", naver_pw="...")
  # 결과: {ok, user, reason}
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from scripts.critical_logger import log_critical
from scripts.logger import get_logger
from scripts.login_detector import detect_login_state, wait_for_login_generic

_log = get_logger(__name__)

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / "data" / ".env_naver"

NAVER_LOGIN_URL = "https://www.naver.com/"


# ── 자격증명 로드 ──────────────────────────────────────────────────────────


def _load_credentials(
    naver_id: str | None = None,
    naver_pw: str | None = None,
) -> tuple[str | None, str | None]:
    """ID/PW 조회. 파라미터 → 통합 저장소(credentials.json, 암호화) → 환경변수 → 레거시 파일."""
    nid = naver_id
    pw = naver_pw

    # 1. 통합 저장소 (암호화)
    if not nid or not pw:
        try:
            from scripts.credentials import get_cred

            cred = get_cred("naver")
            if not nid and cred.get("id"):
                nid = cred["id"]
            if not pw and cred.get("pw"):
                pw = cred["pw"]
        except Exception as e:
            _log.debug("통합 자격증명 로드 실패: %s", e)

    # 2. 환경변수
    if not nid:
        nid = os.environ.get("NAVER_ID")
    if not pw:
        pw = os.environ.get("NAVER_PW")

    # 3. 레거시 평문 파일 (백업 경로)
    if (not nid or not pw) and ENV_FILE.exists():
        try:
            for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k == "NAVER_ID" and not nid:
                    nid = v
                elif k == "NAVER_PW" and not pw:
                    pw = v
        except Exception as e:
            _log.debug("자격증명 파일 읽기 실패: %s", e)

    return nid, pw


def save_credentials(naver_id: str, naver_pw: str) -> Path:
    """자격증명 파일 저장 (data/.env_naver). git ignore 필수.

    파일 권한: 0o600 (소유자만 읽기/쓰기)
    """
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    content = f"NAVER_ID={naver_id}\nNAVER_PW={naver_pw}\n"
    ENV_FILE.write_text(content, encoding="utf-8")
    try:
        os.chmod(ENV_FILE, 0o600)
    except Exception:
        pass
    _log.info("[naver-auth] 자격증명 저장: %s", ENV_FILE)
    return ENV_FILE


# ── 봇 감지 회피 타이핑 + 안전 입력 ────────────────────────────────────────


def _safe_human_input(page, selector: str, value: str, label: str = "필드", delay_ms: int = 80) -> dict:
    """입력 전 필드 검사 → 기존 값 처리 후 사람처럼 타이핑.

    동작:
      1. 현재 입력 값 확인
      2. 비어있음 → 바로 입력
      3. 같은 값 → skip
      4. 다른 값 → 전체 선택 + 삭제 후 새 값 입력
      5. 입력 후 검증 (실제 값이 들어갔는지)

    Returns:
        {ok, action: "skip"|"empty"|"replaced", before, after}
    """
    try:
        el = page.locator(selector).first
        try:
            el.wait_for(state="visible", timeout=5000)
        except Exception:
            # Naver can report the input as visible in the call log while
            # wait_for still times out during dynamic security script setup.
            if not el.is_visible(timeout=1000):
                raise

        # 1. 현재 값 확인
        current = ""
        try:
            current = el.input_value(timeout=1500) or ""
        except Exception:
            pass

        # 2. 분기
        if current == value:
            _log.info("[naver-auth] %s 동일 값 — skip", label)
            return {"ok": True, "action": "skip", "before": current, "after": current}

        if current:
            # 다른 값 있음 → 전체 선택 + 삭제
            _log.warning("[naver-auth] %s 에 다른 값 존재 (%d자) — 삭제 후 재입력", label, len(current))
            el.click(timeout=2000)
            time.sleep(0.3)
            page.keyboard.press("Control+a")
            time.sleep(0.15)
            page.keyboard.press("Delete")
            time.sleep(0.3)
            # 삭제 확인
            after_clear = ""
            try:
                after_clear = el.input_value(timeout=1000) or ""
            except Exception:
                pass
            if after_clear:
                # 여전히 남아있으면 fill로 한번 더
                try:
                    el.fill("", timeout=1500)
                except Exception:
                    pass
            action = "replaced"
        else:
            action = "empty"

        # 3. 새 값 입력 (사람처럼 한 글자씩)
        el.click(timeout=2000)
        time.sleep(0.4)
        for ch in value:
            page.keyboard.type(ch, delay=delay_ms)
        time.sleep(0.3)

        # 4. 입력 검증
        final = ""
        try:
            final = el.input_value(timeout=1500) or ""
        except Exception:
            pass

        if final != value:
            _log.warning("[naver-auth] %s 입력 검증 실패 (기대=%d자, 실제=%d자)", label, len(value), len(final))
            return {"ok": False, "action": action, "before": current, "after": final, "reason": "value_mismatch"}

        _log.info("[naver-auth] %s 입력 완료 (%s, %d자)", label, action, len(value))
        return {"ok": True, "action": action, "before": current, "after": final}

    except Exception as e:
        _log.error("[naver-auth] %s 입력 실패: %s", label, e)
        return {"ok": False, "action": "error", "reason": str(e)[:80]}


def _redact_input_result(result: dict) -> dict:
    """Remove raw credential values from a safe_human_input result."""
    redacted = dict(result)
    for key in ("before", "after"):
        if key in redacted:
            value = str(redacted.get(key) or "")
            redacted[f"{key}_len"] = len(value)
            redacted[key] = "[REDACTED]" if value else ""
    return redacted


def _human_type(page, selector: str, text: str, delay_ms: int = 80) -> None:
    """[deprecated] _safe_human_input 사용 권장. 호환성 유지용."""
    el = page.locator(selector).first
    el.click(timeout=3000)
    time.sleep(0.4)
    for ch in text:
        page.keyboard.type(ch, delay=delay_ms)


# ── 캡차/보안문자 감지 ─────────────────────────────────────────────────────


def _submit_login_form(page) -> dict:
    """Submit the login form with fallbacks for unstable animated buttons."""
    selector = '.btn_login, #log\\.login, button[type="submit"]'
    try:
        page.locator(selector).first.click(timeout=3000)
        return {"ok": True, "method": "click"}
    except Exception as click_error:
        _log.warning("[naver-auth] login button normal click failed: %s", str(click_error)[:120])

    try:
        clicked = page.evaluate(
            """() => {
                const btn = document.querySelector('.btn_login, #log\\\\.login, button[type="submit"]');
                if (!btn) return false;
                btn.click();
                return true;
            }"""
        )
        if clicked:
            return {"ok": True, "method": "js_click"}
    except Exception as js_error:
        _log.warning("[naver-auth] login button js click failed: %s", str(js_error)[:120])

    try:
        page.locator("#pw").press("Enter", timeout=2000)
        return {"ok": True, "method": "enter"}
    except Exception as enter_error:
        return {"ok": False, "reason": str(enter_error)[:120]}


def _open_login_from_naver_main(page) -> dict:
    """Start Naver login from www.naver.com, then wait for the login form."""
    page.goto(NAVER_LOGIN_URL, timeout=15000, wait_until="domcontentloaded")
    time.sleep(1.0)

    try:
        if page.locator("#id").first.is_visible(timeout=1000):
            return {"ok": True, "method": "already_on_login_form"}
    except Exception:
        pass

    selectors = (
        "a[href*='nid.naver.com/nidlogin.login']",
        "a.MyView-module__link_login___HpHMW",
        "a.link_login",
        "#account a",
        "#gnb_login_button",
    )
    for selector in selectors:
        try:
            el = page.locator(selector).first
            if not el.is_visible(timeout=1000):
                continue
            el.click(timeout=3000)
            page.locator("#id").first.wait_for(state="visible", timeout=10000)
            return {"ok": True, "method": f"click:{selector}"}
        except Exception:
            continue

    return {"ok": False, "reason": "login_link_not_found"}


def _detect_captcha(page) -> bool:
    """캡차/보안문자/2차인증 감지."""
    try:
        return page.evaluate("""
        (() => {
            const txt = (document.body?.innerText || '').toLowerCase();
            if (/캡차|보안문자|captcha|2단계|2차\\s*인증|otp|일회용/i.test(txt)) return true;
            // 이미지 input
            if (document.querySelector('img[id*="captcha"], img[src*="captcha"]')) return true;
            return false;
        })();
        """)
    except Exception:
        return False


# ── 메인 로그인 함수 ────────────────────────────────────────────────────────


def login_naver(
    page,
    naver_id: str | None = None,
    naver_pw: str | None = None,
    wait_for_user_s: int = 300,
    force_relogin: bool = False,
) -> dict[str, Any]:
    """네이버 ID/PW 로그인.

    Args:
        page: Playwright Page
        naver_id: 네이버 ID (없으면 환경변수/파일 조회)
        naver_pw: 네이버 PW (동일)
        wait_for_user_s: 캡차 등 발생 시 사용자 수동 처리 대기 시간

    Returns:
        {ok, user, reason, captcha_required}
    """
    # 1. 자격증명
    nid, pw = _load_credentials(naver_id, naver_pw)
    if not nid or not pw:
        return {
            "ok": False,
            "reason": "no_credentials",
            "hint": "환경변수 NAVER_ID/NAVER_PW 또는 data/.env_naver 파일 필요",
        }

    log_critical("AUTH_SUCCESS", "네이버 로그인 시도", user=nid, mode="auto_login_start")

    # 2. 이미 로그인 상태 확인 (같은 사용자/다른 사용자)
    try:
        state = detect_login_state(page)
        if state.get("logged_in") and "naver" in page.url and not force_relogin:
            current_user = state.get("user", "")
            if (current_user and nid in current_user) or current_user == nid:
                _log.info("[naver-auth] 동일 사용자 이미 로그인됨: %s", current_user)
                return {"ok": True, "user": current_user, "reason": "already_logged_in"}
            else:
                _log.warning("[naver-auth] 다른 사용자 로그인 상태: %s (목표: %s)", current_user, nid)
                # 로그아웃 후 재로그인 필요
                # 일단 알림 후 진행 (사용자가 결정)
                return {
                    "ok": False,
                    "reason": "different_user_logged_in",
                    "current_user": current_user,
                    "target_user": nid,
                    "hint": "현재 다른 사용자로 로그인됨. 먼저 로그아웃 필요.",
                }
    except Exception:
        pass

    # 3. 로그인 페이지 진입
    _log.info("[naver-auth] 로그인 페이지 진입")
    entry_result = _open_login_from_naver_main(page)
    if not entry_result.get("ok"):
        return {
            "ok": False,
            "reason": f"login_entry_failed:{entry_result.get('reason', 'unknown')}",
            "needs_manual": True,
            "current_url": page.url,
        }
    time.sleep(1)

    # 4. ID/PW 입력 — 안전 입력 (기존 자동완성 값 처리)
    id_result = _safe_human_input(page, "#id", nid, label="ID", delay_ms=70)
    if not id_result["ok"]:
        _log.error("[naver-auth] ID 입력 실패: %s", id_result.get("reason"))
        return {"ok": False, "reason": f"id_input_failed:{id_result.get('reason', 'unknown')}", "id_result": id_result}
    time.sleep(0.6)

    pw_result = _safe_human_input(page, "#pw", pw, label="PW", delay_ms=80)
    if not pw_result["ok"]:
        _log.error("[naver-auth] PW 입력 실패: %s", pw_result.get("reason"))
        return {
            "ok": False,
            "reason": f"pw_input_failed:{pw_result.get('reason', 'unknown')}",
            "pw_result": _redact_input_result(pw_result),
        }
    time.sleep(0.5)

    _log.info("[naver-auth] 입력 완료 — ID:%s, PW:%s", id_result["action"], pw_result["action"])

    # 5. 로그인 버튼 클릭
    try:
        submit_result = _submit_login_form(page)
        if not submit_result.get("ok"):
            raise RuntimeError(submit_result.get("reason", "submit_failed"))
        time.sleep(3)
    except Exception as e:
        _log.error("[naver-auth] 로그인 버튼 클릭 실패: %s", e)
        return {"ok": False, "reason": f"submit_failed:{str(e)[:60]}"}

    # 6. 캡차/2차인증 감지
    if _detect_captcha(page):
        _log.warning("[naver-auth] 캡차/2차인증 감지 → 사용자 수동 처리 대기")
        log_critical("AUTH_FAIL", "네이버 로그인 캡차/2차인증", user=nid, mode="captcha_detected")
        # 사용자가 수동으로 처리할 때까지 대기
        state = wait_for_login_generic(page, max_wait_s=wait_for_user_s, poll_interval=3.0)
        if state.get("logged_in"):
            user = state.get("user") or nid
            log_critical("AUTH_SUCCESS", "네이버 로그인 성공 (사용자 처리)", user=user, mode="auto_login_done_manual")
            return {"ok": True, "user": user, "reason": "user_handled_captcha"}
        return {"ok": False, "reason": "captcha_timeout", "captcha_required": True, "needs_manual": True}

    # 7. 일반 성공 검증
    time.sleep(2)
    state = detect_login_state(page)
    if state.get("logged_in"):
        user = state.get("user") or nid
        _log.info("[naver-auth] 로그인 성공: %s", user)
        log_critical("AUTH_SUCCESS", "네이버 로그인 성공", user=user, mode="auto_login_done")
        return {"ok": True, "user": user, "reason": "ok"}

    # 8. 실패
    # URL이 여전히 로그인 페이지면 실패
    if "nidlogin" in page.url or "login" in page.url:
        log_critical("AUTH_FAIL", "네이버 로그인 실패", user=nid, mode="auto_login_fail")
        return {"ok": False, "reason": "credential_or_blocked", "current_url": page.url, "needs_manual": True}

    # 9. 점수 낮아도 다른 페이지로 이동했으면 일단 ok
    return {"ok": state.get("score", 0) >= 2, "user": state.get("user"), "reason": "ambiguous"}


def ensure_naver_login(
    page,
    naver_id: str | None = None,
    naver_pw: str | None = None,
    return_url: str | None = None,
) -> dict[str, Any]:
    """현재 페이지의 네이버 도메인 로그인 확인 → 미로그인이면 자동 로그인 → 원래 페이지 복귀."""
    # 현재 페이지가 네이버 도메인이 아니면 로그인 판정 전에 네이버로 이동
    # (호출처가 about:blank/타 사이트에 있어도 쿠키 기반 로그인을 올바로 감지하기 위함)
    try:
        _cur = page.url or ""
    except Exception:
        _cur = ""
    if "naver.com" not in _cur:
        try:
            page.goto("https://www.naver.com/", timeout=20000, wait_until="domcontentloaded")
            time.sleep(1)
        except Exception:
            pass

    state = detect_login_state(page)
    if state.get("logged_in"):
        return {"ok": True, "user": state.get("user"), "reason": "already_logged_in"}

    original_url = return_url or page.url

    # ── 순차 인증창 게이트 (SSO 우선) ──────────────────────────────────────────
    # 네이버 세션이 있으면 커머스 SSO(간편 로그인)를 자동 클릭한다. 그 결과 2단계 인증(2FA)·
    # 캡차가 뜨면 자동 입력이 불가능한 보안 단계이므로 명확한 사유로 반환(섹션 실패로 묻히지 않게).
    try:
        from scripts.naver.auth_window_gate import (
            STAGE_CAPTCHA,
            STAGE_LOGGED_IN,
            STAGE_TWO_FACTOR,
            advance_once,
        )

        step = advance_once(page)
        if step.get("action") == "sso_clicked":
            time.sleep(5)
            step = advance_once(page)
            if step.get("action") == "wait_callback":
                time.sleep(4)
                step = advance_once(page)
        if step.get("stage") == STAGE_LOGGED_IN and detect_login_state(page).get("logged_in"):
            ls = detect_login_state(page)
            return {"ok": True, "user": ls.get("user"), "reason": "sso_logged_in"}
        if step.get("stage") in (STAGE_TWO_FACTOR, STAGE_CAPTCHA):
            reason = "two_factor_required" if step["stage"] == STAGE_TWO_FACTOR else "captcha_required"
            _log.warning("[naver-auth] 인증창 게이트: %s → 사용자 입력 대기", reason)
            return {
                "ok": False,
                "reason": reason,
                "needs_user": True,
                "hint": step.get("hint"),
                "captcha_required": step["stage"] == STAGE_CAPTCHA,
            }
    except Exception as e:
        _log.debug("[naver-auth] auth-gate 스킵: %s", str(e)[:100])

    # ── fallback: 기존 자격증명 기반 로그인 ────────────────────────────────────
    result = login_naver(page, naver_id, naver_pw)
    if not result["ok"]:
        return result

    # 원래 페이지 복귀
    if original_url and "nidlogin" not in original_url:
        try:
            page.goto(original_url, timeout=15000, wait_until="domcontentloaded")
            time.sleep(2)
        except Exception:
            pass
    return result
