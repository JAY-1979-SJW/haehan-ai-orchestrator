"""Naver Mail 안읽은 메일 분류/요약 보고 + 단계별 화면 캡쳐.

main-page-first 정책:
  - https://mail.naver.com/ 로 곧장 진입 (사용자 이미 로그인됨)
  - nidlogin.login 우회 금지 (site_entry_policy.assert_main_page_first 가드)

캡쳐: data/inspection/mail_20260520/*.png
보안: 쿠키/토큰/PW 출력 금지. 본인 메일 내용은 출력 허용.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.request
from pathlib import Path

import websocket

from core.agent_runtime.policy import site_entry_policy as sep

CDP_PORT = 9222
CAP_DIR = Path("data/inspection/mail_20260520")
CAP_DIR.mkdir(parents=True, exist_ok=True)

MAIL_MAIN = "https://mail.naver.com/"
MAX_READ = 15


# ── CDP 헬퍼 ────────────────────────────────────────────────────────


def _ws_browser() -> str:
    with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=2) as r:
        return json.loads(r.read())["webSocketDebuggerUrl"]


def _list_pages() -> list[dict]:
    with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/list", timeout=2) as r:
        return [t for t in json.loads(r.read() or b"[]") if t.get("type") == "page"]


def _send(ws, msg_id, method, params=None, timeout=8.0):
    ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
    deadline = time.time() + timeout
    while time.time() < deadline:
        ws.settimeout(max(0.5, deadline - time.time()))
        try:
            raw = ws.recv()
        except Exception:  # noqa: BLE001 - 네이버 메일 미읽음 리포트 스크립트(읽기전용, WS 기반 CDP 통신) — 응답수신 실패 시 타임아웃 결과 반환, JSON파싱 실패는 continue, 쓰기 없음
            return {"id": msg_id, "_timeout": True}
        try:
            m = json.loads(raw)
        except Exception:  # noqa: BLE001 - 네이버 메일 미읽음 리포트 스크립트(읽기전용, WS 기반 CDP 통신) — 응답수신 실패 시 타임아웃 결과 반환, JSON파싱 실패는 continue, 쓰기 없음
            continue
        if m.get("id") == msg_id:
            return m
    return {"id": msg_id, "_timeout": True}


def _open_ws_for(target_id: str):
    for t in _list_pages():
        if t.get("id") == target_id:
            return websocket.create_connection(t["webSocketDebuggerUrl"], timeout=8)
    raise RuntimeError("target_not_found")


def navigate(target_id, url):
    w = _open_ws_for(target_id)
    _send(w, 10, "Page.navigate", {"url": url}, timeout=6.0)
    w.close()


def evaluate(target_id, expr, timeout=8.0):
    w = _open_ws_for(target_id)
    ev = _send(
        w, 1, "Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True}, timeout=timeout
    )
    w.close()
    val = ev.get("result", {}).get("result", {}).get("value")
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:  # noqa: BLE001 - 네이버 메일 미읽음 리포트 스크립트(읽기전용, WS 기반 CDP 통신) — 응답수신 실패 시 타임아웃 결과 반환, JSON파싱 실패는 continue, 쓰기 없음
            return val
    return val


def screenshot(target_id, name) -> Path | None:
    w = _open_ws_for(target_id)
    ev = _send(w, 2, "Page.captureScreenshot", {"format": "png"}, timeout=10.0)
    w.close()
    data = ev.get("result", {}).get("data")
    if not data:
        return None
    p = CAP_DIR / f"{name}.png"
    p.write_bytes(base64.b64decode(data))
    return p


def wait_dom(target_id, expr, timeout=18.0, interval=1.0):
    """expr 가 truthy 가 될 때까지 대기."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        v = evaluate(target_id, f"({expr}) ? true : false", timeout=4.0)
        if v is True:
            return True
        time.sleep(interval)
    return False


# ── Naver Mail 상호작용 ─────────────────────────────────────────────

