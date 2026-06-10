"""gonobi 블로그 HTTP 수집기 (CDP 없이 requests 사용, L5 Site Module).

수집 대상: https://blog.naver.com/gonobi
- 카테고리 목록 → 포스트 목록 → 포스트 본문 + 이미지 URL
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BLOG_ID = "gonobi"
BASE_URL = "https://blog.naver.com"
POST_LIST_URL = f"{BASE_URL}/PostList.naver"
POST_VIEW_URL = f"{BASE_URL}/PostView.naver"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": f"{BASE_URL}/{BLOG_ID}",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

CATEGORIES: list[tuple[str, str]] = [
    ("블로그", "24"),
    ("라인/간접/T5", "21"),
    ("마그네틱/레일", "22"),
    ("매입/스포트", "11"),
    ("엠케이통상 소식", "13"),
    ("공지사항", "18"),
    ("★시공사례", "19"),
    ("제품소개", "17"),
    ("IoT 시리즈", "34"),
    ("홈조명", "14"),
    ("욕실/환풍기", "35"),
    ("배선기구", "29"),
    ("시계/거울", "31"),
    ("펜던트", "8"),
    ("센서/직부", "25"),
    ("벽등", "16"),
    ("스탠드", "10"),
    ("산업조명", "27"),
    ("소방기구", "30"),
    ("외벽등/외부등", "32"),
    ("램프", "12"),
    ("기타", "36"),
]


@dataclass
class GonobiPost:
    log_no: str
    category_no: str
    category_name: str
    url: str
    title: str = ""
    body: str = ""
    images: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    written_at: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def _fetch_post_list(session: requests.Session, cat_no: str, page: int = 1) -> list[str]:
    """카테고리 페이지에서 logNo 목록 반환."""
    resp = session.get(
        POST_LIST_URL,
        params={"blogId": BLOG_ID, "categoryNo": cat_no, "currentPage": page},
        timeout=10,
    )
    if resp.status_code != 200:
        return []
    log_nos = list(dict.fromkeys(re.findall(rf"{BLOG_ID}[/\\](\d{{10,}})", resp.text)))
    return log_nos


def _fetch_post_detail(session: requests.Session, log_no: str) -> dict:
    """포스트 본문 + 이미지 URL 수집."""
    # PostView.naver 직접 접근이 본문을 가장 안정적으로 반환
    url = f"{BASE_URL}/PostView.naver?blogId={BLOG_ID}&logNo={log_no}"
    try:
        resp = session.get(url, timeout=10)
        if resp.status_code != 200:
            return {}
    except Exception as e:
        logger.warning("포스트 수집 실패 %s: %s", log_no, e)
        return {}

    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    # 제목
    title = ""
    for sel in [".se-title-text", ".pcol1", "h3.title"]:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            title = el.get_text(strip=True)
            break

    # 본문 텍스트
    body = ""
    for sel in [".se-main-container", ".post-view", "#postViewArea", ".post_ct"]:
        el = soup.select_one(sel)
        if el:
            body = el.get_text(separator="\n", strip=True)[:3000]
            break

    # 이미지
    images: list[str] = []
    for img in soup.select("img[src]"):
        src = img.get("src", "")
        if "postfiles" in src or "blogfiles" in src or "mblogthumb" in src:
            images.append(src)

    # 태그
    tags = [t.get_text(strip=True) for t in soup.select(".post_tag a, .se-hashtag")]

    # 작성일
    written_at = ""
    date_el = soup.select_one(".se_publishDate, .date, .se-date")
    if date_el:
        written_at = date_el.get_text(strip=True)

    return {"title": title, "body": body, "images": images, "tags": tags, "written_at": written_at}


def iter_all_posts(
    delay: float = 0.5,
    categories: list[tuple[str, str]] | None = None,
    progress_cb=None,
) -> Iterator[GonobiPost]:
    """전체 카테고리 포스트를 순회하며 yield."""
    session = _session()
    cats = categories or CATEGORIES
    total_cats = len(cats)

    for cat_idx, (cat_name, cat_no) in enumerate(cats):
        page = 1
        seen: set[str] = set()

        while True:
            log_nos = _fetch_post_list(session, cat_no, page)
            new = [ln for ln in log_nos if ln not in seen]
            if not new:
                break
            seen.update(new)

            for log_no in new:
                detail = _fetch_post_detail(session, log_no)
                post = GonobiPost(
                    log_no=log_no,
                    category_no=cat_no,
                    category_name=cat_name,
                    url=f"{BASE_URL}/{BLOG_ID}/{log_no}",
                    **{
                        k: detail.get(k, v)
                        for k, v in [
                            ("title", ""),
                            ("body", ""),
                            ("images", []),
                            ("tags", []),
                            ("written_at", ""),
                        ]
                    },
                )
                if progress_cb:
                    progress_cb(cat_idx + 1, total_cats, cat_name, log_no, post.title)
                yield post
                time.sleep(delay)

            # 다음 페이지 존재 여부
            if (
                f"currentPage={page + 1}"
                not in session.get(
                    POST_LIST_URL,
                    params={"blogId": BLOG_ID, "categoryNo": cat_no, "currentPage": page + 1},
                    timeout=10,
                ).text
            ):
                break
            page += 1
            if page > 20:
                break
