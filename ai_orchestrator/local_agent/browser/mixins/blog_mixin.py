from __future__ import annotations
import re
import time
from pathlib import Path
from typing import Optional

def _js(name: str) -> str:
    from pathlib import Path as _Path
    return (_Path(__file__).parent.parent / "_js" / name).read_text(encoding="utf-8")

class BlogMixin:
    """네이버 블로그 기능 Mixin."""

    # ── 프레임 헬퍼 ────────────────────────────────────────────────────────────

    def _get_blog_post_frame(self, blog_id: str):
        """PostList 프레임 반환 (실제 블로그 콘텐츠)."""
        return next(
            (f for f in self._page.frames
             if 'PostList' in (f.url or '') and blog_id in (f.url or '')),
            None,
        )

    def _get_blog_widget_frame(self, blog_id: str):
        """WidgetView 프레임 반환 (이웃수 등)."""
        return next(
            (f for f in self._page.frames
             if 'WidgetView' in (f.url or '') and blog_id in (f.url or '')),
            None,
        )

    # ── 네이버 블로그 ──────────────────────────────────────────────────────────

    def blog_info(self, blog_url: str) -> dict:
        """블로그 기본정보 조회."""
        blog_id = blog_url.rstrip("/").split("/")[-1]
        self.go(blog_url)
        time.sleep(2.5)

        raw_title = self._page.title() or ""
        title = re.sub(r'\s*[:\-–]\s*네이버\s*블로그\s*$', '', raw_title).strip()
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
            lines = [l.strip() for l in body.splitlines() if l.strip() and len(l.strip()) > 5]
            # 제목, 메뉴 키워드 이후 첫 줄
            skip_keywords = {"NAVER", "블로그", "블로그 메뉴", "포토로그", "지도", "서재", "메모", "태그", "안부"}
            for ln in lines:
                if ln not in skip_keywords and not re.match(r'^(메뉴|본문|이웃|서비스)', ln):
                    description = ln[:200]
                    break
        except Exception:
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
            except Exception:
                pass

        # 프로필 이미지
        try:
            profile_img = frame.evaluate(
                "document.querySelector('.profile_img img, .blog_profile img, "
                ".se-profile-image img')?.src || ''"
            ) or ""
        except Exception:
            pass

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
        """블로그 카테고리 목록."""
        blog_id = blog_url.rstrip("/").split("/")[-1]
        self.go(blog_url)
        time.sleep(2.5)

        categories = []
        frame = self._get_blog_post_frame(blog_id) or self._page

        try:
            result = frame.evaluate("""
            (() => {
              const res = [];
              const seen = new Set();
              // categoryNo 파라미터 포함 링크 직접 탐색
              const anchors = document.querySelectorAll('a[href*="categoryNo"]');
              for (const a of anchors) {
                const href = a.href || '';
                const m = href.match(/categoryNo=(\\d+)/);
                if (!m) continue;
                const catNo = m[1];
                if (catNo === '0' || seen.has(catNo)) continue;
                seen.add(catNo);
                const text = (a.innerText || a.textContent || '').trim().split('\\n')[0].trim();
                if (!text || text.length < 1) continue;
                // 게시글 수: "(N)" 또는 "N개" 패턴 모두 처리
                const li = a.closest('li') || a.parentElement;
                const liTxt = li ? li.innerText : '';
                const cntM = liTxt.match(/\\((\\d+)\\)/) || liTxt.match(/(\\d+)\\s*개/);
                const cnt = cntM ? parseInt(cntM[1]) : 0;
                res.push({name: text, category_no: catNo, post_count: cnt});
              }
              return res;
            })()
            """)
            categories = result
        except Exception:
            pass

        return categories

    def blog_posts(self, blog_url: str, category_no: str = "",
                   page: int = 1, max_posts: int = 30) -> list[dict]:
        """블로그 포스트 목록."""
        blog_id = blog_url.rstrip("/").split("/")[-1]
        url = f"https://blog.naver.com/{blog_id}"
        if category_no:
            url += f"?categoryNo={category_no}"
        if page > 1:
            url += ("&" if category_no else "?") + f"currentPage={page}"

        self.go(url)
        time.sleep(2.5)

        posts = []
        seen: set[str] = set()

        # PostList 프레임에서 포스트 추출
        frame = self._get_blog_post_frame(blog_id) or self._page
        try:
            result = frame.evaluate("""
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
              return res;
            })()
            """)
            for p in result:
                if p["log_no"] not in seen:
                    seen.add(p["log_no"])
                    posts.append(p)
        except Exception:
            pass

        # 폴백: extract_blog_posts.js (카드형 레이아웃)
        if not posts:
            try:
                result = frame.evaluate(_js("extract_blog_posts.js"))
                for p in result:
                    if p.get("log_no") and p["log_no"] not in seen:
                        seen.add(p["log_no"])
                        posts.append(p)
            except Exception:
                pass

        if not posts:
            links = self.extract_links(filter_href=f"blog.naver.com/{blog_id}/")
            for lk in links[:max_posts]:
                m = re.search(r'/(\d{10,})', lk.get("href", ""))
                if m:
                    posts.append({
                        "log_no": m.group(1),
                        "title": lk.get("text", "")[:100],
                        "date": "",
                        "summary": "",
                        "thumb_url": "",
                        "href": lk.get("href", ""),
                        "comment_count": 0,
                    })

        # 최종 폴백: 모바일 URL (m.blog.naver.com) — PC 추출이 2개 미만이면 실행
        if len(posts) < 2:
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
            except Exception:
                pass

        return posts[:max_posts]

    def blog_read_post(self, post_url: str) -> dict:
        """블로그 포스트 본문 읽기."""
        m_id = re.search(r"blog\.naver\.com/(\w+)/(\d{10,})|blogId=(\w+)[^&]*logNo=(\d+)", post_url)
        blog_id = (m_id.group(1) or m_id.group(3)) if m_id else ""
        log_no = (m_id.group(2) or m_id.group(4)) if m_id else ""

        self.go(post_url)
        time.sleep(3)

        title = ""
        author = ""
        written_at = ""
        body = ""
        tags = []
        comment_count = 0
        like_count = 0
        images = []
        comments = []

        # PostView 프레임 우선 탐색 (본문 내용 있는 iframe)
        frame = self._page
        if log_no:
            # PostView.naver 프레임 우선 (실제 본문)
            _f = next((f for f in self._page.frames
                       if "PostView" in (f.url or "") and log_no in (f.url or "")), None)
            if not _f:
                # 폴백: logNo 포함 프레임 중 body 비어있지 않은 것
                for f in self._page.frames:
                    if log_no in (f.url or "") and "PostView" not in (f.url or ""):
                        try:
                            txt = f.inner_text("body", timeout=500)
                            if txt and len(txt) > 50:
                                _f = f
                                break
                        except Exception:
                            pass
            if _f:
                frame = _f

        try:
            # 제목: <title> 파싱 후 " : 네이버 블로그", " - 네이버 블로그" 제거
            raw_title = re.search(r"<title>(.+?)</title>", frame.content())
            if raw_title:
                title = re.sub(r'\s*[:\-–]\s*네이버\s*블로그\s*$', '', raw_title.group(1)).strip()[:200]

            # 작성자 + 작성일: .writer 선택자 → "닉네임 ・ YYYY. MM. DD. HH:MM"
            try:
                writer_txt = frame.locator('.writer').first.inner_text(timeout=1000).strip()
                parts = re.split(r'[·・•]', writer_txt, maxsplit=1)
                author = parts[0].strip() if parts else ""
                if len(parts) > 1:
                    date_m = re.search(r'(\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.\s*\d{1,2}:\d{2})', parts[1])
                    written_at = date_m.group(1).strip() if date_m else parts[1].strip()
            except Exception:
                body_txt = frame.inner_text("body")
                m_date = re.search(r'(\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.\s*\d{1,2}:\d{2})', body_txt)
                written_at = m_date.group(1) if m_date else ""

            # 작성자 폴백: .nick 선택자 또는 blogId
            if not author:
                for auth_sel in ['.nick', '.blog_author', '.author_name']:
                    try:
                        nick = frame.locator(auth_sel).first.inner_text(timeout=500).strip().split('\n')[0]
                        if nick:
                            author = nick
                            break
                    except Exception:
                        pass
                if not author:
                    author = blog_id

            # 공감/댓글 수
            page_txt = frame.inner_text("body")
            m_like = re.search(r"공감\s+(\d+)", page_txt)
            like_count = int(m_like.group(1)) if m_like else 0
            m_cmt = re.search(r"댓글\s+(\d+)", page_txt)
            comment_count = int(m_cmt.group(1)) if m_cmt else 0

            # 본문
            body = frame.locator('.se-main-container, #postViewArea, .post_ct').first.inner_text(timeout=2000).strip()[:8000]
        except Exception:
            pass

        # 이미지 (본문 프레임에서 추출, 프로필 이미지 제외)
        try:
            raw_imgs = frame.evaluate(_js("extract_blog_images.js")) or []
            images = [
                img for img in raw_imgs
                if not re.search(r'blogpf|thumb|profile|avatar', img.get("src", ""), re.I)
            ]
        except Exception:
            pass

        # 댓글
        try:
            comments = frame.evaluate(_js("extract_blog_comments.js")) or []
        except Exception:
            pass

        # 태그
        try:
            tags = [t.strip() for t in frame.locator('.tag_area a, .post_tag a').all_inner_texts()
                    if t.strip()]
        except Exception:
            pass

        return {
            "blog_id": blog_id,
            "log_no": log_no,
            "title": title,
            "author": author,
            "written_at": written_at,
            "body": body,
            "images": [img.get("src", "") if isinstance(img, dict) else "" for img in images],
            "tags": tags,
            "comment_count": comment_count,
            "like_count": like_count,
            "comments": comments,
        }

    def blog_post_images(self, post_url: str) -> list[dict]:
        """포스트 이미지 목록."""
        self.go(post_url)
        time.sleep(2)

        images = []
        try:
            result = self._page.evaluate(_js("extract_blog_images.js"))
            images = result or []
        except Exception:
            pass

        return images

    def blog_search(self, query: str, page: int = 1,
                    max_results: int = 30) -> list[dict]:
        """블로그 검색."""
        import urllib.parse
        q = urllib.parse.quote(query)
        start = (page - 1) * 10 + 1
        url = f"https://search.naver.com/search.naver?where=post&query={q}&start={start}"

        self.go(url)
        time.sleep(2)

        results = []
        try:
            result = self._page.evaluate(_js("extract_blog_search.js"))
            results = result or []
        except Exception:
            pass

        return results[:max_results]

    def blog_guestbook(self, blog_url: str, max_entries: int = 30) -> list[dict]:
        """방명록 읽기."""
        blog_id = blog_url.rstrip("/").split("/")[-1]
        url = f"https://blog.naver.com/GuestBook.naver?blogId={blog_id}"

        self.go(url)
        time.sleep(2.5)

        entries = []
        try:
            body = self._page.inner_text("body")
            lines = [l.strip() for l in body.splitlines() if l.strip()]
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
                    entries.append({
                        "author": author,
                        "written_at": written_at,
                        "message": message,
                        "replies": [],
                    })
                else:
                    i += 1
        except Exception:
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
            except Exception:
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

    def blog_post_comments(self, post_url: str,
                           max_comments: int = 100) -> list[dict]:
        """단일 포스트 댓글 수집 (페이지네이션 포함)."""
        self.go(post_url)
        time.sleep(3)

        comments = []
        try:
            result = self._page.evaluate(_js("extract_blog_comments.js"))
            comments = result or []

            # 댓글 더보기 반복 클릭
            for _ in range(10):
                if len(comments) >= max_comments:
                    break
                try:
                    more_btn = self._page.locator('.u_cbox_btn_more').first
                    if more_btn.is_visible(timeout=500):
                        more_btn.click()
                        time.sleep(1.2)
                        result = self._page.evaluate(_js("extract_blog_comments.js"))
                        comments.extend(result or [])
                    else:
                        break
                except Exception:
                    break
        except Exception:
            pass

        return comments[:max_comments]

    def blog_all_comments(self, blog_url: str, category_no: str = "",
                          max_posts: int = 50,
                          max_comments_per_post: int = 50) -> list[dict]:
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
            except Exception as e:
                print(f" → 오류: {e}")

        return all_comments

    def blog_stats_detail(self, blog_url: str) -> dict:
        """블로그 상세 통계."""
        blog_id = blog_url.rstrip("/").split("/")[-1]
        self.go(blog_url)
        time.sleep(2)

        stats = {}
        try:
            result = self._page.evaluate(_js("extract_blog_stats.js"))
            stats = result or {}
        except Exception:
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

    def blog_tag_posts(self, blog_url: str, tag: str,
                       max_posts: int = 30) -> list[dict]:
        """특정 태그 포스트 목록."""
        blog_id = blog_url.rstrip("/").split("/")[-1]
        import urllib.parse
        tag_enc = urllib.parse.quote(tag)
        url = f"https://blog.naver.com/{blog_id}?tag={tag_enc}"

        self.go(url)
        time.sleep(2)

        posts = []
        try:
            result = self._page.evaluate(_js("extract_blog_posts.js"))
            posts = result or []
        except Exception:
            pass

        return posts[:max_posts]

    # ── 블로그 WRITE 메서드 ─────────────────────────────────────────────────────

    def blog_write_post(self, title: str, body: str,
                        category_no: str = "",
                        tags: list[str] | None = None,
                        image_paths: list[str] | None = None,
                        is_public: bool = True) -> dict:
        """포스트 작성."""
        self.go("https://blog.naver.com/posting/write")
        time.sleep(3)

        try:
            self._page.locator('.se-title-input, #subject').first.fill(title)
            time.sleep(0.5)

            self._page.locator('.se-text-paragraph').first.click()
            time.sleep(0.5)
            self._page.keyboard.type(body)
            time.sleep(0.5)

            if category_no:
                try:
                    self._page.locator('.category_select').first.click()
                    time.sleep(0.5)
                    self._page.locator(f'[data-category-no="{category_no}"]').first.click()
                except Exception:
                    pass

            if tags:
                try:
                    self._page.locator('.tag_input').first.fill(", ".join(tags))
                except Exception:
                    pass

            if image_paths:
                for img_path in image_paths:
                    try:
                        self._page.locator('input[type="file"]').first.set_input_files(img_path)
                        time.sleep(1.5)
                    except Exception:
                        pass

            publish_btn = self._page.locator('.publish_btn, .btn_publish').first
            publish_btn.click()
            time.sleep(2)

            # log_no 파싱
            current_url = self._page.url
            m = re.search(r'/(\d{10,})', current_url)
            log_no = m.group(1) if m else ""

            return {"ok": True, "log_no": log_no, "url": current_url, "error": ""}
        except Exception as e:
            return {"ok": False, "log_no": "", "url": "", "error": str(e)}

    def blog_edit_post(self, blog_id: str, log_no: str,
                       title: str = "", body: str = "",
                       tags: list[str] | None = None) -> dict:
        """포스트 수정."""
        url = f"https://blog.naver.com/PostModify.naver?blogId={blog_id}&logNo={log_no}"
        self.go(url)
        time.sleep(3)

        try:
            if title:
                self._page.locator('.se-title-input, #subject').first.clear()
                self._page.locator('.se-title-input, #subject').first.fill(title)
                time.sleep(0.5)

            if body:
                self._page.locator('.se-text-paragraph').first.click()
                time.sleep(0.5)
                self._page.keyboard.press("Control+A")
                self._page.keyboard.type(body)
                time.sleep(0.5)

            if tags:
                try:
                    self._page.locator('.tag_input').first.clear()
                    self._page.locator('.tag_input').first.fill(", ".join(tags))
                except Exception:
                    pass

            self._page.locator('.save_btn, .btn_save').first.click()
            time.sleep(1.5)

            return {"ok": True, "log_no": log_no, "error": ""}
        except Exception as e:
            return {"ok": False, "log_no": log_no, "error": str(e)}

    def blog_delete_post(self, blog_id: str, log_no: str) -> dict:
        """포스트 삭제."""
        url = f"https://blog.naver.com/{blog_id}/{log_no}"
        self.go(url)
        time.sleep(2)

        try:
            self._page.on("dialog", lambda dialog: dialog.accept())
            self._page.locator('.more_btn, [class*="more"]').first.click()
            time.sleep(0.5)
            self._page.locator('.del_btn, [class*="delete"]').first.click()
            time.sleep(1)
            return {"ok": True, "error": ""}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def blog_upload_image(self, image_path: str) -> dict:
        """이미지 업로드."""
        try:
            self._page.locator('input[type="file"]').first.set_input_files(image_path)
            time.sleep(2)
            img_url = self._page.evaluate("document.querySelector('.se-image-resource')?.src || ''")
            if img_url:
                return {"ok": True, "image_url": img_url, "error": ""}
            return {"ok": False, "image_url": "", "error": "이미지 URL 추출 실패"}
        except Exception as e:
            return {"ok": False, "image_url": "", "error": str(e)}

    def blog_write_comment(self, post_url: str, text: str) -> dict:
        """댓글 작성."""
        self.go(post_url)
        time.sleep(2.5)

        try:
            comment_input = self._page.locator('.u_cbox_input, .reply_input, #comment_text').first
            comment_input.click()
            comment_input.fill(text)
            time.sleep(0.5)

            submit_btn = self._page.locator('.u_cbox_btn_upload, .btn_comment_write').first
            submit_btn.click()
            time.sleep(1.5)

            return {"ok": True, "error": ""}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def blog_delete_comment(self, post_url: str, comment_index: int = 0) -> dict:
        """댓글 삭제."""
        self.go(post_url)
        time.sleep(2.5)

        try:
            delete_btns = self._page.locator('.u_cbox_btn_delete, .btn_delete_comment').all()
            if comment_index < len(delete_btns):
                self._page.on("dialog", lambda dialog: dialog.accept())
                delete_btns[comment_index].click()
                time.sleep(1)
                return {"ok": True, "error": ""}
            return {"ok": False, "error": "댓글 인덱스 초과"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def blog_like_post(self, post_url: str) -> dict:
        """공감 클릭."""
        self.go(post_url)
        time.sleep(2)

        try:
            like_btn = self._page.locator('.u_likeit_text, .sympathy_btn, [class*="like"]').first
            like_btn.click()
            time.sleep(1)

            m = re.search(r"공감\s*\(?\s*(\d+)", self._page.inner_text("body"))
            like_count = int(m.group(1)) if m else 0

            return {"ok": True, "is_liked": True, "like_count": like_count, "error": ""}
        except Exception as e:
            return {"ok": False, "is_liked": False, "like_count": 0, "error": str(e)}

    def blog_unlike_post(self, post_url: str) -> dict:
        """공감 취소."""
        return self.blog_like_post(post_url)

    def blog_add_neighbor(self, target_blog_url: str, is_mutual: bool = False) -> dict:
        """이웃 추가."""
        self.go(target_blog_url)
        time.sleep(2)

        try:
            add_btn = self._page.locator('.btn_add_friend, .add_buddy, [class*="add_neighbor"]').first
            add_btn.click()
            time.sleep(1)

            if is_mutual:
                try:
                    mutual_btn = self._page.locator('.btn_mutual, [class*="mutual"]').first
                    mutual_btn.click()
                except Exception:
                    pass

            confirm_btn = self._page.locator('.btn_confirm, .btn_ok').first
            confirm_btn.click()
            time.sleep(1)

            return {"ok": True, "error": ""}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def blog_remove_neighbor(self, target_blog_url: str) -> dict:
        """이웃 삭제."""
        self.go(target_blog_url)
        time.sleep(2)

        try:
            self._page.on("dialog", lambda dialog: dialog.accept())
            del_btn = self._page.locator('.btn_del_friend, .del_buddy, [class*="del_neighbor"]').first
            del_btn.click()
            time.sleep(1)

            return {"ok": True, "error": ""}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def blog_write_guestbook(self, blog_url: str, message: str) -> dict:
        """방명록 작성."""
        blog_id = blog_url.rstrip("/").split("/")[-1]
        url = f"https://blog.naver.com/GuestBook.naver?blogId={blog_id}"
        self.go(url)
        time.sleep(2)

        try:
            input_field = self._page.locator('#memo_text, .guestbook_input').first
            input_field.fill(message)
            time.sleep(0.5)

            submit_btn = self._page.locator('.btn_register, .btn_submit').first
            submit_btn.click()
            time.sleep(1.5)

            return {"ok": True, "error": ""}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def blog_scrap_post(self, post_url: str) -> dict:
        """포스트 스크랩."""
        self.go(post_url)
        time.sleep(2)

        try:
            scrap_btn = self._page.locator('.scrap_btn, [class*="scrap"]').first
            scrap_btn.click()
            time.sleep(1)

            return {"ok": True, "error": ""}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── 이웃 자동화 메서드 ──────────────────────────────────────────────────────

    def blog_visit_neighbors(self, blog_url: str,
                              max_neighbors: int = 20,
                              delay: float = 2.0) -> list[dict]:
        """이웃 블로그 순차 방문 + 정보 수집."""
        neighbors = self.blog_neighbors(blog_url, max_neighbors=max_neighbors)
        results = []

        for i, neighbor in enumerate(neighbors, 1):
            print(f"  [{i}/{len(neighbors)}] {neighbor.get('nickname', '')}...", end="", flush=True)
            try:
                info = self.blog_info(neighbor["blog_url"])
                posts = self.blog_posts(neighbor["blog_url"], max_posts=1)
                last_post = posts[0] if posts else {}

                results.append({
                    "blog_id": neighbor["blog_id"],
                    "nickname": neighbor["nickname"],
                    "last_post_title": last_post.get("title", ""),
                    "last_post_date": last_post.get("date", ""),
                    "visitor_today": info.get("visitor_today", 0),
                    "neighbor_count": info.get("neighbor_count", 0),
                    "visit_ok": True,
                })
                print(" ✓")
                time.sleep(delay)
            except Exception as e:
                print(f" ✗ {e}")
                results.append({
                    "blog_id": neighbor["blog_id"],
                    "nickname": neighbor["nickname"],
                    "last_post_title": "",
                    "last_post_date": "",
                    "visitor_today": 0,
                    "neighbor_count": 0,
                    "visit_ok": False,
                })

        return results

    def blog_comment_neighbors(self, blog_url: str,
                                comment_text: str,
                                max_neighbors: int = 10,
                                delay: float = 3.0,
                                skip_already_commented: bool = True) -> list[dict]:
        """이웃 최신 포스트에 댓글 작성."""
        neighbors = self.blog_neighbors(blog_url, max_neighbors=max_neighbors)
        results = []

        for i, neighbor in enumerate(neighbors, 1):
            print(f"  [{i}/{len(neighbors)}] {neighbor.get('nickname', '')}...", end="", flush=True)
            try:
                posts = self.blog_posts(neighbor["blog_url"], max_posts=1)
                if not posts:
                    print(" 포스트 없음")
                    continue

                post = posts[0]
                post_url = post.get("href", "")

                if skip_already_commented:
                    comments = self.blog_post_comments(post_url, max_comments=30)
                    my_nickname = ""
                    try:
                        my_info = self.blog_info("https://blog.naver.com/")
                        my_nickname = my_info.get("title", "").split("-")[0].strip()
                    except Exception:
                        pass

                    if any(my_nickname in c.get("author", "") for c in comments):
                        print(" 이미 댓글함")
                        continue

                self.blog_write_comment(post_url, comment_text)
                results.append({
                    "blog_id": neighbor["blog_id"],
                    "post_url": post_url,
                    "post_title": post.get("title", ""),
                    "ok": True,
                    "error": "",
                })
                print(" ✓ 댓글 작성")
                time.sleep(delay)
            except Exception as e:
                print(f" ✗ {e}")
                results.append({
                    "blog_id": neighbor["blog_id"],
                    "post_url": "",
                    "post_title": "",
                    "ok": False,
                    "error": str(e),
                })

        return results

    def blog_like_neighbors(self, blog_url: str,
                              max_neighbors: int = 20,
                              delay: float = 2.0) -> list[dict]:
        """이웃 최신 포스트 공감."""
        neighbors = self.blog_neighbors(blog_url, max_neighbors=max_neighbors)
        results = []

        for i, neighbor in enumerate(neighbors, 1):
            print(f"  [{i}/{len(neighbors)}] {neighbor.get('nickname', '')}...", end="", flush=True)
            try:
                posts = self.blog_posts(neighbor["blog_url"], max_posts=1)
                if not posts:
                    print(" 포스트 없음")
                    continue

                post = posts[0]
                post_url = post.get("href", "")

                result = self.blog_like_post(post_url)
                results.append({
                    "blog_id": neighbor["blog_id"],
                    "post_url": post_url,
                    "ok": result["ok"],
                    "like_count": result.get("like_count", 0),
                    "error": result["error"],
                })
                print(f" ✓ 공감 ({result.get('like_count', 0)})")
                time.sleep(delay)
            except Exception as e:
                print(f" ✗ {e}")
                results.append({
                    "blog_id": neighbor["blog_id"],
                    "post_url": "",
                    "ok": False,
                    "like_count": 0,
                    "error": str(e),
                })

        return results

    def blog_visit_and_comment(self, blog_url: str,
                                comment_text: str,
                                max_neighbors: int = 10,
                                also_like: bool = True,
                                delay: float = 3.5) -> list[dict]:
        """이웃 방문 + 공감 + 댓글."""
        neighbors = self.blog_neighbors(blog_url, max_neighbors=max_neighbors)
        results = []

        for i, neighbor in enumerate(neighbors, 1):
            print(f"  [{i}/{len(neighbors)}] {neighbor.get('nickname', '')}...", end="", flush=True)
            try:
                posts = self.blog_posts(neighbor["blog_url"], max_posts=1)
                if not posts:
                    print(" 포스트 없음")
                    continue

                post = posts[0]
                post_url = post.get("href", "")

                visited = True
                liked = False
                commented = False

                if also_like:
                    like_result = self.blog_like_post(post_url)
                    liked = like_result["ok"]

                comment_result = self.blog_write_comment(post_url, comment_text)
                commented = comment_result["ok"]

                results.append({
                    "blog_id": neighbor["blog_id"],
                    "post_url": post_url,
                    "visited": visited,
                    "liked": liked,
                    "commented": commented,
                    "error": "",
                })
                print(" ✓")
                time.sleep(delay)
            except Exception as e:
                print(f" ✗ {e}")
                results.append({
                    "blog_id": neighbor["blog_id"],
                    "post_url": "",
                    "visited": False,
                    "liked": False,
                    "commented": False,
                    "error": str(e),
                })

        return results

    def blog_neighbor_activity(self, blog_url: str,
                                days: int = 7) -> list[dict]:
        """이웃 최근 N일 활동 현황."""
        neighbors = self.blog_neighbors(blog_url)
        results = []

        for neighbor in neighbors:
            try:
                posts = self.blog_posts(neighbor["blog_url"], max_posts=3)
                post_count_recent = 0

                for post in posts:
                    date_str = post.get("date", "")
                    if date_str:
                        m = re.search(r"(\d{4})\.(\d{2})\.(\d{2})", date_str)
                        if m:
                            from datetime import datetime, timedelta
                            post_date = datetime.strptime(f"{m.group(1)}-{m.group(2)}-{m.group(3)}", "%Y-%m-%d")
                            if (datetime.now() - post_date).days <= days:
                                post_count_recent += 1

                last_post = posts[0] if posts else {}
                is_active = post_count_recent > 0

                results.append({
                    "blog_id": neighbor["blog_id"],
                    "nickname": neighbor["nickname"],
                    "post_count_recent": post_count_recent,
                    "last_post_date": last_post.get("date", ""),
                    "last_post_title": last_post.get("title", ""),
                    "is_active": is_active,
                })
            except Exception:
                results.append({
                    "blog_id": neighbor["blog_id"],
                    "nickname": neighbor["nickname"],
                    "post_count_recent": 0,
                    "last_post_date": "",
                    "last_post_title": "",
                    "is_active": False,
                })

        return results

    def blog_mutual_request_all(self, blog_url: str,
                                  max_targets: int = 20) -> list[dict]:
        """서로이웃이 아닌 이웃에게 서로이웃 신청."""
        neighbors = self.blog_neighbors(blog_url, max_neighbors=max_targets)
        results = []

        for i, neighbor in enumerate(neighbors, 1):
            if neighbor.get("is_mutual"):
                continue

            print(f"  [{i}/{len(neighbors)}] {neighbor.get('nickname', '')} 서로이웃 신청...", end="", flush=True)
            try:
                result = self.blog_add_neighbor(neighbor["blog_url"], is_mutual=True)
                results.append({
                    "blog_id": neighbor["blog_id"],
                    "ok": result["ok"],
                    "error": result["error"],
                })
                print(" ✓")
                time.sleep(3.0)
            except Exception as e:
                print(f" ✗ {e}")
                results.append({
                    "blog_id": neighbor["blog_id"],
                    "ok": False,
                    "error": str(e),
                })

        return results

    # ── 멀티 블로그 수집 메서드 ────────────────────────────────────────────────

    def blog_bulk_collect(self, blog_urls: list[str],
                           include_posts: bool = True,
                           include_comments: bool = False,
                           include_images: bool = False,
                           max_posts_each: int = 20) -> list[dict]:
        """여러 블로그 일괄 수집."""
        results = []

        for i, blog_url in enumerate(blog_urls, 1):
            print(f"\n[{i}/{len(blog_urls)}] {blog_url} 수집 중...")
            try:
                blog_data = self.blog_info(blog_url)

                if include_posts:
                    blog_data["posts"] = self.blog_posts(blog_url, max_posts=max_posts_each)

                    if include_comments:
                        blog_data["comments"] = self.blog_all_comments(blog_url, max_posts=max_posts_each)

                    if include_images:
                        for post in blog_data.get("posts", [])[:5]:
                            post["images"] = self.blog_post_images(post.get("href", ""))

                results.append(blog_data)
                time.sleep(2.0)
            except Exception as e:
                print(f"  오류: {e}")
                results.append({"blog_id": blog_url.split("/")[-1], "error": str(e)})

        return results

    def blog_monitor_keywords(self, keywords: list[str],
                                page: int = 1,
                                max_each: int = 20) -> dict:
        """키워드 검색 → 결과 수집."""
        results = {}

        for keyword in keywords:
            print(f"\n검색: '{keyword}'...")
            try:
                search_results = self.blog_search(keyword, page=page, max_results=max_each)
                results[keyword] = search_results
                time.sleep(1.5)
            except Exception as e:
                print(f"  오류: {e}")
                results[keyword] = []

        return results

    def blog_track_blogger(self, target_blog_url: str,
                             save_path: str = "") -> dict:
        """블로거 전체 정보 스냅샷."""
        from datetime import datetime

        print(f"블로거 추적: {target_blog_url}")
        info = self.blog_info(target_blog_url)
        categories = self.blog_categories(target_blog_url)
        recent_posts = self.blog_posts(target_blog_url, max_posts=10)
        stats = self.blog_stats_detail(target_blog_url)

        # 태그 수집 — 최근 포스트 최대 5개 읽어서 태그 집계
        top_tags: dict[str, int] = {}
        for post in recent_posts[:5]:
            href = post.get("href", "")
            if not href:
                continue
            try:
                post_data = self.blog_read_post(href)
                for tag in post_data.get("tags", []):
                    if tag:
                        top_tags[tag] = top_tags.get(tag, 0) + 1
            except Exception:
                pass
        # 빈도순 정렬
        top_tags = dict(sorted(top_tags.items(), key=lambda x: x[1], reverse=True))

        snapshot = {
            "captured_at": datetime.now().isoformat(),
            "blog_info": info,
            "categories": categories,
            "recent_posts": recent_posts,
            "stats": stats,
            "top_tags": top_tags,
        }

        if save_path:
            import json
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
            print(f"  저장: {save_path}")

        return snapshot

    def blog_search_bulk(self, query: str, max_pages: int = 3,
                          collect_post: bool = False) -> list[dict]:
        """검색 결과 여러 페이지 수집."""
        results = []

        for page in range(1, max_pages + 1):
            print(f"  페이지 {page}/{max_pages}...", end="", flush=True)
            try:
                page_results = self.blog_search(query, page=page)

                if collect_post:
                    for result in page_results:
                        post_url = result.get("href", "")
                        if post_url:
                            try:
                                post_data = self.blog_read_post(post_url)
                                result["body"] = post_data.get("body", "")
                                result["images"] = post_data.get("images", [])
                            except Exception:
                                pass

                results.extend(page_results)
                print(f" {len(page_results)}개")
                time.sleep(1.5)
            except Exception as e:
                print(f" 오류: {e}")

        return results

    def blog_compare_bloggers(self, blog_urls: list[str]) -> list[dict]:
        """블로거 비교표."""
        results = []

        for blog_url in blog_urls:
            try:
                info = self.blog_info(blog_url)
                posts = self.blog_posts(blog_url, max_posts=20)

                avg_comments = 0
                avg_likes = 0
                if posts:
                    avg_comments = sum(p.get("comment_count", 0) for p in posts) / len(posts)
                    # 좋아요: 최근 5개 포스트 직접 읽어서 like_count 평균
                    like_counts = []
                    for p in posts[:5]:
                        href = p.get("href", "")
                        if href:
                            try:
                                pd = self.blog_read_post(href)
                                like_counts.append(pd.get("like_count", 0))
                            except Exception:
                                pass
                    if like_counts:
                        avg_likes = sum(like_counts) / len(like_counts)

                results.append({
                    "blog_id": info["blog_id"],
                    "title": info["title"],
                    "post_count": len(posts),
                    "neighbor_count": info["neighbor_count"],
                    "visitor_total": info["visitor_total"],
                    "visitor_today": info["visitor_today"],
                    "avg_comments": round(avg_comments, 1),
                    "avg_likes": avg_likes,
                })
                time.sleep(2.0)
            except Exception as e:
                print(f"  {blog_url} 오류: {e}")

        return results

    # ── 사진 다운로드 메서드 ────────────────────────────────────────────────────

    def blog_download_images(self, post_url: str,
                               save_dir: str = "data/blog_images") -> dict:
        """단일 포스트 이미지 다운로드."""
        m = re.search(r"blog\.naver\.com/(\w+)/(\d{10,})|blogId=(\w+).*logNo=(\d+)", post_url)
        blog_id = m.group(1) or m.group(3) if m else ""
        log_no = m.group(2) or m.group(4) if m else ""

        post_save_dir = Path(save_dir) / blog_id / log_no
        post_save_dir.mkdir(parents=True, exist_ok=True)

        images = self.blog_post_images(post_url)
        downloaded = 0
        failed = 0
        paths = []

        for i, img in enumerate(images, 1):
            src = img.get("src", "") if isinstance(img, dict) else img
            if not src:
                continue

            try:
                result = self.download_attachment(src, save_dir=str(post_save_dir))
                if result["ok"]:
                    downloaded += 1
                    paths.append(result["path"])
                    print(f"    이미지 {i}/{len(images)}: ✓ {Path(result['path']).name}")
                else:
                    failed += 1
                    print(f"    이미지 {i}/{len(images)}: ✗ {result['error']}")
            except Exception as e:
                failed += 1
                print(f"    이미지 {i}/{len(images)}: ✗ {e}")

        return {
            "ok": failed == 0,
            "downloaded": downloaded,
            "failed": failed,
            "paths": paths,
            "save_dir": str(post_save_dir),
        }

    def blog_download_all_images(self, blog_url: str,
                                   save_dir: str = "data/blog_images",
                                   category_no: str = "",
                                   max_pages: int = 5) -> dict:
        """블로그 전체 이미지 다운로드."""
        blog_id = blog_url.rstrip("/").split("/")[-1]
        total_posts = 0
        downloaded = 0
        failed = 0

        for page in range(1, max_pages + 1):
            print(f"\n[페이지 {page}/{max_pages}]")
            posts = self.blog_posts(blog_url, category_no=category_no, page=page, max_posts=30)

            if not posts:
                print("  포스트 없음, 종료")
                break

            for i, post in enumerate(posts, 1):
                total_posts += 1
                post_url = post.get("href", "")
                print(f"  [{i}/{len(posts)}] {post['title'][:40]}...")

                try:
                    result = self.blog_download_images(post_url, save_dir=save_dir)
                    downloaded += result["downloaded"]
                    failed += result["failed"]
                    time.sleep(1.5)
                except Exception as e:
                    print(f"    오류: {e}")
                    failed += len(self.blog_post_images(post_url))

        return {
            "ok": failed == 0,
            "total_posts": total_posts,
            "downloaded": downloaded,
            "failed": failed,
            "save_dir": str(Path(save_dir) / blog_id),
        }

    def blog_save_post_html(self, post_url: str,
                             save_dir: str = "data/blog_html") -> dict:
        """포스트를 HTML로 저장."""
        m = re.search(r"blog\.naver\.com/(\w+)/(\d{10,})|blogId=(\w+).*logNo=(\d+)", post_url)
        blog_id = m.group(1) or m.group(3) if m else ""
        log_no = m.group(2) or m.group(4) if m else ""

        self.go(post_url)
        time.sleep(2)

        try:
            html_content = self._page.content()
            save_path = Path(save_dir) / blog_id / f"{log_no}.html"
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_text(html_content, encoding="utf-8")

            return {
                "ok": True,
                "path": str(save_path),
                "size": save_path.stat().st_size,
                "error": "",
            }
        except Exception as e:
            return {
                "ok": False,
                "path": "",
                "size": 0,
                "error": str(e),
            }

    # ── 내 블로그 URL 자동 탐지 ─────────────────────────────────────────────────

    def my_blog_url(self) -> str:
        """로그인된 사용자의 블로그 URL 자동 탐지.

        blog.naver.com/MyBlog.naver 리다이렉트 → 실제 블로그 URL 추출.
        로그인 안 된 경우 빈 문자열 반환.
        """
        result = self.go("https://blog.naver.com/MyBlog.naver", wait=3.0)
        if not result.ok:
            return ""

        current_url = self._page.url
        # 리다이렉트 후 blog.naver.com/{blog_id} 형태가 되면 성공
        m = re.search(r'blog\.naver\.com/([^/?#]+)', current_url)
        if m:
            blog_id = m.group(1)
            # 시스템 경로 제외 (MyBlog, PostList 등)
            skip = {"MyBlog.naver", "PostList.naver", "BlogHome.naver",
                    "home", "market", "PostView.naver"}
            if blog_id not in skip and not blog_id.endswith(".naver"):
                return f"https://blog.naver.com/{blog_id}"

        # 폴백: 페이지 내 "내 블로그" 링크 탐색
        try:
            links = self.extract_links(filter_href="blog.naver.com/")
            for link in links:
                href = link.get("href", "")
                text = link.get("text", "")
                if "내 블로그" in text or "내블로그" in text:
                    m2 = re.search(r'blog\.naver\.com/([^/?#]+)', href)
                    if m2 and not m2.group(1).endswith(".naver"):
                        return f"https://blog.naver.com/{m2.group(1)}"
        except Exception:
            pass

        return ""

