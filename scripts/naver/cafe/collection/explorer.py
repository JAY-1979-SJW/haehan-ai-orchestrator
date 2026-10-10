"""네이버 카페 탐색 — 내 카페 목록 조회 / 카페 구조 파악.

사용:
    python -m scripts.naver.cafe._runner my-cafes
    python -m scripts.naver.cafe._runner explore --cafe-url=https://cafe.naver.com/0moo
"""

from __future__ import annotations

import json
import re
import time

from playwright.sync_api import Page

from ai_orchestrator.paths.runtime import data_dir
from scripts.common.app_paths import repo_root
from scripts.common.logger import get_logger
from scripts.naver.common.auth import ensure_naver_login

_log = get_logger(__name__)

ROOT = repo_root()
_DATA_DIR = data_dir() / "cafe"

_CAFE_HOME_URL = "https://section.cafe.naver.com/ca-fe/home"
_LIST_URL = (
    "https://cafe.naver.com/ArticleList.nhn?search.clubid={clubid}&search.boardtype=L&search.page=1&userDisplay=1"
)


# 가입카페 전용 API (홈 DOM에는 추천/최근방문 카페가 섞여 부정확).
_MY_CAFE_API = (
    "https://apis.naver.com/cafe-home-web/cafe-home/v3/homepc?myCafeCount=500&useMyCafeEvent=false&articleCount=0"
)


def _fetch_joined_cafes_via_api(page: Page) -> list[dict]:
    """가입카페 전용 API로 정확한 목록만 조회(추천/최근방문 제외). 실패 시 빈 리스트."""
    try:
        raw = page.evaluate(
            """async (u) => {
                try {
                    const ctrl = new AbortController();
                    const timer = setTimeout(() => ctrl.abort(), 25000);
                    const r = await fetch(u, {headers: {'Accept': 'application/json'}, credentials: 'include', signal: ctrl.signal});
                    clearTimeout(timer);
                    if (!r.ok) return '';
                    return await r.text();
                } catch (e) { return ''; }
            }""",
            _MY_CAFE_API,
        )
        if not raw:
            return []
        data = json.loads(raw)
        result = data.get("message", {}).get("result", {}) or {}
        items = (result.get("myCafe", {}) or {}).get("cafes", []) or []
        out = []
        for c in items:
            slug = c.get("cafeUrl", "")
            if not slug:
                continue
            out.append(
                {
                    "cafe_id": slug,
                    "cafe_name": c.get("cafeName", ""),
                    "href": f"https://cafe.naver.com/{slug}",
                    "clubid": str(c.get("cafeId", "")),  # 숫자 clubid — 수집 시 재사용 가능
                    "member_count": 0,
                    # 활동 필드(가입 카페 활동 분석용 — 이미지 주소·광고 정보 등은 가져오지 않는다)
                    "new_articles": int(c.get("articleNewCounts") or 0),
                    "last_update": str(c.get("lastUpdateDate") or ""),
                    "last_visit": str(c.get("lastVisitDate") or ""),
                    "favorite": bool(c.get("favoriteCafe")),
                    "manage": bool(c.get("manageCafe")),
                    "dormant": bool(c.get("dormantCafe")),
                    "power": bool(c.get("powerCafe")),
                    "open_type": str(c.get("openType") or ""),
                }
            )
        return out
    except Exception as e:  # noqa: BLE001 - 가입 카페 목록 API 조회(읽기전용) - 조회 실패 시 빈 리스트 반환
        _log.debug("[explorer] 가입카페 API 오류: %s", str(e)[:100])
        return []


def get_my_cafes(page: Page) -> list[dict]:
    """내가 가입한 카페 목록 반환(호환용). 출처가 필요하면 `get_my_cafes_with_source` 를 쓴다.

    Returns:
        [{ cafe_id, cafe_name, href, member_count }]
    """
    return get_my_cafes_with_source(page)[0]


