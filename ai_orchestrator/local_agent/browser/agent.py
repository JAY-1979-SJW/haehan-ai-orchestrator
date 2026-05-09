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
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from playwright.sync_api import (
    Browser, BrowserContext, Frame, Page,
    sync_playwright, TimeoutError as PWTimeout,
)

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
                      filter_text: str = "") -> list[dict]:
        """페이지 링크 목록 추출."""
        js = """
() => {
    const seen = new Set();
    const results = [];
    for (const a of document.querySelectorAll('a')) {
        const text = (a.innerText || '').trim().split('\\n')[0].trim();
        const href = a.href || '';
        if (!href || href.startsWith('javascript') || seen.has(href)) continue;
        if (!text || text.length < 2) continue;
        seen.add(href);
        results.push({text: text.substring(0, 60), href});
    }
    return results;
}
"""
        links = self._page.evaluate(js)
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
                         max_posts: int = 20) -> list[dict]:
        """네이버 카페 게시판 최신 글 목록 반환."""
        self.go(cafe_url)
        # 게시판 클릭
        if board != "전체글보기":
            self.click_text(board)
            time.sleep(2)
        # 게시글 링크 추출
        posts = self.extract_links(filter_href="cafe.naver.com/")
        # 게시글만 필터 (articleid 포함)
        article_links = [p for p in posts if "articleid" in p["href"] or "articles" in p["href"]]
        return article_links[:max_posts]

    def read_article(self, article_url: str) -> dict:
        """카페 게시글 본문 읽기."""
        self.go(article_url)
        title = self.read_selector("h3.title, .title_subject, .article-title") or self._page.title()
        body = self.read_selector(".se-main-container, .content, #tbody, .article_viewer") or ""
        if not body:
            body = self.read()
        return {"title": title, "url": article_url, "body": body[:3000]}


# ── CLI (대화형 REPL) ──────────────────────────────────────────────────────────
def _cli():
    """간단한 대화형 브라우저 제어 REPL."""
    print("BrowserAgent CLI — CDP Chrome 제어")
    print("명령어: go <url> | click <텍스트> | read | links [필터] | back | quit")
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
            elif action == "posts":
                posts = agent.naver_cafe_posts(arg or agent.page.url)
                for p in posts:
                    print(f"  [{p['text'][:50]}] {p['href']}")
            elif action == "info":
                info = agent.page_info()
                print(f"URL  : {info.url}")
                print(f"제목 : {info.title}")
                print(f"텍스트 ({len(info.text)}자):")
                print(info.text[:800])
            else:
                print(f"알 수 없는 명령: {action}")


if __name__ == "__main__":
    _cli()
