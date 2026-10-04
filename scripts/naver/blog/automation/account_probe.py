"""로그인된 네이버 계정 식별 — 블로그 관리 주소의 공개 alias 를 읽는다(읽기 전용).

기준서: docs/specs/2026-10-01_electron_naver_auto_login.md, docs/specs/2026-09-30_blog_auto_writing_automation.md §4

`admin.blog.naver.com/{alias}/` 의 alias 는 로그인 ID 가 아니라 **공개 주소**다. 조명 계정 skyjwshin 은 공개 주소를
`beautiful-light`(하이픈 포함)로 바꿨다 — 2026-08-24 에 정규식이 하이픈을 못 잡고 로그인 ID 와 비교해 정상 로그인을
로그아웃으로 오판한 사고가 있었다(publish.connect_and_ensure_login 주석). 그래서 alias 는 accounts 의 `public_alias` 와 비교한다.

이 모듈은 로그아웃·쿠키 삭제·로그인 시도를 하지 않는다. 블로그 홈으로 이동해 링크를 읽을 뿐이다
(호출자가 전용 새 탭을 넘겨야 사용자의 작업 탭이 이동하지 않는다).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from scripts.naver.blog.accounts import BLOG_ACCOUNTS

BLOG_HOME_URL = "https://section.blog.naver.com/BlogHome.naver"
_ADMIN_HREF = re.compile(r"admin\.blog\.naver\.com/([A-Za-z0-9_-]+)/")

_ALIAS_JS = """() => {
    const a = document.querySelector('a[href*="admin.blog.naver.com/"]');
    return a ? a.href : null;
}"""


def extract_alias(href: str | None) -> str | None:
    """`https://admin.blog.naver.com/beautiful-light/...` → `beautiful-light`. 하이픈·밑줄 포함, 없으면 None."""
    match = _ADMIN_HREF.search(href or "")
    return match.group(1) if match else None


def alias_to_blog_id(alias: str | None, accounts: Mapping[str, Mapping[str, Any]] = BLOG_ACCOUNTS) -> str | None:
    """공개 alias(또는 로그인 ID) → 등록된 블로그 계정 ID. 등록되지 않은 값이면 None."""
    if not alias:
        return None
    for blog_id, account in accounts.items():
        if alias in (account.get("public_alias"), blog_id):
            return blog_id
    return None


def read_alias(page: Any, *, timeout_ms: int = 15000) -> str | None:
    """블로그 홈으로 이동해 관리 주소 링크에서 alias 를 읽는다. 링크가 없으면(로그아웃·블로그 없음) None."""
    page.goto(BLOG_HOME_URL, wait_until="domcontentloaded", timeout=timeout_ms)
    page.wait_for_timeout(1500)
    return extract_alias(page.evaluate(_ALIAS_JS))