LIST_EXPR = r"""
JSON.stringify((function(){
  // Naver Mail v2 — li.mail_item (가상화 리스트)
  const rows = Array.from(document.querySelectorAll('li.mail_item'));
  const out = [];
  for (const r of rows) {
    const cls = (r.className || '');
    // 메일 ID
    const m = cls.match(/mail-(\d+)/);
    const sn = m ? m[1] : '';
    // 읽음 상태: '읽은 메일' 라벨 버튼이 aria-pressed='true' = 이미 읽음
    const read_btn = r.querySelector('.toggle_read_wrap label[role="button"]');
    const aria = read_btn ? (read_btn.getAttribute('aria-pressed')||'false') : 'false';
    const is_unread = (aria !== 'true');
    // 발신자
    const sender_btn = r.querySelector('.button_sender');
    const sender_name = sender_btn ? (sender_btn.innerText||'').trim() : '';
    const sender_full = sender_btn ? (sender_btn.getAttribute('title')||'').trim() : '';
    // 제목
    const title_el = r.querySelector('.mail_title .text');
    const subject = title_el ? (title_el.innerText||'').trim() : '';
    // 미리보기 (있는 경우)
    const prev_el = r.querySelector('.mail_preview, .preview_text, .mail_inner .preview');
    const preview = prev_el ? (prev_el.innerText||'').trim() : '';
    // 시각, 용량
    const date_el = r.querySelector('.mail_date');
    const size_el = r.querySelector('.mail_volume');
    // 메일 링크
    const link_el = r.querySelector('.mail_title_link');
    const href = link_el ? link_el.getAttribute('href') : '';
    out.push({
      sn,
      is_unread,
      sender_name: sender_name.slice(0,120),
      sender_full: sender_full.slice(0,200),
      subject: subject.slice(0,300),
      preview: preview.slice(0,300),
      time_txt: date_el ? (date_el.innerText||'').trim().slice(0,40) : '',
      size_txt: size_el ? (size_el.innerText||'').trim().slice(0,20) : '',
      href,
    });
  }
  return {
    href: location.href, title: document.title, count: out.length, items: out,
    body_len: (document.body.innerText||'').length,
  };
})())
"""


CLASSIFY_RULES = [
    # (label, sender_substr_or_re, subject_keywords)
    (
        "결제/영수증",
        ["paypal", "kakaopay", "naverpay", "billing", "결제", "영수증", "invoice"],
        ["결제", "영수증", "구매", "주문"],
    ),
    (
        "공식/계정",
        ["noreply", "no-reply", "naver", "google", "kakao", "github"],
        ["보안", "비밀번호", "로그인", "계정", "인증"],
    ),
    ("뉴스레터", ["newsletter", "subscribe", "news"], ["뉴스레터", "newsletter", "주간", "월간"]),
    (
        "쇼핑/프로모션",
        ["shop", "mall", "11st", "coupang", "gmarket", "musinsa", "올리브영"],
        ["할인", "쿠폰", "프로모션", "세일", "특가"],
    ),
    (
        "업무/계약",
        ["@haehan", "계약", "견적", "발주", "송금", "세금계산서", "비전아이"],
        ["견적", "계약", "발주", "송금", "세금계산서", "공사"],
    ),
    ("EUM/공제회", ["cw.or.kr", "공제회", "건설근로자"], ["EUM", "공제회", "단말기", "전자카드"]),
    ("일반/광고", ["광고", "ad@", "promo"], ["광고", "이벤트"]),
]


def classify(sender: str, subject: str) -> str:
    s = (sender + " " + subject).lower()
    for label, sender_kws, sub_kws in CLASSIFY_RULES:
        for kw in sender_kws + sub_kws:
            if kw.lower() in s:
                return label
    return "기타"


_FRAME_EXPR = r"""
        JSON.stringify((function(){
          const frames = Array.from(document.querySelectorAll('iframe'));
          return frames.map(f => ({src:f.src, name:f.name, id:f.id}));
        })())
        """

