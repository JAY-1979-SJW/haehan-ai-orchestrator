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
    from scripts.browser.agent.agent import BrowserAgent

    with BrowserAgent() as agent:
        agent.go("https://cafe.naver.com")
        agent.click_text("내 카페 관리")
        cafes = agent.extract_links(filter_href="cafe.naver.com/")
        print(agent.read())  # 정제된 페이지 텍스트

CLI
===
    python -m scripts.browser.agent.agent
"""

from __future__ import annotations

import contextlib
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Frame,
    Page,
    sync_playwright,
)

_JS_DIR = Path(__file__).parent / "_js"


def _js(name: str) -> str:
    """_js/ 디렉터리의 JS 파일을 읽어 반환."""
    return (_JS_DIR / name).read_text(encoding="utf-8")


# ── 설정 ─────────────────────────────────────────────────────────────────────
CDP_URL = "http://127.0.0.1:9222"
DEFAULT_WAIT = 2.5  # 이동 후 기본 대기(초)
RENDER_POLL = 0.3  # 렌더링 폴링 간격
RENDER_MAX = 8.0  # 렌더링 최대 대기

_NOISE_WORDS = {
    "새 창에서 열림",
    "로그인",
    "Copyright",
    "ⓒ",
    "NAVER",
    "바로가기",
    "건너뛰기",
    "접근성",
}
_NOISE_PATTERNS = re.compile(r"^(\d{1,2}|\d{4}\.\d{2}\.\d{2}\.?|좋아요\s*\d*|댓글\s*\d*)$")


# ── 결과 타입 ─────────────────────────────────────────────────────────────────
@dataclass
class ActionResult:
    ok: bool
    data: Any = None
    error: str = ""

    def __bool__(self):
        return self.ok


@dataclass
class PageInfo:
    url: str
    title: str
    text: str  # 정제된 본문 텍스트
    links: list[dict] = field(default_factory=list)
    forms: list[dict] = field(default_factory=list)


# ── BrowserAgent ──────────────────────────────────────────────────────────────
from scripts.browser.agent.calendar_mixin import CalendarMixin  # noqa: E402
from scripts.browser.agent.mybox_mixin import MyBoxMixin  # noqa: E402
from scripts.naver.agent_mixins.blog_mixin import BlogMixin  # noqa: E402
from scripts.naver.agent_mixins.cafe_mixin import CafeMixin  # noqa: E402
from scripts.naver.agent_mixins.mail_mixin import MailMixin  # noqa: E402


class BrowserAgent(CafeMixin, BlogMixin, MailMixin, CalendarMixin, MyBoxMixin):
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
        from scripts.browser.agent.cdp_launcher import ensure_cdp
        from scripts.common.cdp_audit import L2

        self._session_id = str(uuid.uuid4())
        self._connect_t0 = time.time()
        ensure_cdp()
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.connect_over_cdp(self._cdp_url)
        self._ctx = self._browser.contexts[0]
        self._page = self._ctx.pages[0]
        # 새탭 자동 흡수
        self._ctx.on("page", self._on_new_page)
        L2(
            "CDP_CONNECT",
            "browser_agent",
            session_id=self._session_id,
            contexts_count=len(self._browser.contexts),
            pages_count=len(self._ctx.pages),
        )
        return self

    def close(self):
        from scripts.common.cdp_audit import L2

        if self._pw:
            self._pw.stop()
        L2(
            "CDP_DISCONNECT",
            "browser_agent",
            session_id=getattr(self, "_session_id", ""),
            duration_ms=int((time.time() - getattr(self, "_connect_t0", time.time())) * 1000),
        )

    def _on_new_page(self, new_page: Page):
        """팝업/새탭이 열리면 현재 페이지로 교체."""
        new_page.wait_for_load_state("domcontentloaded", timeout=10000)
        self._page = new_page

    @property
    def page(self) -> Page:
        """현재 페이지. connect() 전에는 RuntimeError(예전엔 None 을 돌려줘 호출부에서 영문 AttributeError 가 났음)."""
        if self._page is None:
            raise RuntimeError("브라우저에 연결되지 않았습니다 — connect() 를 먼저 호출하세요")
        return self._page

    # ── 이동 ─────────────────────────────────────────────────────────────────
    def go(self, url: str, wait: float = DEFAULT_WAIT) -> ActionResult:
        """URL로 이동. SPA 렌더링 완료까지 대기."""
        try:
            self.page.goto(url, timeout=20000)
            self._wait_render(wait)
            return ActionResult(ok=True, data=self.page.url)
        except Exception as e:  # noqa: BLE001 - 범용 브라우저 액션 실행기 — 각 동작 실패는 ActionResult(ok=False, error) 로 반환하거나 안전한 기본값(빈 문자열/리스트)으로 폴백, 파일 다운로드는 방법을 순차 재시도, 결제·삭제 없음(2026-09-28 검토)
            return ActionResult(ok=False, error=str(e))

    def back(self):
        self.page.go_back()
        self._wait_render()

    # ── 클릭 ─────────────────────────────────────────────────────────────────
    def click(self, selector: str, wait: float = DEFAULT_WAIT) -> ActionResult:
        """CSS 셀렉터로 클릭."""
        try:
            self.page.click(selector, timeout=5000)
            self._wait_render(wait)
            return ActionResult(ok=True)
        except Exception as e:  # noqa: BLE001 - 범용 브라우저 액션 실행기 — 각 동작 실패는 ActionResult(ok=False, error) 로 반환하거나 안전한 기본값(빈 문자열/리스트)으로 폴백, 파일 다운로드는 방법을 순차 재시도, 결제·삭제 없음(2026-09-28 검토)
            return ActionResult(ok=False, error=str(e))

    def click_text(self, text: str, exact: bool = False, wait: float = DEFAULT_WAIT) -> ActionResult:
        """텍스트로 요소 찾아 클릭. 없으면 링크 href 매칭 시도."""
        # 1. Playwright 텍스트 로케이터
        try:
            loc = self.page.get_by_text(text, exact=exact).first
            loc.click(timeout=5000)
            self._wait_render(wait)
            return ActionResult(ok=True)
        except Exception:  # noqa: S110, BLE001
            pass

        # 2. 링크 텍스트 포함 매칭
        try:
            self.page.locator(f"a:has-text('{text}')").first.click(timeout=5000)
            self._wait_render(wait)
            return ActionResult(ok=True)
        except Exception:  # noqa: S110, BLE001
            pass

        # 3. 버튼 텍스트
        try:
            self.page.locator(f"button:has-text('{text}')").first.click(timeout=3000)
            self._wait_render(wait)
            return ActionResult(ok=True)
        except Exception as e:  # noqa: BLE001 - 범용 브라우저 액션 실행기 — 각 동작 실패는 ActionResult(ok=False, error) 로 반환하거나 안전한 기본값(빈 문자열/리스트)으로 폴백, 파일 다운로드는 방법을 순차 재시도, 결제·삭제 없음(2026-09-28 검토)
            return ActionResult(ok=False, error=f"'{text}' 요소를 찾을 수 없음: {e}")

    def click_link(self, href_contains: str, wait: float = DEFAULT_WAIT) -> ActionResult:
        """href에 특정 문자열이 포함된 링크 클릭."""
        try:
            self.page.locator(f"a[href*='{href_contains}']").first.click(timeout=5000)
            self._wait_render(wait)
            return ActionResult(ok=True)
        except Exception as e:  # noqa: BLE001 - 범용 브라우저 액션 실행기 — 각 동작 실패는 ActionResult(ok=False, error) 로 반환하거나 안전한 기본값(빈 문자열/리스트)으로 폴백, 파일 다운로드는 방법을 순차 재시도, 결제·삭제 없음(2026-09-28 검토)
            return ActionResult(ok=False, error=str(e))

    # ── 입력 ─────────────────────────────────────────────────────────────────
    def type(self, selector: str, text: str, clear: bool = True) -> ActionResult:
        """필드에 텍스트 입력."""
        try:
            el = self.page.locator(selector).first
            if clear:
                el.clear()
            el.type(text, delay=30)
            return ActionResult(ok=True)
        except Exception as e:  # noqa: BLE001 - 범용 브라우저 액션 실행기 — 각 동작 실패는 ActionResult(ok=False, error) 로 반환하거나 안전한 기본값(빈 문자열/리스트)으로 폴백, 파일 다운로드는 방법을 순차 재시도, 결제·삭제 없음(2026-09-28 검토)
            return ActionResult(ok=False, error=str(e))

    def press(self, key: str):
        self.page.keyboard.press(key)
        time.sleep(0.5)

    # ── 스크롤 ───────────────────────────────────────────────────────────────
    def scroll(self, direction: str = "down", amount: int = 500):
        dy = amount if direction == "down" else -amount
        self.page.mouse.wheel(0, dy)
        time.sleep(0.4)

    def scroll_to_bottom(self, max_scrolls: int = 10):
        """페이지 끝까지 스크롤."""
        for _ in range(max_scrolls):
            prev = self.page.evaluate("document.body.scrollHeight")
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(0.8)
            curr = self.page.evaluate("document.body.scrollHeight")
            if curr == prev:
                break

    # ── 읽기 ─────────────────────────────────────────────────────────────────
    def read(self, clean: bool = True) -> str:
        """현재 페이지 텍스트. clean=True면 노이즈 제거."""
        text = self.page.inner_text("body")
        if clean:
            text = self._clean_text(text)
        return text

    def read_selector(self, selector: str) -> str:
        """특정 셀렉터의 텍스트."""
        try:
            return self.page.locator(selector).first.inner_text()
        except Exception:  # noqa: BLE001 - 범용 브라우저 액션 실행기 — 각 동작 실패는 ActionResult(ok=False, error) 로 반환하거나 안전한 기본값(빈 문자열/리스트)으로 폴백, 파일 다운로드는 방법을 순차 재시도, 결제·삭제 없음(2026-09-28 검토)
            return ""

    def page_info(self) -> PageInfo:
        """현재 페이지의 URL·제목·텍스트·링크·폼 정보."""
        return PageInfo(
            url=self.page.url,
            title=self.page.title(),
            text=self.read(),
            links=self.extract_links(),
            forms=self.extract_forms(),
        )

    # ── 데이터 추출 ───────────────────────────────────────────────────────────
    def extract_links(self, filter_href: str = "", filter_text: str = "", frame: Frame | None = None) -> list[dict]:
        """페이지 링크 목록 추출. frame 지정 시 해당 프레임에서 추출."""
        target = frame or self.page
        links = target.evaluate(_js("extract_links.js"))
        if filter_href:
            links = [l for l in links if filter_href in l["href"]]  # noqa: E741
        if filter_text:
            ft = filter_text.lower()
            links = [l for l in links if ft in l["text"].lower()]  # noqa: E741
        return links

    def extract_table(self, selector: str = "table") -> list[list[str]]:
        """테이블 데이터 추출."""
        try:
            return self.page.evaluate(f"""
