"""Extract Kakao REST API key and Client Secret to .env.local — no secret in stdout.

읽기 전용: 키 확인 후 .env.local에 저장. 원문 출력 없음.
금지: Client Secret 재발급/폐기, 앱 삭제, screenshot, 비밀번호 입력.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_BASE = "https://developers.kakao.com"
_LOGIN_SUCCESS_TEXTS = ["내 애플리케이션", "앱 목록", "로그아웃"]
_LOGIN_TOKENS = ("로그인", "카카오 계정", "이메일", "비밀번호", "sign in", "2fa", "인증번호")
_REAUTH_TOKENS = ("비밀번호를 입력", "재인증", "본인 확인", "2단계 인증", "추가 인증")


# ── env helpers ───────────────────────────────────────────────────────────────

def _load_env(path: str) -> dict[str, str]:
    result: dict[str, str] = {}
    if not os.path.exists(path):
        return result
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


def _load_lines(path: str) -> list[str]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return f.readlines()


def _upsert_key(lines: list[str], key: str, value: str) -> list[str]:
    prefix = f"{key}="
    updated = False
    result = []
    for line in lines:
        if line.startswith(prefix):
            result.append(f"{key}={value}\n")
            updated = True
        else:
            result.append(line)
    if not updated:
        if result and not result[-1].endswith("\n"):
            result.append("\n")
        result.append(f"{key}={value}\n")
    return result


def _atomic_write(path: str, lines: list[str]) -> None:
    dir_ = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=dir_)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.writelines(lines)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ── page helpers ──────────────────────────────────────────────────────────────

def _page_text(page: Any) -> str:
    try:
        return page.content() or ""
    except Exception:
        return ""


def _has_login_signal(page: Any) -> bool:
    try:
        title = page.title() or ""
    except Exception:
        title = ""
    text = (title + " " + _page_text(page)[:3000]).lower()
    return any(t.lower() in text for t in _LOGIN_SUCCESS_TEXTS)


def _needs_login(page: Any) -> bool:
    try:
        title = page.title() or ""
    except Exception:
        title = ""
    text = (title + " " + _page_text(page)[:2000]).lower()
    return any(t.lower() in text for t in _LOGIN_TOKENS)


def _needs_reauth(page: Any) -> bool:
    text = _page_text(page)[:2000].lower()
    return any(t.lower() in text for t in _REAUTH_TOKENS)


def _goto(page: Any, url: str, wait_ms: int = 12000) -> None:
    try:
        page.goto(url, wait_until="networkidle", timeout=wait_ms)
    except Exception:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=wait_ms)
        except Exception:
            pass


def _read_input_value(page: Any, selector: str) -> Optional[str]:
    """Read a single input field value. Returns None if not found."""
    try:
        el = page.query_selector(selector)
        if el:
            return el.input_value()
    except Exception:
        pass
    return None


def _read_all_inputs(page: Any) -> list[str]:
    """Read all input values on the page."""
    vals: list[str] = []
    try:
        page.wait_for_timeout(800)
        els = page.query_selector_all("input[type='text'], input:not([type]), input[type='password']")
        for el in els:
            try:
                v = el.input_value() or ""
                if v:
                    vals.append(v)
            except Exception:
                pass
    except Exception:
        pass
    return vals


def _click_show_button(page: Any) -> bool:
    """Click a '보기' or '확인' button to reveal masked secret. Returns True if clicked."""
    candidates = ["보기", "확인", "Show", "복사", "보이기"]
    for label in candidates:
        try:
            btn = page.get_by_text(label, exact=True)
            if btn.count() > 0:
                btn.first.click()
                page.wait_for_timeout(600)
                return True
        except Exception:
            pass
    # button containing '보기'
    try:
        btns = page.query_selector_all("button")
        for b in btns:
            try:
                txt = b.inner_text().strip()
                if txt in ("보기", "확인", "Show"):
                    b.click()
                    page.wait_for_timeout(600)
                    return True
            except Exception:
                pass
    except Exception:
        pass
    return False


# ── key extraction ─────────────────────────────────────────────────────────────

def _get_page_lines(page: Any) -> list[str]:
    try:
        text = page.inner_text("body") or ""
        return [l.strip() for l in text.split('\n') if l.strip()]
    except Exception:
        return []


def _extract_keys_from_platform_key_page(page: Any, app_id: str) -> tuple[Optional[str], Optional[str]]:
    """Navigate to platform-key page, extract REST API key and Client Secret.

    Returns (rest_api_key, client_secret). Values are read from visible text — no masking.
    絶 대 stdout 출력 없음.
    """
    url = f"{_BASE}/console/app/{app_id}/config/platform-key"
    _goto(page, url, wait_ms=15000)
    try:
        page.wait_for_timeout(1500)
    except Exception:
        pass

    # ── Step 1: extract REST API key from initial page text ──────────────────
    # Page structure after load (text lines):
    #   "REST API 키"  →  "REST API 키 추가"  →  "대표"  →  key_name  →  "더보기"  →  <32-hex>
    # The REST API key is the 32-char lowercase hex string in the REST API 키 section.
    rest_api_key: Optional[str] = None
    _HEX32_PATTERN = re.compile(r'^[0-9a-f]{32}$')
    _TOKEN_PATTERN = re.compile(r'^[A-Za-z0-9+/=_\-]{16,}$')

    lines = _get_page_lines(page)
    in_rest_section = False
    past_js_section = False
    for line in lines:
        if "REST API 키" in line and "추가" not in line and "수정" not in line:
            in_rest_section = True
        if "JavaScript 키" in line or "네이티브 앱 키" in line:
            if in_rest_section:
                past_js_section = True
        if in_rest_section and not past_js_section:
            if _HEX32_PATTERN.match(line):
                rest_api_key = line
                break

    # ── Step 2: click "클라이언트 시크릿" to expand and read client secret ──
    client_secret: Optional[str] = None
    try:
        cs_span = page.get_by_text("클라이언트 시크릿", exact=True)
        if cs_span.count() > 0:
            cs_span.first.click()
            try:
                page.wait_for_timeout(1500)
            except Exception:
                pass

            # After expansion, lines contain:
            #  "카카오 로그인" → "코드 재발급" → "코드 삭제" → "코드" → <secret_value> → "활성화"
            expanded_lines = _get_page_lines(page)
            in_kakao_login_cs = False
            found_code_label = False
            for line in expanded_lines:
                if line == "카카오 로그인":
                    in_kakao_login_cs = True
                    found_code_label = False
                if in_kakao_login_cs and line == "코드":
                    found_code_label = True
                    continue
                if found_code_label and _TOKEN_PATTERN.match(line):
                    client_secret = line
                    break
                if line in ("비즈니스 인증", "활성화") and found_code_label:
                    break
    except Exception:
        pass

    return rest_api_key, client_secret


# ── main ──────────────────────────────────────────────────────────────────────

def run(
    app_id: str,
    target_env: str,
    nextauth_url: str,
    dry_run: bool = False,
    rotate_nextauth_secret: bool = False,
    dwell_seconds: int = 0,
    _browser_factory: Any = None,
) -> dict[str, Any]:

    result: dict[str, Any] = {
        "ok": False,
        "dry_run": dry_run,
        "KAKAO_CLIENT_ID_present": False,
        "KAKAO_CLIENT_ID_length": 0,
        "KAKAO_CLIENT_SECRET_present": False,
        "KAKAO_CLIENT_SECRET_length": 0,
        "NEXTAUTH_URL": nextauth_url,
        "NEXTAUTH_SECRET_present": False,
        "NEXTAUTH_SECRET_length": 0,
        "raw_secret_printed": False,
        "warnings": [],
        "errors": [],
    }

    # Load session
    try:
        from ai_orchestrator.sites import secrets_policy as _sp
        _state_path = _sp.session_state_path("kakao_developers")
        _storage_state_arg: dict = {"storage_state": str(_state_path)} if _state_path.is_file() else {}
    except Exception as e:
        result["errors"].append(f"session_load_failed: {e}")
        _storage_state_arg = {}

    if not _storage_state_arg:
        result["warnings"].append("no_saved_session: browser will show login page")

    factory = _browser_factory
    if factory is None:
        try:
            from playwright.sync_api import sync_playwright
            factory = sync_playwright
        except ImportError:
            result["errors"].append("playwright_not_installed")
            return result

    rest_api_key: Optional[str] = None
    client_secret: Optional[str] = None

    try:
        with factory() as pw:
            browser = pw.chromium.launch(headless=False)
            try:
                context = browser.new_context(**_storage_state_arg)
                page = context.new_page()

                # Navigate to console
                _goto(page, f"{_BASE}/console/app", wait_ms=15000)
                try:
                    page.bring_to_front()
                except Exception:
                    pass

                # Check login state
                if _needs_reauth(page):
                    result["warnings"].append("reauth_required: 재인증 요구됨 — 비밀번호 입력 없이 중단")
                    result["errors"].append("reauth_required")
                    return result

                if not _has_login_signal(page):
                    # Wait briefly for session to load
                    time.sleep(3)
                    if not _has_login_signal(page):
                        result["warnings"].append("session_may_be_expired: login page shown")

                if dwell_seconds > 0:
                    time.sleep(dwell_seconds)

                # dry-run: only check access
                if dry_run:
                    can_access = _has_login_signal(page)
                    result["ok"] = can_access
                    result["dry_run_access"] = can_access
                    return result

                # Extract both keys from platform-key page
                rest_api_key, client_secret = _extract_keys_from_platform_key_page(page, app_id)

                if rest_api_key:
                    result["KAKAO_CLIENT_ID_present"] = True
                    result["KAKAO_CLIENT_ID_length"] = len(rest_api_key)
                else:
                    result["warnings"].append("REST_API_key_not_found")

                if client_secret:
                    result["KAKAO_CLIENT_SECRET_present"] = True
                    result["KAKAO_CLIENT_SECRET_length"] = len(client_secret)
                else:
                    result["warnings"].append("client_secret_not_found")

            finally:
                try:
                    browser.close()
                except Exception:
                    pass
    except Exception as e:
        result["errors"].append(f"browser_error: {str(e)[:200]}")
        return result

    # Write to .env.local
    existing = _load_env(target_env)
    lines = _load_lines(target_env)

    if rest_api_key:
        lines = _upsert_key(lines, "KAKAO_CLIENT_ID", rest_api_key)
    if client_secret:
        lines = _upsert_key(lines, "KAKAO_CLIENT_SECRET", client_secret)

    lines = _upsert_key(lines, "NEXTAUTH_URL", nextauth_url)

    # NEXTAUTH_SECRET: generate only if absent or rotate requested
    existing_ns = existing.get("NEXTAUTH_SECRET", "")
    if rotate_nextauth_secret or not existing_ns:
        new_ns = secrets.token_urlsafe(48)
        lines = _upsert_key(lines, "NEXTAUTH_SECRET", new_ns)
        ns_val = new_ns
    else:
        ns_val = existing_ns

    result["NEXTAUTH_SECRET_present"] = bool(ns_val)
    result["NEXTAUTH_SECRET_length"] = len(ns_val)

    _atomic_write(target_env, lines)

    result["ok"] = bool(rest_api_key and client_secret)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Kakao app keys to .env.local")
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--target-env", required=True)
    parser.add_argument("--nextauth-url", default="https://attendance.haehan-ai.kr")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rotate-nextauth-secret", action="store_true")
    parser.add_argument("--dwell-seconds", type=int, default=0)
    parser.add_argument("--json", action="store_true", dest="output_json")
    args = parser.parse_args()

    result = run(
        app_id=args.app_id,
        target_env=args.target_env,
        nextauth_url=args.nextauth_url,
        dry_run=args.dry_run,
        rotate_nextauth_secret=args.rotate_nextauth_secret,
        dwell_seconds=args.dwell_seconds,
    )

    if args.output_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "PASS" if result.get("ok") else "FAIL"
        print(f"[{status}] dry_run={result['dry_run']}")
        print(f"  KAKAO_CLIENT_ID   present={result['KAKAO_CLIENT_ID_present']} length={result['KAKAO_CLIENT_ID_length']}")
        print(f"  KAKAO_CLIENT_SECRET present={result['KAKAO_CLIENT_SECRET_present']} length={result['KAKAO_CLIENT_SECRET_length']}")
        print(f"  NEXTAUTH_URL      = {result['NEXTAUTH_URL']}")
        print(f"  NEXTAUTH_SECRET   present={result['NEXTAUTH_SECRET_present']} length={result['NEXTAUTH_SECRET_length']}")
        if result.get("warnings"):
            for w in result["warnings"]:
                print(f"  WARN: {w}")
        if result.get("errors"):
            for e in result["errors"]:
                print(f"  ERROR: {e}")


if __name__ == "__main__":
    main()
