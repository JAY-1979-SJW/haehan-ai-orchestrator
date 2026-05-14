"""Google ID/PW 자동 로그인 모듈 (네이버 auth.py 동일 패턴).

Google 로그인 특성:
  - 2단계: ID 입력 → Next → PW 입력 → Next
  - 봇 감지 강함 (사람처럼 천천히 타이핑)
  - 2단계 인증(2FA) 거의 필수 → 사용자에게 위임
  - "이 기기를 기억" 화면 등 추가 단계 자동 처리

자격증명 우선순위:
  1. 함수 파라미터 (google_id, google_pw)
  2. 환경변수 (GOOGLE_ID, GOOGLE_PW)
  3. .env 파일 (data/.env_google)

사용:
  from scripts.google.auth import login_google, ensure_google_login
  from scripts.web_connector import get_page

  page = get_page()
  result = login_google(page)  # 환경변수/파일 사용
  # 또는: login_google(page, google_id="...", google_pw="...")
  # 결과: {ok, user, reason, captcha_required}
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from scripts.logger import get_logger
from scripts.critical_logger import log_critical
from scripts.login_detector import detect_login_state, wait_for_login_generic

_log = get_logger(__name__)

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / "data" / ".env_google"

GOOGLE_LOGIN_URL = "https://accounts.google.com/signin"


# ── 자격증명 로드 ──────────────────────────────────────────────────────────

def _load_credentials(
    google_id: str | None = None,
    google_pw: str | None = None,
) -> tuple[str | None, str | None]:
    """ID/PW 조회. 파라미터 → 통합 저장소(credentials.json, 암호화) → 환경변수 → 레거시 파일."""
    gid = google_id
    pw = google_pw

    # 1. 통합 저장소 (암호화)
    if not gid or not pw:
        try:
            from scripts.credentials import get_cred
            cred = get_cred("google")
            if not gid and cred.get("id"):
                gid = cred["id"]
            if not pw and cred.get("pw"):
                pw = cred["pw"]
        except Exception as e:
            _log.debug("통합 자격증명 로드 실패: %s", e)

    # 2. 환경변수
    if not gid:
        gid = os.environ.get("GOOGLE_ID")
    if not pw:
        pw = os.environ.get("GOOGLE_PW")

    # 3. 레거시 평문 파일 (백업 경로)
    if (not gid or not pw) and ENV_FILE.exists():
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
                if k == "GOOGLE_ID" and not gid:
                    gid = v
                elif k == "GOOGLE_PW" and not pw:
                    pw = v
        except Exception as e:
            _log.debug("자격증명 파일 읽기 실패: %s", e)

    return gid, pw


def save_credentials(google_id: str, google_pw: str) -> Path:
    """자격증명 파일 저장 (data/.env_google). git ignore 필수."""
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    content = f"GOOGLE_ID={google_id}\nGOOGLE_PW={google_pw}\n"
    ENV_FILE.write_text(content, encoding="utf-8")
    try:
        os.chmod(ENV_FILE, 0o600)
    except Exception:
        pass
    _log.info("[google-auth] 자격증명 저장: %s", ENV_FILE)
    return ENV_FILE


# ── 안전 입력 (기존 값 확인 → 다르면 교체) ─────────────────────────────────

def _safe_human_input(page, selector: str, value: str,
                      label: str = "필드", delay_ms: int = 90) -> dict:
    """입력 전 필드 검사 → 기존 값 처리 후 사람처럼 타이핑.

    네이버 auth와 동일한 알고리즘:
      1. 현재 값 확인
      2. 같은 값 → skip
      3. 다른 값 → Ctrl+A + Delete → 재입력
      4. 입력 후 검증
    """
    try:
        el = page.locator(selector).first
        el.wait_for(state="visible", timeout=8000)

        current = ""
        try:
            current = el.input_value(timeout=1500) or ""
        except Exception:
            pass

        if current == value:
            _log.info("[google-auth] %s 동일 값 — skip", label)
            return {"ok": True, "action": "skip", "before": current, "after": current}

        if current:
            _log.warning("[google-auth] %s 에 다른 값 존재 (%d자) — 삭제 후 재입력", label, len(current))
            el.click(timeout=2000)
            time.sleep(0.3)
            page.keyboard.press("Control+a")
            time.sleep(0.15)
            page.keyboard.press("Delete")
            time.sleep(0.3)
            after_clear = ""
            try:
                after_clear = el.input_value(timeout=1000) or ""
            except Exception:
                pass
            if after_clear:
                try:
                    el.fill("", timeout=1500)
                except Exception:
                    pass
            action = "replaced"
        else:
            action = "empty"

        # 사람처럼 한 글자씩
        el.click(timeout=2000)
        time.sleep(0.4)
        for ch in value:
            page.keyboard.type(ch, delay=delay_ms)
        time.sleep(0.3)

        final = ""
        try:
            final = el.input_value(timeout=1500) or ""
        except Exception:
            pass

        if final != value:
            _log.warning("[google-auth] %s 입력 검증 실패 (기대=%d자, 실제=%d자)",
                         label, len(value), len(final))
            return {"ok": False, "action": action, "before": current, "after": final,
                    "reason": "value_mismatch"}

        _log.info("[google-auth] %s 입력 완료 (%s, %d자)", label, action, len(value))
        return {"ok": True, "action": action, "before": current, "after": final}

    except Exception as e:
        _log.error("[google-auth] %s 입력 실패: %s", label, e)
        return {"ok": False, "action": "error", "reason": str(e)[:80]}


# ── 2FA / 보안검증 감지 ────────────────────────────────────────────────────

def _detect_2fa_or_challenge(page) -> tuple[bool, str]:
    """Google 2FA / 보안검증 / 캡차 감지.

    Returns: (감지여부, 사유)
    """
    try:
        result = page.evaluate("""
        (() => {
            const txt = (document.body?.innerText || '').toLowerCase();
            const url = location.href.toLowerCase();
            // 2단계 인증
            if (/2.?step|2.?단계|verify it'?s you|본인 확인|보안 인증|otp|일회용/i.test(txt)) {
                return ['2fa', '2단계 인증'];
            }
            // 캡차
            if (/captcha|로봇이 아닙니다|i'?m not a robot/i.test(txt)) {
                return ['captcha', '캡차'];
            }
            // challenge URL
            if (url.includes('/challenge/') || url.includes('/signin/v2/challenge')) {
                return ['challenge', 'Google challenge 페이지'];
            }
            // 비정상 활동 차단
            if (/unusual activity|이 계정에 비정상적인|차단/i.test(txt)) {
                return ['blocked', '비정상 활동 차단'];
            }
            return [null, null];
        })();
        """)
        if isinstance(result, list) and result[0]:
            return True, result[1] or result[0]
        return False, ""
    except Exception:
        return False, ""


# ── 메인 로그인 함수 ────────────────────────────────────────────────────────

def login_google(
    page,
    google_id: str | None = None,
    google_pw: str | None = None,
    wait_for_user_s: int = 300,
) -> dict[str, Any]:
    """Google ID/PW 로그인 (2단계 폼).

    Args:
        page: Playwright Page
        google_id: Google 계정 이메일 (없으면 환경변수/파일)
        google_pw: 비밀번호
        wait_for_user_s: 2FA 등 발생 시 사용자 처리 대기 시간

    Returns:
        {ok, user, reason, captcha_required}
    """
    # 1. 자격증명
    gid, pw = _load_credentials(google_id, google_pw)
    if not gid or not pw:
        return {"ok": False, "reason": "no_credentials",
                "hint": "환경변수 GOOGLE_ID/GOOGLE_PW 또는 data/.env_google 파일 필요"}

    log_critical("AUTH_SUCCESS", "구글 로그인 시도", user=gid, mode="auto_login_start")

    # 2. 이미 로그인 상태 확인
    try:
        state = detect_login_state(page)
        if state.get("logged_in") and ("google" in page.url or "gmail" in page.url):
            current_user = state.get("user", "")
            if current_user and (gid in current_user or current_user == gid):
                _log.info("[google-auth] 동일 사용자 이미 로그인됨: %s", current_user)
                return {"ok": True, "user": current_user, "reason": "already_logged_in"}
            elif current_user:
                _log.warning("[google-auth] 다른 사용자 로그인 상태: %s (목표: %s)",
                             current_user, gid)
                return {"ok": False, "reason": "different_user_logged_in",
                        "current_user": current_user, "target_user": gid,
                        "hint": "현재 다른 사용자로 로그인됨. 먼저 로그아웃 필요."}
    except Exception:
        pass

    # 3. 로그인 페이지 진입
    _log.info("[google-auth] 로그인 페이지 진입")
    page.goto(GOOGLE_LOGIN_URL, timeout=15000, wait_until="domcontentloaded")
    time.sleep(2.5)

    # 3-1. signin 진입 후 myaccount/리다이렉트되면 이미 로그인된 것
    if "myaccount.google.com" in page.url or "/signin" not in page.url:
        try:
            user_info = page.evaluate("""
            () => {
                const t = (document.body?.innerText || '');
                const m = t.match(/([\\w.+-]+@[\\w.-]+\\.[a-z]{2,})/i);
                return m ? m[1] : null;
            }
            """)
        except Exception:
            user_info = None
        _log.info("[google-auth] signin 리다이렉트 — 이미 로그인됨: %s", user_info or gid)
        log_critical("AUTH_SUCCESS", "구글 이미 로그인 (signin 리다이렉트)",
                     user=user_info or gid, mode="already_logged_in_redirect")
        return {"ok": True, "user": user_info or gid, "reason": "already_logged_in_redirect"}

    # 4. ID 입력 (1단계)
    id_result = _safe_human_input(
        page, 'input[type="email"], #identifierId', gid,
        label="ID(이메일)", delay_ms=80,
    )
    if not id_result["ok"]:
        _log.error("[google-auth] ID 입력 실패: %s", id_result.get("reason"))
        return {"ok": False, "reason": f"id_input_failed:{id_result.get('reason', 'unknown')}",
                "id_result": id_result}
    time.sleep(0.6)

    # 5. ID 다음 버튼 클릭 (#identifierNext)
    try:
        page.locator('#identifierNext button, #identifierNext, button:has-text("다음"), button:has-text("Next")').first.click(timeout=3000)
        time.sleep(2.5)
    except Exception as e:
        _log.error("[google-auth] ID 다음 버튼 실패: %s", e)
        return {"ok": False, "reason": f"id_next_failed:{str(e)[:60]}"}

    # ID 단계 오류 감지 (계정 없음, 사용 안됨 등)
    try:
        err = page.evaluate("""
        () => {
            const t = (document.body?.innerText || '');
            if (/계정을 찾을 수 없|couldn'?t find your|존재하지 않는|사용할 수 없/i.test(t)) return '계정 없음/사용불가';
            return null;
        }
        """)
        if err:
            _log.error("[google-auth] ID 단계 오류: %s", err)
            return {"ok": False, "reason": f"id_error:{err}"}
    except Exception:
        pass

    # 6. PW 입력 (2단계)
    pw_result = _safe_human_input(
        page, 'input[type="password"], input[name="Passwd"]', pw,
        label="PW", delay_ms=90,
    )
    if not pw_result["ok"]:
        _log.error("[google-auth] PW 입력 실패: %s", pw_result.get("reason"))
        return {"ok": False, "reason": f"pw_input_failed:{pw_result.get('reason', 'unknown')}",
                "pw_result": pw_result}
    time.sleep(0.5)

    _log.info("[google-auth] 입력 완료 — ID:%s, PW:%s",
              id_result["action"], pw_result["action"])

    # 7. PW 다음 버튼 클릭 (#passwordNext)
    try:
        page.locator('#passwordNext button, #passwordNext, button:has-text("다음"), button:has-text("Next")').first.click(timeout=3000)
        time.sleep(4)
    except Exception as e:
        _log.error("[google-auth] PW 다음 버튼 실패: %s", e)
        return {"ok": False, "reason": f"pw_next_failed:{str(e)[:60]}"}

    # 8. 2FA / 보안 검증 감지
    detected, reason_text = _detect_2fa_or_challenge(page)
    if detected:
        _log.warning("[google-auth] %s 감지 → 사용자 수동 처리 대기 (%ds)", reason_text, wait_for_user_s)
        log_critical("AUTH_FAIL", f"구글 로그인 {reason_text}", user=gid, mode="2fa_detected")
        state = wait_for_login_generic(page, max_wait_s=wait_for_user_s, poll_interval=3.0)
        if state.get("logged_in"):
            user = state.get("user") or gid
            log_critical("AUTH_SUCCESS", "구글 로그인 성공 (사용자 처리)",
                         user=user, mode="auto_login_done_manual")
            return {"ok": True, "user": user, "reason": "user_handled_2fa"}
        return {"ok": False, "reason": "2fa_timeout", "captcha_required": True,
                "detected": reason_text}

    # 9. 일반 성공 검증
    time.sleep(2)
    state = detect_login_state(page)
    if state.get("logged_in"):
        user = state.get("user") or gid
        _log.info("[google-auth] 로그인 성공: %s", user)
        log_critical("AUTH_SUCCESS", "구글 로그인 성공", user=user, mode="auto_login_done")
        return {"ok": True, "user": user, "reason": "ok"}

    # 10. 실패 — URL이 여전히 로그인/challenge면 실패
    if "signin" in page.url or "accounts.google.com" in page.url:
        log_critical("AUTH_FAIL", "구글 로그인 실패", user=gid, mode="auto_login_fail")
        return {"ok": False, "reason": "credential_or_blocked", "current_url": page.url}

    return {"ok": state.get("score", 0) >= 2, "user": state.get("user"), "reason": "ambiguous"}


def ensure_google_login(
    page,
    google_id: str | None = None,
    google_pw: str | None = None,
    return_url: str | None = None,
) -> dict[str, Any]:
    """현재 페이지의 Google 로그인 확인 → 미로그인이면 자동 로그인 → 원래 페이지 복귀."""
    state = detect_login_state(page)
    if state.get("logged_in") and ("google" in page.url or "gmail" in page.url):
        return {"ok": True, "user": state.get("user"), "reason": "already_logged_in"}

    original_url = return_url or page.url
    result = login_google(page, google_id, google_pw)
    if not result["ok"]:
        return result

    if original_url and "accounts.google.com" not in original_url:
        try:
            page.goto(original_url, timeout=15000, wait_until="domcontentloaded")
            time.sleep(2)
        except Exception:
            pass
    return result
