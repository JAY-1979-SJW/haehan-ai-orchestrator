"""blog_mixin 블로그 읽기/조회 기능 (BlogReadMixin).

info/categories/posts/read_post/images/search/guestbook/neighbors/comments/stats/tag.
BlogMixin 다중상속의 기본 읽기 능력. [docs/module_separation_standard.md]
"""

from __future__ import annotations

import contextlib
import re
import time
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from scripts.naver.agent_mixins.blog_mixin_common import _js

_BLOG_POSTS_DOM_JS = """
            (() => {
              const res = [];
              const seen = new Set();

              // 방법1: td.p12 구조 (구형 Naver Blog - URL 링크 + 제목 td)
              const p12cells = document.querySelectorAll('td.p12');
              for (const td of p12cells) {
                const urlA = td.querySelector('p.url a, a[href*="blog.naver.com"]');
                if (!urlA) continue;
                const href = urlA.href || '';
                const m = href.match(/[/](\\d{10,})/) || href.match(/logNo=(\\d+)/);
                const logNo = m ? m[1] : '';
                if (!logNo || seen.has(logNo)) continue;
                seen.add(logNo);
                // 제목: td innerText 첫 줄 (카테고리명 제거 - "제목  카테고리" 형식)
                const lines = td.innerText.trim().split('\\n').map(l => l.trim()).filter(Boolean);
                const rawTitle = lines[0] || '';
                const title = rawTitle.split(/\\s{2,}/)[0].trim();
                if (!title || title.length < 2) continue;
                // 날짜: YYYY. M. D. HH:MM 패턴
                const dateM = td.innerText.match(/(\\d{4}\\.\\s*\\d{1,2}\\.\\s*\\d{1,2}\\..*)/);
                const date = dateM ? dateM[1].trim().slice(0,20) : '';
                res.push({log_no: logNo, title: title.slice(0,100), date, summary:'', thumb_url:'', href, comment_count:0});
              }
              if (res.length) return res;

              // 방법2: blog.naver.com/{blogId}/{logNo} 직접 링크
              for (const a of document.querySelectorAll('a[href*="blog.naver.com"]')) {
                const href = a.href || '';
                const m = href.match(/blog\\.naver\\.com\\/\\w+\\/(\\d{10,})/);
                if (!m || seen.has(m[1])) continue;
                seen.add(m[1]);
                // 부모 td/li에서 제목 추출
                const container = a.closest('td') || a.closest('li') || a.parentElement;
                const lines = container ? container.innerText.trim().split('\\n').map(l=>l.trim()).filter(Boolean) : [];
                const title = lines.find(l => l.length > 2 && !l.startsWith('http') && !l.match(/^\\d{4}\\./) ) || '';
                if (!title) continue;
                res.push({log_no: m[1], title: title.slice(0,100), date:'', summary:'', thumb_url:'', href, comment_count:0});
              }
              if (res.length) return res;

              // 방법3: PostView.naver?blogId=...&logNo=... 쿼리스트링 형식
              for (const a of document.querySelectorAll('a[href*="logNo="]')) {
                const href = a.href || '';
                const m = href.match(/logNo=(\\d{10,})/);
                if (!m || seen.has(m[1])) continue;
                seen.add(m[1]);
                const title = a.textContent.trim();
                if (!title || title.length < 2) continue;
                res.push({log_no: m[1], title: title.slice(0,100), date:'', summary:'', thumb_url:'', href, comment_count:0});
              }
              return res;
            })()
            """