PAGES_EXPR = r"""
    JSON.stringify((function(){
      const btns = Array.from(document.querySelectorAll('.pagination .page_list .page .page_link'));
      return btns.map(b => (b.innerText||'').trim().replace(/[^0-9]/g,'')).filter(s=>s);
    })())
    """

CLICK_PAGE_EXPR_TPL = r"""
    (function(){
      const btns = Array.from(document.querySelectorAll('.pagination .page_list .page .page_link'));
      for(const b of btns){
        if((b.innerText||'').trim().replace(/[^0-9]/g,'') === %r){ b.click(); return true; }
      }
      // 다음(▶) 또는 마지막(▶▶)
      const next = document.querySelector('.pagination .page_navigation_next, .pagination .next');
      if(next){ next.click(); return 'next'; }
      return false;
    })()
    """


def _ensure_mail_tab():
    target_id = None
    for t in _list_pages():
        if "mail.naver.com" in t.get("url", ""):
            target_id = t["id"]
            break
    if not target_id:
        # about:blank or 새 탭
        for t in _list_pages():
            if t.get("url") in ("about:blank", "chrome://newtab/"):
                target_id = t["id"]
                break
        if not target_id:
            bws = websocket.create_connection(_ws_browser(), timeout=8)
            new = _send(bws, 1, "Target.createTarget", {"url": "about:blank"}, timeout=5.0)
            target_id = new.get("result", {}).get("targetId")
            bws.close()
        print(f"[1] navigate {MAIL_MAIN}")
        navigate(target_id, MAIL_MAIN)
        time.sleep(4.0)
        wait_dom(target_id, "document.querySelector('li.mail_item')", timeout=20.0)
        time.sleep(1.5)
    else:
        print(f"[1] mail.naver.com 탭 재사용: {target_id[:12]}")
        wait_dom(target_id, "document.querySelector('li.mail_item')", timeout=10.0)
    return target_id


def _extract_list(target_id):
    data = evaluate(target_id, LIST_EXPR, timeout=8.0)
    if not isinstance(data, dict):
        # iframe 내부일 가능성 — 모든 frame 평가
        print(f"  list 평가 실패, frame 탐색 시도 ... data={str(data)[:200]}")
        # frame 안에서 다시 시도
        frames = evaluate(target_id, _FRAME_EXPR, timeout=6.0)
        print(f"  frames: {frames}")
        data = {"items": [], "_frames": frames}
    return data


def _init_items(data):
    all_items = {}  # sn -> item

    def merge(items):
        for it in items:
            sn = it.get("sn") or (it.get("subject", "") + "|" + it.get("sender_name", ""))
            if sn and sn not in all_items:
                all_items[sn] = it

    if isinstance(data, dict):
        merge(data.get("items", []))
    return all_items, merge


def _get_pages_avail(target_id):
    pages_avail = evaluate(target_id, PAGES_EXPR, timeout=4.0)
    if not isinstance(pages_avail, list):
        pages_avail = []
    print(f"[2.1] pagination 페이지 후보: {pages_avail}")
    return pages_avail


def _walk_pages(target_id, pages_avail, all_items, merge):
    visited = {"1"}
    for pg in pages_avail + [str(i) for i in range(1, 21)]:
        if pg in visited:
            continue
        visited.add(pg)
        clicked = evaluate(target_id, CLICK_PAGE_EXPR_TPL % pg, timeout=4.0)
        if not clicked:
            continue
        time.sleep(1.5)
        wait_dom(target_id, "document.querySelector('li.mail_item')", timeout=8.0)
        more = evaluate(target_id, LIST_EXPR, timeout=6.0)
        if isinstance(more, dict):
            before = len(all_items)
            merge(more.get("items", []))
            added = len(all_items) - before
            print(f"  page {pg}: +{added}건  누적 {len(all_items)}")
            if added == 0:
                # 더 이상 새 mail 없음 — 다음 페이지 시도 끝
                # 단 페이지 후보에 더 있을 수 있으니 한 번 더 확인
                if int(pg) > max(int(x) for x in pages_avail or ["1"]) + 2:
                    break
        else:
            print(f"  page {pg}: list eval 실패")
        if len(all_items) >= 80:
            break


