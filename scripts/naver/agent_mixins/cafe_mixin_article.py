"""cafe_mixin 글 읽기/스크랩/첨부 기능 (CafeArticleMixin).

read_article/extract_attachments/liked·scrapped/_fetch_graphql_bff.
CafeMixin 이 다중상속. [docs/module_separation_standard.md]
"""

from __future__ import annotations

import contextlib
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scripts.naver.agent_mixins.cafe_mixin_common import _js

# 네이버 카페 파일 호스트만 첨부파일로 인정
_CAFE_FILE_HOSTS = (
    "downapi.cafe.naver.com",
    "cafefile.cafe.naver.com",
    "cafeattach.naver.net",
    "cafefiles.cafe.naver.com",
)
_CAFE_FILE_URL_KEYWORDS = (
    "FileDownload",
    "cafe.naver.com/CafeFileDownload",
)

_ATTACH_SELECTORS = [
    ".AttachFileList a",
    ".attach_file_list a",
    ".file_area a",
    ".AttachFile a",
    "ul.attach_list a",
    ".se-file-component a",
    "a[href*='FileDownload']",
]

_ATTACH_EXT_PATTERN = re.compile(
    r"\.(dwg|pdf|xlsx?|docx?|pptx?|zip|rar|7z|hwp|hwpx|dxf|dgn|skp|rvt|ifc|csv|txt)$",
    re.IGNORECASE,
)

_ATTACH_JS = """
                    (() => {
                        const res = [];
                        const extRe = /\\.(dwg|pdf|xlsx?|docx?|pptx?|zip|rar|7z|hwp|hwpx|dxf|dgn|skp|rvt|ifc|csv|txt)$/i;
                        const cafeHosts = ['downapi.cafe.naver.com','cafefile.cafe.naver.com',
                                           'cafeattach.naver.net','cafefiles.cafe.naver.com'];
                        for (const a of document.querySelectorAll('a')) {
                            const href = a.href || '';
                            const txt = (a.innerText || a.textContent || '').trim();
                            if (!href) continue;
                            let isAttach = href.includes('FileDownload');
                            if (!isAttach) {
                                try {
                                    const u = new URL(href);
                                    isAttach = cafeHosts.some(h => u.hostname === h);
                                } catch(e) {}
                            }
                            if (isAttach) {
                                const m = extRe.exec(txt) || extRe.exec(href);
                                res.push({ name: txt, url: href, ext: m ? m[1].toLowerCase() : '' });
                            }
                        }
                        return res;
                    })()
                    """

_ARTICLE_BODY_SELECTORS = [
    ".se-main-container",
    ".article_viewer",
    "#tbody",
    ".article-viewer",
    ".se-component-content",
    ".content_area",
    ".articleDetailView",
]
_ARTICLE_TITLE_SELECTORS = [
    "h3.title_text",
    ".title_area h3",
    ".article_header h3",
    ".title_subject",
    ".article-title",
    "h3.title",
    ".tit-txt",
]


def _safe_inner_text(frame, sel: str, timeout: int = 1000) -> str:
    try:
        return frame.locator(sel).first.inner_text(timeout=timeout).strip()
    except Exception:  # noqa: BLE001 - 네이버 카페 게시글 읽기 전용 파싱(본문/첨부파일 추출) — 실패는 안전한 기본값(빈 값/False)으로 폴백, 쓰기·결제 없음(2026-09-28 검토)
        return ""


def _is_cafe_attach_url(href: str) -> bool:
    if any(kw in href for kw in _CAFE_FILE_URL_KEYWORDS):
        return True
    try:
        from urllib.parse import urlparse

        host = urlparse(href).hostname or ""
        return any(host == h for h in _CAFE_FILE_HOSTS)
    except Exception:  # noqa: BLE001 - 네이버 카페 게시글 읽기 전용 파싱(본문/첨부파일 추출) — 실패는 안전한 기본값(빈 값/False)으로 폴백, 쓰기·결제 없음(2026-09-28 검토)
        return False


def _attachment_size(el) -> str:
    size = ""
    try:
        parent_text = el.locator("..").inner_text(timeout=300)
        size_m = re.search(r"(\d+(?:\.\d+)?\s*(?:KB|MB|GB|Bytes?))", parent_text, re.IGNORECASE)
        if size_m:
            size = size_m.group(1)
    except Exception:  # noqa: S110, BLE001
        pass
    return size


