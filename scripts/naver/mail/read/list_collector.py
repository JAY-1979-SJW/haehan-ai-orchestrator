"""Naver Mail v2 받은편지함 목록 수집 (페이지네이션 전수).

순수 파서(parse_list_payload) 와 CDP 호출(collect_all_pages) 분리 → 테스트 가능.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from scripts.naver.mail.read import cdp

LIST_EXPR = r"""
JSON.stringify((function(){
  const rows = Array.from(document.querySelectorAll('li.mail_item'));
  const out = [];
  for (const r of rows) {
    const cls = (r.className || '');
    const m = cls.match(/mail-(\d+)/);
    const sn = m ? m[1] : '';
    const read_btn = r.querySelector('.toggle_read_wrap label[role="button"]');
    const aria = read_btn ? (read_btn.getAttribute('aria-pressed')||'false') : 'false';
    const is_unread = (aria !== 'true');
    const sb = r.querySelector('.button_sender');
    const sender_name = sb ? (sb.innerText||'').trim() : '';
    const sender_full = sb ? (sb.getAttribute('title')||'').trim() : '';
    const title_el = r.querySelector('.mail_title .text');
    const subject = title_el ? (title_el.innerText||'').trim() : '';
    const date_el = r.querySelector('.mail_date');
    const size_el = r.querySelector('.mail_volume');
    const link_el = r.querySelector('.mail_title_link');
    const href = link_el ? link_el.getAttribute('href') : '';
    out.push({
      sn, is_unread,
      sender_name: sender_name.slice(0,120),
      sender_full: sender_full.slice(0,200),
      subject: subject.slice(0,300),
      time_txt: date_el ? (date_el.innerText||'').trim().slice(0,40) : '',
      size_txt: size_el ? (size_el.innerText||'').trim().slice(0,20) : '',
      href,
    });
  }
  return {
    href: location.href, title: document.title,
    count: out.length, items: out,
  };
})())
"""


PAGES_EXPR = r"""
JSON.stringify((function(){
  const btns = Array.from(document.querySelectorAll('.pagination .page_list .page .page_link'));
  return btns.map(b => (b.innerText||'').trim().replace(/[^0-9]/g,'')).filter(Boolean);
})())
"""


def _click_page_expr(page_num: str) -> str:
    pn = str(page_num)
    return (
        "(function(){"
        "var btns=Array.from(document.querySelectorAll('.pagination .page_list .page .page_link'));"
        "for(var i=0;i<btns.length;i++){"
        "if((btns[i].innerText||'').trim().replace(/[^0-9]/g,'')==='" + pn + "'){btns[i].click();return true;}}"
        "var nx=document.querySelector('.pagination .page_navigation_next, .pagination .next');"
        "if(nx){nx.click();return 'next';}return false;})()"
    )


@dataclass
class ListItem:
    sn: str
    is_unread: bool
    sender_name: str
    sender_full: str
    subject: str
    time_txt: str
    size_txt: str
    href: str


def parse_list_payload(payload: dict) -> list[ListItem]:
    out = []
    for it in (payload or {}).get("items", []):
        out.append(
            ListItem(
                sn=it.get("sn", "") or "",
                is_unread=bool(it.get("is_unread")),
                sender_name=it.get("sender_name", "") or "",
                sender_full=it.get("sender_full", "") or "",
                subject=it.get("subject", "") or "",
                time_txt=it.get("time_txt", "") or "",
                size_txt=it.get("size_txt", "") or "",
                href=it.get("href", "") or "",
            )
        )
    return out


def _merge_items(merged: dict[str, ListItem], items) -> None:
    for it in items:
        key = it.sn or f"{it.subject}|{it.sender_name}"
        if key and key not in merged:
            merged[key] = it


def collect_all_pages(target_id: str, *, max_pages: int = 20, max_items: int = 200) -> tuple[list[ListItem], dict]:
    """현재 페이지(받은편지함 등) 의 전체 페이지 순회."""
    merged: dict[str, ListItem] = {}

    def _merge(items):
        _merge_items(merged, items)

    # page 1 수집
    cdp.wait_dom(target_id, "document.querySelector('li.mail_item')", timeout=15.0)
    first = cdp.evaluate(target_id, LIST_EXPR, timeout=6.0)
    href = (first or {}).get("href", "")
    title = (first or {}).get("title", "")
    _merge(parse_list_payload(first or {}))

    pages = cdp.evaluate(target_id, PAGES_EXPR, timeout=4.0) or []
    if not isinstance(pages, list):
        pages = []

    visited = {"1"}
    candidates = pages + [str(i) for i in range(2, max_pages + 1)]
    consecutive_empty = 0
    for pg in candidates:
        if pg in visited:
            continue
        visited.add(pg)
        clicked = cdp.evaluate(target_id, _click_page_expr(pg), timeout=4.0)
        if not clicked:
            consecutive_empty += 1
            if consecutive_empty >= 2:
                break
            continue
        time.sleep(1.2)
        cdp.wait_dom(target_id, "document.querySelector('li.mail_item')", timeout=8.0)
        more = cdp.evaluate(target_id, LIST_EXPR, timeout=6.0)
        before = len(merged)
        _merge(parse_list_payload(more or {}))
        added = len(merged) - before
        if added == 0:
            consecutive_empty += 1
            if consecutive_empty >= 2:
                break
        else:
            consecutive_empty = 0
        if len(merged) >= max_items:
            break

    return list(merged.values()), {"href": href, "title": title}
