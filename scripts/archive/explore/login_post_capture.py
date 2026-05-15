"""사용자 1회 수동 로그인 후 자동 사이트맵 수집 (Phase 4).

흐름:
  1. 사용자가 사이트 도메인 지정 (예: hanabank.com)
  2. 스크립트가 로그인 페이지로 자동 이동
  3. 사용자가 직접 ID/PW + 인증서 + QR 등 로그인 진행
  4. 스크립트가 백그라운드 폴링으로 로그인 성공 감지:
     - "로그아웃" 텍스트 등장
     - URL이 로그인 페이지에서 벗어남
     - 쿠키 변화 (세션 쿠키 등장)
     - 사용자명 표시
  5. 로그인 성공 즉시 자동 수집:
     - 로그인 후 메인 페이지 메뉴
     - 사이트맵 깊이 1 (메뉴 클릭 후 페이지들)
     - 주요 폼/기능 메타데이터
  6. 사이트맵 JSON에 post_login 키로 저장

사용:
  python scripts/login_post_capture.py --domain hanabank.com
  python scripts/login_post_capture.py --url https://www.hanabank.com/common/login.do
  python scripts/login_post_capture.py --domain hometax.go.kr --depth 2

옵션:
  --domain      : 도메인 (사이트맵에서 로그인 URL 자동 조회)
  --url         : 로그인 URL 직접 지정
  --depth       : 사이트맵 수집 깊이 (1=메뉴만, 2=메뉴+하위)
  --max-pages   : 최대 수집 페이지 수 (기본 20)
  --wait        : 로그인 대기 최대 시간 초 (기본 600=10분)
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
from scripts.critical_logger import log_critical
from scripts.logger import get_logger

_log = get_logger(__name__)
SITEMAP_DIR = ROOT / "data" / "sitemap"


# ── 로그인 성공 감지 ────────────────────────────────────────────────────────

LOGIN_SUCCESS_JS = r"""
(initialUrl) => {
    // 1. URL 변경 (로그인 페이지에서 벗어남)
    const urlChanged = location.href !== initialUrl &&
        !/(login|signin|auth)/i.test(location.href);

    // 2. "로그아웃" 또는 사용자 메뉴 등장
    const txt = (document.body?.innerText || '').toLowerCase();
    const logoutPresent = /로그아웃|sign\s*out|logout|log\s*out/i.test(txt);
    const myMenuPresent = /마이페이지|my\s*page|내정보|my\s*account|환영합니다|welcome/i.test(txt);

    // 3. 쿠키 변화 (세션 쿠키 후보)
    const cookies = document.cookie;
    const sessionKws = ['JSESSION', 'PHPSESS', 'session', 'auth', 'token', 'SSID'];
    const hasSession = sessionKws.some(k => cookies.includes(k));

    // 4. 비밀번호 필드 사라짐 (로그인 폼 사라짐)
    const pwGone = document.querySelectorAll('input[type="password"]').length === 0;

    const score = (urlChanged ? 2 : 0) +
                  (logoutPresent ? 3 : 0) +
                  (myMenuPresent ? 1 : 0) +
                  (hasSession ? 1 : 0) +
                  (pwGone && urlChanged ? 1 : 0);

    return {
        url: location.href,
        url_changed: urlChanged,
        logout_present: logoutPresent,
        my_menu_present: myMenuPresent,
        has_session_cookie: hasSession,
        pw_field_gone: pwGone,
        score: score,
        success: score >= 3
    };
}
"""


# ── 로그인 후 메뉴/사이트맵 수집 ────────────────────────────────────────────

CAPTURE_POST_LOGIN_JS = r"""
(() => {
    const isVisible = (el) => {
        const s = window.getComputedStyle(el);
        if (s.display === 'none' || s.visibility === 'hidden') return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 || r.height > 0;
    };

    const result = {
        url: location.href,
        title: document.title || '',
        captured_at: new Date().toISOString(),
    };

    // 1. 메인 메뉴 (네비게이션)
    const menus = [];
    const seen = new Set();
    document.querySelectorAll('nav a, [role=navigation] a, .gnb a, .lnb a, .menu a, header a, aside a').forEach(a => {
        if (!isVisible(a)) return;
        const t = (a.innerText || '').trim().replace(/\s+/g, ' ').substring(0, 40);
        const h = a.href || '';
        if (t && t.length >= 2 && t.length < 40 && !seen.has(t)) {
            seen.add(t);
            menus.push({
                text: t,
                href: h.substring(0, 200),
                category: a.closest('nav, .gnb, .lnb, header, aside')?.className?.substring(0, 30) || ''
            });
        }
    });
    result.menus = menus.slice(0, 100);

    // 2. 마이페이지/내정보 영역 식별
    const myInfoLinks = [];
    document.querySelectorAll('a').forEach(a => {
        if (!isVisible(a)) return;
        const t = (a.innerText || '').trim();
        if (/마이페이지|내정보|로그아웃|My\s*Page|My\s*Account|sign\s*out/i.test(t)) {
            myInfoLinks.push({text: t.substring(0, 30), href: (a.href || '').substring(0, 200)});
        }
    });
    result.my_info_area = myInfoLinks.slice(0, 10);

    // 3. 폼 (조회/입력 화면 후보)
    const forms = [];
    document.querySelectorAll('form').forEach(f => {
        const inputs = Array.from(f.querySelectorAll('input, select, textarea')).map(i => ({
            type: i.type || i.tagName,
            name: i.name || i.id || '',
            label: i.placeholder || i.getAttribute('aria-label') || ''
        })).filter(i => !['hidden', 'submit'].includes(i.type)).slice(0, 10);
        if (inputs.length) {
            forms.push({
                action: (f.action || '').substring(0, 200),
                method: f.method || '',
                inputs: inputs
            });
        }
    });
    result.forms = forms.slice(0, 5);

    // 4. 사용자 정보 표시 (이름/아이디 노출 영역)
    const userBlocks = [];
    document.querySelectorAll('.user-name, .username, .user-info, [class*=user-name], [class*=member-name]').forEach(el => {
        if (!isVisible(el)) return;
        const t = (el.innerText || '').trim();
        if (t && t.length < 50) {
            userBlocks.push({cls: el.className.substring(0, 40), text: t.substring(0, 30)});
        }
    });
    result.user_blocks = userBlocks.slice(0, 5);

    return result;
})();
"""


def wait_for_login(page, initial_url: str, max_wait_s: int = 600) -> dict:
    """로그인 성공 폴링 대기. 사용자가 직접 로그인 진행하는 동안 백그라운드 감지."""
    print(f"\n  [대기] 사용자가 로그인 완료할 때까지 폴링 중...")
    print(f"  [최대 {max_wait_s}초 ({max_wait_s//60}분)]")
    print(f"  [Ctrl+C로 중단]")

    start = time.time()
    last_status = ""
    while time.time() - start < max_wait_s:
        try:
            status = page.evaluate(LOGIN_SUCCESS_JS, initial_url)
            if status.get("success"):
                elapsed = int(time.time() - start)
                print(f"\n  ✓ 로그인 감지! (점수 {status['score']}/8, {elapsed}초 경과)")
                print(f"    URL: {status['url']}")
                print(f"    로그아웃 표시: {status['logout_present']}")
                print(f"    세션쿠키: {status['has_session_cookie']}")
                return status

            # 진행상황 표시
            status_str = f"score={status['score']} url_chg={status['url_changed']} logout={status['logout_present']}"
            if status_str != last_status:
                print(f"  ... {status_str}")
                last_status = status_str
        except Exception as e:
            _log.debug(f"폴링 오류: {e}")
        time.sleep(3)

    print(f"\n  ✗ 시간 초과 ({max_wait_s}초)")
    return {"success": False, "timeout": True}


# ── 깊이 1 사이트맵 수집 ────────────────────────────────────────────────────

def capture_depth_1(page, base_data: dict, max_pages: int = 20) -> list[dict]:
    """로그인 후 메인 메뉴 따라 각 페이지 방문 + 메타 수집."""
    pages_data = []
    menus = (base_data.get("menus") or [])[:max_pages]
    base_host = urlparse(base_data.get("url", "")).hostname or ""

    for i, m in enumerate(menus, 1):
        href = m.get("href", "")
        text = m.get("text", "")
        if not href or href.endswith("#"):
            continue
        try:
            h_host = urlparse(href).hostname
            if h_host and h_host != base_host:
                continue  # 외부 도메인 스킵
        except Exception:
            continue

        try:
            print(f"    [{i:2}/{len(menus)}] {text[:25]:<25} {href[:60]}", end=" ")
            page.goto(href, timeout=10000, wait_until="domcontentloaded")
            time.sleep(1.5)
            try:
                handle_page_popups(page, timeout_s=1.0)
            except Exception:
                pass

            page_info = page.evaluate("""
            (() => ({
                url: location.href,
                title: document.title || '',
                heading: document.querySelector('h1,h2')?.innerText?.trim().substring(0, 60) || '',
                form_count: document.querySelectorAll('form').length,
                table_count: document.querySelectorAll('table').length,
                input_count: document.querySelectorAll('input,select,textarea').length,
            }))();
            """)
            pages_data.append({
                "menu_text": text,
                "menu_href": href,
                **page_info,
            })
            print("✓")
        except Exception as e:
            print(f"✗ {str(e)[:40]}")
            pages_data.append({"menu_text": text, "menu_href": href, "error": str(e)[:80]})

    return pages_data


# ── 메인 ────────────────────────────────────────────────────────────────────

def resolve_login_url(domain: str | None, url: str | None) -> tuple[str, str]:
    """도메인 또는 직접 URL → 로그인 URL 결정"""
    if url:
        d = urlparse(url).hostname or ""
        return url, d
    if domain:
        known = get_known_login_url(domain)
        if known:
            return known, domain
        # 사이트맵에서 login.url 찾기
        sm = SITEMAP_DIR / f"{domain}_auto.json"
        if not sm.exists():
            sm = SITEMAP_DIR / f"www.{domain}_auto.json"
        if sm.exists():
            d = json.loads(sm.read_text(encoding="utf-8"))
            login_url = (d.get("login") or {}).get("url")
            if login_url:
                return login_url, domain
        # fallback: 메인페이지
        return f"https://www.{domain}", domain
    raise ValueError("--domain 또는 --url 중 하나 필요")


def main():
    parser = argparse.ArgumentParser(description="사용자 로그인 후 사이트맵 자동 수집")
    parser.add_argument("--domain", default=None, help="도메인 (예: hanabank.com)")
    parser.add_argument("--url", default=None, help="로그인 URL 직접 지정")
    parser.add_argument("--depth", type=int, default=1, help="수집 깊이 (1 또는 2)")
    parser.add_argument("--max-pages", type=int, default=20, help="최대 수집 페이지 수")
    parser.add_argument("--wait", type=int, default=600, help="로그인 대기 최대 초")
    args = parser.parse_args()

    login_url, domain = resolve_login_url(args.domain, args.url)
    print(f"\n{'='*70}")
    print(f"  로그인 후 사이트맵 자동 수집")
    print(f"  도메인: {domain}")
    print(f"  로그인 URL: {login_url}")
    print(f"  수집 깊이: {args.depth}  |  최대 {args.max_pages}페이지")
    print(f"{'='*70}\n")

    page = get_page()

    # 1. 로그인 페이지로 이동
    print(f"  [1단계] 로그인 페이지 이동...")
    page.goto(login_url, timeout=15000, wait_until="domcontentloaded")
    time.sleep(2)
    try:
        handle_page_popups(page, timeout_s=2.0)
    except Exception:
        pass
    initial_url = page.url
    print(f"  ✓ 도착: {initial_url}")

    log_critical("AUTH_SUCCESS", f"로그인 후 수집 시작: {domain}",
                 domain=domain, login_url=login_url, mode="post_capture_start")

    # 2. 사용자 로그인 대기
    print(f"\n  [2단계] 사용자 로그인 대기")
    print(f"  → 브라우저에서 직접 로그인 진행하세요")
    print(f"  → 인증서/QR/PUSH/카카오 등 어떤 방식이든 OK")
    print(f"  → 로그인 완료되면 자동으로 다음 단계 진행됩니다")
    status = wait_for_login(page, initial_url, max_wait_s=args.wait)

    if not status.get("success"):
        print(f"\n  ✗ 로그인 미완료. 스크립트 종료.")
        sys.exit(1)

    # 3. 로그인 후 메인 페이지 수집
    print(f"\n  [3단계] 로그인 후 메인 페이지 수집...")
    time.sleep(2)  # 추가 로딩 대기
    main_capture = page.evaluate(CAPTURE_POST_LOGIN_JS)
    print(f"  ✓ 메뉴 {len(main_capture['menus'])}개 수집")
    print(f"  ✓ 마이페이지 링크 {len(main_capture['my_info_area'])}개")
    print(f"  ✓ 폼 {len(main_capture['forms'])}개")

    # 4. 깊이 1 수집 (메뉴 따라 각 페이지 방문)
    depth1_data = []
    if args.depth >= 1:
        print(f"\n  [4단계] 메뉴 따라 페이지 수집 (깊이 1, 최대 {args.max_pages}개)...")
        depth1_data = capture_depth_1(page, main_capture, max_pages=args.max_pages)
        print(f"  ✓ {len(depth1_data)}개 페이지 수집")

    # 5. 사이트맵 JSON 업데이트
    print(f"\n  [5단계] 사이트맵 저장...")
    sm_path = SITEMAP_DIR / f"{domain}_auto.json"
    if not sm_path.exists():
        sm_path = SITEMAP_DIR / f"www.{domain}_auto.json"

    if sm_path.exists():
        data = json.loads(sm_path.read_text(encoding="utf-8"))
    else:
        data = {"domain": domain, "category": "unknown"}

    data["post_login"] = {
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "login_url": login_url,
        "post_url": status["url"],
        "detection_score": status.get("score"),
        "main_page": main_capture,
        "depth_1_pages": depth1_data,
        "summary": {
            "menu_count": len(main_capture["menus"]),
            "my_info_count": len(main_capture["my_info_area"]),
            "form_count": len(main_capture["forms"]),
            "depth_1_count": len(depth1_data),
        }
    }

    out_path = sm_path if sm_path.exists() else SITEMAP_DIR / f"{domain}_auto.json"
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ 저장: {out_path.name}")

    log_critical("AUTH_SUCCESS", f"로그인 후 사이트맵 수집 완료: {domain}",
                 domain=domain,
                 menu_count=len(main_capture["menus"]),
                 depth_1_count=len(depth1_data),
                 mode="post_capture_done")

    print(f"\n{'='*70}")
    print(f"  완료 | {domain}")
    print(f"  - 메뉴: {len(main_capture['menus'])}개")
    print(f"  - 깊이1 페이지: {len(depth1_data)}개")
    print(f"  - 저장: {out_path}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n사용자 중단")
        sys.exit(0)
    except Exception as e:
        _log.error("실패: %s", e)
        import traceback
        traceback.print_exc()
        sys.exit(1)