def _attachment_from_element(el, seen_urls: set[str]) -> dict | None:
    href = el.get_attribute("href") or ""
    if not href or href in seen_urls:
        return None
    if not _is_cafe_attach_url(href):
        return None
    name = el.inner_text(timeout=500).strip()
    seen_urls.add(href)
    ext_m = _ATTACH_EXT_PATTERN.search(name) or _ATTACH_EXT_PATTERN.search(href)
    ext = ext_m.group(1).lower() if ext_m else ""
    size = _attachment_size(el)
    return {
        "name": name or Path(href.split("?")[0]).name,
        "url": href,
        "size": size,
        "ext": ext,
    }


def _collect_frame_attachments(frame, seen_urls: set[str], attachments: list[dict]) -> None:
    for sel in _ATTACH_SELECTORS:
        try:
            els = frame.locator(sel).all()
        except Exception:  # noqa: BLE001, S112
            continue
        for el in els:
            try:
                item = _attachment_from_element(el, seen_urls)
                if item is not None:
                    attachments.append(item)
            except Exception:  # noqa: BLE001, S112
                continue


def _collect_js_attachments(search_frames: list, seen_urls: set[str], attachments: list[dict]) -> None:
    """JS 방식 폴백: evaluate로 모든 a 태그 스캔."""
    js_result = []
    for frame in search_frames:
        try:
            js_result = frame.evaluate(_ATTACH_JS)
            if js_result:
                break
        except Exception:  # noqa: BLE001, S112
            continue
    for r in js_result:
        if r.get("url") and r["url"] not in seen_urls:
            seen_urls.add(r["url"])
            attachments.append({"name": r.get("name", ""), "url": r["url"], "size": "", "ext": r.get("ext", "")})


def _article_id_from_url(url: str) -> str:
    aid_m = re.search(r"articles/(\d+)|articleid=(\d+)", url)
    return (aid_m.group(1) or aid_m.group(2)) if aid_m else ""


def _is_article_frame_for(f, target_aid: str) -> bool:
    url = f.url or ""
    if "about:blank" in url:
        return False
    path = url.split("?")[0]
    # f-e 프레임(메인)은 제외 — ca-fe/ 프레임(cafe_main)만 우선
    if "f-e/cafes" in path and f.name != "cafe_main":
        return False
    # article_id 불일치 프레임 제외 (이전 캐시 방지)
    if target_aid and f.name == "cafe_main" and target_aid not in (f.url or ""):
        return False
    return any(kw in path for kw in ("ArticleRead", "articles/", "ca-fe/"))


def _scan_frame_for_title_body(frame, in_article_frames: bool, st: dict) -> None:
    """프레임 1개에서 제목/본문을 찾아 st(title/body/af)에 반영한다."""
    if not st["title"]:
        for sel in _ARTICLE_TITLE_SELECTORS:
            t = _safe_inner_text(frame, sel)
            if t:
                st["title"] = t
                break
    for sel in _ARTICLE_BODY_SELECTORS:
        b = _safe_inner_text(frame, sel, timeout=2000)
        if b and len(b) > 20:
            st["body"] = b
            st["af"] = frame
            break
    if not st["body"] and in_article_frames:
        fb = ""
        with contextlib.suppress(Exception):
            fb = frame.inner_text("body")
        if fb and len(fb.strip()) > 50:
            st["body"] = fb.strip()
            st["af"] = frame


def _extract_article_meta(meta_frame) -> dict:
    """작성일/조회수/작성자/게시판/좋아요/태그 추출."""
    # 작성일 / 조회수
    info_raw = _safe_inner_text(meta_frame, ".article_info")
    view_m = re.search(r"조회\s*([\d,]+)", info_raw)
    view_count = view_m.group(1) if view_m else ""
    date_m = re.search(r"(\d{4}\.\d{2}\.\d{2}\.?\s*\d{2}:\d{2})", info_raw)
    written_at = date_m.group(1).strip() if date_m else ""

    # 작성자
    author = _safe_inner_text(meta_frame, ".nickname")

    # 게시판명
    board = _safe_inner_text(meta_frame, ".board_link") or _safe_inner_text(meta_frame, ".board_name")

    # 좋아요
    like_raw = _safe_inner_text(meta_frame, ".like_count") or _safe_inner_text(meta_frame, "em.u_cnt._count")
    like_count = re.sub(r"[^\d,]", "", like_raw)

    # 태그
    tags_raw = (
        _safe_inner_text(meta_frame, ".tag_list")
        or _safe_inner_text(meta_frame, ".TagList")
        or _safe_inner_text(meta_frame, ".tag_area")
    )
    tags = [t.strip().lstrip("#") for t in tags_raw.split("\n") if t.strip().startswith("#")]
    return {
        "view_count": view_count,
        "written_at": written_at,
        "author": author,
        "board": board,
        "like_count": like_count,
        "tags": tags,
    }