() => {{
    const table = document.querySelector('{selector}');
    if (!table) return [];
    return Array.from(table.querySelectorAll('tr')).map(tr =>
        Array.from(tr.querySelectorAll('th,td')).map(td => td.innerText.trim())
    );
}}
""")
        except Exception:  # noqa: BLE001 - 범용 브라우저 액션 실행기 — 각 동작 실패는 ActionResult(ok=False, error) 로 반환하거나 안전한 기본값(빈 문자열/리스트)으로 폴백, 파일 다운로드는 방법을 순차 재시도, 결제·삭제 없음(2026-09-28 검토)
            return []

    def extract_forms(self) -> list[dict]:
        """페이지 폼 필드 목록."""
        return self.page.evaluate("""
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
            locs = self.page.get_by_text(description).all()
            for loc in locs[:5]:
                tag = loc.evaluate("el => el.tagName.toLowerCase()")
                candidates.append(f"{tag}:has-text('{description}')")
        except Exception:  # noqa: S110, BLE001
            pass
        return candidates

    def wait_for(
        self,
        selector: str | None = None,
        text: str | None = None,
        timeout: float = 10.0,
    ) -> bool:
        """셀렉터 또는 텍스트가 나타날 때까지 대기."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if selector:
                    self.page.wait_for_selector(selector, timeout=1000)
                    return True
                if text and text in self.page.inner_text("body"):
                    return True
            except Exception:  # noqa: S110, BLE001
                pass
            time.sleep(RENDER_POLL)
        return False

    # ── 페이지네이션 ──────────────────────────────────────────────────────────
    def collect_all_pages(
        self, item_selector: str, next_selector: str = "a:has-text('다음')", max_pages: int = 10
    ) -> list[str]:
        """다음 버튼을 클릭하며 모든 페이지의 아이템 텍스트 수집."""
        all_items: list[Any] = []
        for _ in range(max_pages):
            items = self.page.locator(item_selector).all_inner_texts()
            all_items.extend(items)
            try:
                self.page.locator(next_selector).first.click(timeout=3000)
                self._wait_render()
            except Exception:  # noqa: BLE001 - 범용 브라우저 액션 실행기 — 각 동작 실패는 ActionResult(ok=False, error) 로 반환하거나 안전한 기본값(빈 문자열/리스트)으로 폴백, 파일 다운로드는 방법을 순차 재시도, 결제·삭제 없음(2026-09-28 검토)
                break
        return all_items

    # ── 내부 유틸 ─────────────────────────────────────────────────────────────
    def _wait_render(self, extra: float = DEFAULT_WAIT):
        """SPA 렌더링 완료 대기: DOM 안정화 + 추가 대기."""
        # 렌더 대기 best-effort - 실패해도 아래 DOM 크기 안정화 루프로 계속 진행
        with contextlib.suppress(Exception):
            self.page.wait_for_load_state("domcontentloaded", timeout=8000)
        # DOM 크기 안정화 확인
        prev_len = 0
        deadline = time.time() + RENDER_MAX
        while time.time() < deadline:
            try:
                curr_len = len(self.page.inner_text("body"))
                if curr_len == prev_len and curr_len > 0:
                    break
                prev_len = curr_len
            except Exception:  # noqa: BLE001 - 범용 브라우저 액션 실행기 — 각 동작 실패는 ActionResult(ok=False, error) 로 반환하거나 안전한 기본값(빈 문자열/리스트)으로 폴백, 파일 다운로드는 방법을 순차 재시도, 결제·삭제 없음(2026-09-28 검토)
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
        for l in lines:  # noqa: E741
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
            raw = self.page.inner_text("body")
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
                clicked = self.page.evaluate(f"""
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

    def naver_cafe_posts(self, cafe_url: str, board: str = "전체글보기", max_posts: int = 30) -> list[dict]:
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

        for frame in self.page.frames:
            try:
                posts = frame.evaluate(_js("extract_posts.js"))
                for p in posts:
                    if p["href"] not in seen:
                        seen.add(p["href"])
                        all_posts.append(p)
            except Exception:  # noqa: BLE001, S112
                continue

        # 폴백: 메인 프레임 일반 링크에서 articleid 포함 추출
        if not all_posts:
            links = self.extract_links()
            for l in links:  # noqa: E741
                if ("articleid" in l["href"] or "/articles/" in l["href"]) and l["href"] not in seen:
                    seen.add(l["href"])
                    all_posts.append({"title": l["text"], "href": l["href"]})

        return all_posts[:max_posts]

    def _download_via_requests(self, file_url: str, save_path: Path, filename: str) -> dict | None:
        """1차: requests + 브라우저 쿠키. 성공 시 결과 dict, 실패 시 None(2차로 진행)."""
        import requests

        try:
            cookies_raw = self._ctx.cookies()
            jar = requests.cookies.RequestsCookieJar()
            for c in cookies_raw:
                jar.set(c["name"], c["value"], domain=c.get("domain", ""), path=c.get("path", "/"))

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": "https://cafe.naver.com/",
            }
            resp = requests.get(file_url, cookies=jar, headers=headers, stream=True, timeout=30, allow_redirects=True)
            resp.raise_for_status()

            # 파일명 결정: Content-Disposition 우선
            suggested = filename
            if not suggested:
                suggested = self._filename_from_content_disposition(resp.headers.get("Content-Disposition", ""))
            if not suggested:
                suggested = Path(file_url.split("?")[0]).name or "download"

            dest = save_path / suggested
            with dest.open("wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)

            if dest.stat().st_size == 0:
                dest.unlink(missing_ok=True)
                raise ValueError("다운로드된 파일이 비어있음")

            return {"ok": True, "path": str(dest), "error": ""}

        except Exception:  # noqa: BLE001
            return None  # 2차 시도로 진행

    @staticmethod
    def _filename_from_content_disposition(cd: str) -> str:
        import urllib.parse

        fn_m = re.search(r'filename\*?=["\']?(?:UTF-8\'\')?([^"\';\r\n]+)', cd, re.IGNORECASE)
        if not fn_m:
            return ""
        raw_fn = fn_m.group(1).strip()
        try:
            return urllib.parse.unquote(raw_fn)
        except Exception:  # noqa: BLE001 - 범용 브라우저 액션 실행기 — 각 동작 실패는 ActionResult(ok=False, error) 로 반환하거나 안전한 기본값(빈 문자열/리스트)으로 폴백, 파일 다운로드는 방법을 순차 재시도, 결제·삭제 없음(2026-09-28 검토)
            return raw_fn

    def _download_via_new_tab(self, file_url: str, save_path: Path, filename: str) -> dict | None:
        """3차: 새 탭. 성공 시 결과 dict, 실패 시 None."""
        try:
            with self._ctx.expect_page() as new_page_info:
                self.page.evaluate(f"window.open({file_url!r}, '_blank')")
            new_page = new_page_info.value
            try:
                with new_page.expect_download(timeout=30000) as dl_info:
                    pass
                download = dl_info.value
                suggested = filename or download.suggested_filename or "file"
                dest = save_path / suggested
                download.save_as(str(dest))
                new_page.close()
                return {"ok": True, "path": str(dest), "error": ""}
            except Exception:  # noqa: BLE001 - 범용 브라우저 액션 실행기 — 각 동작 실패는 ActionResult(ok=False, error) 로 반환하거나 안전한 기본값(빈 문자열/리스트)으로 폴백, 파일 다운로드는 방법을 순차 재시도, 결제·삭제 없음(2026-09-28 검토)
                new_page.close()
        except Exception:  # noqa: S110, BLE001
            pass
        return None

    def download_attachment(self, file_url: str, save_dir: str = "data/downloads", filename: str = "") -> dict:
        """첨부파일 다운로드.

        1차: requests + 브라우저 쿠키 (네이버 카페 파일 호스트)
        2차: Playwright download 이벤트 폴백

        반환:
            ok    - 성공 여부
            path  - 저장된 로컬 경로
            error - 실패 시 오류 메시지
        """
        import requests  # noqa: F401 - 기존 동작 유지(미설치 시 mkdir 이전에 ImportError)

        save_path = Path(save_dir)
        save_path.mkdir(parents=True, exist_ok=True)

        # ── 1차: requests + 쿠키 ─────────────────────────────────────────────
        result = self._download_via_requests(file_url, save_path, filename)
        if result is not None:
            return result

        # ── 2차: Playwright download 이벤트 ─────────────────────────────────
        try:
            with self.page.expect_download(timeout=30000) as dl_info:
                self.page.evaluate(f"window.location.href = {file_url!r}")
            download = dl_info.value
            suggested = filename or download.suggested_filename or Path(file_url.split("?")[0]).name or "file"
            dest = save_path / suggested
            download.save_as(str(dest))
            return {"ok": True, "path": str(dest), "error": ""}
        except Exception as pw_err:  # noqa: BLE001 - 범용 브라우저 액션 실행기 — 각 동작 실패는 ActionResult(ok=False, error) 로 반환하거나 안전한 기본값(빈 문자열/리스트)으로 폴백, 파일 다운로드는 방법을 순차 재시도, 결제·삭제 없음(2026-09-28 검토)
            # 3차: 새 탭
            result = self._download_via_new_tab(file_url, save_path, filename)
            if result is not None:
                return result
            return {"ok": False, "path": "", "error": str(pw_err)}


# ── CLI (대화형 REPL) ──────────────────────────────────────────────────────────
def _cli_go(agent: BrowserAgent, arg: str) -> None:
    r = agent.go(arg)
    print("→", agent.page.url, "✓" if r else f"✗ {r.error}")


def _cli_click(agent: BrowserAgent, arg: str) -> None:
    r = agent.click_text(arg)
    print("클릭", "✓" if r else f"✗ {r.error}")
    if r:
        print("현재:", agent.page.url)


def _cli_read(agent: BrowserAgent, arg: str) -> None:
    print(agent.read()[:2000])


def _cli_links(agent: BrowserAgent, arg: str) -> None:
    links = agent.extract_links(filter_href=arg)
    for l in links[:30]:  # noqa: E741
        print(f"  [{l['text'][:40]:40}] {l['href']}")
    print(f"  총 {len(links)}개")


def _cli_back(agent: BrowserAgent, arg: str) -> None:
    agent.back()
    print("→", agent.page.url)


def _cli_scroll(agent: BrowserAgent, arg: str) -> None:
    agent.scroll(arg or "down")


def _cli_cafes(agent: BrowserAgent, arg: str) -> None:
    cafes = agent.naver_cafe_list()
    for i, c in enumerate(cafes, 1):
        print(f"  {i:2}. {c['text'][:45]:45} | {c['href']}")
    print(f"  총 {len(cafes)}개")


def _cli_info(agent: BrowserAgent, arg: str) -> None:
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


def _cli_boards(agent: BrowserAgent, arg: str) -> None:
    url = arg or agent.page.url
    boards = agent.cafe_boards(url)
    for i, b in enumerate(boards, 1):
        print(f"  {i:2}. {b['name'][:35]:35} | menuid={b['menu_id']}")
    print(f"  총 {len(boards)}개")


def _cli_posts(agent: BrowserAgent, arg: str) -> None:
    parts2 = arg.split(None, 1)
    url = parts2[0] if parts2 else agent.page.url
    board = parts2[1] if len(parts2) > 1 else "전체글보기"
    posts = agent.cafe_posts(url, board)
    for i, p in enumerate(posts, 1):
        cmt = f"[{p.get('comments', '?')}]" if p.get("comments") else ""
        print(f"  {i:2}. {p['title'][:45]:45} {cmt} {p.get('date', '')}")
    print(f"  총 {len(posts)}개")


def _cli_popular(agent: BrowserAgent, arg: str) -> None:
    url = arg or agent.page.url
    posts = agent.cafe_popular(url)
    for i, p in enumerate(posts, 1):
        cmt = f"[{p.get('comments', '?')}]" if p.get("comments") else ""
        print(f"  {i:2}. {p['title'][:45]:45} {cmt} {p.get('views', '')}조회")
    print(f"  총 {len(posts)}개")


def _cli_search(agent: BrowserAgent, arg: str) -> None:
    parts2 = arg.split(None, 1)
    if len(parts2) < 2:
        print("사용법: search <카페URL> <검색어>")
    else:
        posts = agent.cafe_search(parts2[0], parts2[1])
        for i, p in enumerate(posts, 1):
            print(f"  {i:2}. {p['title'][:50]:50} {p.get('date', '')}")
        print(f"  총 {len(posts)}개")


def _cli_article(agent: BrowserAgent, arg: str) -> None:
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


def _cli_pageinfo(agent: BrowserAgent, arg: str) -> None:
    info = agent.page_info()
    print(f"URL  : {info.url}")
    print(f"제목 : {info.title}")
    print(f"텍스트 ({len(info.text)}자):")
    print(info.text[:800])


# action 문자열 → 실행 함수. 원래 _cli() 의 if/elif action == ... 순서를 그대로 옮긴 것 —
# 동작은 동일하다(2026-09-29 STD-08: if/elif 14개가 mccabe/pylint 에 "분기 14개"로 그대로
# 잡혀 dict 조회로 바꿨다). quit/exit/q 는 while 루프를 직접 break 해야 해서 그대로 남김.
_CLI_ACTIONS: dict[str, Callable[[BrowserAgent, str], None]] = {
    "go": _cli_go,
    "click": _cli_click,
    "read": _cli_read,
    "links": _cli_links,
    "back": _cli_back,
    "scroll": _cli_scroll,
    "cafes": _cli_cafes,
    "info": _cli_info,
    "boards": _cli_boards,
    "posts": _cli_posts,
    "popular": _cli_popular,
    "search": _cli_search,
    "article": _cli_article,
    "pageinfo": _cli_pageinfo,
}


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
            handler = _CLI_ACTIONS.get(action)
            if handler is None:
                print(f"알 수 없는 명령: {action}")
                continue
            handler(agent, arg)


if __name__ == "__main__":
    _cli()
