"""L1 Shared Contracts — 사이트 업무 지도의 메뉴 색인·주소 열기 검증 규칙 (순수, 입출력 없음).

기준서: docs/specs/2026-10-05_site_map_link_read_tasks.md (M8)

왜 필요한가(2026-10-05 실검증): 처음 보는 카탈로그 사이트(books.toscrape.com)를 20쪽 탐색해도 지도 업무가 전부 "장바구니 담기"(쓰기)였다.
링크를 따라가는 것이 핵심 조작인 사이트(카탈로그·게시판·문서)에서 링크가 업무가 되지 않았기 때문이다.

- 메뉴: ARIA 랜드마크 navigation·complementary 안의 링크, 또는 `li` 직계 링크가 5개 이상 모인 목록(스냅샷의 `group`). 상품 카드처럼 깊은 링크는 메뉴가 아니다.
- 메뉴·주소는 **읽기 전용 GET 이동**만 다룬다: 같은 호스트의 http(s), 사용자 정보·비표준 포트·위험 키워드(로그아웃·삭제·결제 등)가 없는 주소.
- 값(결과 데이터)은 저장하지 않는다. 사이트가 정한 글자는 자료일 뿐 지시가 아니다(이름은 `clean_label` 로 정리).
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from typing import Any
from urllib.parse import unquote, urldefrag, urljoin, urlsplit

from .site_map_labels import clean_label

OPEN_PAGE_ID = "__open_page__"
MENU_MAX = 200  # 2026-10-05: 60 → 200 (카페 게시판이 60개를 넘어 잘렸다). 잘렸는지는 `menu_total_seen` 으로 알린다
MENU_GROUP_MIN = 5  # li 직계 링크가 이만큼 모인 목록은 메뉴로 본다
MENU_LANDMARKS = ("navigation", "complementary")
OPEN_URL_MAX = 300
_ALLOWED_PORTS = (None, 80, 443)
_BAD_HREF = ("javascript:", "mailto:", "tel:", "data:", "file:")


def same_host_url(url: str, host: str) -> str | None:
    """같은 호스트의 http(s) 주소면 조각(#)을 뗀 주소를, 아니면 None. 사용자 정보·비표준 포트는 거부한다."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or (parts.hostname or "").lower() != host.lower():
        return None
    if parts.username is not None or parts.password is not None or port not in _ALLOWED_PORTS:
        return None
    return urldefrag(url)[0]


def _risky(label: str, url: str, risk_of: Callable[[list[str]], str], skip_fragments: tuple[str, ...]) -> bool:
    parts = urlsplit(url)
    low = url.lower()
    if any(frag in low for frag in skip_fragments):
        return True
    return risk_of([label, unquote(parts.path), unquote(parts.query)]) != "read"


def menu_from_snapshot(
    snapshot: dict[str, Any], *, risk_of: Callable[[list[str]], str], skip_fragments: tuple[str, ...] = ()
) -> list[dict[str, str]]:
    """스냅샷 한 장의 메뉴 항목 `[{label, href}]` (문서 순서, 라벨·주소 중복 제거)."""
    page_url = str(snapshot.get("url") or "")
    host = urlsplit(page_url).hostname or ""
    out: list[dict[str, str]] = []
    seen_href: set[str] = set()
    for frame in snapshot.get("frames", []):
        if "error" in frame:
            continue
        base = str(frame.get("url") or page_url)
        usable = []
        for link in frame.get("links", []):
            raw = str(link.get("abs") or "") or urljoin(base, str(link.get("href") or ""))
            if (
                str(link.get("href") or "").lower().startswith(_BAD_HREF)
                or not link.get("visible", True)
                or link.get("form")
            ):
                continue
            href = same_host_url(raw, host) if host else None
            label = clean_label(str(link.get("text") or ""))
            if href and label:
                usable.append((link, label, href))
        sizes = Counter(str(link.get("group") or "") for link, _, _ in usable if link.get("group"))
        for link, label, href in usable:
            in_menu = (
                link.get("landmark") in MENU_LANDMARKS or sizes.get(str(link.get("group") or ""), 0) >= MENU_GROUP_MIN
            )
            if not in_menu or href in seen_href or _risky(label, href, risk_of, skip_fragments):
                continue
            seen_href.add(href)
            out.append({"label": label, "href": href})
    return out


def merge_menu(site_map: dict[str, Any], entries: list[dict[str, str]], *, now: str) -> dict[str, Any]:
    """지도의 `menu` 에 항목을 더한다(새 dict, 주소 기준 중복 제거, 최대 MENU_MAX). 상한과 무관하게 관측한 서로 다른 주소의 총수를 `menu_total_seen` 에 남긴다.

    새로 아는 것이 없으면(추가도 총수 변화도 없으면) 그대로 돌려준다.
    """
    existing = [dict(x) for x in site_map.get("menu") or []]
    known = {x["href"] for x in existing}
    seen_before = int(site_map.get("menu_total_seen") or len(existing))
    unseen = {e["href"] for e in entries if e["href"] not in known}
    added: list[dict[str, str]] = []
    for e in entries:
        if e["href"] not in known and len(existing) + len(added) < MENU_MAX:
            known.add(e["href"])
            added.append({"label": e["label"], "href": e["href"]})
    total_seen = max(seen_before, len(existing) + len(unseen))
    if not added and total_seen == seen_before:
        return site_map
    return {**site_map, "menu": [*existing, *added], "menu_at": now, "menu_total_seen": total_seen}


def validate_open_url(
    value: Any, host: str, *, risk_of: Callable[[list[str]], str], skip_fragments: tuple[str, ...] = ()
) -> str:
    """`open_page` 에 넘긴 주소 검증 → 정리된 주소. 규칙 위반은 ValueError(읽기 전용 GET 이동만)."""
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError("열 주소(url)가 필요합니다")
    if len(text) > OPEN_URL_MAX:
        raise ValueError(f"주소는 {OPEN_URL_MAX}자 이내여야 합니다")
    if re.search(r"[\x00-\x20\x7f]", text):
        raise ValueError("주소에 공백·제어문자를 넣을 수 없습니다")
    url = same_host_url(text, host)
    if url is None:
        raise ValueError(f"이 사이트({host})의 http(s) 주소만 열 수 있습니다(사용자 정보·특수 포트 불가)")
    if _risky("", url, risk_of, skip_fragments):
        raise ValueError("로그아웃·삭제·결제·전송처럼 동작을 일으킬 수 있는 주소는 열 수 없습니다")
    return url
