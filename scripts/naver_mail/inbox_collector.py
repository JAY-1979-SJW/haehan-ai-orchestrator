"""받은편지함 P0 수집기 — 전체 페이지네이션 + 안읽은 필터 + 모드별 동작.

설계:
  - Actions 프로토콜로 CDP I/O 추상화 (테스트에서 fake 주입 가능)
  - 페이지네이션 종료 조건:
      a) "다음" 버튼 없음 + 페이지 후보 더 없음
      b) 같은 sn 만 반복 (added=0) 2회 연속
      c) max_pages / max_items 도달 → WARN_LIMIT_REACHED
  - sn 중복 제거 + duplicate 카운트 기록
  - 안읽은 필터: '안읽은 메일' 버튼 클릭 (모드 UNREAD_ONLY)
  - FULL_READ 는 본 모듈에선 plan만, 실행은 caller (CDP 호출 주입)

기존 scripts/naver/mail_read/list_collector.py 의 LIST_EXPR / PAGES_EXPR 을 재사용 (코드 보존).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Protocol

from scripts.naver.mail_read import list_collector as base_lc
from scripts.naver.mail_read.list_collector import LIST_EXPR, PAGES_EXPR

from . import read_state_guard as rsg
from . import time_parser as tp


# ── 모드/제한 ────────────────────────────────────────────────────────

DEFAULT_MAX_PAGES = 200
DEFAULT_MAX_ITEMS = 5000


# ── Actions 추상화 (테스트에서 fake) ─────────────────────────────────

class Actions(Protocol):
    def evaluate(self, expr: str) -> Any: ...
    def click(self, selector_or_expr: str) -> Any: ...
    def navigate(self, url: str) -> None: ...
    def wait_dom(self, expr_truthy: str, timeout_s: float = 8.0) -> bool: ...


# ── 결과 모델 ────────────────────────────────────────────────────────

@dataclass
class CollectedItem:
    folder_id: str
    folder_name: str
    sn: str
    subject_masked: str
    sender_masked: str
    display_time: str
    parsed_at_iso: str
    parse_warning: str
    read_state: str  # "UNREAD" / "READ"
    has_attachment: bool
    collect_mode: str
    size_txt: str = ""
    href: str = ""


@dataclass
class CollectionResult:
    folder_id: str
    folder_name: str
    mode: str
    items: list[CollectedItem] = field(default_factory=list)
    total_seen: int = 0          # 페이지에서 본 row 합 (중복 포함)
    dup_count: int = 0
    last_page_reached: bool = False
    warn_limit_reached: bool = False
    unread_count_ui: int = -1    # 폴더 라벨에서 파싱한 안읽은 수
    collected_unread: int = 0
    duplicate_sns: list[str] = field(default_factory=list)
    pages_visited: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ── PII 마스킹 (mail_read.body_reader.redact 재사용) ─────────────────

from scripts.naver.mail_read.body_reader import redact as _redact


def _mask_subject(s: str) -> str:
    # 제목은 일반적으로 노출 가능하나 안전을 위해 redact() 통과
    return _redact(s)[:300]


def _mask_sender(s: str) -> str:
    return _redact(s)[:200]


# ── 폴더명 / 안읽은 카운트 파싱 ─────────────────────────────────────

import re

_TITLE_UNREAD_RE = re.compile(r"\(\s*(\d+)\s*\)")


def parse_folder_meta(payload: dict) -> tuple[str, int]:
    title = (payload or {}).get("title", "") or ""
    href = (payload or {}).get("href", "") or ""
    # folder name 은 title 의 "받은메일함(N) : 네이버 메일" 패턴
    name = title.split(":")[0].strip() if ":" in title else title
    name = re.sub(r"\s*\(\s*\d+\s*\)\s*$", "", name).strip()
    m = _TITLE_UNREAD_RE.search(title)
    unread_cnt = int(m.group(1)) if m else -1
    return name, unread_cnt


def folder_id_from_url(url: str) -> str:
    m = re.search(r"/v2/folders/([^/]+)/", url or "")
    return m.group(1) if m else ""


# ── 안읽은 필터 적용 ────────────────────────────────────────────────

UNREAD_FILTER_CLICK_EXPR = r"""
(function(){
  // 필터 메뉴 열기 후 '안읽은 메일' 항목 클릭
  // Naver Mail v2 — '안읽은 메일' 텍스트의 버튼/링크 후보
  const candidates = Array.from(document.querySelectorAll('button, a, li'));
  const unread = candidates.find(el => {
    const t = (el.innerText||'').trim();
    return t === '안읽은 메일' || t.startsWith('안읽은 메일');
  });
  if (unread) { unread.click(); return true; }
  return false;
})()
"""


def apply_unread_filter(actions: Actions, timeout_s: float = 6.0) -> bool:
    """안읽은 필터 클릭 시도. 적용되면 페이지 1로 가도록 잠시 대기."""
    rsg.assert_action_allowed("filter_unread")  # whitelisted (not in FORBIDDEN)
    ok = actions.evaluate(UNREAD_FILTER_CLICK_EXPR)
    if not ok:
        # 메뉴가 닫혀있을 수 있음 — '보기' 또는 필터 메뉴 토글 후 재시도 (best-effort)
        actions.evaluate(
            "(function(){var b=document.querySelector("
            "'.button_filter_unread, [class*=\"filter_unread\"], .filter_btn');"
            "if(b){b.click();return true;}return false;})()"
        )
        time.sleep(0.6)
        ok = actions.evaluate(UNREAD_FILTER_CLICK_EXPR)
    actions.wait_dom("document.querySelector('li.mail_item')", timeout_s=timeout_s)
    return bool(ok)


# ── 페이지네이션 수집 ───────────────────────────────────────────────

def _click_page_expr(pg: str) -> str:
    return (
        "(function(){"
        "var btns=Array.from(document.querySelectorAll('.pagination .page_list .page .page_link'));"
        f"for(var i=0;i<btns.length;i++){{if((btns[i].innerText||'').trim().replace(/[^0-9]/g,'')==='{pg}')"
        "{btns[i].click();return true;}}"
        "var nx=document.querySelector('.pagination .page_navigation_next, .pagination .next');"
        "if(nx){nx.click();return 'next';}return false;})()"
    )


def collect_inbox(
    actions: Actions,
    *,
    mode: str = rsg.MODE_LIST_ONLY,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_items: int = DEFAULT_MAX_ITEMS,
    now_for_time: Any = None,  # datetime injection for tests
) -> CollectionResult:
    rsg.assert_mode_valid(mode)

    # UNREAD_ONLY: 필터 적용 후 수집
    if mode == rsg.MODE_UNREAD_ONLY:
        apply_unread_filter(actions)
        time.sleep(0.5)

    # page 1 evaluate
    actions.wait_dom("document.querySelector('li.mail_item')", timeout_s=12.0)
    first = actions.evaluate(LIST_EXPR) or {}
    folder_name, unread_ui = parse_folder_meta(first)
    folder_id = folder_id_from_url(first.get("href", ""))

    result = CollectionResult(
        folder_id=folder_id,
        folder_name=folder_name,
        mode=mode,
        unread_count_ui=unread_ui,
    )
    seen_sns: dict[str, CollectedItem] = {}

    def _absorb(payload: dict, page_label: str) -> int:
        added = 0
        for raw in (payload or {}).get("items", []) or []:
            result.total_seen += 1
            sn = (raw.get("sn") or "").strip()
            if not sn:
                # sn 없는 row 는 fallback key
                fkey = f"NOSN|{raw.get('subject','')[:60]}|{raw.get('sender_name','')[:40]}"
                if fkey in seen_sns:
                    result.dup_count += 1
                    continue
                sn_to_use = fkey
            else:
                if sn in seen_sns:
                    result.dup_count += 1
                    if sn not in result.duplicate_sns:
                        result.duplicate_sns.append(sn)
                    continue
                sn_to_use = sn
            pt = tp.parse_korean_time(raw.get("time_txt", "") or "", now=now_for_time)
            it = CollectedItem(
                folder_id=folder_id,
                folder_name=folder_name,
                sn=sn,
                subject_masked=_mask_subject(raw.get("subject", "") or ""),
                sender_masked=_mask_sender(
                    (raw.get("sender_full") or raw.get("sender_name") or "")
                ),
                display_time=(raw.get("time_txt") or "").strip(),
                parsed_at_iso=pt.iso,
                parse_warning=pt.warning,
                read_state="UNREAD" if raw.get("is_unread") else "READ",
                has_attachment=False,  # 행에 첨부 표시는 별도 — best-effort 후속
                collect_mode=mode,
                size_txt=(raw.get("size_txt") or "").strip(),
                href=(raw.get("href") or "").strip(),
            )
            seen_sns[sn_to_use] = it
            added += 1
            if len(seen_sns) >= max_items:
                result.warn_limit_reached = True
                result.notes.append(f"max_items={max_items}_도달")
                break
        return added

    _absorb(first, "1")
    result.pages_visited.append("1")

    pages = actions.evaluate(PAGES_EXPR) or []
    if not isinstance(pages, list):
        pages = []

    visited = {"1"}
    consecutive_empty = 0
    candidates = pages + [str(i) for i in range(2, max_pages + 1)]
    for pg in candidates:
        if result.warn_limit_reached:
            break
        if pg in visited:
            continue
        visited.add(pg)
        if len(result.pages_visited) >= max_pages:
            result.warn_limit_reached = True
            result.notes.append(f"max_pages={max_pages}_도달")
            break
        clicked = actions.evaluate(_click_page_expr(pg))
        if not clicked:
            consecutive_empty += 1
            if consecutive_empty >= 2:
                result.last_page_reached = True
                break
            continue
        time.sleep(1.0)
        actions.wait_dom("document.querySelector('li.mail_item')", timeout_s=8.0)
        more = actions.evaluate(LIST_EXPR) or {}
        added = _absorb(more, pg)
        result.pages_visited.append(pg)
        if added == 0:
            consecutive_empty += 1
            if consecutive_empty >= 2:
                result.last_page_reached = True
                break
        else:
            consecutive_empty = 0

    # 종료 — collected_unread 계산
    result.items = list(seen_sns.values())
    result.collected_unread = sum(1 for i in result.items if i.read_state == "UNREAD")
    if not result.warn_limit_reached and not result.last_page_reached:
        # 자연 종료 — 명시적 last 표시
        result.last_page_reached = True
        result.notes.append("자연_종료_(pages_exhausted)")
    return result


# ── JSON schema 검증 ────────────────────────────────────────────────

REQUIRED_FIELDS = ("folder_id", "folder_name", "sn", "subject_masked",
                   "sender_masked", "display_time", "parsed_at_iso",
                   "read_state", "has_attachment", "collect_mode")


def validate_item_schema(d: dict) -> list[str]:
    missing = [k for k in REQUIRED_FIELDS if k not in d]
    return missing


def result_to_dict(r: CollectionResult) -> dict:
    return {
        "folder_id": r.folder_id,
        "folder_name": r.folder_name,
        "mode": r.mode,
        "items": [asdict(i) for i in r.items],
        "total_seen": r.total_seen,
        "dup_count": r.dup_count,
        "last_page_reached": r.last_page_reached,
        "warn_limit_reached": r.warn_limit_reached,
        "unread_count_ui": r.unread_count_ui,
        "collected_unread": r.collected_unread,
        "duplicate_sns": r.duplicate_sns,
        "pages_visited": r.pages_visited,
        "notes": r.notes,
    }