class BlogReadMixin:
    if TYPE_CHECKING:
        # 다른 믹스인의 메서드·속성(go, _page …)을 self(MRO)로 쓴다 — 정적 검사기에는 합쳐진 클래스가 보이지 않으므로 알려 준다(런타임 영향 없음).
        def __getattr__(self, name: str) -> Any: ...

    def blog_info(self, blog_url: str) -> dict:
        """블로그 기본정보 조회."""
        blog_id = blog_url.rstrip("/").split("/")[-1]
        self.go(blog_url)
        time.sleep(2.5)

        raw_title = self._page.title() or ""
        title = re.sub(r"\s*[:\-–]\s*네이버\s*블로그\s*$", "", raw_title).strip()
        description = ""
        neighbor_count = 0
        visitor_today = 0
        visitor_total = 0
        profile_img = ""

        # PostList 프레임에서 설명/방문자 수 추출
        post_frame = self._get_blog_post_frame(blog_id)
        frame = post_frame or self._page
        try:
            body = frame.inner_text("body")
            m_today = re.search(r"오늘\s*([\d,]+)", body)
            if m_today:
                visitor_today = int(m_today.group(1).replace(",", ""))
            m_total = re.search(r"전체\s*([\d,]+)", body)
            if m_total:
                visitor_total = int(m_total.group(1).replace(",", ""))

            # 블로그 소개 (소개 문단 첫 의미있는 줄)
            lines = [ln.strip() for ln in body.splitlines() if ln.strip() and len(ln.strip()) > 5]
            # 제목, 메뉴 키워드 이후 첫 줄
            skip_keywords = {"NAVER", "블로그", "블로그 메뉴", "포토로그", "지도", "서재", "메모", "태그", "안부"}
            for ln in lines:
                if ln not in skip_keywords and not re.match(r"^(메뉴|본문|이웃|서비스)", ln):
                    description = ln[:200]
                    break
        except Exception:  # noqa: S110, BLE001
            pass

        # WidgetView 프레임에서 이웃 수 추출
        widget_frame = self._get_blog_widget_frame(blog_id)
        if widget_frame:
            try:
                w_body = widget_frame.inner_text("body")
                m_n = re.search(r"전체\s*이웃\s*\n?([\d,]+)\s*명", w_body)
                if not m_n:
                    m_n = re.search(r"([\d,]+)\s*명", w_body)
                if m_n:
                    neighbor_count = int(m_n.group(1).replace(",", ""))
            except Exception:  # noqa: S110, BLE001
                pass

        # 프로필 이미지
        with suppress(Exception):
            profile_img = (
                frame.evaluate(
                    "document.querySelector('.profile_img img, .blog_profile img, .se-profile-image img')?.src || ''"
                )
                or ""
            )

        return {
            "blog_id": blog_id,
            "title": title,
            "description": description,
            "neighbor_count": neighbor_count,
            "visitor_today": visitor_today,
            "visitor_total": visitor_total,
            "profile_img": profile_img,
        }

    def blog_categories(self, blog_url: str) -> list[dict]:
        """블로그 카테고리 목록 (포스트 수 포함).

        PostTitleListAsync API로 전체 포스트를 가져와 카테고리별로 집계한다.
        구형 레이아웃은 카테고리 옆 숫자를 DOM에 표시하지 않아 iframe 파싱이 신뢰 불가.
        """
        blog_id = blog_url.rstrip("/").split("/")[-1]

        # API로 전체 포스트 수집
        all_posts = self._fetch_all_posts_via_api(blog_id)

        # 카테고리별 포스트 수 집계 (API 기반)
        cat_counts: dict[str, int] = {}
        for p in all_posts:
            cat_no = str(p.get("categoryNo", ""))
            cat_counts[cat_no] = cat_counts.get(cat_no, 0) + 1

        # 카테고리 이름은 DOM에서 가져옴 (API에 name 미포함)
        self.go(blog_url)
        time.sleep(2.5)
        frame = self._get_blog_post_frame(blog_id) or self._page
        dom_cats: list[dict] = []
        with suppress(Exception):
            dom_cats = frame.evaluate("""
            (() => {
              const res = [];
              const seen = new Set();
              const anchors = document.querySelectorAll('a[href*="categoryNo"]');
              for (const a of anchors) {
                const href = a.href || '';
                const m = href.match(/categoryNo=(\\d+)/);
                if (!m) continue;
                const catNo = m[1];
                if (catNo === '0' || seen.has(catNo)) continue;
                seen.add(catNo);
                const text = (a.innerText || a.textContent || '').trim().split('\\n')[0].trim();
                if (!text) continue;
                res.push({name: text, category_no: catNo});
              }
              return res;
            })()
            """)

        if dom_cats:
            return [{**c, "post_count": cat_counts.get(c["category_no"], 0)} for c in dom_cats]

        # DOM도 실패 시 API 집계만으로 반환
        return [{"name": cat_no, "category_no": cat_no, "post_count": cnt} for cat_no, cnt in cat_counts.items()]

    def _fetch_all_posts_via_api(self, blog_id: str, category_no: str = "") -> list[dict]:
        """PostTitleListAsync API로 전체 포스트 목록 반환.

        구형/신형 레이아웃 모두 동작하며, iframe 재로딩 문제를 우회한다.
        """
        import re as _re
        from urllib.parse import unquote_plus

        all_posts: list[dict] = []
        seen: set[str] = set()

        for page_no in range(1, 50):
            url = (
                f"https://blog.naver.com/PostTitleListAsync.naver"
                f"?blogId={blog_id}&currentPage={page_no}&countPerPage=30"
                f"&categoryNo={category_no}"
            )
            # 브라우저 세션으로 API 호출
            raw = self._page.evaluate(f"""
            (() => {{
                return new Promise(resolve => {{
                    fetch("{url}", {{credentials: 'include'}})
                        .then(r => r.text()).then(t => resolve(t))
                        .catch(e => resolve(''));
                }});
            }})()
            """)
            if not raw:
                break

            # \' → ' 치환 후 JSON 파싱 (API가 invalid JSON escape \' 를 포함)
            fixed = _re.sub(r"\\'", "'", raw)
            try:
                data = __import__("json").loads(fixed)
            except Exception:  # noqa: BLE001 - 블로그 콘텐츠 읽기 전용 스크래핑 — 사이트 구조 변경 시 추출만 실패하고 빈 값/기본값으로 폴백, 쓰기·결제·인증 없음(2026-09-28 검토)
                break

            total = int(data.get("totalCount", 0))
            posts = data.get("postList", [])
            if not posts:
                break

            for p in posts:
                log_no = str(p.get("logNo", ""))
                if log_no and log_no not in seen:
                    seen.add(log_no)
                    all_posts.append(
                        {
                            "log_no": log_no,
                            "title": unquote_plus(p.get("title", "")),
                            "categoryNo": str(p.get("categoryNo", "")),
                            "categoryName": unquote_plus(p.get("categoryName", "")),
                            "date": str(p.get("addDate", ""))[:10],
                            "href": f"https://blog.naver.com/{blog_id}/{log_no}",
                            "summary": "",
                            "thumb_url": "",
                            "comment_count": 0,
                        }
                    )

            if len(all_posts) >= total:
                break

        return all_posts

    def _blog_posts_dom_fallback(self, blog_id: str, posts: list, seen: set[str]) -> object:
        """API 실패 시 DOM 폴백 1~2단계. posts/seen 을 갱신하고 사용한 frame 을 반환."""
        # PostList 프레임에서 포스트 추출
        frame = self._get_blog_post_frame(blog_id) or self._page
        try:
            result = frame.evaluate(_BLOG_POSTS_DOM_JS)
            for p in result:
                if p["log_no"] not in seen:
                    seen.add(p["log_no"])
                    posts.append(p)
        except Exception:  # noqa: S110, BLE001
            pass

        # 폴백: extract_blog_posts.js (카드형 레이아웃)
        if not posts:
            try:
                result = frame.evaluate(_js("extract_blog_posts.js"))
                for p in result:
                    if p.get("log_no") and p["log_no"] not in seen:
                        seen.add(p["log_no"])
                        posts.append(p)
            except Exception:  # noqa: S110, BLE001
                pass
        return frame

    def _blog_posts_link_fallback(self, blog_id: str, max_posts: int, posts: list) -> None:
        links = self.extract_links(filter_href=f"blog.naver.com/{blog_id}/")
        for lk in links[:max_posts]:
            m = re.search(r"/(\d{10,})", lk.get("href", ""))
            if m:
                posts.append(
                    {
                        "log_no": m.group(1),
                        "title": lk.get("text", "")[:100],
                        "date": "",
                        "summary": "",
                        "thumb_url": "",
                        "href": lk.get("href", ""),
                        "comment_count": 0,
                    }
                )

    def _blog_posts_mobile_fallback(self, blog_id: str, category_no: str, posts: list, seen: set[str]) -> None:
        """최종 폴백: 모바일 URL (m.blog.naver.com)."""
        try:
            mobile_url = f"https://m.blog.naver.com/{blog_id}"
            if category_no:
                mobile_url += f"?categoryNo={category_no}"
            self.go(mobile_url)
            time.sleep(2.5)
            self.scroll_to_bottom(max_scrolls=3)
            time.sleep(1.5)
            result = self._page.evaluate(_js("extract_blog_posts_mobile.js"))
            for p in result:
                if p.get("log_no") and p["log_no"] not in seen:
                    seen.add(p["log_no"])
                    posts.append(p)
        except Exception:  # noqa: S110, BLE001
            pass

    def blog_posts(self, blog_url: str, category_no: str = "", page: int = 1, max_posts: int = 30) -> list[dict]:
        """블로그 포스트 목록.

        PostTitleListAsync API를 우선 사용한다.
        구형 iframe 레이아웃은 categoryNo URL 파라미터를 반영하지 않아 API가 필수.
        """
        blog_id = blog_url.rstrip("/").split("/")[-1]

        # API 기반 수집 (카테고리·페이지 필터 모두 정확히 동작)
        api_posts = self._fetch_all_posts_via_api(blog_id, category_no=category_no)
        if api_posts:
            start = (page - 1) * max_posts
            return api_posts[start : start + max_posts]

        # API 실패 시 기존 DOM 폴백
        url = f"https://blog.naver.com/{blog_id}"
        if category_no:
            url += f"?categoryNo={category_no}"
        if page > 1:
            url += ("&" if category_no else "?") + f"currentPage={page}"

        self.go(url)
        time.sleep(2.5)

        posts: list = []
        seen: set[str] = set()

        self._blog_posts_dom_fallback(blog_id, posts, seen)

        if not posts:
            self._blog_posts_link_fallback(blog_id, max_posts, posts)

        # 최종 폴백: 모바일 URL (m.blog.naver.com) — PC 추출이 2개 미만이면 실행
        if len(posts) < 2:
            self._blog_posts_mobile_fallback(blog_id, category_no, posts, seen)

        return posts[:max_posts]

    def _pick_post_frame(self, log_no: str) -> Any:
        """PostView 프레임 우선 탐색 (본문 내용 있는 iframe)."""
        frame = self._page
        if log_no:
            # PostView.naver 프레임 우선 (실제 본문)
            _f = next((f for f in self._page.frames if "PostView" in (f.url or "") and log_no in (f.url or "")), None)
            if not _f:
                # 폴백: logNo 포함 프레임 중 body 비어있지 않은 것
                for f in self._page.frames:
                    if log_no in (f.url or "") and "PostView" not in (f.url or ""):
                        try:
                            txt = f.inner_text("body", timeout=500)
                            if txt and len(txt) > 50:
                                _f = f
                                break
                        except Exception:  # noqa: S110, BLE001
                            pass
            if _f:
                frame = _f
        return frame

    @staticmethod
    def _fill_author_and_date(frame: Any, info: dict) -> None:
        # 작성자 + 작성일: .writer 선택자 → "닉네임 ・ YYYY. MM. DD. HH:MM"
        try:
            writer_txt = frame.locator(".writer").first.inner_text(timeout=1000).strip()
            parts = re.split(r"[·・•]", writer_txt, maxsplit=1)
            info["author"] = parts[0].strip() if parts else ""
            if len(parts) > 1:
                date_m = re.search(r"(\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.\s*\d{1,2}:\d{2})", parts[1])
                info["written_at"] = date_m.group(1).strip() if date_m else parts[1].strip()
        except Exception:  # noqa: BLE001 - 블로그 콘텐츠 읽기 전용 스크래핑 — 사이트 구조 변경 시 추출만 실패하고 빈 값/기본값으로 폴백, 쓰기·결제·인증 없음(2026-09-28 검토)
            body_txt = frame.inner_text("body")
            m_date = re.search(r"(\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.\s*\d{1,2}:\d{2})", body_txt)
            info["written_at"] = m_date.group(1) if m_date else ""

    @staticmethod
    def _fill_author_fallback(frame: Any, info: dict, blog_id: str) -> None:
        """작성자 폴백: .nick 선택자 또는 blogId."""
        if info["author"]:
            return
        for auth_sel in [".nick", ".blog_author", ".author_name"]:
            try:
                nick = frame.locator(auth_sel).first.inner_text(timeout=500).strip().split("\n")[0]
                if nick:
                    info["author"] = nick
                    break
            except Exception:  # noqa: S110, BLE001
                pass
        if not info["author"]:
            info["author"] = blog_id

    def _fill_post_text_fields(self, frame: Any, blog_id: str, info: dict) -> None:
        """제목/작성자/작성일/공감·댓글 수/본문을 info 에 단계별로 채운다 (예외 시 이미 채운 값은 유지)."""
        # 제목: <title> 파싱 후 " : 네이버 블로그", " - 네이버 블로그" 제거
        raw_title = re.search(r"<title>(.+?)</title>", frame.content())
        if raw_title:
            info["title"] = re.sub(r"\s*[:\-–]\s*네이버\s*블로그\s*$", "", raw_title.group(1)).strip()[:200]

        self._fill_author_and_date(frame, info)
        self._fill_author_fallback(frame, info, blog_id)

        # 공감/댓글 수
        page_txt = frame.inner_text("body")
        m_like = re.search(r"공감\s+(\d+)", page_txt)
        info["like_count"] = int(m_like.group(1)) if m_like else 0
        m_cmt = re.search(r"댓글\s+(\d+)", page_txt)
        info["comment_count"] = int(m_cmt.group(1)) if m_cmt else 0

        # 본문
        info["body"] = (
            frame.locator(".se-main-container, #postViewArea, .post_ct").first.inner_text(timeout=2000).strip()[:8000]
        )

    def blog_read_post(self, post_url: str) -> dict:
        """블로그 포스트 본문 읽기."""
        m_id = re.search(r"blog\.naver\.com/(\w+)/(\d{10,})|blogId=(\w+)[^&]*logNo=(\d+)", post_url)
        blog_id = (m_id.group(1) or m_id.group(3)) if m_id else ""
        log_no = (m_id.group(2) or m_id.group(4)) if m_id else ""

        self.go(post_url)
        time.sleep(3)

        info: dict = {
            "title": "",
            "author": "",
            "written_at": "",
            "body": "",
            "comment_count": 0,
            "like_count": 0,
        }
        tags = []
        images = []
        comments: list[Any] = []

        frame = self._pick_post_frame(log_no)

        with contextlib.suppress(Exception):
            self._fill_post_text_fields(frame, blog_id, info)

        # 이미지 (본문 프레임에서 추출, 프로필 이미지 제외)
        try:
            raw_imgs = frame.evaluate(_js("extract_blog_images.js")) or []
            images = [
                img for img in raw_imgs if not re.search(r"blogpf|thumb|profile|avatar", img.get("src", ""), re.I)
            ]
        except Exception:  # noqa: S110, BLE001
            pass

        # 댓글
        with suppress(Exception):
            comments = frame.evaluate(_js("extract_blog_comments.js")) or []

        # 태그
        with suppress(Exception):
            tags = [t.strip() for t in frame.locator(".tag_area a, .post_tag a").all_inner_texts() if t.strip()]

        return {
            "blog_id": blog_id,
            "log_no": log_no,
            "title": info["title"],
            "author": info["author"],
            "written_at": info["written_at"],
            "body": info["body"],
            "images": [img.get("src", "") if isinstance(img, dict) else "" for img in images],
            "tags": tags,
            "comment_count": info["comment_count"],
            "like_count": info["like_count"],
            "comments": comments,
        }

    def blog_post_images(self, post_url: str) -> list[dict]:
        """포스트 이미지 목록."""
        self.go(post_url)
        time.sleep(2)

        images: list[Any] = []
        try:
            result = self._page.evaluate(_js("extract_blog_images.js"))
            images = result or []
        except Exception:  # noqa: S110, BLE001
            pass

        return images

    def blog_search(self, query: str, page: int = 1, max_results: int = 30) -> list[dict]:
        """블로그 검색."""
        import urllib.parse

        q = urllib.parse.quote(query)
        start = (page - 1) * 10 + 1
        url = f"https://search.naver.com/search.naver?where=post&query={q}&start={start}"

        self.go(url)
        time.sleep(2)

        results: list[Any] = []
        try:
            result = self._page.evaluate(_js("extract_blog_search.js"))
            results = result or []
        except Exception:  # noqa: S110, BLE001
            pass

        return results[:max_results]

    def blog_guestbook(self, blog_url: str, max_entries: int = 30) -> list[dict]:
        """방명록 읽기."""
        blog_id = blog_url.rstrip("/").split("/")[-1]
        url = f"https://blog.naver.com/GuestBook.naver?blogId={blog_id}"

        self.go(url)
        time.sleep(2.5)

        entries: list[Any] = []
        try:
            body = self._page.inner_text("body")
            lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
            i = 0
            while i < len(lines) and len(entries) < max_entries:
                m_date = re.search(r"\d{4}\.\d{2}\.\d{2}", lines[i])
                if m_date and i > 0:
                    author = lines[i - 1]
                    written_at = lines[i]
                    msg_lines = []
                    i += 1
                    while i < len(lines) and not re.search(r"\d{4}\.\d{2}\.\d{2}", lines[i]):
                        msg_lines.append(lines[i])
                        i += 1
                    message = " ".join(msg_lines).strip()[:500]
                    entries.append(
                        {
                            "author": author,
                            "written_at": written_at,
                            "message": message,
                            "replies": [],
                        }
                    )
                else:
                    i += 1
        except Exception:  # noqa: S110, BLE001
            pass

        return entries

    def blog_neighbors(self, blog_url: str, max_neighbors: int = 50) -> list[dict]:
        """이웃 목록."""
        blog_id = blog_url.rstrip("/").split("/")[-1]
        self.go(f"https://blog.naver.com/{blog_id}")
        time.sleep(3)

        neighbors = []
        js = _js("extract_blog_neighbors.js")

        def _extract(frame) -> list[dict]:
            try:
                result = frame.evaluate(js)
                if isinstance(result, dict):
                    return result.get("neighbors", [])
                if isinstance(result, list):
                    return result
            except Exception:  # noqa: S110, BLE001
                pass
            return []

        # WidgetView 프레임 우선 탐색 (이웃 위젯)
        for frame in self._page.frames:
            url = frame.url or ""
            if "WidgetView" in url and blog_id in url:
                got = _extract(frame)
                if got:
                    neighbors = got
                    break

        # 폴백: PostList 프레임 또는 메인 페이지
        if not neighbors:
            frame = self._get_blog_post_frame(blog_id) or self._page
            neighbors = _extract(frame)

        return neighbors[:max_neighbors]

    def blog_post_comments(self, post_url: str, max_comments: int = 100) -> list[dict]:
        """단일 포스트 댓글 수집 (페이지네이션 포함)."""
        self.go(post_url)
        time.sleep(3)

        comments: list[Any] = []
        try:
            result = self._page.evaluate(_js("extract_blog_comments.js"))
            comments = result or []

            # 댓글 더보기 반복 클릭
            for _ in range(10):
                if len(comments) >= max_comments:
                    break
                try:
                    more_btn = self._page.locator(".u_cbox_btn_more").first
                    if more_btn.is_visible(timeout=500):
                        more_btn.click()
                        time.sleep(1.2)
                        result = self._page.evaluate(_js("extract_blog_comments.js"))
                        comments.extend(result or [])
                    else:
                        break
                except Exception:  # noqa: BLE001 - 블로그 콘텐츠 읽기 전용 스크래핑 — 사이트 구조 변경 시 추출만 실패하고 빈 값/기본값으로 폴백, 쓰기·결제·인증 없음(2026-09-28 검토)
                    break
        except Exception:  # noqa: S110, BLE001
            pass

        return comments[:max_comments]

    def blog_all_comments(
        self, blog_url: str, category_no: str = "", max_posts: int = 50, max_comments_per_post: int = 50
    ) -> list[dict]:
        """블로그 전체 포스트 댓글 수집."""
        posts = self.blog_posts(blog_url, category_no=category_no, max_posts=max_posts)
        all_comments = []

        for i, post in enumerate(posts, 1):
            post_url = post.get("href", "")
            if not post_url:
                continue
            print(f"  [{i}/{len(posts)}] {post['title'][:40]}... 댓글 수집", end="", flush=True)
            try:
                comments = self.blog_post_comments(post_url, max_comments=max_comments_per_post)
                for cmt in comments:
                    cmt["log_no"] = post["log_no"]
                    cmt["post_title"] = post["title"]
                    cmt["post_url"] = post_url
                all_comments.extend(comments)
                print(f" → {len(comments)}개")
                time.sleep(1.5)
            except Exception as e:  # noqa: BLE001 - 블로그 콘텐츠 읽기 전용 스크래핑 — 사이트 구조 변경 시 추출만 실패하고 빈 값/기본값으로 폴백, 쓰기·결제·인증 없음(2026-09-28 검토)
                print(f" → 오류: {e}")

        return all_comments

    def blog_stats_detail(self, blog_url: str) -> dict:
        """블로그 상세 통계."""
        self.go(blog_url)
        time.sleep(2)

        stats: dict[Any, Any] = {}
        try:
            result = self._page.evaluate(_js("extract_blog_stats.js"))
            stats = result or {}
        except Exception:  # noqa: S110, BLE001
            pass

        return {
            "visitor_today": stats.get("visitor_today", 0),
            "visitor_week": stats.get("visitor_week", 0),
            "visitor_month": stats.get("visitor_month", 0),
            "visitor_total": stats.get("visitor_total", 0),
            "post_count": stats.get("post_count", 0),
            "comment_count": stats.get("comment_count", 0),
            "neighbor_count": stats.get("neighbor_count", 0),
            "top_posts": stats.get("top_posts", []),
        }

    def blog_tag_posts(self, blog_url: str, tag: str, max_posts: int = 30) -> list[dict]:
        """특정 태그 포스트 목록."""
        blog_id = blog_url.rstrip("/").split("/")[-1]
        import urllib.parse

        tag_enc = urllib.parse.quote(tag)
        url = f"https://blog.naver.com/{blog_id}?tag={tag_enc}"

        self.go(url)
        time.sleep(2)

        posts: list[Any] = []
        try:
            result = self._page.evaluate(_js("extract_blog_posts.js"))
            posts = result or []
        except Exception:  # noqa: S110, BLE001
            pass

        return posts[:max_posts]
