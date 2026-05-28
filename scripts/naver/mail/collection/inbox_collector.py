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

from scripts.naver.mail.processing import read_state_guard as rsg
from scripts.naver.mail.utilities import time_parser as tp


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
    filter_applied: bool = False
    filter_evidence: dict = field(default_factory=dict)
    mismatch_reason: str = ""
    # PAGINATION_DEPTH_01 추가:
    pagination_strategy_used: str = ""   # "url_page" | "page_button" | "next_arrow" | "mixed"
    page_records: list[dict] = field(default_factory=list)
    # 각 page_record: {idx, url, item_count, unread_count, sn_hash, next_state}
    last_page_evidence: list[str] = field(default_factory=list)
    # 가능 값: "next_disabled" | "no_new_sn" | "url_page_no_change" |
    #          "scroll_no_more" | "dom_last_marker"
    ui_count_scope_evidence: dict = field(default_factory=dict)
    # {inbox_unread, total_aggregate, smart_folder_breakdown, source}


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

# ── 안읽은 필터 — 2단계 (드롭다운) + 직접 링크 fallback ─────────────

UNREAD_DIRECT_LINK_EXPR = r"""
(function(){
  // 1차: 받은편지함 내부 직접 링크 (a.unread_mail_link / a.unread_mail)
  var a = document.querySelector('a.unread_mail_link, a.unread_mail');
  if (a && a.offsetParent !== null) { a.click(); return 'direct_link'; }
  return false;
})()
"""

UNREAD_DROPDOWN_OPEN_EXPR = r"""
(function(){
  var btn = document.querySelector('.button_task_wrap.button_filter, .button_filter');
  if (!btn) return false;
  btn.click();
  return true;
})()
"""

UNREAD_DROPDOWN_CLICK_EXPR = r"""
(function(){
  // 드롭다운이 열린 상태에서 '안읽은 메일' context 아이템 클릭
  var items = Array.from(document.querySelectorAll(
    '.layer_context.layer_list_filter button.button_context_item, '
    + '.layer_context button.button_context_item, '
    + '.layer_list_filter li.context_item, '
    + '.layer_list_filter button'
  ));
  for (var i = 0; i < items.length; i++) {
    var t = (items[i].innerText || '').trim();
    if (t === '안읽은 메일') { items[i].click(); return 'dropdown_item'; }
  }
  return false;
})()
"""

# 필터 적용 marker — '안읽은 메일' 토스트/선택됨 표시 확인용
FILTER_EVIDENCE_EXPR = r"""
JSON.stringify((function(){
  var sel = document.querySelector('.layer_context.layer_list_filter .selected, '
    + '.lnb_filtered_mailbox .selected, .button_filter[aria-pressed="true"]');
  var summary = document.querySelector('.mail_toolbar_summary');
  var summary_txt = summary ? (summary.innerText||'').replace(/\s+/g,' ').slice(0,200) : '';
  return {
    has_selected_marker: !!sel,
    selected_text: sel ? (sel.innerText||'').trim().slice(0,80) : '',
    summary_text: summary_txt,
    url: location.href,
    title: document.title,
    li_count: document.querySelectorAll('li.mail_item').length,
  };
})())
"""


def apply_unread_filter(actions: Actions, *, timeout_s: float = 6.0
                        ) -> tuple[bool, dict]:
    """안읽은 필터 적용 — 직접 링크 우선, 실패 시 드롭다운 2-step.

    Returns:
        (ok, evidence) — evidence 는 적용 전후 DOM marker / li count / url / summary
    """
    rsg.assert_action_allowed("filter_unread")

    pre = actions.evaluate(FILTER_EVIDENCE_EXPR) or {}
    method = ""
    # 1) 직접 링크
    res = actions.evaluate(UNREAD_DIRECT_LINK_EXPR)
    if res:
        method = str(res)
    else:
        # 2) 드롭다운 2-step
        open_ok = actions.evaluate(UNREAD_DROPDOWN_OPEN_EXPR)
        if open_ok:
            time.sleep(0.1)
            click_ok = actions.evaluate(UNREAD_DROPDOWN_CLICK_EXPR)
            if click_ok:
                method = str(click_ok)
    time.sleep(0.2)
    actions.wait_dom("document.querySelector('li.mail_item')", timeout_s=timeout_s)
    post = actions.evaluate(FILTER_EVIDENCE_EXPR) or {}
    evidence = {
        "method": method,
        "pre": pre,
        "post": post,
        "li_count_changed": (
            isinstance(pre, dict) and isinstance(post, dict)
            and pre.get("li_count") != post.get("li_count")
        ),
        "url_changed": (
            isinstance(pre, dict) and isinstance(post, dict)
            and pre.get("url") != post.get("url")
        ),
    }
    return (bool(method), evidence)


