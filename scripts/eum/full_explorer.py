"""EUM 사이트 전체 세밀 탐색 스크립트.

기존 site_explorer.py보다 훨씬 깊게 탐색:
  - 로그인 후 메뉴 전체 트리 수집
  - 모든 WEBMAN 페이지 방문 + 페이지네이션까지 탐색
  - 각 페이지의 테이블 헤더/컬럼 구조, 필터 select 옵션 전체
  - 폼 action/method/입력필드 타입 상세
  - 버튼 텍스트/onclick/href 전체
  - 팝업/모달 존재 여부
  - API 엔드포인트 탐지 (XHR/Fetch 패턴)
  - 페이지별 데이터 샘플 1행 추출
  - 접근 제한 페이지 별도 분류

결과 파일:
  data/eum_full_site_map.json  — 전체 탐색 결과
  data/eum_full_site_map.txt   — 사람이 읽기 쉬운 요약 보고서

사용:
    python scripts/eum/full_explorer.py
    python scripts/entry/cdp_cli.py eum explore
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from scripts.eum.access_handler import detect_and_handle, is_access_blocked  # noqa: E402
from scripts.common.logger import get_logger  # noqa: E402
from scripts.common.op_log import log_op, op_context  # noqa: E402
from scripts.browser.popup.popup_classifier import classify  # noqa: E402
from scripts.browser.navigator.popup_watcher import install_watcher, poll_events  # noqa: E402

log = get_logger(__name__)

EUM_BASE = "https://eum.cw.or.kr"


def _eum_dir() -> Path:
    from scripts.common.data_paths import get_app_dir

    return get_app_dir("eum")


DATA_DIR = _eum_dir()

# ── 탐색 대상 페이지 목록 ──────────────────────────────────────────────
# 알려진 WEBMAN 코드 + 추정 코드까지 포함
WEBMAN_TARGETS = [
    # 단말기 관리
    ("WEBMAN370M00", "설치안내대상"),
    ("WEBMAN380M00", "현장별단말기목록"),
    ("WEBMAN381M00", "단말기설치계획"),
    ("WEBMAN382M00", "단말기철거"),
    ("WEBMAN383M00", "철거확인"),
    ("WEBMAN390M00", "단말기설치현황"),
    ("WEBMAN391M00", "단말기설치현황상세"),
    ("WEBMAN400M00", "단말기이력관리"),
    ("WEBMAN401M00", "단말기이력상세"),
    # 공사/현장 관련 추정
    ("WEBMAN300M00", "공사관리"),
    ("WEBMAN310M00", "공사목록"),
    ("WEBMAN320M00", "현장관리"),
    ("WEBMAN330M00", "사업장관리"),
    # 회원/업체 관련 추정
    ("WEBMAN100M00", "업체관리"),
    ("WEBMAN110M00", "회원관리"),
    ("WEBMAN200M00", "공제가입관리"),
    # 통계/보고서 추정
    ("WEBMAN500M00", "통계조회"),
    ("WEBMAN510M00", "월별통계"),
    ("WEBMAN600M00", "보고서"),
    # 설정/관리
    ("WEBMAN700M00", "시스템관리"),
    ("WEBMAN710M00", "권한관리"),
    ("WEBMAN800M00", "공지사항"),
    ("WEBMAN900M00", "마이페이지"),
]

# 최상위 메뉴 경로 후보
MENU_PATHS = [
    "/main",
    "/mypage",
    "/web/man/menu",
    "/web/main",
]

# ── JavaScript 추출 코드 ──────────────────────────────────────────────

_JS_FULL_EXTRACT = """
() => {
    const result = {};

    // 1. 페이지 기본 정보
    result.url = window.location.href;
    result.title = document.title;
    result.readyState = document.readyState;

    // 2. 메뉴/네비게이션 전체
    const navSelectors = [
        'nav', '.gnb', '.lnb', '.snb', '#nav', '#menu',
        '.menu', '.nav', 'ul.menu', '.sidebar', '.sidemenu',
        '[class*="menu"]', '[class*="nav"]', '[id*="menu"]', '[id*="nav"]'
    ];
    const navLinks = new Map();
    navSelectors.forEach(sel => {
        document.querySelectorAll(sel + ' a').forEach(a => {
            const href = a.href || '';
            const text = (a.innerText || a.textContent || '').trim();
            if (text && href && !href.startsWith('javascript') && !navLinks.has(href)) {
                navLinks.set(href, {
                    text, href,
                    id: a.id || '',
                    cls: a.className || '',
                    parent_sel: sel
                });
            }
        });
    });
    result.nav_links = Array.from(navLinks.values());

    // 3. 모든 링크
    result.all_links = Array.from(document.querySelectorAll('a[href]'))
        .map(a => ({
            text: (a.innerText || '').trim().substring(0, 50),
            href: a.href,
            onclick: a.getAttribute('onclick') || ''
        }))
        .filter(l => l.text || l.onclick)
        .slice(0, 100);

    // 4. 테이블 전체 (헤더 + 데이터 샘플 1행)
    result.tables = Array.from(document.querySelectorAll('table')).map((t, idx) => {
        const allTR = t.querySelectorAll('tr');
        const headers = [];
        const sample_row = [];

        // 헤더 수집 (th 또는 첫 행 td)
        let headerRowCount = 0;
        allTR.forEach((tr, i) => {
            const ths = tr.querySelectorAll('th');
            if (ths.length > 0) {
                ths.forEach(th => headers.push((th.innerText || '').trim()));
                headerRowCount++;
            }
        });

        // 데이터 첫 행 샘플
        let dataFound = false;
        allTR.forEach((tr, i) => {
            if (dataFound) return;
            const tds = tr.querySelectorAll('td');
            if (tds.length > 0) {
                tds.forEach(td => sample_row.push((td.innerText || '').trim().substring(0, 30)));
                dataFound = true;
            }
        });

        return {
            index: idx,
            id: t.id || '',
            cls: t.className || '',
            total_rows: allTR.length,
            header_rows: headerRowCount,
            headers: headers,
            sample_row: sample_row,
            col_count: headers.length || sample_row.length
        };
    });

    // 5. 폼 전체 (action/method/입력필드 타입까지)
    result.forms = Array.from(document.querySelectorAll('form')).map((f, idx) => {
        const inputs = Array.from(f.querySelectorAll('input, select, textarea')).map(el => ({
            tag: el.tagName.toLowerCase(),
            type: el.type || '',
            name: el.name || '',
            id: el.id || '',
            placeholder: el.placeholder || '',
            required: el.required || false,
            value_sample: el.type === 'password' ? '***' : (el.value || '').substring(0, 20)
        }));
        return {
            index: idx,
            id: f.id || '',
            name: f.name || '',
            action: f.action || '',
            method: (f.method || 'GET').toUpperCase(),
            inputs: inputs
        };
    });

    // 6. 버튼 전체
    result.buttons = Array.from(document.querySelectorAll(
        'button, input[type="button"], input[type="submit"], input[type="reset"]'
    )).map(b => ({
        text: (b.innerText || b.value || '').trim(),
        type: b.type || '',
        id: b.id || '',
        cls: b.className || '',
        onclick: b.getAttribute('onclick') || '',
        disabled: b.disabled || false
    })).filter(b => b.text).slice(0, 30);

    // 7. Select 필터 전체 (모든 옵션 포함)
    result.selects = Array.from(document.querySelectorAll('select')).map(s => ({
        id: s.id || '',
        name: s.name || '',
        cls: s.className || '',
        options: Array.from(s.options).map(o => ({
            value: o.value,
            text: o.text.trim()
        }))
    }));

    // 8. 팝업/모달 탐지
    result.modals = Array.from(document.querySelectorAll(
        '.modal, .popup, [class*="modal"], [class*="popup"], [role="dialog"]'
    )).map(m => ({
        id: m.id || '',
        cls: m.className || '',
        visible: m.offsetParent !== null,
        title: (m.querySelector('.modal-title, .popup-title, h3, h4')?.innerText || '').trim()
    }));

    // 9. 페이지네이션 탐지
    const pagers = document.querySelectorAll(
        '.pager, .pagination, [class*="pager"], [class*="pagination"]'
    );
    result.pagination = {
        exists: pagers.length > 0,
        pages: Array.from(pagers).map(p => ({
            cls: p.className,
            text: (p.innerText || '').trim().substring(0, 100)
        }))
    };

    // 10. 검색 조건 영역 탐지
    const searchAreas = document.querySelectorAll(
        '.search, .search-area, [class*="search"], [id*="search"], form'
    );
    result.search_area = {
        exists: searchAreas.length > 0,
        count: searchAreas.length
    };

    // 11. 에러/접근제한 메시지 탐지
    const bodyText = document.body?.innerText || '';
    result.access_denied = (
        bodyText.includes('접근') && bodyText.includes('권한') ||
        bodyText.includes('403') ||
        bodyText.includes('로그인이 필요') ||
        bodyText.includes('권한이 없')
    ) && !bodyText.includes('로그아웃');

    result.error_messages = Array.from(document.querySelectorAll(
        '.error, .alert, .warning, [class*="error"], [class*="alert"]'
    )).map(e => (e.innerText || '').trim()).filter(t => t).slice(0, 5);

    // 12. 스크립트에서 API URL 패턴 추출
    const scripts = Array.from(document.scripts);
    const apiUrls = new Set();
    scripts.forEach(s => {
        const src = s.src || s.innerText || '';
        const matches = src.match(/['"](\\/[a-zA-Z0-9\\/\\-_]+\\.(?:json|do|action|api)[^'"]*)['"]/g) || [];
        matches.forEach(m => apiUrls.add(m.replace(/['"]/g, '')));
    });
    result.api_urls = Array.from(apiUrls).slice(0, 20);

    return result;
}
"""

_JS_WAIT_READY = """
() => document.readyState === 'complete'
"""


# ── 핵심 탐색 함수 ───────────────────────────────────────────────────


def _safe_goto(page, url: str, timeout: int = 15000) -> bool:
    """URL 이동. 실패 시 False 반환."""
    try:
        page.goto(url, timeout=timeout)
        page.wait_for_load_state("networkidle", timeout=timeout)
        return True
    except Exception as e:  # noqa: BLE001 - EUM(건설근로자공제회) 사이트 구조 탐지 읽기전용 스크립트 - 실패 시 print 경고 후 빈 dict/list 반환
        log.debug("goto 실패: url=%s err=%s", url, e)
        return False


def _find_abnormal_keyword(page, url: str) -> tuple[str | None, str]:
    """popup_watcher 이벤트 → 페이지 텍스트 순으로 비정상 접근 키워드를 찾는다. (키워드, 스니펫)."""
    # 1단계: popup_watcher 설치
    try:
        install_watcher(page)
        time.sleep(0.5)  # MutationObserver 초기화 대기
    except Exception as e:  # noqa: BLE001 - EUM(건설근로자공제회) 사이트 구조 탐지 읽기전용 스크립트 - 실패 시 print 경고 후 빈 dict/list 반환
        log.debug(f"[EUM] popup_watcher 설치 실패: {e}")

    # 2단계: popup_watcher 이벤트 확인 (비정상 접근)
    events = poll_events(page)
    detected_keyword = None
    detected_snippet = ""

    for event in events:
        marker = event.get("marker", "")
        # 비정상 접근 관련 마커 확인
        if marker in [
            "비정상적인 접근",
            "자동화 프로그램",
            "자동 프로그램",
            "봇으로 판단",
            "접근 차단",
            "이용이 제한",
            "서비스 차단",
            "Abnormal access",
            "bot detected",
        ]:
            detected_keyword = marker
            detected_snippet = event.get("snippet", "")
            log.warning(f"[EUM] popup_watcher 감지: '{marker}' @ {url}")
            break

    # 3단계: 팝업이 감지되지 않으면 fallback으로 page.text_content() 확인
    if not detected_keyword:
        page_text = page.text_content().strip()
        abnormal_keywords = [
            "비정상적인 접근",
            "자동 프로그램",
            "자동화",
            "봇으로 판단",
            "접근 차단",
            "이용이 제한",
            "서비스 차단",
            "보안상의 이유",
            "Abnormal access",
            "bot detected",
            "automated access",
        ]
        for kw in abnormal_keywords:
            if kw.lower() in page_text.lower():
                detected_keyword = kw
                detected_snippet = page_text[:200]
                log.warning(f"[EUM] 텍스트 매칭 감지: '{kw}' @ {url}")
                break
    return detected_keyword, detected_snippet


def _check_abnormal_access(page, url: str, info: dict[str, Any]) -> bool:
    """비정상 접근(봇 차단 등) 감지·복구 시도. 복구 실패로 접근 불가면 info 를 갱신하고 True."""
    try:
        detected_keyword, detected_snippet = _find_abnormal_keyword(page, url)

        # 4단계: 감지된 비정상 접근 처리
        if detected_keyword:
            decision = classify(marker=detected_keyword, snippet=detected_snippet)

            if is_access_blocked(decision):
                log.critical(f"[EUM] 접근 차단됨: {decision['category']}")

                # 자동 복구 시도
                if detect_and_handle(page, decision):
                    log.info("[EUM] 접근 복구됨, 재시도")
                else:
                    info["accessible"] = False
                    info["error"] = f"접근 차단: {decision['category']} (자동 복구 실패)"
                    log.critical(f"[EUM] 접근 불가능: {info['error']}")
                    return True

    except Exception as e:  # noqa: BLE001 - EUM(건설근로자공제회) 사이트 구조 탐지 읽기전용 스크립트 - 실패 시 print 경고 후 빈 dict/list 반환
        log.debug(f"[EUM] 비정상 접근 감지 오류 (무시): {e}")
    return False


def _extract_page(page, url: str, name: str) -> dict[str, Any]:
    """단일 페이지 전체 구조 추출."""
    info: dict[str, Any] = {
        "url": url,
        "name": name,
        "final_url": "",
        "accessible": True,
        "error": "",
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
    }

    ok = _safe_goto(page, url)
    if not ok:
        info["accessible"] = False
        info["error"] = "페이지 이동 실패 (타임아웃 또는 네트워크 오류)"
        return info

    info["final_url"] = page.url

    # 리다이렉트로 로그인 페이지 이동 감지
    if "login" in page.url.lower() and "login" not in url.lower():
        info["accessible"] = False
        info["error"] = "로그인 페이지로 리다이렉트 — 세션 만료 또는 접근 제한"
        return info

    # ⚠️  비정상 접근 감지 (popup_watcher 통합)
    if _check_abnormal_access(page, url, info):
        return info

    # JS 전체 추출
    try:
        extracted = page.evaluate(_JS_FULL_EXTRACT)
        info.update(extracted)
    except Exception as e:  # noqa: BLE001 - EUM(건설근로자공제회) 사이트 구조 탐지 읽기전용 스크립트 - 실패 시 print 경고 후 빈 dict/list 반환
        log.warning("JS 추출 실패: url=%s err=%s", url, e)
        info["error"] = f"JS 실행 오류: {e}"

    # 접근 제한 확인
    if info.get("access_denied"):
        info["accessible"] = False
        info["error"] = "접근 제한 (권한 없음)"

    return info


def _explore_webman_pages(page) -> list[dict[str, Any]]:
    """알려진 + 추정 WEBMAN 페이지 전체 탐색."""
    results = []
    total = len(WEBMAN_TARGETS)

    for i, (code, name) in enumerate(WEBMAN_TARGETS, 1):
        url = f"{EUM_BASE}/web/man/{code}"
        log.info("[%d/%d] 탐색: %s (%s)", i, total, code, name)
        print(f"  [{i:2d}/{total}] {code} ({name})...", end=" ", flush=True)

        data = _extract_page(page, url, name)
        data["code"] = code

        accessible = data.get("accessible", True)
        table_cnt = len(data.get("tables", []))
        select_cnt = len(data.get("selects", []))
        btn_cnt = len(data.get("buttons", []))

        if accessible:
            print(f"접근가능  테이블:{table_cnt} 필터:{select_cnt} 버튼:{btn_cnt}")
        else:
            print(f"접근제한  ({data.get('error', '')})")

        results.append(data)
        time.sleep(0.5)  # 서버 부하 방지

    return results


def _explore_menu(page) -> dict[str, Any]:
    """메인 페이지 메뉴 구조 탐색."""
    log.info("메인 메뉴 탐색 시작")
    menu_result: dict[str, Any] = {
        "main_page": {},
        "mypage": {},
        "all_internal_links": [],
    }

    # 메인 페이지
    if _safe_goto(page, f"{EUM_BASE}/main"):
        try:
            data = page.evaluate(_JS_FULL_EXTRACT)
            menu_result["main_page"] = data
            # 내부 링크만 분류
            menu_result["all_internal_links"] = [
                lnk
                for lnk in data.get("all_links", [])
                if EUM_BASE in lnk.get("href", "") or lnk.get("href", "").startswith("/")
            ]
        except Exception as e:  # noqa: BLE001 - EUM(건설근로자공제회) 사이트 구조 탐지 읽기전용 스크립트 - 실패 시 print 경고 후 빈 dict/list 반환
            log.warning("메인 페이지 추출 실패: %s", e)

    # 마이페이지
    if _safe_goto(page, f"{EUM_BASE}/mypage"):
        try:
            data = page.evaluate(_JS_FULL_EXTRACT)
            menu_result["mypage"] = data
        except Exception as e:  # noqa: BLE001 - EUM(건설근로자공제회) 사이트 구조 탐지 읽기전용 스크립트 - 실패 시 print 경고 후 빈 dict/list 반환
            log.warning("마이페이지 추출 실패: %s", e)

    return menu_result


def _explore_extra_paths(page, extra_links: list[dict]) -> list[dict[str, Any]]:
    """메뉴에서 발견된 추가 링크 탐색."""
    results = []
    visited = set()

    for link in extra_links:
        href = link.get("href", "")
        if not href or href in visited:
            continue
        if EUM_BASE not in href and not href.startswith("/"):
            continue
        if any(skip in href for skip in ["javascript:", "#", "mailto:", "tel:"]):
            continue

        visited.add(href)
        url = href if href.startswith("http") else f"{EUM_BASE}{href}"

        log.info("추가 링크 탐색: %s (%s)", link.get("text", ""), url)
        data = _extract_page(page, url, link.get("text", ""))
        results.append(data)
        time.sleep(0.3)

    return results


# ── 보고서 생성 ──────────────────────────────────────────────────────


def _append_accessible_page(p: dict[str, Any], lines: list[str]) -> None:
    """접근 가능 페이지 1개의 요약 줄들을 lines 에 추가."""
    code = p.get("code", "")
    name = p.get("name", "")
    tables = p.get("tables", [])
    selects = p.get("selects", [])
    buttons = p.get("buttons", [])
    pagination = p.get("pagination", {})

    lines.append(f"\n  [{code}] {name}")
    lines.append(f"    URL: {p.get('final_url', p.get('url', ''))}")
    lines.append(f"    테이블: {len(tables)}개 / 필터: {len(selects)}개 / 버튼: {len(buttons)}개")

    for t in tables:
        if t.get("headers"):
            lines.append(f"    테이블[{t['index']}] 행:{t['total_rows']} 컬럼:{t['col_count']}")
            lines.append(f"      헤더: {' | '.join(t['headers'][:10])}")
            if t.get("sample_row"):
                lines.append(f"      샘플: {' | '.join(t['sample_row'][:10])}")

    for s in selects:
        opts = [o["text"] for o in s.get("options", [])]
        lines.append(f"    필터[{s.get('id') or s.get('name', '?')}]: {', '.join(opts[:8])}")

    for b in buttons[:8]:
        lines.append(f"    버튼: [{b.get('text', '')}] type={b.get('type', '')} id={b.get('id', '')}")

    if pagination.get("exists"):
        lines.append("    페이지네이션: 존재")

    api_urls = p.get("api_urls", [])
    if api_urls:
        lines.append(f"    API 엔드포인트 ({len(api_urls)}개):")
        for api in api_urls[:5]:
            lines.append(f"      {api}")


def _generate_report(result: dict[str, Any]) -> str:
    """탐색 결과를 사람이 읽기 쉬운 텍스트 보고서로 변환."""
    lines = []
    lines.append("=" * 70)
    lines.append("  EUM 사이트 전체 탐색 보고서")
    lines.append(f"  탐색일시: {result.get('explored_at', '')}")
    lines.append(f"  기준 URL: {EUM_BASE}")
    lines.append("=" * 70)

    # 메뉴 링크 요약
    main_data = result.get("menu", {}).get("main_page", {})
    nav_links = main_data.get("nav_links", [])
    lines.append(f"\n[메뉴 구조] 네비게이션 링크 {len(nav_links)}개")
    for lnk in nav_links:
        lines.append(f"  - {lnk.get('text', ''):<20} {lnk.get('href', '')}")

    # WEBMAN 페이지 요약
    webman_pages = result.get("webman_pages", [])
    accessible = [p for p in webman_pages if p.get("accessible")]
    denied = [p for p in webman_pages if not p.get("accessible")]

    lines.append(
        f"\n[WEBMAN 페이지] 탐색 {len(webman_pages)}개 / 접근가능 {len(accessible)}개 / 접근제한 {len(denied)}개"
    )

    lines.append("\n  ── 접근 가능 페이지 ──")
    for p in accessible:
        _append_accessible_page(p, lines)

    lines.append("\n  ── 접근 제한 페이지 ──")
    for p in denied:
        lines.append(f"  [{p.get('code', '')}] {p.get('name', '')} — {p.get('error', '')}")

    # 전체 통계
    lines.append("\n" + "=" * 70)
    lines.append("  [전체 통계]")
    total_tables = sum(len(p.get("tables", [])) for p in accessible)
    total_selects = sum(len(p.get("selects", [])) for p in accessible)
    total_buttons = sum(len(p.get("buttons", [])) for p in accessible)
    lines.append(f"  접근가능 페이지: {len(accessible)}개")
    lines.append(f"  접근제한 페이지: {len(denied)}개")
    lines.append(f"  총 테이블: {total_tables}개")
    lines.append(f"  총 필터(select): {total_selects}개")
    lines.append(f"  총 버튼: {total_buttons}개")
    lines.append("=" * 70)

    return "\n".join(lines)


# ── 메인 ────────────────────────────────────────────────────────────


def explore_all(page) -> dict[str, Any]:
    """전체 탐색 실행. 결과 dict 반환."""
    result: dict[str, Any] = {
        "explored_at": datetime.now().isoformat(timespec="seconds"),
        "base_url": EUM_BASE,
        "menu": {},
        "webman_pages": [],
        "extra_pages": [],
    }

    with op_context("eum_full_explore", base=EUM_BASE):
        # 1. 메인 메뉴 탐색
        print("\n[1단계] 메인 메뉴 탐색")
        result["menu"] = _explore_menu(page)

        # 2. 메뉴에서 발견된 추가 링크 탐색
        extra_links = result["menu"].get("all_internal_links", [])
        if extra_links:
            print(f"\n[2단계] 메뉴 내 추가 링크 탐색 ({len(extra_links)}개)")
            result["extra_pages"] = _explore_extra_paths(page, extra_links[:30])

        # 3. WEBMAN 페이지 전체 탐색
        print(f"\n[3단계] WEBMAN 페이지 탐색 ({len(WEBMAN_TARGETS)}개)")
        result["webman_pages"] = _explore_webman_pages(page)

    return result


def main() -> None:
    """CLI 실행."""
    from scripts.eum.auth import is_logged_in, login
    from scripts.browser.cdp.connection import get_page

    print("=" * 70)
    print("  EUM 전체 사이트 세밀 탐색")
    print(f"  시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    page = get_page()

    # 로그인
    if not is_logged_in(page):
        print("\n로그인 필요 — 자동 로그인 시도...")
        res = login(page)
        if not res["ok"]:
            print(f"✘ 로그인 실패: {res['reason']}")
            print("  .env 파일에 EUM_ID / EUM_PW 를 입력하세요.")
            return
        print(f"✔ 로그인 성공: {res['user']}")
    else:
        print("✔ 기존 세션 사용")

    # 탐색 실행
    result = explore_all(page)

    # JSON 저장
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    json_path = DATA_DIR / "eum_full_site_map.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    log_op("eum_full_explore", ok=True, message=f"저장: {json_path}")

    # 텍스트 보고서 저장
    report_txt = _generate_report(result)
    txt_path = DATA_DIR / "eum_full_site_map.txt"
    txt_path.write_text(report_txt, encoding="utf-8")

    # 요약 출력
    accessible = [p for p in result["webman_pages"] if p.get("accessible")]
    denied = [p for p in result["webman_pages"] if not p.get("accessible")]

    print(f"\n{'=' * 70}")
    print(f"  탐색 완료: {result['explored_at']}")
    print(f"  접근가능 페이지: {len(accessible)}개 / 접근제한: {len(denied)}개")
    print(f"  JSON: {json_path}")
    print(f"  보고서: {txt_path}")
    print(f"{'=' * 70}")
    print("\n[접근 가능 페이지]")
    for p in accessible:
        t = len(p.get("tables", []))
        s = len(p.get("selects", []))
        print(f"  ✓ {p.get('code', ''):<16} {p.get('name', ''):<20} 테이블:{t} 필터:{s}")
    if denied:
        print("\n[접근 제한 페이지]")
        for p in denied:
            print(f"  ✗ {p.get('code', ''):<16} {p.get('name', '')}")


if __name__ == "__main__":
    main()
