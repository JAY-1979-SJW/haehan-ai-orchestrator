"""범용 브라우저 에이전트 — CDP 연결된 Chrome을 자유자재로 제어.

핵심 설계 원칙
==============
1. 스마트 셀렉터: 텍스트·CSS·XPath·위치 순서로 자동 폴백
2. SPA/iframe 자동 대기: 렌더링 완료 감지
3. 새탭/팝업 자동 흡수: 같은 컨텍스트에서 처리
4. 정제된 텍스트 추출: 노이즈(네비·버튼·광고) 자동 제거
5. 페이지네이션 자동 처리

사용 예
=======
    from ai_orchestrator.local_agent.browser.agent import BrowserAgent

    with BrowserAgent() as agent:
        agent.go("https://cafe.naver.com")
        agent.click_text("내 카페 관리")
        cafes = agent.extract_links(filter_href="cafe.naver.com/")
        print(agent.read())  # 정제된 페이지 텍스트

CLI
===
    python -m ai_orchestrator.local_agent.browser.agent
"""
from __future__ import annotations

import re
import time
from typing import Optional
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from playwright.sync_api import (
    Browser, BrowserContext, Frame, Page,
    sync_playwright, TimeoutError as PWTimeout,
)

_JS_DIR = Path(__file__).parent / "_js"

def _js(name: str) -> str:
    """_js/ 디렉터리의 JS 파일을 읽어 반환."""
    return (_JS_DIR / name).read_text(encoding="utf-8")

# ── 설정 ─────────────────────────────────────────────────────────────────────
CDP_URL = "http://localhost:9222"
DEFAULT_WAIT = 2.5          # 이동 후 기본 대기(초)
RENDER_POLL  = 0.3          # 렌더링 폴링 간격
RENDER_MAX   = 8.0          # 렌더링 최대 대기

_NOISE_WORDS = {
    "새 창에서 열림", "로그인", "Copyright", "ⓒ", "NAVER",
    "바로가기", "건너뛰기", "접근성",
}
_NOISE_PATTERNS = re.compile(
    r"^(\d{1,2}|\d{4}\.\d{2}\.\d{2}\.?|좋아요\s*\d*|댓글\s*\d*)$"
)


# ── 결과 타입 ─────────────────────────────────────────────────────────────────
@dataclass
class ActionResult:
    ok: bool
    data: Any = None
    error: str = ""

    def __bool__(self): return self.ok


@dataclass
class PageInfo:
    url: str
    title: str
    text: str                        # 정제된 본문 텍스트
    links: list[dict] = field(default_factory=list)
    forms: list[dict] = field(default_factory=list)


