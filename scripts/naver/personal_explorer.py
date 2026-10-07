"""네이버 개인 계정 관련 서비스 전체 탐색.

로그인된 네이버 계정으로 접근 가능한 모든 네이버 서비스 자동 진입 + 사이트맵 수집.

탐색 대상:
  - 블로그 (관리/작성)
  - 메일
  - 카페 (My Cafe)
  - 캘린더
  - 마이박스 (클라우드)
  - 페이 / 마이비즈
  - 스마트스토어 / 쇼핑파트너센터
  - 광고센터 / 모먼트
  - 톡톡 / 인플루언서
  - 시리즈 / 웹툰
  - 검색광고

각 서비스마다:
  - 로그인 상태 자동 감지
  - 메인 페이지 메타 수집 (메뉴/폼/사용자명)
  - 통계/대시보드 항목 추출

결과: data/sitemap/naver_personal_summary.json
"""

from __future__ import annotations

import contextlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.auth.login_detector import detect_login_state  # noqa: E402
from scripts.browser.cdp.connection import get_page  # noqa: E402
from scripts.browser.popup.popup_detector import close_popup_windows, handle_page_popups  # noqa: E402
from scripts.common.critical_logger import log_critical  # noqa: E402
from scripts.common.logger import get_logger  # noqa: E402

_log = get_logger(__name__)
SITEMAP_DIR = ROOT / "data" / "sitemap"
SITEMAP_DIR.mkdir(parents=True, exist_ok=True)


# ── 네이버 개인 서비스 카탈로그 ─────────────────────────────────────────────

PERSONAL_SERVICES = [
    # (이름, URL, 카테고리, 설명)
    ("naver_main", "https://www.naver.com/", "포털", "네이버 메인"),
    ("my_naver", "https://naver.com/main", "포털", "My네이버"),
    ("nid_profile", "https://nid.naver.com/user2/help/myInfoV2", "계정", "내 정보"),
    ("nid_security", "https://nid.naver.com/user2/help/secureV2", "계정", "보안 설정"),
    # 콘텐츠
    ("blog_admin", "https://admin.blog.naver.com/", "콘텐츠", "블로그 관리"),
    ("blog_my", "https://blog.naver.com/skyjwsin", "콘텐츠", "내 블로그"),
    ("blog_stats", "https://blog.naver.com/PostWriteFormDocControl.naver?blogId=skyjwsin", "콘텐츠", "블로그 통계"),
    ("influencer", "https://in.naver.com/", "콘텐츠", "인플루언서 센터"),
    ("series", "https://series.naver.com/", "콘텐츠", "시리즈"),
    ("moment", "https://m.blog.naver.com/MomentFeed.naver", "콘텐츠", "모먼트"),
    # 커뮤니티/소통
    ("cafe_my", "https://section.cafe.naver.com/ca-fe/home/recent-articles", "커뮤니티", "내 카페"),
    ("cafe_admin", "https://cafe.naver.com/ManageCafe.nhn", "커뮤니티", "카페 관리"),
    ("talk", "https://talk.naver.com/", "커뮤니티", "톡톡"),
    ("band", "https://band.us/", "커뮤니티", "밴드"),
    # 메일/일정
    ("mail", "https://mail.naver.com/", "메일", "네이버 메일"),
    ("calendar", "https://calendar.naver.com/", "일정", "네이버 캘린더"),
    # 클라우드/파일
    ("mybox", "https://mybox.naver.com/", "클라우드", "마이박스"),
    # 결제/금융
    ("pay", "https://pay.naver.com/", "결제", "네이버 페이"),
    ("pay_history", "https://order.pay.naver.com/home", "결제", "결제 내역"),
    ("mybiz", "https://mybiz.pay.naver.com/dashboard", "결제", "마이비즈"),
    ("pay_point", "https://nid.naver.com/user2/help/payV2", "결제", "포인트 관리"),
    # 커머스/사업
    ("smartstore", "https://sell.smartstore.naver.com/#/home/dashboard", "커머스", "스마트스토어 셀러센터"),
    ("shopping_partner", "https://center.shopping.naver.com/", "커머스", "쇼핑파트너센터"),
    ("commerce_solution", "https://solution.smartstore.naver.com/", "커머스", "커머스솔루션마켓"),
    ("ads", "https://ads.naver.com/", "광고", "광고주센터"),
    ("ad_searchad", "https://searchad.naver.com/", "광고", "검색광고"),
    ("ad_smartchannel", "https://saedu.naver.com/", "광고", "성과형 광고"),
    # 부동산/지도/검색 도구
    ("maps_my", "https://map.naver.com/p/?c=My", "도구", "내 지도"),
    ("place_owner", "https://new.smartplace.naver.com/", "도구", "스마트플레이스"),
    # 클로바/AI
    ("clova", "https://clova.ai/ko", "AI", "Clova"),
    # 콘텐츠 소비
    ("webtoon", "https://comic.naver.com/index", "엔터", "네이버 웹툰"),
    ("vibe", "https://vibe.naver.com/", "엔터", "VIBE 음악"),
    ("tv", "https://tv.naver.com/", "엔터", "네이버 TV"),
    ("sports", "https://sports.news.naver.com/", "엔터", "스포츠"),
]


