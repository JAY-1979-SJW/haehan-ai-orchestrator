"""각 사이트의 로그인 페이지 자동 식별 + 폼 구조 분석 (Phase 3).

동작:
  1. data/sitemap/*_auto.json 읽어 각 사이트의 메뉴 링크 분석
  2. "로그인/Login/Sign in" 텍스트 또는 URL 패턴(/login, /signin)으로 로그인 페이지 후보 추출
  3. 로그인 페이지 이동 후 폼 구조 분석 (실제 입력 안 함)
  4. 결과를 같은 사이트맵 JSON에 'login' 키로 추가

수집 정보:
  - login.url: 로그인 페이지 URL
  - login.detection: 어떻게 발견했는지 (menu_link / url_guess)
  - login.form.username_selector: 사용자명 입력 셀렉터
  - login.form.password_selector: 비밀번호 입력 셀렉터
  - login.form.submit_selector: 제출 버튼 셀렉터
  - login.methods: ["id_pw", "cert", "kakao", "naver", "google", "qr", "pass"]
  - login.security_modules: 로그인 페이지에서 감지된 보안 모듈

사용:
  python scripts/login_page_explorer.py                    # 전체 사이트맵
  python scripts/login_page_explorer.py --category BANK_VISIT
  python scripts/login_page_explorer.py --skip-existing    # login 키 이미 있으면 건너뜀
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urljoin

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.web_connector import get_page
from scripts.popup_detector import handle_page_popups
from scripts.known_login_urls import get_known_login_url
from scripts.logger import get_logger

_log = get_logger(__name__)

SITEMAP_DIR = ROOT / "data" / "sitemap"


# ── 로그인 URL 후보 탐지 ────────────────────────────────────────────────────

LOGIN_TEXT_KEYWORDS = [
    "로그인", "Login", "login", "LOGIN",
    "Sign in", "Sign In", "Signin", "sign in",
    "Log in", "Log In", "log in",
    "내정보", "마이페이지", "MY",
]

LOGIN_URL_KEYWORDS = [
    "/login", "/signin", "/sign-in", "/sign_in",
    "/auth", "/users/sign_in", "/account/login",
    "/member/login", "/user/login", "/usr/login",
    "/customer/login", "/my/login",
]


def find_login_url(meta: dict, base_url: str, domain: str = "") -> tuple[str | None, str]:
    """사이트 메타데이터에서 로그인 URL 후보 추출.

    우선순위:
      0. known_login_urls.py 명시 매핑
      1. 메뉴 텍스트 매칭
      2. 메뉴 URL 패턴 매칭

    Returns: (url, detection_method)
    """
    # 0. 명시 매핑 우선
    known = get_known_login_url(domain)
    if known:
        return known, "known_catalog"

    if not meta:
        return None, "no_meta"

    base_host = urlparse(base_url).hostname or ""
    menus = meta.get("menus") or []

    # 1. 메뉴 텍스트에서 로그인 키워드 매칭
    for m in menus:
        text = (m.get("text") or "").strip()
        href = m.get("href") or ""
        if not text or not href:
            continue
        if any(kw == text or kw in text for kw in LOGIN_TEXT_KEYWORDS[:6]):
            try:
                href_host = urlparse(href).hostname
                if not href_host or href_host == base_host:
                    full_url = urljoin(base_url, href) if not href.startswith("http") else href
                    return full_url, "menu_text"
            except Exception:
                pass

    # 2. 메뉴 URL에서 로그인 패턴 매칭
    for m in menus:
        href = m.get("href") or ""
        if not href:
            continue
        href_lower = href.lower()
        for pat in LOGIN_URL_KEYWORDS:
            if pat in href_lower:
                try:
                    href_host = urlparse(href).hostname
                    if not href_host or href_host == base_host:
                        full_url = urljoin(base_url, href) if not href.startswith("http") else href
                        return full_url, f"url_pattern:{pat}"
                except Exception:
                    pass

    return None, "not_found"


# ── 메인 페이지에서 직접 로그인 링크 찾기 (메뉴 데이터 한계 보완) ─────────────

SCAN_LOGIN_LINK_JS = r"""
(() => {
    const kws = ['로그인', 'Login', 'LOGIN', 'login', 'Sign in', 'Sign In', 'Log in'];
    const isVisible = (el) => {
        const s = window.getComputedStyle(el);
        if (s.display === 'none' || s.visibility === 'hidden') return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 || r.height > 0;
    };

    const candidates = [];

    // 페이지 전체 a/button/span에서 "로그인" 텍스트 검색
    document.querySelectorAll('a, button, span, div[role="button"]').forEach(el => {
        const t = (el.innerText || el.getAttribute('aria-label') || '').trim();
        if (!t || t.length > 20) return;
        if (kws.some(k => t === k || t.startsWith(k))) {
            if (!isVisible(el)) return;
            const href = el.href || el.getAttribute('data-href') || '';
            const onclick = el.getAttribute('onclick') || '';
            candidates.push({
                tag: el.tagName,
                text: t.substring(0, 30),
                href: href.substring(0, 200),
                onclick: onclick.substring(0, 100)
            });
        }
    });

    return candidates.slice(0, 10);
})();
"""


def scan_login_link_on_page(page, base_url: str) -> str | None:
    """현재 페이지에서 로그인 링크 직접 스캔 (메뉴 데이터로 못 찾는 경우)."""
    try:
        candidates = page.evaluate(SCAN_LOGIN_LINK_JS)
        base_host = urlparse(base_url).hostname or ""
        for c in candidates:
            href = c.get("href", "")
            if href and href != base_url and not href.endswith("#"):
                try:
                    h_host = urlparse(href).hostname
                    if not h_host or h_host == base_host:
                        return urljoin(base_url, href) if not href.startswith("http") else href
                except Exception:
                    pass
        return None
    except Exception:
        return None


# ── 로그인 페이지 폼 분석 ───────────────────────────────────────────────────

ANALYZE_LOGIN_JS = r"""
(() => {
    const isVisible = (el) => {
        const s = window.getComputedStyle(el);
        if (s.display === 'none' || s.visibility === 'hidden') return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 || r.height > 0;
    };

    const cssEscape = (s) => {
        if (window.CSS && CSS.escape) return CSS.escape(s);
        return s.replace(/[^a-zA-Z0-9_-]/g, '\\$&');
    };

    const sel = (el) => {
        if (!el) return null;
        if (el.id) return '#' + cssEscape(el.id);
        if (el.name) return el.tagName.toLowerCase() + '[name="' + el.name + '"]';
        const cls = (el.className || '').toString().trim().split(/\s+/).filter(Boolean);
        if (cls.length) return el.tagName.toLowerCase() + '.' + cls.slice(0, 2).map(cssEscape).join('.');
        return el.tagName.toLowerCase();
    };

    const result = {
        url: location.href,
        title: document.title || '',
        forms_count: document.querySelectorAll('form').length,
    };

    // 비밀번호 필드 찾기 (있으면 표준 ID/PW)
    const pwFields = Array.from(document.querySelectorAll('input[type="password"]')).filter(isVisible);
    const hasPwField = pwFields.length > 0;

    // 인증 UI 감지 (password 없어도 인증서/QR/카카오 등 있으면 로그인 페이지)
    const bodyText = (document.body?.innerText || '').toLowerCase();
    const bodyHtml = (document.body?.innerHTML || '');
    const hasCertUI = /공인인증|공동인증|인증서\s*로그인|하나인증서|원큐인증/.test(bodyText);
    const hasQrUI = /QR\s*(코드|로그인|인증)|qr\s*(code|login)/i.test(bodyText) ||
                    /qr/i.test(bodyHtml);
    const hasMobileAuthUI = /PASS\s*인증|pass\s*인증|모바일\s*인증/i.test(bodyText);
    const hasSocialUI = /카카오\s*로그인|네이버\s*로그인|google\s*sign|apple\s*sign/i.test(bodyText);
    const hasOtpUI = /OTP|일회용\s*비밀번호/i.test(bodyText);

    const hasAnyAuthUI = hasPwField || hasCertUI || hasQrUI || hasMobileAuthUI || hasSocialUI || hasOtpUI;

    if (!hasAnyAuthUI) {
        result.form_detected = false;
        result.reason = 'no_auth_ui';
        return result;
    }
    result.form_detected = true;
    result.has_password_field = hasPwField;

    // 폼 정보는 password 필드 있을 때만
    if (hasPwField) {
        const pw = pwFields[0];
        result.password_selector = sel(pw);

        const allInputs = Array.from(document.querySelectorAll('input')).filter(isVisible);
        const pwIdx = allInputs.indexOf(pw);
        let userInput = null;
        for (let i = pwIdx - 1; i >= 0; i--) {
            const t = (allInputs[i].type || '').toLowerCase();
            if (['text', 'email', 'tel', ''].includes(t)) {
                userInput = allInputs[i];
                break;
            }
        }
        result.username_selector = userInput ? sel(userInput) : null;
        result.username_type = userInput ? userInput.type : null;
        result.username_placeholder = userInput ? userInput.placeholder : null;

        const form = pw.closest('form');
        let submit = null;
        if (form) {
            submit = form.querySelector('button[type="submit"], input[type="submit"]');
            if (!submit) {
                const btns = Array.from(form.querySelectorAll('button, a.btn, a[role="button"]'));
                submit = btns.find(b => {
                    const t = (b.innerText || '').trim();
                    return /로그인|login|sign\s*in/i.test(t);
                }) || btns[btns.length - 1];
            }
        }
        result.submit_selector = sel(submit);
        result.submit_text = submit ? (submit.innerText || '').trim().substring(0, 30) : null;
    }

    // 인증 방식 집계 (위의 hasXxxUI 변수 활용)
    const methods = [];
    if (hasPwField) methods.push('id_pw');
    if (hasCertUI) methods.push('cert');
    if (hasQrUI) methods.push('qr');
    if (hasMobileAuthUI) methods.push('pass');
    if (hasOtpUI) methods.push('otp');
    if (/카카오\s*(로그인|계정)|kakao\s*login/i.test(bodyText)) methods.push('kakao');
    if (/네이버\s*(로그인|계정)|naver\s*login/i.test(bodyText)) methods.push('naver');
    if (/google\s*(로그인|sign)|구글\s*로그인/i.test(bodyText)) methods.push('google');
    if (/apple\s*(로그인|sign)|애플\s*로그인/i.test(bodyText)) methods.push('apple');
    if (/facebook\s*(로그인|sign)|페이스북\s*로그인/i.test(bodyText)) methods.push('facebook');
    if (/지문|biometric|fido/i.test(bodyText)) methods.push('biometric');
    result.methods = methods;

    // 보안 모듈
    const secuKw = ['AnySign', 'TouchEn', 'Veraport', 'INISAFE', 'XecureWeb',
                    'WizIN', 'NPKI', 'CrossEx', 'IPinside'];
    const html = (document.body?.innerHTML || '');
    result.security_modules = secuKw.filter(k => html.includes(k));

    // 추가정보: ID 저장 체크박스, 캡차 등
    result.has_remember = !!document.querySelector('input[type="checkbox"]');
    result.has_captcha = /captcha|recaptcha|hcaptcha/i.test(html);

    return result;
})();
"""


def analyze_login_page(page) -> dict:
    """메인 페이지에서 폼 찾기. 없으면 iframe 내부도 검사."""
    result = page.evaluate(ANALYZE_LOGIN_JS)
    if result.get("form_detected"):
        return result

    # iframe 내부 검사
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            fr = frame.evaluate(ANALYZE_LOGIN_JS)
            if fr.get("form_detected"):
                fr["in_iframe"] = True
                fr["iframe_url"] = frame.url
                return fr
        except Exception:
            continue
    return result


# ── 사이트 1개 처리 ──────────────────────────────────────────────────────────

def explore_login_for_site(page, sitemap_path: Path, timeout_s: int = 12) -> dict:
    """사이트맵 JSON 1개에 login 정보 추가"""
    try:
        data = json.loads(sitemap_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"path": sitemap_path.name, "ok": False, "error": f"read_fail:{e}"}

    if not data.get("success"):
        return {"path": sitemap_path.name, "ok": False, "error": "main_not_success"}

    base_url = data.get("url") or data.get("meta", {}).get("url")
    if not base_url:
        return {"path": sitemap_path.name, "ok": False, "error": "no_url"}

    meta = data.get("meta") or {}
    domain = data.get("domain") or urlparse(base_url).hostname or ""
    login_url, detection = find_login_url(meta, base_url, domain)

    result = {
        "path": sitemap_path.name,
        "domain": domain,
        "category": data.get("category"),
        "ok": False,
    }

    # 메뉴 데이터로 못 찾으면: 메인 페이지로 가서 직접 스캔
    if not login_url:
        try:
            page.goto(base_url, timeout=timeout_s * 1000, wait_until="domcontentloaded")
            time.sleep(1.5)
            try:
                handle_page_popups(page, timeout_s=1.5)
            except Exception:
                pass
            scanned = scan_login_link_on_page(page, base_url)
            if scanned:
                login_url = scanned
                detection = "page_scan"
        except Exception:
            pass

    if not login_url:
        # 메인 페이지에 로그인 폼이 있는 경우도 있음 (네이버 등)
        if meta.get("login_required") and data.get("meta", {}).get("forms"):
            login_url = base_url
            detection = "main_has_form"
        else:
            data["login"] = {"detected": False, "reason": "no_login_url"}
            sitemap_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            result["error"] = "login_url_not_found"
            return result

    # 로그인 페이지 이동 + 분석
    try:
        page.goto(login_url, timeout=timeout_s * 1000, wait_until="domcontentloaded")
        time.sleep(1.5)
        try:
            handle_page_popups(page, timeout_s=1.5)
        except Exception:
            pass
        form_info = analyze_login_page(page)

        login_data = {
            "detected": form_info.get("form_detected", False),
            "url": login_url,
            "detection_method": detection,
            "analyzed_at": datetime.now().isoformat(timespec="seconds"),
        }

        if form_info.get("form_detected"):
            login_data["form"] = {
                "username_selector": form_info.get("username_selector"),
                "username_type": form_info.get("username_type"),
                "username_placeholder": form_info.get("username_placeholder"),
                "password_selector": form_info.get("password_selector"),
                "submit_selector": form_info.get("submit_selector"),
                "submit_text": form_info.get("submit_text"),
            }
            login_data["methods"] = form_info.get("methods") or []
            login_data["security_modules"] = form_info.get("security_modules") or []
            login_data["has_remember"] = form_info.get("has_remember")
            login_data["has_captcha"] = form_info.get("has_captcha")
            result["ok"] = True
            result["methods"] = login_data["methods"]
        else:
            login_data["reason"] = form_info.get("reason", "no_form")
            result["error"] = "no_form_on_page"

        data["login"] = login_data
        sitemap_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    except Exception as e:
        data["login"] = {"detected": False, "reason": f"error:{str(e)[:100]}"}
        sitemap_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        result["error"] = f"navigate_fail:{str(e)[:80]}"

    return result


# ── 메인 ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="사이트 로그인 페이지 자동 식별")
    parser.add_argument("--category", default=None, help="특정 카테고리만")
    parser.add_argument("--skip-existing", action="store_true",
                        help="login 키 이미 있는 사이트맵은 건너뜀")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=12)
    args = parser.parse_args()

    files = sorted(SITEMAP_DIR.glob("*_auto.json"))
    print(f"전체 사이트맵: {len(files)}개")

    # 필터링
    if args.category or args.skip_existing:
        filtered = []
        for f in files:
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if args.category and d.get("category") != args.category:
                continue
            if args.skip_existing and d.get("login"):
                continue
            filtered.append(f)
        files = filtered
        print(f"필터링 후: {len(files)}개")

    if args.limit > 0:
        files = files[: args.limit]

    print(f"\n{'='*70}")
    print(f"  로그인 페이지 자동 식별  |  대상: {len(files)}개")
    print(f"{'='*70}\n")

    page = get_page()
    results = []

    for i, f in enumerate(files, 1):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            domain = d.get("domain", f.stem)
            cat = d.get("category", "?")
        except Exception:
            domain = f.stem
            cat = "?"

        print(f"  [{i:3}/{len(files)}] [{cat:<18}] {domain}", end=" ", flush=True)
        r = explore_login_for_site(page, f, timeout_s=args.timeout)
        results.append(r)

        if r["ok"]:
            methods = ",".join(r.get("methods", [])) or "id_pw"
            print(f"✓  방식=[{methods}]")
        else:
            print(f"·  {r.get('error', '')[:50]}")

        time.sleep(0.3)

    # 요약
    ok = sum(1 for r in results if r["ok"])
    fail = len(results) - ok
    print(f"\n{'='*70}")
    print(f"  완료  |  로그인 폼 식별 성공: {ok}/{len(results)}")
    print(f"{'='*70}\n")

    # 카테고리별 통계
    from collections import Counter
    cat_ok = Counter()
    cat_total = Counter()
    for r in results:
        cat_total[r.get("category", "?")] += 1
        if r["ok"]:
            cat_ok[r.get("category", "?")] += 1

    print("[카테고리별 로그인 식별 결과]")
    for cat in sorted(cat_total):
        print(f"  {cat:<22} {cat_ok[cat]:>3}/{cat_total[cat]}")

    # 결과 저장
    out = ROOT / "data" / f"login_explorer_result_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  결과: {out.name}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n사용자 중단")
        sys.exit(0)
    except Exception as e:
        _log.error("실행 실패: %s", e)
        import traceback
        traceback.print_exc()
        sys.exit(1)