# ── BrowserAgent ──────────────────────────────────────────────────────────────
class BrowserAgent:
    """CDP 연결된 Chrome을 제어하는 범용 브라우저 에이전트."""

    def __init__(self, cdp_url: str = CDP_URL, headless: bool = False):
        self._cdp_url = cdp_url
        self._pw = None
        self._browser: Browser | None = None
        self._ctx: BrowserContext | None = None
        self._page: Page | None = None

    # ── 컨텍스트 매니저 ──────────────────────────────────────────────────────
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.close()

    def connect(self):
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.connect_over_cdp(self._cdp_url)
        self._ctx = self._browser.contexts[0]
        self._page = self._ctx.pages[0]
        # 새탭 자동 흡수
        self._ctx.on("page", self._on_new_page)
        return self

    def close(self):
        if self._pw:
            self._pw.stop()

    def _on_new_page(self, new_page: Page):
        """팝업/새탭이 열리면 현재 페이지로 교체."""
        new_page.wait_for_load_state("domcontentloaded", timeout=10000)
        self._page = new_page

    @property
    def page(self) -> Page:
        return self._page

    # ── 이동 ─────────────────────────────────────────────────────────────────
    def go(self, url: str, wait: float = DEFAULT_WAIT) -> ActionResult:
        """URL로 이동. SPA 렌더링 완료까지 대기."""
        try:
            self._page.goto(url, timeout=20000)
            self._wait_render(wait)
            return ActionResult(ok=True, data=self._page.url)
        except Exception as e:
            return ActionResult(ok=False, error=str(e))

    def back(self):
        self._page.go_back()
        self._wait_render()

    # ── 클릭 ─────────────────────────────────────────────────────────────────
    def click(self, selector: str, wait: float = DEFAULT_WAIT) -> ActionResult:
        """CSS 셀렉터로 클릭."""
        try:
            self._page.click(selector, timeout=5000)
            self._wait_render(wait)
            return ActionResult(ok=True)
        except Exception as e:
            return ActionResult(ok=False, error=str(e))

    def click_text(self, text: str, exact: bool = False,
                   wait: float = DEFAULT_WAIT) -> ActionResult:
        """텍스트로 요소 찾아 클릭. 없으면 링크 href 매칭 시도."""
        # 1. Playwright 텍스트 로케이터
        try:
            loc = self._page.get_by_text(text, exact=exact).first
            loc.click(timeout=5000)
            self._wait_render(wait)
            return ActionResult(ok=True)
        except Exception:
            pass

        # 2. 링크 텍스트 포함 매칭
        try:
            self._page.locator(f"a:has-text('{text}')").first.click(timeout=5000)
            self._wait_render(wait)
            return ActionResult(ok=True)
        except Exception:
            pass

        # 3. 버튼 텍스트
        try:
            self._page.locator(f"button:has-text('{text}')").first.click(timeout=3000)
            self._wait_render(wait)
            return ActionResult(ok=True)
        except Exception as e:
            return ActionResult(ok=False, error=f"'{text}' 요소를 찾을 수 없음: {e}")

    def click_link(self, href_contains: str,
                   wait: float = DEFAULT_WAIT) -> ActionResult:
        """href에 특정 문자열이 포함된 링크 클릭."""
        try:
            self._page.locator(f"a[href*='{href_contains}']").first.click(timeout=5000)
            self._wait_render(wait)
            return ActionResult(ok=True)
        except Exception as e:
            return ActionResult(ok=False, error=str(e))

    # ── 입력 ─────────────────────────────────────────────────────────────────
    def type(self, selector: str, text: str,
             clear: bool = True) -> ActionResult:
        """필드에 텍스트 입력."""
        try:
            el = self._page.locator(selector).first
            if clear:
                el.clear()
            el.type(text, delay=30)
            return ActionResult(ok=True)
        except Exception as e:
            return ActionResult(ok=False, error=str(e))

    def press(self, key: str):
        self._page.keyboard.press(key)
        time.sleep(0.5)

    # ── 스크롤 ───────────────────────────────────────────────────────────────
    def scroll(self, direction: str = "down", amount: int = 500):
        dy = amount if direction == "down" else -amount
        self._page.mouse.wheel(0, dy)
        time.sleep(0.4)

    def scroll_to_bottom(self, max_scrolls: int = 10):
        """페이지 끝까지 스크롤."""
        for _ in range(max_scrolls):
            prev = self._page.evaluate("document.body.scrollHeight")
            self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(0.8)
            curr = self._page.evaluate("document.body.scrollHeight")
            if curr == prev:
                break

    # ── 읽기 ─────────────────────────────────────────────────────────────────
    def read(self, clean: bool = True) -> str:
        """현재 페이지 텍스트. clean=True면 노이즈 제거."""
        text = self._page.inner_text("body")
        if clean:
            text = self._clean_text(text)
        return text

    def read_selector(self, selector: str) -> str:
        """특정 셀렉터의 텍스트."""
        try:
            return self._page.locator(selector).first.inner_text()
        except Exception:
            return ""

    def page_info(self) -> PageInfo:
        """현재 페이지의 URL·제목·텍스트·링크·폼 정보."""
        return PageInfo(
            url=self._page.url,
            title=self._page.title(),
            text=self.read(),
            links=self.extract_links(),
            forms=self.extract_forms(),
        )

    # ── 데이터 추출 ───────────────────────────────────────────────────────────
    def extract_links(self, filter_href: str = "",
                      filter_text: str = "",
                      frame: Frame | None = None) -> list[dict]:
        """페이지 링크 목록 추출. frame 지정 시 해당 프레임에서 추출."""
        target = frame or self._page
        links = target.evaluate(_js("extract_links.js"))
        if filter_href:
            links = [l for l in links if filter_href in l["href"]]
        if filter_text:
            ft = filter_text.lower()
            links = [l for l in links if ft in l["text"].lower()]
        return links

    def extract_table(self, selector: str = "table") -> list[list[str]]:
        """테이블 데이터 추출."""
        try:
            return self._page.evaluate(f"""
() => {{
    const table = document.querySelector('{selector}');
    if (!table) return [];
    return Array.from(table.querySelectorAll('tr')).map(tr =>
        Array.from(tr.querySelectorAll('th,td')).map(td => td.innerText.trim())
    );
}}
""")
        except Exception:
            return []

    def extract_forms(self) -> list[dict]:
        """페이지 폼 필드 목록."""
        return self._page.evaluate("""
() => Array.from(document.querySelectorAll('input,textarea,select')).map(el => ({
    tag: el.tagName.toLowerCase(),
    type: el.type || '',
    name: el.name || el.id || '',
    placeholder: el.placeholder || '',
    value: el.type === 'password' ? '[HIDDEN]' : (el.value || '').substring(0,50),
}))
""")

    def find_elements(self, description: str) -> list[str]:
        """자연어 설명으로 관련 셀렉터 후보 반환."""
        candidates = []
        # 텍스트 매칭
        try:
            locs = self._page.get_by_text(description).all()
            for loc in locs[:5]:
                tag = loc.evaluate("el => el.tagName.toLowerCase()")
                candidates.append(f"{tag}:has-text('{description}')")
        except Exception:
            pass
        return candidates

    def wait_for(self, selector: str = None, text: str = None,
                 timeout: float = 10.0) -> bool:
        """셀렉터 또는 텍스트가 나타날 때까지 대기."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if selector:
                    self._page.wait_for_selector(selector, timeout=1000)
                    return True
                if text and text in self._page.inner_text("body"):
                    return True
            except Exception:
                pass
            time.sleep(RENDER_POLL)
        return False

    # ── 페이지네이션 ──────────────────────────────────────────────────────────
    def collect_all_pages(self, item_selector: str,
                          next_selector: str = "a:has-text('다음')",
                          max_pages: int = 10) -> list[str]:
        """다음 버튼을 클릭하며 모든 페이지의 아이템 텍스트 수집."""
        all_items = []
        for _ in range(max_pages):
            items = self._page.locator(item_selector).all_inner_texts()
            all_items.extend(items)
            try:
                self._page.locator(next_selector).first.click(timeout=3000)
                self._wait_render()
            except Exception:
                break
        return all_items

    # ── 내부 유틸 ─────────────────────────────────────────────────────────────
    def _wait_render(self, extra: float = DEFAULT_WAIT):
        """SPA 렌더링 완료 대기: DOM 안정화 + 추가 대기."""
        try:
            self._page.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception:
            pass
        # DOM 크기 안정화 확인
        prev_len = 0
        deadline = time.time() + RENDER_MAX
        while time.time() < deadline:
            try:
                curr_len = len(self._page.inner_text("body"))
                if curr_len == prev_len and curr_len > 0:
                    break
                prev_len = curr_len
            except Exception:
                break
            time.sleep(RENDER_POLL)
        time.sleep(max(0, extra - RENDER_POLL))

    @staticmethod
    def _clean_text(text: str) -> str:
        """노이즈 라인 제거 + 중복 공백 정리."""
        lines = []
        for line in text.splitlines():
            line = line.strip()
            if not line or len(line) < 2:
                continue
            if any(w in line for w in _NOISE_WORDS):
                continue
            if _NOISE_PATTERNS.match(line):
                continue
            lines.append(line)
        # 연속 중복 제거
        deduped = []
        prev = None
        for l in lines:
            if l != prev:
                deduped.append(l)
            prev = l
        return "\n".join(deduped)

    # ── 고수준 작업 ───────────────────────────────────────────────────────────
    def naver_cafe_list(self) -> list[dict]:
        """네이버 가입 카페 전체 목록 반환 (페이지네이션 자동 처리).

        내 카페 관리 페이지에서 탭 구분자로 카페명을 파싱.
        a.page_item 클릭으로 페이지 이동.
        """
        self.go("https://section.cafe.naver.com/ca-fe/home/manage-my-cafe/join")
        time.sleep(4)

        def _parse_names() -> list[str]:
            raw = self._page.inner_text("body")
            names = []
            for line in raw.splitlines():
                if not line.startswith("\t"):
                    continue
                name = line.strip()
                if not name or "전체메일" in name or "탈퇴" in name:
                    continue
                if len(name) >= 2:
                    names.append(name)
            return names

        all_names: list[str] = []
        for pnum in range(1, 8):
            names = _parse_names()
            new = [n for n in names if n not in all_names]
            all_names.extend(new)
            if pnum < 7:
                next_n = pnum + 1
                clicked = self._page.evaluate(f"""