# ── 페이지 메타 추출 JS ─────────────────────────────────────────────────────

EXTRACT_JS = r"""
() => {
    const isVisible = (el) => {
        const s = window.getComputedStyle(el);
        if (s.display === 'none' || s.visibility === 'hidden') return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    };

    const txt = (document.body?.innerText || '').toLowerCase();

    const result = {
        url: location.href,
        title: document.title,
        captured_at: new Date().toISOString(),
        body_len: (document.body?.innerText || '').length,
    };

    // 로그인 상태
    result.has_logout = /로그아웃|sign\s*out|logout/i.test(txt);
    result.pw_field = document.querySelectorAll('input[type="password"]').length;

    // 사용자명 추출
    const userSelectors = ['.user-name', '.username', '[class*="user-name"]',
                           '[class*="profile-name"]', '#gnb_my_name',
                           '[class*="MyView"]'];
    let userName = null;
    for (const sel of userSelectors) {
        const el = document.querySelector(sel);
        if (el && isVisible(el)) {
            userName = (el.innerText || '').trim().substring(0, 30);
            if (userName) break;
        }
    }
    if (!userName) {
        const m = /([가-힣A-Za-z0-9_.-]{2,20})\s*님/.exec(document.body?.innerText || '');
        if (m) userName = m[1];
    }
    result.user = userName;

    // 메뉴 추출 (상위)
    const menus = [];
    const seen = new Set();
    document.querySelectorAll('nav a, .gnb a, header a, [role=navigation] a, .menu a').forEach(a => {
        if (!isVisible(a)) return;
        const t = (a.innerText || '').trim().replace(/\s+/g, ' ').substring(0, 30);
        const h = a.href || '';
        if (t && t.length >= 2 && !seen.has(t)) {
            seen.add(t);
            menus.push({text: t, href: h.substring(0, 150)});
        }
    });
    result.menus = menus.slice(0, 40);

    // 통계/카운터 텍스트 (예: "오늘 방문 N명")
    const stats = [];
    document.querySelectorAll('.stat, [class*="stat"], [class*="count"], [class*="number"]').forEach(el => {
        if (!isVisible(el)) return;
        const t = (el.innerText || '').trim();
        if (t && t.length < 30 && /[\d,]+/.test(t)) {
            stats.push(t.substring(0, 40));
        }
    });
    result.stats = [...new Set(stats)].slice(0, 15);

    // 에러/접근불가 감지
    result.access_denied = /접근\s*권한|권한이\s*없|access\s*denied|로그인이\s*필요|로그인하기/i.test(txt) &&
                           !result.has_logout;

    return result;
}
"""


# ── 메인 ────────────────────────────────────────────────────────────────────


def explore_service(page, svc: dict) -> dict:
    name, url, category, desc = svc["name"], svc["url"], svc["category"], svc["desc"]
    result = {
        "name": name,
        "category": category,
        "desc": desc,
        "url": url,
        "ok": False,
    }
    try:
        page.goto(url, timeout=15000, wait_until="domcontentloaded")
        time.sleep(2.5)
        # 팝업/별도창 정리 - 실패는 무시하고 계속 진행(읽기전용 탐색)
        with contextlib.suppress(Exception):
            handle_page_popups(page, timeout_s=1.5)

        meta = page.evaluate(EXTRACT_JS)
        result["meta"] = meta
        result["ok"] = True
        result["final_url"] = meta.get("url", "")
        result["user"] = meta.get("user")
        result["has_logout"] = meta.get("has_logout")
        result["menu_count"] = len(meta.get("menus", []))
        result["access_denied"] = meta.get("access_denied")

        # 사이트맵 개별 저장
        out = SITEMAP_DIR / f"naver_{name}_auto.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:  # noqa: BLE001 - 네이버 개인 서비스 전체 사이트맵 탐색(읽기전용) — 각 except는 팝업 무시 또는 서비스별 오류를 결과 dict의 error 필드에 기록하고 다음 서비스 탐색으로 계속, 최종 예외도 traceback 출력 후 안전 종료.
        result["error"] = str(e)[:150]
    return result