# ── 다음 페이지 상태 / lnb breakdown ─────────────────────────────────

NEXT_STATE_EXPR = r"""
JSON.stringify((function(){
  var nx = document.querySelector(
    '.pagination .button_next, .pagination .page_navigation_next, '
    + '.pagination .next, button.button_next');
  if (!nx) return {next_present: false, next_disabled: true,
                   selected_page: ''};
  var dis = !!nx.disabled || nx.getAttribute('aria-disabled')==='true'
            || nx.classList.contains('disabled');
  var sel = document.querySelector('.pagination .page.selected .page_link');
  var sel_pg = sel ? (sel.innerText||'').trim().replace(/[^0-9]/g,'') : '';
  var btns = Array.from(document.querySelectorAll(
    '.pagination .page_list .page .page_link'))
    .map(b=>(b.innerText||'').trim().replace(/[^0-9]/g,''))
    .filter(Boolean);
  return {next_present: true, next_disabled: dis,
          selected_page: sel_pg, visible_page_buttons: btns};
})())
"""

# Naver Mail lnb 의 폴더별 unread count 분해
LNB_UNREAD_BREAKDOWN_EXPR = r"""
JSON.stringify((function(){
  var items = Array.from(document.querySelectorAll('.lnb .mailbox_item, .lnb a'));
  var breakdown = {};
  var total_aggregate = -1;
  var inbox_unread = -1;
  for (var i = 0; i < items.length; i++) {
    var el = items[i];
    var text = (el.innerText||'').replace(/\s+/g,' ').trim();
    var title = el.getAttribute('title')||'';
    // "전체 안읽은 메일" — 합산
    if (title === '전체 안읽은 메일' || /^전체 안읽은/.test(text)) {
      var m = text.match(/(\d+)/);
      if (m) total_aggregate = parseInt(m[1], 10);
    }
    // 받은메일함 unread
    if (/받은메일함/.test(text) && /안 ?읽은/.test(text)) {
      var m2 = text.match(/안 ?읽은 메일 (\d+) ?개/);
      if (m2) inbox_unread = parseInt(m2[1], 10);
    }
    // 스마트메일함 하위 (프로모션/청구·결제/SNS/카페 등)
    var smart = ['프로모션','청구·결제','SNS','카페','쇼핑','뉴스레터'];
    for (var s = 0; s < smart.length; s++) {
      var name = smart[s];
      if (text.indexOf(name + ' 안 ') >= 0 || text.indexOf(name + '\n안') >= 0
          || text.startsWith(name + ' 안')) {
        var m3 = text.match(/안 ?읽은 메일 (\d+) ?개/);
        if (m3) breakdown[name] = parseInt(m3[1], 10);
      }
    }
  }
  // toolbar 현재 폴더 unread
  var tb = document.querySelector('.mail_toolbar_summary');
  var tb_unread = -1;
  if (tb) {
    var m4 = (tb.innerText||'').match(/안읽은 메일\s*(\d+)\s*개/);
    if (m4) tb_unread = parseInt(m4[1], 10);
  }
  // source 판정
  var source = 'inbox_only';
  var sum_smart = 0;
  for (var k in breakdown) sum_smart += breakdown[k];
  if (total_aggregate > 0 && inbox_unread > 0
      && total_aggregate > inbox_unread + 5) {
    source = 'aggregate_with_smart_folders';
  }
  return {
    inbox_unread: inbox_unread,
    total_aggregate: total_aggregate,
    smart_folder_breakdown: breakdown,
    toolbar_current_unread: tb_unread,
    source: source,
  };
})())
"""