def get_my_cafes_with_source(page: Page) -> tuple[list[dict], str]:
    """내 가입 카페 목록과 그 **출처**(`api`=가입카페 전용 API, `dom`=화면 읽기 대신 — 추천·최근 방문이 섞일 수 있음).

    출처는 변동 비교의 보호 규칙이 쓴다(화면 읽기 결과로는 신규·탈퇴를 판정하지 않는다).
    """
    if not ensure_naver_login(page).get("ok"):
        raise RuntimeError("네이버 로그인 필요")

    _log.info("[explorer] 카페홈 접속: %s", _CAFE_HOME_URL)
    page.goto(_CAFE_HOME_URL, timeout=30000, wait_until="domcontentloaded")
    time.sleep(2)

    # 1순위: 가입카페 전용 API (정확)
    cafes = _fetch_joined_cafes_via_api(page)
    if cafes:
        _log.info("[explorer] 내 가입카페 %d개 (API)", len(cafes))
        return cafes, "api"

    # 폴백: API 실패 시 기존 DOM 스크래핑(추천/최근방문 혼입 가능 — 최후수단)
    _log.warning("[explorer] 가입카페 API 실패 — DOM 폴백")
    time.sleep(6)
    cafes = page.evaluate(r"""() => {
        const seen = new Set();
        const result = [];
        document.querySelectorAll('a[href]').forEach(a => {
            const href = a.href || '';
            const m = href.match(/^https:\/\/cafe\.naver\.com\/([a-zA-Z0-9_]+)$/);
            if (!m) return;
            const cafeId = m[1];
            if (cafeId === 'cafesupport') return;
            if (seen.has(cafeId)) return;
            seen.add(cafeId);

            // 카페명: 링크 자신 또는 인접 요소에서 추출
            const container = a.closest('li, [class*="item"], [class*="cafe"]') || a.parentElement;
            let name = '';
            if (container) {
                const nameEl = container.querySelector('[class*="name"], strong, b, .title');
                name = (nameEl?.innerText || container.innerText || '').trim().split('\n')[0];
            }
            if (!name) name = a.innerText.trim().split('\n')[0];

            // 멤버 수
            const memberText = container?.innerText || '';
            const memberM = memberText.match(/멤버수\s*[\n\s]*([\d,]+)/);
            const member_count = memberM ? parseInt(memberM[1].replace(/,/g, '')) : 0;

            result.push({ cafe_id: cafeId, cafe_name: name, href, member_count });
        });
        return result;
    }""")

    _log.info("[explorer] 내 카페 %d개 확인(화면 읽기)", len(cafes))
    return cafes, "dom"


def explore_cafe(page: Page, cafe_url: str) -> dict:
    """카페 구조 탐색 — 게시판 목록, 회원수, 소개 반환.

    Args:
        page: Playwright 페이지
        cafe_url: 카페 홈 URL (예: https://cafe.naver.com/0moo)

    Returns:
        {
            cafe_id, cafe_name, clubid, member_count,
            boards: [{ name, menu_id }],
            description, created_at
        }
    """
    if not ensure_naver_login(page).get("ok"):
        raise RuntimeError("네이버 로그인 필요")

    _log.info("[explorer] 카페 탐색: %s", cafe_url)
    page.goto(cafe_url, timeout=25000, wait_until="domcontentloaded")
    time.sleep(4)

    info = page.evaluate(r"""() => {
        // clubid 추출
        let clubid = '';
        const scripts = Array.from(document.querySelectorAll('script'));
        for (const s of scripts) {
            const m = (s.textContent || '').match(/clubid['":\s]+(\d+)/i);
            if (m) { clubid = m[1]; break; }
        }
        if (!clubid) {
            const m = location.href.match(/clubid=(\d+)/);
            if (m) clubid = m[1];
        }

        // 카페명
        const cafe_name = (
            document.querySelector('.cafe-name, .cafetitle, h1.title, [class*="cafe-title"]')?.innerText ||
            document.title
        ).trim().split('\n')[0];

        // 회원수
        const memberText = document.querySelector('[class*="member"], .member-count, .total_count')?.innerText || '';
        const memberM = memberText.replace(/,/g, '').match(/\d+/);
        const member_count = memberM ? parseInt(memberM[0]) : 0;

        // 게시판 목록 (좌측 메뉴)
        const boardEls = document.querySelectorAll(
            '.cafe-menu-list li a, #menuListBar li a, .MenuList a, [class*="board-list"] a, [class*="menu-list"] a'
        );
        const boards = Array.from(boardEls).map(a => {
            const m = a.href.match(/menuid=(\d+)/);
            return { name: a.innerText.trim(), menu_id: m ? m[1] : '' };
        }).filter(b => b.name && b.menu_id);

        // 소개
        const description = document.querySelector(
            '.cafe-intro, .intro-text, [class*="description"], [class*="intro"]'
        )?.innerText?.trim() || '';

        return { cafe_name, clubid, member_count, boards, description };
    }""")

    # URL에서 cafe_id 추출
    m = re.search(r"cafe\.naver\.com/([a-zA-Z0-9_]+)", cafe_url)
    cafe_id = m.group(1) if m else ""

    result = {
        "cafe_id": cafe_id,
        "cafe_url": cafe_url,
        **info,
    }
    _log.info("[explorer] 탐색 완료: %s (게시판 %d개)", result.get("cafe_name"), len(info.get("boards", [])))
    return result


def save_my_cafes(cafes: list[dict]) -> str:
    """내 카페 목록 JSON 저장."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _DATA_DIR / "my_cafes.json"
    path.write_text(json.dumps(cafes, ensure_ascii=False, indent=2), encoding="utf-8")
    _log.info("[explorer] 내 카페 목록 저장: %s", path)
    return str(path)