def _print_category_summary(by_cat: dict) -> None:
    """카테고리별 요약 출력."""
    print(f"\n{'=' * 70}")
    print("  카테고리별 요약")
    print(f"{'=' * 70}")
    for cat in sorted(by_cat):
        items = by_cat[cat]
        ok = sum(1 for r in items if r["ok"])
        logged = sum(1 for r in items if r["ok"] and r.get("has_logout"))
        denied = sum(1 for r in items if r["ok"] and r.get("access_denied"))
        print(f"  {cat:<10} 성공 {ok}/{len(items)} | 로그인 인식 {logged} | 접근불가 {denied}")


def main():
    print(f"\n{'=' * 70}")
    print(f"  네이버 개인 서비스 전체 탐색  |  {len(PERSONAL_SERVICES)}개")
    print(f"{'=' * 70}\n")

    existing = get_page()
    ctx = existing.context
    # 새 탭 생성 (현재 작업 보존)
    page = ctx.new_page()
    print(f"  [신규 탭 생성] 총 {len(ctx.pages)}개 탭")

    # 로그인 상태 확인 (네이버 메인 진입)
    print("\n  [로그인 상태 확인] naver.com 진입...")
    page.goto("https://www.naver.com/", timeout=15000, wait_until="domcontentloaded")
    time.sleep(2)
    state = detect_login_state(page)
    if state.get("logged_in"):
        print(f"  ✓ 로그인됨: {state.get('user')}")
        log_critical(
            "PORTAL_VISIT", "네이버 개인 서비스 탐색 시작", user=state.get("user"), services=len(PERSONAL_SERVICES)
        )
    else:
        print("  ⚠ 로그인 안됨 (탐색은 계속 — 일부 서비스 접근 제한 가능)")

    # 서비스 순회
    print("\n  [서비스 탐색]")
    results = []
    for i, (name, url, category, desc) in enumerate([(s[0], s[1], s[2], s[3]) for s in PERSONAL_SERVICES], 1):
        svc = {"name": name, "url": url, "category": category, "desc": desc}
        print(f"    [{i:2}/{len(PERSONAL_SERVICES)}] [{category:<6}] {desc:<22}", end=" ", flush=True)
        r = explore_service(page, svc)
        results.append(r)

        if not r["ok"]:
            print(f"✗  {r.get('error', '')[:50]}")
            continue

        marks = []
        if r.get("has_logout"):
            marks.append("🔓로그인")
        if r.get("access_denied"):
            marks.append("⚠접근불가")
        user_str = f" [{r.get('user', '')}]" if r.get("user") else ""
        marks_str = " " + " ".join(marks) if marks else ""
        print(f"✓  메뉴 {r.get('menu_count', 0):>2}개{marks_str}{user_str}")

        # 별도 창 팝업 정리 - 실패는 무시하고 계속 진행(읽기전용 탐색)
        with contextlib.suppress(Exception):
            close_popup_windows(page)

    # 결과 정리
    by_cat = {}
    for r in results:
        by_cat.setdefault(r["category"], []).append(r)

    _print_category_summary(by_cat)

    # 통합 저장
    summary = {
        "explored_at": datetime.now().isoformat(timespec="seconds"),
        "logged_in_user": state.get("user"),
        "total": len(results),
        "success": sum(1 for r in results if r["ok"]),
        "logged_in_pages": sum(1 for r in results if r.get("has_logout")),
        "by_category": {cat: len(items) for cat, items in by_cat.items()},
        "services": results,
    }
    out = ROOT / "data" / "sitemap" / "naver_personal_summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  ✓ 통합 저장: {out.name}")
    print("  ✓ 개별 사이트맵: data/sitemap/naver_*_auto.json")

    log_critical(
        "PORTAL_VISIT",
        "네이버 개인 서비스 탐색 완료",
        user=state.get("user"),
        success=summary["success"],
        logged_pages=summary["logged_in_pages"],
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n중단됨")
    except Exception:  # noqa: BLE001 - 네이버 개인 서비스 전체 사이트맵 탐색(읽기전용) — 각 except는 팝업 무시 또는 서비스별 오류를 결과 dict의 error 필드에 기록하고 다음 서비스 탐색으로 계속, 최종 예외도 traceback 출력 후 안전 종료.
        import traceback

        traceback.print_exc()
        sys.exit(1)