def _bump_page_url(current_url: str, page_n: int) -> str:
    """URL의 page 쿼리를 N으로 설정. ?page=N 직접 이동용."""
    if not current_url or not current_url.startswith("http"):
        return ""
    from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
    p = urlparse(current_url)
    qs = dict(parse_qsl(p.query, keep_blank_values=True))
    qs["page"] = str(page_n)
    return urlunparse(p._replace(query=urlencode(qs)))


def _advance_page(actions: "Actions", target_idx: int,
                  current_url: str) -> tuple[bool, str]:
    """전략 우선순위: url_page → page_button → next_arrow.

    Returns (advanced, strategy_label).
    """
    # A. URL?page=N (가장 신뢰)
    new_url = _bump_page_url(current_url, target_idx)
    if new_url:
        actions.navigate(new_url)
        time.sleep(0.2)
        ok = actions.wait_dom("document.querySelector('li.mail_item')", timeout_s=6.0)
        if ok:
            return (True, "url_page")

    # B. 번호 버튼
    clicked = actions.evaluate(_click_page_expr(str(target_idx)))
    if clicked:
        return (True, "page_button")

    # C. next-arrow
    clicked = actions.evaluate(
        "(function(){var nx=document.querySelector("
        "'.pagination .button_next:not([disabled]):not(.disabled), "
        ".pagination .page_navigation_next:not([disabled]):not(.disabled), "
        ".pagination .next:not([disabled]):not(.disabled)');"
        "if(nx){nx.click();return true;}return false;})()"
    )
    if clicked:
        return (True, "next_arrow")
    return (False, "")


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
    filter_applied = False
    filter_evidence: dict = {}
    if mode == rsg.MODE_UNREAD_ONLY:
        filter_applied, filter_evidence = apply_unread_filter(actions)
        time.sleep(0.1)

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
        filter_applied=filter_applied,
        filter_evidence=filter_evidence,
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

    def _sn_hash(payload: dict) -> str:
        import hashlib
        sns = sorted((it.get("sn") or "") for it in (payload or {}).get("items", []))
        return hashlib.sha1("|".join(sns).encode()).hexdigest()[:12]

    def _next_state() -> dict:
        return actions.evaluate(NEXT_STATE_EXPR) or {}

    def _record_page(idx: int, payload: dict) -> None:
        items = (payload or {}).get("items", [])
        result.page_records.append({
            "idx": idx,
            "url": (payload or {}).get("href", ""),
            "item_count": len(items),
            "unread_count": sum(1 for r in items if r.get("is_unread")),
            "sn_hash": _sn_hash(payload),
            "next_state": _next_state(),
        })

    _absorb(first, "1")
    result.pages_visited.append("1")
    _record_page(1, first)

    strategies_used: set[str] = set()
    consecutive_no_new = 0
    page_index = 1
    while True:
        if result.warn_limit_reached:
            break
        if page_index >= max_pages:
            result.warn_limit_reached = True
            result.notes.append(f"max_pages={max_pages}_도달")
            break
        target_idx = page_index + 1

        # 다음 페이지 전 sn_hash 기준점
        sn_hash_before = result.page_records[-1]["sn_hash"]
        url_before = result.page_records[-1]["url"]
        nxt_before = result.page_records[-1]["next_state"]

        # next 가 disabled 면 즉시 종료 근거 수집
        if nxt_before.get("next_disabled") is True:
            result.last_page_evidence.append("next_disabled")

        advanced, strat = _advance_page(actions, target_idx, url_before)
        if not advanced:
            # URL/번호/next 모두 실패 — last_page_evidence 보강
            if "next_disabled" not in result.last_page_evidence:
                # 추가 검증: URL ?page=N+1 직접 시도해도 변화 없음
                trial_url = _bump_page_url(url_before, target_idx)
                if trial_url:
                    actions.navigate(trial_url)
                    time.sleep(0.2)
                    actions.wait_dom("document.querySelector('li.mail_item')", timeout_s=6.0)
                    after = actions.evaluate(LIST_EXPR) or {}
                    if _sn_hash(after) == sn_hash_before:
                        result.last_page_evidence.append("url_page_no_change")
                    else:
                        # 의외로 변화 — 진행
                        page_index += 1
                        added = _absorb(after, str(page_index))
                        result.pages_visited.append(str(page_index))
                        _record_page(page_index, after)
                        strategies_used.add("url_page")
                        if added == 0:
                            consecutive_no_new += 1
                            if consecutive_no_new >= 2:
                                result.last_page_evidence.append("no_new_sn")
                                break
                        else:
                            consecutive_no_new = 0
                        continue
            # 종료 판정 (근거 2개 이상 요구)
            if len(set(result.last_page_evidence)) >= 2:
                result.last_page_reached = True
            else:
                result.notes.append(
                    f"insufficient_last_page_evidence:{result.last_page_evidence}"
                )
                # 추가 증거 부족 — WARN
            break

        strategies_used.add(strat)
        time.sleep(0.2)
        actions.wait_dom("document.querySelector('li.mail_item')", timeout_s=8.0)
        more = actions.evaluate(LIST_EXPR) or {}

        # sn_hash 가 이전과 동일 — URL/click 이 실제로는 진행 안 함
        if _sn_hash(more) == sn_hash_before:
            # url_page 전략이 실패한 것 → evidence 누적, absorb 하지 않음
            if strat == "url_page":
                result.last_page_evidence.append("url_page_no_change")
            else:
                result.last_page_evidence.append("no_new_sn")
            # 종료 판정
            if len(set(result.last_page_evidence)) >= 2:
                result.last_page_reached = True
                break
            # 단일 근거라도 한 번 더 시도하지 않고 곧장 종료 후보
            consecutive_no_new += 1
            if consecutive_no_new >= 2:
                # 근거 부족이라도 무한 루프 방지 — last_page_reached False 로 두고 종료
                result.notes.append(
                    f"loop_safety_break_evidence={list(set(result.last_page_evidence))}"
                )
                break
            continue

        page_index += 1
        added = _absorb(more, str(page_index))
        result.pages_visited.append(str(page_index))
        _record_page(page_index, more)
        if added == 0:
            consecutive_no_new += 1
            if consecutive_no_new >= 2:
                result.last_page_evidence.append("no_new_sn")
                if len(set(result.last_page_evidence)) >= 2:
                    result.last_page_reached = True
                    break
        else:
            consecutive_no_new = 0

    # UI count scope evidence 수집
    result.ui_count_scope_evidence = actions.evaluate(LNB_UNREAD_BREAKDOWN_EXPR) or {}

    # pagination 전략 정리
    if len(strategies_used) == 1:
        result.pagination_strategy_used = next(iter(strategies_used))
    elif len(strategies_used) > 1:
        result.pagination_strategy_used = "mixed:" + ",".join(sorted(strategies_used))
    else:
        result.pagination_strategy_used = "single_page"

    # 종료 — collected_unread 계산
    result.items = list(seen_sns.values())
    result.collected_unread = sum(1 for i in result.items if i.read_state == "UNREAD")

    # last_page_reached 최종 판정
    if not result.warn_limit_reached and not result.last_page_reached:
        # 자연 종료 시: 근거가 2개 이상이어야 True
        if len(set(result.last_page_evidence)) >= 2:
            result.last_page_reached = True
            result.notes.append("자연_종료_근거2개+")
        else:
            result.last_page_reached = False
            result.notes.append(
                f"WARN_DYNAMIC_PAGE_MISSED_evidence={result.last_page_evidence}"
            )
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
        "filter_applied": r.filter_applied,
        "filter_evidence": r.filter_evidence,
        "mismatch_reason": r.mismatch_reason,
        "pagination_strategy_used": r.pagination_strategy_used,
        "page_records": r.page_records,
        "last_page_evidence": r.last_page_evidence,
        "ui_count_scope_evidence": r.ui_count_scope_evidence,
    }