def _classify_unread(unread):
    classified = {}
    for it in unread:
        sender_blob = it.get("sender_name", "") + " " + it.get("sender_full", "")
        lbl = classify(sender_blob, it.get("subject", ""))
        classified.setdefault(lbl, []).append(it)
    return classified


def _print_report(unread, classified, data):
    print("\n=== 안읽은 메일 분류 보고 ===")
    if not unread:
        print("(안읽은 메일 없음 또는 리스트 추출 실패)")
        if isinstance(data, dict) and data.get("_frames"):
            print("DOM iframe 탐지됨 — 메인 페이지 DOM 에서 메일 항목 셀렉터가 안 잡힘. iframe 내부 진입 필요.")
    else:
        for lbl, lst in sorted(classified.items(), key=lambda x: -len(x[1])):
            print(f"\n[{lbl}] {len(lst)}건")
            for it in lst:
                print(f"  - 보낸이: {it.get('sender_name', '')}  <{it.get('sender_full', '')}>")
                print(f"    제목: {it.get('subject', '')}")
                if it.get("preview"):
                    print(f"    미리보기: {it['preview']}")
                if it.get("time_txt"):
                    print(f"    시각: {it['time_txt']}  크기: {it.get('size_txt', '')}")


def _save_report_json(href, title, items, unread, classified):
    out_json = CAP_DIR / "mail_unread_report.json"
    out_json.write_text(
        json.dumps(
            {
                "href": href,
                "title": title,
                "total": len(items),
                "unread": len(unread),
                "classified": {
                    lbl: [
                        {
                            k: it.get(k)
                            for k in ("sender_name", "sender_full", "subject", "preview", "time_txt", "size_txt", "sn")
                        }
                        for it in lst
                    ]
                    for lbl, lst in classified.items()
                },
                "items_raw_first_20": items[:20],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n[json] {out_json}")


def main():
    # GUARD
    sep.assert_main_page_first(MAIL_MAIN, "naver")

    # 이미 mail.naver.com 에 있으면 그 탭 사용, 아니면 새로 진입
    target_id = _ensure_mail_tab()

    cap1 = screenshot(target_id, "01_mail_main")
    print(f"  screenshot → {cap1}")

    # 2) 메일 리스트 추출
    data = _extract_list(target_id)

    # 페이지네이션 — Naver Mail v2 는 페이지 단위 (15개/page)
    all_items, merge = _init_items(data)

    # 안읽은 필터 적용은 생략(전체 페이지 순회로 다 잡음). 페이지 1..N 클릭.
    pages_avail = _get_pages_avail(target_id)

    # 페이지 2..끝 순회 (현재 page 1 이미 수집됨)
    # 페이지 후보가 [1,2,3] 처럼만 보이고 더 있을 수 있으므로 1..20 시도하면서 빈 페이지 stop
    _walk_pages(target_id, pages_avail, all_items, merge)

    items = list(all_items.values())
    href = data.get("href", "") if isinstance(data, dict) else ""
    title = data.get("title", "") if isinstance(data, dict) else ""

    print(f"\n[2] mail list: href={href} title={title} collected={len(items)}")

    unread = [it for it in items if it.get("is_unread")]
    print(f"  unread = {len(unread)} / total collected {len(items)}")

    # 3) 분류
    classified = _classify_unread(unread)

    # 4) 보고
    _print_report(unread, classified, data)

    # 5) 결과 JSON 저장
    _save_report_json(href, title, items, unread, classified)

    # 6) 캡쳐 종료
    cap2 = screenshot(target_id, "02_mail_list_after")
    print(f"[capture] {cap2}")

    # 탭은 mail.naver.com 유지 (사용자 작업 데이터 보존 원칙)


if __name__ == "__main__":
    main()