def _parse_article_comments(meta_frame, comments: list[dict]) -> None:
    comment_els = meta_frame.locator(".CommentItem, .comment_item").all()
    for el in comment_els:
        raw = el.inner_text(timeout=1000).strip()
        lines = [l.strip() for l in raw.splitlines() if l.strip()]  # noqa: E741
        # 첫 줄 = 닉네임, 마지막 날짜 줄, 나머지 = 본문
        comment_author = lines[0] if lines else ""
        cdate_m = re.search(r"(\d{4}\.\d{2}\.\d{2}\.?\s*\d{2}:\d{2})", raw)
        comment_date = cdate_m.group(1).strip() if cdate_m else ""
        # 닉네임·날짜·'답글쓰기' 제외한 본문
        body_lines = [
            l
            for l in lines[1:]  # noqa: E741
            if l not in {comment_author, comment_date, "답글쓰기"} and not re.match(r"\d{4}\.\d{2}\.\d{2}", l)
        ]
        comment_body = " ".join(body_lines).strip()
        comments.append(
            {
                "author": comment_author,
                "body": comment_body[:500],
                "written_at": comment_date,
            }
        )


class CafeArticleMixin:
    if TYPE_CHECKING:
        # 다른 믹스인의 메서드·속성(go, _page …)을 self(MRO)로 쓴다 — 정적 검사기에는 합쳐진 클래스가 보이지 않으므로 알려 준다(런타임 영향 없음).
        def __getattr__(self, name: str) -> Any: ...

    def cafe_liked_articles(self, cafe_url: str, max_posts: int = 30) -> list[dict]:
        """내가 좋아요한 게시글 목록.

        반환 list[dict]:
            article_id / title / author / date / href
        """
        club_id = self._get_club_id(cafe_url)
        if not club_id:
            return []

        url = f"https://cafe.naver.com/f-e/cafes/{club_id}/liked-articles"
        self.go(url)
        time.sleep(3)

        posts = self._extract_fe_article_list(max_posts=max_posts)
        return posts

    # ── 스크랩한 글 ──────────────────────────────────────────────────────────────

    def cafe_scrapped_articles(self, cafe_url: str, max_posts: int = 30) -> list[dict]:
        """내가 스크랩한 게시글 목록.

        반환 list[dict]:
            article_id / title / author / date / href
        """
        club_id = self._get_club_id(cafe_url)
        if not club_id:
            return []

        url = f"https://cafe.naver.com/f-e/cafes/{club_id}/scraps"
        self.go(url)
        time.sleep(3)

        return self._extract_fe_article_list(max_posts=max_posts)

    def _extract_fe_article_list(self, max_posts: int = 30) -> list[dict]:
        """현재 f-e 페이지에서 게시글 목록 추출 (공통 헬퍼)."""
        posts: list[dict] = []
        seen: set[str] = set()

        for frame in self._page.frames:
            if "about:blank" in (frame.url or ""):
                continue
            try:
                result = frame.evaluate(_js("extract_cafe_posts.js"))
                for p in result:
                    aid_m = re.search(r"articles/(\d+)|articleid=(\d+)", p.get("href", ""))
                    aid = (aid_m.group(1) or aid_m.group(2)) if aid_m else ""
                    if not aid or aid in seen:
                        continue
                    seen.add(aid)
                    p["article_id"] = aid
                    posts.append(p)
                if posts:
                    break
            except Exception:  # noqa: BLE001, S112
                continue

        return posts[:max_posts]

    def _wait_for_cafe_main(self, target_aid: str) -> None:
        """cafe_main 프레임이 대상 article_id를 포함할 때까지 최대 5초 대기."""
        if target_aid:
            for _ in range(10):
                _cafe_main = next(
                    (f for f in self._page.frames if f.name == "cafe_main" and target_aid in (f.url or "")),
                    None,
                )
                if _cafe_main:
                    break
                time.sleep(0.5)

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

        # 요청한 article_id 추출 (cafe_main 프레임 검증에 사용)
        _target_aid = _article_id_from_url(article_url)

        # cafe_main 프레임이 대상 article_id를 포함할 때까지 최대 5초 대기
        self._wait_for_cafe_main(_target_aid)

        # 아티클 관련 프레임 우선 탐색 (URL 경로 기준, 쿼리 파라미터 오탐 방지)
        frames = self._page.frames

        article_frames = [f for f in frames if _is_article_frame_for(f, _target_aid)]
        article_frame_ids = {id(f) for f in article_frames}  # 프레임 객체는 동일성으로 비교(= 이전 list `in` 과 같은 의미, O(1))
        other_frames = [f for f in frames if id(f) not in article_frame_ids]
        ordered = article_frames + other_frames

        # 본문이 있는 아티클 프레임(af) 탐색
        st: dict = {"title": "", "body": "", "af": None}
        for frame in ordered:
            if st["body"]:
                break
            try:
                _scan_frame_for_title_body(frame, id(frame) in article_frame_ids, st)
            except Exception:  # noqa: BLE001, S112
                continue

        title = st["title"]
        body = st["body"]
        af = st["af"]
        if not title:
            title = self._page.title()
        if not body:
            body = self.read()

        # ── 메타 정보 추출 (아티클 프레임 우선) ─────────────────────────────
        meta_frame = af or (article_frames[0] if article_frames else self._page)
        meta = _extract_article_meta(meta_frame)

        # ── 댓글 파싱 ────────────────────────────────────────────────────────
        comments: list[dict] = []
        with contextlib.suppress(Exception):
            _parse_article_comments(meta_frame, comments)

        return {
            "title": title,
            "url": article_url,
            "board": meta["board"],
            "author": meta["author"],
            "written_at": meta["written_at"],
            "view_count": meta["view_count"],
            "like_count": meta["like_count"],
            "comment_count": len(comments),
            "tags": meta["tags"],
            "body": body[:5000],
            "comments": comments,
            "attachments": self._extract_attachments_from_frames(
                search_frames=article_frames if article_frames else frames
            ),
        }

    def _extract_attachments_from_frames(self, search_frames: list) -> list[dict]:
        """주어진 프레임 목록에서 첨부파일 링크 추출 (내부 메서드)."""
        attachments: list[dict] = []
        seen_urls: set[str] = set()

        for frame in search_frames:
            try:
                _collect_frame_attachments(frame, seen_urls, attachments)
            except Exception:  # noqa: BLE001, S112
                continue

        # JS 방식 폴백: evaluate로 모든 a 태그 스캔
        if not attachments:
            _collect_js_attachments(search_frames, seen_urls, attachments)

        return attachments

    def extract_attachments(self, article_url: str) -> list[dict]:
        """게시글 URL에서 첨부파일 목록 추출 (페이지 이동 포함).

        반환 list[dict]:
            name  - 파일명 / 버튼 텍스트
            url   - 다운로드 URL
            size  - 파일 크기 (문자열, 없으면 "")
            ext   - 확장자 소문자
        """
        self.go(article_url)
        time.sleep(3)
        frames = self._page.frames

        def _is_article_frame(f) -> bool:
            url = f.url or ""
            if "about:blank" in url:
                return False
            path = url.split("?")[0]
            if "f-e/cafes" in path and f.name != "cafe_main":
                return False
            return any(kw in path for kw in ("ArticleRead", "articles/", "ca-fe/"))

        article_frames = [f for f in frames if _is_article_frame(f)]
        search_frames = article_frames if article_frames else frames
        return self._extract_attachments_from_frames(search_frames)

    # ── GraphQL BFF 직접 호출 ────────────────────────────────────────────────────

    def _fetch_graphql_bff(self, query: str, variables: dict, operation_name: str = "") -> dict:
        """bff.cafe.naver.com/graphql 을 브라우저 쿠키로 직접 호출.

        ca-fe SPA가 Apollo 쿼리를 실행하지 않는 문제를 우회하는 방식.
        반환: GraphQL 응답 dict (data / errors), 실패 시 {"data": None, "errors": [...]}
        """
        import requests

        try:
            cookies_raw = self._ctx.cookies()
            jar = requests.cookies.RequestsCookieJar()
            for c in cookies_raw:
                jar.set(c["name"], c["value"], domain=c.get("domain", ""), path=c.get("path", "/"))

            payload: dict = {"query": query, "variables": variables}
            if operation_name:
                payload["operationName"] = operation_name

            headers = {
                "Content-Type": "application/json",
                "Referer": "https://cafe.naver.com/",
                "Origin": "https://cafe.naver.com",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            }
            resp = requests.post(
                "https://bff.cafe.naver.com/graphql",
                json=payload,
                cookies=jar,
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:  # noqa: BLE001 - 네이버 카페 게시글 읽기 전용 파싱(본문/첨부파일 추출) — 실패는 안전한 기본값(빈 값/False)으로 폴백, 쓰기·결제 없음(2026-09-28 검토)
            return {"data": None, "errors": [{"message": str(e)}]}

    # ── 앨범 (사진 게시글, GraphQL BFF) ──────────────────────────────────────────

    _GQL_PHOTO_ARTICLES = """
    query CafePhotoArticles($cafeId: String!, $menuId: String, $page: Int, $perPage: Int) {
      cafePhotoArticles(cafeId: $cafeId, menuId: $menuId, page: $page, perPage: $perPage) {
        totalCount
        items {
          articleId
          subject
          writerId
          writerNickname
          writeDate
          readCount
          commentCount
          likeCount
          thumbnail { url width height }
        }
      }
    }
    """