() => {{
    for (const el of document.querySelectorAll('a.page_item, span.page_item')) {{
        if ((el.innerText || el.textContent || '').trim() === '{next_n}') {{
            el.click(); return true;
        }}
    }}
    return false;
}}
""")
                if not clicked:
                    break
                time.sleep(3)

        # href는 카페 URL 규칙으로 생성
        return [{"text": n, "href": ""} for n in all_names]

    def naver_cafe_posts(self, cafe_url: str,
                         board: str = "전체글보기",
                         max_posts: int = 30) -> list[dict]:
        """네이버 카페 게시판 최신 글 목록 반환.

        새 카페 UI(f-e)와 구 UI(cafe.naver.com/xxx) 모두 지원.
        """
        self.go(cafe_url)
        time.sleep(2)

        # 게시판 클릭
        if board != "전체글보기":
            self.click_text(board)
            time.sleep(2)

        # 모든 프레임에서 게시글 링크 수집
        all_posts: list[dict] = []
        seen: set[str] = set()

        for frame in self._page.frames:
            try:
                posts = frame.evaluate(_js("extract_posts.js"))
                for p in posts:
                    if p["href"] not in seen:
                        seen.add(p["href"])
                        all_posts.append(p)
            except Exception:
                continue

        # 폴백: 메인 프레임 일반 링크에서 articleid 포함 추출
        if not all_posts:
            links = self.extract_links()
            for l in links:
                if ("articleid" in l["href"] or "/articles/" in l["href"]) and l["href"] not in seen:
                    seen.add(l["href"])
                    all_posts.append({"title": l["text"], "href": l["href"]})

        return all_posts[:max_posts]

    # ── 카페 전체 탐색 기능 ───────────────────────────────────────────────────

    def cafe_info(self, cafe_url: str) -> dict:
        """카페 기본 정보 반환.

        반환:
            name         - 카페명
            url          - 카페 URL
            club_id      - 클럽 ID (숫자 문자열)
            manager      - 운영자 닉네임
            opened_at    - 개설일 (예: '2004.04.12')
            grade        - 카페 등급 (예: '나무3단계')
            member_count - 멤버 수 (문자열, 예: '242,106')
            description  - 카페 소개
            boards       - 게시판 목록 (list[dict])
        """
        self.go(cafe_url)
        time.sleep(3)

        def _s(sel: str, timeout: int = 800) -> str:
            try:
                return self._page.locator(sel).first.inner_text(timeout=timeout).strip()
            except Exception:
                return ""

        raw = self._page.inner_text("body")

        # 메인 프레임 사이드바에서 카페 정보 파싱
        name_m = re.search(r"^(.+?)\n", raw)
        name = name_m.group(1).strip() if name_m else ""

        manager_m = re.search(r"\n(.+?)\s*\n\s*매니저", raw)
        manager = manager_m.group(1).strip() if manager_m else ""

        opened_m = re.search(r"(\d{4}\.\d{2}\.\d{2})\.\s*개설", raw)
        opened_at = opened_m.group(1) if opened_m else ""

        grade_m = re.search(r"카페등급\s*\n(.+?)\n", raw)
        grade = grade_m.group(1).strip() if grade_m else ""

        member_m = re.search(r"카페멤버수\s*\n\s*([\d,]+)", raw)
        member_count = member_m.group(1).strip() if member_m else ""

        # 클럽 ID 추출
        club_id = ""
        for link in self.extract_links(filter_href="clubid="):
            m = re.search(r"clubid=(\d+)", link["href"])
            if m:
                club_id = m.group(1)
                break
        if not club_id:
            m = re.search(r"/cafes/(\d+)", cafe_url)
            if m:
                club_id = m.group(1)

        # 게시판 목록
        boards = self.cafe_boards(cafe_url, _skip_goto=True)

        return {
            "name": name,
            "url": cafe_url,
            "club_id": club_id,
            "manager": manager,
            "opened_at": opened_at,
            "grade": grade,
            "member_count": member_count,
            "description": "",
            "boards": boards,
        }

    def cafe_boards(self, cafe_url: str, _skip_goto: bool = False) -> list[dict]:
        """카페 게시판 목록 반환.

        반환: list[dict]
            name  - 게시판명
            href  - 게시판 URL
            count - 게시글 수 (문자열)
        """
        if not _skip_goto:
            self.go(cafe_url)
            time.sleep(3)

        links = self.extract_links()
        boards = []
        seen: set[str] = set()
        for l in links:
            href = l["href"]
            name = l["text"]
            is_board = ("ArticleList" in href or "search.boardtype" in href)
            if not is_board or href in seen or not name or len(name) < 2:
                continue
            seen.add(href)
            # href에서 menuid 추출
            mid_m = re.search(r"menuid=(\d+)", href)
            menu_id = mid_m.group(1) if mid_m else ""
            # clubid 추출
            cid_m = re.search(r"clubid=(\d+)", href)
            club_id = cid_m.group(1) if cid_m else ""
            boards.append({
                "name": name,
                "href": href,
                "menu_id": menu_id,
                "club_id": club_id,
                "count": "",
            })
        return boards

    def _get_club_id(self, cafe_url: str) -> str:
        """카페 URL 또는 사이드바 링크에서 clubid 추출."""
        # URL 자체에서 추출
        m = re.search(r"clubid=(\d+)", cafe_url)
        if m:
            return m.group(1)
        m = re.search(r"/cafes/(\d+)", cafe_url)
        if m:
            return m.group(1)
        # 사이드바 링크에서 추출
        for l in self.extract_links(filter_href="ArticleList"):
            cm = re.search(r"clubid=(\d+)", l["href"])
            if cm:
                return cm.group(1)
        return ""

    def _board_url(self, cafe_url: str, board: str, page: int = 1) -> str:
        """게시판명/URL에서 ArticleList URL 생성."""
        if board.startswith("http"):
            url = board
            sep = "&" if "?" in url else "?"
            if page > 1:
                url += f"{sep}search.page={page}"
            return url
        # 사이드바에서 게시판명 링크 찾기
        for l in self.extract_links(filter_href="ArticleList"):
            if board in l["text"]:
                url = l["href"]
                sep = "&" if "?" in url else "?"
                if page > 1:
                    url += f"{sep}search.page={page}"
                return url
        # 전체글보기 기본
        club_id = self._get_club_id(cafe_url)
        base = (f"https://cafe.naver.com/ArticleList.nhn"
                f"?search.clubid={club_id}&search.boardtype=L")
        if page > 1:
            base += f"&search.page={page}"
        return base

    def cafe_posts(self, cafe_url: str,
                   board: str = "전체글보기",
                   page: int = 1,
                   max_posts: int = 30) -> list[dict]:
        """카페 게시판 게시글 목록 (메타 포함, 페이지 지정 가능).

        Args:
            cafe_url  - 카페 URL (예: https://cafe.naver.com/0moo)
            board     - 게시판명 또는 게시판 URL (기본: 전체글보기)
            page      - 페이지 번호 (기본: 1)
            max_posts - 최대 수집 수

        반환: list[dict]
            title    - 게시글 제목
            href     - 게시글 URL
            author   - 작성자
            date     - 작성일
            views    - 조회수
            comments - 댓글 수
        """
        # 카페 홈으로 이동해 사이드바 링크 확보
        self.go(cafe_url)
        time.sleep(2)

        # 목표 게시판 URL 결정
        target_url = self._board_url(cafe_url, board, page)
        self.go(target_url)
        time.sleep(2)

        all_posts: list[dict] = []
        seen: set[str] = set()

        for frame in self._page.frames:
            try:
                posts = frame.evaluate(_js("extract_cafe_posts.js"))
                for p in posts:
                    href = p.get("href", "")
                    if href and href not in seen:
                        seen.add(href)
                        all_posts.append(p)
            except Exception:
                continue

        return all_posts[:max_posts]

    def cafe_posts_all_pages(self, cafe_url: str,
                             board: str = "전체글보기",
                             max_pages: int = 5) -> list[dict]:
        """여러 페이지에 걸쳐 게시글 목록 수집.

        Args:
            max_pages - 최대 페이지 수 (기본: 5)
        """
        self.go(cafe_url)
        time.sleep(2)
        if board != "전체글보기":
            self.click_text(board)
            time.sleep(2)

        all_posts: list[dict] = []
        seen: set[str] = set()

        for page_num in range(1, max_pages + 1):
            if page_num > 1:
                clicked = self._page.evaluate(f"""
() => {{
    for (const el of document.querySelectorAll('a.page_item, span.page_item, a[class*=page]')) {{
        if ((el.innerText || '').trim() === '{page_num}') {{
            el.click(); return true;
        }}
    }}
    return false;
}}""")
                if not clicked:
                    break
                time.sleep(2.5)

            for frame in self._page.frames:
                try:
                    posts = frame.evaluate(_js("extract_cafe_posts.js"))
                    for p in posts:
                        href = p.get("href", "")
                        if href and href not in seen:
                            seen.add(href)
                            all_posts.append(p)
                except Exception:
                    continue

            if not all_posts and page_num == 1:
                break

        return all_posts

    def cafe_popular(self, cafe_url: str, max_posts: int = 30) -> list[dict]:
        """카페 인기글 목록 반환.

        Args:
            cafe_url - 카페 URL (예: https://cafe.naver.com/0moo)
        """
        # clubid 추출
        club_id = ""
        m = re.search(r"clubid=(\d+)", cafe_url)
        if m:
            club_id = m.group(1)
        if not club_id:
            # cafe slug → clubid 추출 (사이드바 링크에서)
            self.go(cafe_url)
            time.sleep(2)
            for l in self.extract_links(filter_href="ArticleList"):
                cm = re.search(r"clubid=(\d+)", l["href"])
                if cm:
                    club_id = cm.group(1)
                    break

        pop_url = f"https://cafe.naver.com/f-e/cafes/{club_id}/popular" if club_id else ""
        if not pop_url:
            return []

        self.go(pop_url)
        time.sleep(3)

        all_posts: list[dict] = []
        seen: set[str] = set()
        for frame in self._page.frames:
            try:
                posts = frame.evaluate(_js("extract_cafe_posts.js"))
                for p in posts:
                    href = p.get("href", "")
                    if href and href not in seen:
                        seen.add(href)
                        all_posts.append(p)
            except Exception:
                continue

        return all_posts[:max_posts]

    def cafe_search(self, cafe_url: str, query: str,
                    page: int = 1, max_posts: int = 30) -> list[dict]:
        """카페 내 키워드 검색.

        Args:
            cafe_url - 카페 URL
            query    - 검색어
            page     - 페이지 번호
        """
        import urllib.parse

        # clubid 추출
        club_id = ""
        m = re.search(r"clubid=(\d+)", cafe_url)
        if not m:
            self.go(cafe_url)
            time.sleep(2)
            for l in self.extract_links(filter_href="ArticleList"):
                cm = re.search(r"clubid=(\d+)", l["href"])
                if cm:
                    club_id = cm.group(1)
                    break
        else:
            club_id = m.group(1)

        q = urllib.parse.quote(query)
        search_url = (
            f"https://cafe.naver.com/f-e/cafes/{club_id}/menus/0"
            f"?viewType=L&ta=ARTICLE_COMMENT&page={page}&q={q}"
        )
        self.go(search_url)
        time.sleep(3)

        all_posts: list[dict] = []
        seen: set[str] = set()
        for frame in self._page.frames:
            try:
                posts = frame.evaluate(_js("extract_cafe_posts.js"))
                for p in posts:
                    href = p.get("href", "")
                    if href and href not in seen:
                        seen.add(href)
                        all_posts.append(p)
            except Exception:
                continue

        # 폴백: 일반 extract_posts.js
        if not all_posts:
            for frame in self._page.frames:
                try:
                    posts = frame.evaluate(_js("extract_posts.js"))
                    for p in posts:
                        href = p.get("href", "")
                        if href and href not in seen:
                            seen.add(href)
                            all_posts.append({"title": p.get("title", ""), "href": href,
                                              "author": "", "date": "", "views": "", "comments": ""})
                except Exception:
                    continue

        return all_posts[:max_posts]

    def cafe_new_posts(self, cafe_url: str, max_posts: int = 30) -> list[dict]:
        """새 글 (최신 전체글) 목록 반환."""
        return self.cafe_posts(cafe_url, board="전체글보기", max_posts=max_posts)

    def read_article(self, article_url: str) -> dict:
        """카페 게시글 본문·메타·댓글 읽기.

        반환:
            title       - 게시글 제목
            url         - 원본 URL
            board       - 게시판명
            author      - 작성자 닉네임
            written_at  - 작성일시 (예: '2026.05.08. 21:25')
            view_count  - 조회수 (문자열, 예: '350')
            like_count  - 좋아요 수 (문자열)
            comment_count - 댓글 수 (int)
            tags        - 태그 목록 (list[str])
            body        - 본문 (최대 5000자)
            comments    - 댓글 목록 (list[dict]: author/body/written_at)
        """
        self.go(article_url)
        time.sleep(3)

        # 아티클 관련 프레임 우선 탐색 (URL 경로 기준, 쿼리 파라미터 오탐 방지)
        frames = self._page.frames
        def _is_article_frame(f) -> bool:
            url = f.url or ""
            if "about:blank" in url:
                return False
            path = url.split("?")[0]
            # f-e 프레임(메인)은 제외 — ca-fe/ 프레임(cafe_main)만 우선
            if "f-e/cafes" in path and f.name != "cafe_main":
                return False
            return any(kw in path for kw in ("ArticleRead", "articles/", "ca-fe/"))

        article_frames = [f for f in frames if _is_article_frame(f)]
        other_frames = [f for f in frames if f not in article_frames]
        ordered = article_frames + other_frames

        title = ""
        body = ""
        af: Optional[object] = None  # 본문이 있는 아티클 프레임

        body_selectors = [
            ".se-main-container", ".article_viewer", "#tbody",
            ".article-viewer", ".se-component-content",
            ".content_area", ".articleDetailView",
        ]
        title_selectors = [
            "h3.title_text", ".title_area h3", ".article_header h3",
            ".title_subject", ".article-title", "h3.title", ".tit-txt",
        ]

        def _safe(frame, sel: str, timeout: int = 1000) -> str:
            try:
                return frame.locator(sel).first.inner_text(timeout=timeout).strip()
            except Exception:
                return ""

        for frame in ordered:
            if body:
                break
            try:
                if not title:
                    for sel in title_selectors:
                        t = _safe(frame, sel)
                        if t:
                            title = t
                            break
                for sel in body_selectors:
                    b = _safe(frame, sel, timeout=2000)
                    if b and len(b) > 20:
                        body = b
                        af = frame
                        break
                if not body and frame in article_frames:
                    fb = ""
                    try:
                        fb = frame.inner_text("body")
                    except Exception:
                        pass
                    if fb and len(fb.strip()) > 50:
                        body = fb.strip()
                        af = frame
            except Exception:
                continue

        if not title:
            title = self._page.title()
        if not body:
            body = self.read()

        # ── 메타 정보 추출 (아티클 프레임 우선) ─────────────────────────────
        meta_frame = af or (article_frames[0] if article_frames else self._page)

        # 작성일 / 조회수
        info_raw = _safe(meta_frame, ".article_info")
        view_m = re.search(r"조회\s*([\d,]+)", info_raw)
        view_count = view_m.group(1) if view_m else ""
        date_m = re.search(r"(\d{4}\.\d{2}\.\d{2}\.?\s*\d{2}:\d{2})", info_raw)
        written_at = date_m.group(1).strip() if date_m else ""

        # 작성자
        author = _safe(meta_frame, ".nickname")

        # 게시판명
        board = _safe(meta_frame, ".board_link") or _safe(meta_frame, ".board_name")

        # 좋아요
        like_raw = _safe(meta_frame, ".like_count") or _safe(meta_frame, "em.u_cnt._count")
        like_count = re.sub(r"[^\d,]", "", like_raw)

        # 태그
        tags_raw = (_safe(meta_frame, ".tag_list")
                    or _safe(meta_frame, ".TagList")
                    or _safe(meta_frame, ".tag_area"))
        tags = [t.strip().lstrip("#") for t in tags_raw.split("\n") if t.strip().startswith("#")]

        # ── 댓글 파싱 ────────────────────────────────────────────────────────
        comments: list[dict] = []
        try:
            comment_els = meta_frame.locator(".CommentItem, .comment_item").all()
            for el in comment_els:
                raw = el.inner_text(timeout=1000).strip()
                lines = [l.strip() for l in raw.splitlines() if l.strip()]
                # 첫 줄 = 닉네임, 마지막 날짜 줄, 나머지 = 본문
                comment_author = lines[0] if lines else ""
                cdate_m = re.search(r"(\d{4}\.\d{2}\.\d{2}\.?\s*\d{2}:\d{2})", raw)
                comment_date = cdate_m.group(1).strip() if cdate_m else ""
                # 닉네임·날짜·'답글쓰기' 제외한 본문
                body_lines = [
                    l for l in lines[1:]
                    if l not in {comment_author, comment_date, "답글쓰기"}
                    and not re.match(r"\d{4}\.\d{2}\.\d{2}", l)
                ]
                comment_body = " ".join(body_lines).strip()
                comments.append({
                    "author": comment_author,
                    "body": comment_body[:500],
                    "written_at": comment_date,
                })
        except Exception:
            pass

        return {
            "title": title,
            "url": article_url,
            "board": board,
            "author": author,
            "written_at": written_at,
            "view_count": view_count,
            "like_count": like_count,
            "comment_count": len(comments),
            "tags": tags,
            "body": body[:5000],
            "comments": comments,
        }


# ── CLI (대화형 REPL) ──────────────────────────────────────────────────────────
def _cli():
    """간단한 대화형 브라우저 제어 REPL."""
    print("BrowserAgent CLI — CDP Chrome 제어")
    print("명령어:")
    print("  go <url>              | URL 이동")
    print("  click <텍스트>         | 텍스트 클릭")
    print("  read                  | 현재 페이지 텍스트")
    print("  links [필터]           | 링크 목록")
    print("  back                  | 뒤로")
    print("  cafes                 | 내 카페 목록")
    print("  info <카페URL>         | 카페 기본 정보 + 게시판 목록")
    print("  boards <카페URL>       | 게시판 목록")
    print("  posts <카페URL> [게시판] | 게시글 목록")
    print("  popular <카페URL>      | 인기글")
    print("  search <카페URL> <키워드> | 카페 내 검색")
    print("  article <URL>         | 게시글 본문+댓글")
    print("  quit                  | 종료")
    print()

    with BrowserAgent() as agent:
        while True:
            try:
                cmd = input(">>> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not cmd:
                continue

            parts = cmd.split(None, 1)
            action = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""

            if action in ("quit", "exit", "q"):
                break
            elif action == "go":
                r = agent.go(arg)
                print("→", agent.page.url, "✓" if r else f"✗ {r.error}")
            elif action == "click":
                r = agent.click_text(arg)
                print("클릭", "✓" if r else f"✗ {r.error}")
                if r:
                    print("현재:", agent.page.url)
            elif action == "read":
                print(agent.read()[:2000])
            elif action == "links":
                links = agent.extract_links(filter_href=arg)
                for l in links[:30]:
                    print(f"  [{l['text'][:40]:40}] {l['href']}")
                print(f"  총 {len(links)}개")
            elif action == "back":
                agent.back()
                print("→", agent.page.url)
            elif action == "scroll":
                agent.scroll(arg or "down")
            elif action == "cafes":
                cafes = agent.naver_cafe_list()
                for i, c in enumerate(cafes, 1):
                    print(f"  {i:2}. {c['text'][:45]:45} | {c['href']}")
                print(f"  총 {len(cafes)}개")
            elif action == "info":
                url = arg or agent.page.url
                info = agent.cafe_info(url)
                print(f"카페명   : {info['name']}")
                print(f"운영자   : {info['manager']}")
                print(f"개설일   : {info['opened_at']}")
                print(f"등급     : {info['grade']}")
                print(f"멤버수   : {info['member_count']}")
                print(f"게시판   : {len(info['boards'])}개")
                for b in info["boards"][:20]:
                    print(f"  - {b['name'][:30]:30} | {b['href'][:80]}")
            elif action == "boards":
                url = arg or agent.page.url
                boards = agent.cafe_boards(url)
                for i, b in enumerate(boards, 1):
                    print(f"  {i:2}. {b['name'][:35]:35} | menuid={b['menu_id']}")
                print(f"  총 {len(boards)}개")
            elif action == "posts":
                parts2 = arg.split(None, 1)
                url = parts2[0] if parts2 else agent.page.url
                board = parts2[1] if len(parts2) > 1 else "전체글보기"
                posts = agent.cafe_posts(url, board)
                for i, p in enumerate(posts, 1):
                    cmt = f"[{p.get('comments','?')}]" if p.get('comments') else ""
                    print(f"  {i:2}. {p['title'][:45]:45} {cmt} {p.get('date','')}")
                print(f"  총 {len(posts)}개")
            elif action == "popular":
                url = arg or agent.page.url
                posts = agent.cafe_popular(url)
                for i, p in enumerate(posts, 1):
                    cmt = f"[{p.get('comments','?')}]" if p.get('comments') else ""
                    print(f"  {i:2}. {p['title'][:45]:45} {cmt} {p.get('views','')}조회")
                print(f"  총 {len(posts)}개")
            elif action == "search":
                parts2 = arg.split(None, 1)
                if len(parts2) < 2:
                    print("사용법: search <카페URL> <검색어>")
                else:
                    posts = agent.cafe_search(parts2[0], parts2[1])
                    for i, p in enumerate(posts, 1):
                        print(f"  {i:2}. {p['title'][:50]:50} {p.get('date','')}")
                    print(f"  총 {len(posts)}개")
            elif action == "article":
                r = agent.read_article(arg or agent.page.url)
                print(f"제목   : {r['title']}")
                print(f"작성자 : {r['author']} | {r['written_at']}")
                print(f"조회수 : {r['view_count']} | 좋아요: {r['like_count']} | 댓글: {r['comment_count']}")
                print(f"태그   : {r['tags']}")
                print(f"본문({len(r['body'])}자):")
                print(r["body"][:1000])
                if r["comments"]:
                    print(f"\n댓글 {len(r['comments'])}개:")
                    for c in r["comments"]:
                        print(f"  [{c['author']}] {c['written_at']}: {c['body'][:80]}")
            elif action == "pageinfo":
                info = agent.page_info()
                print(f"URL  : {info.url}")
                print(f"제목 : {info.title}")
                print(f"텍스트 ({len(info.text)}자):")
                print(info.text[:800])
            else:
                print(f"알 수 없는 명령: {action}")


if __name__ == "__main__":
    _cli()
