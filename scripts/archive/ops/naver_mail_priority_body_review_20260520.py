"""ORCHESTRATOR_NAVER_MAIL_PRIORITY_BODY_REVIEW_01.

시급 메일 4건 본문 열람 + 핵심 요약 + 조치 판단 + 피싱 확인.
삭제/읽음/이동/답장 금지. PII 마스킹.
"""

from __future__ import annotations

import base64
import json
import re
import time
import urllib.request
from pathlib import Path

import websocket

from core.agent_runtime.policy import site_entry_policy as sep

CDP_PORT = 9222
CAP_DIR = Path("data/inspection/mail_20260520/bodies")
CAP_DIR.mkdir(parents=True, exist_ok=True)

TARGETS = [
    {"sn": "112364", "tag": "coupang_support_listing_stop", "expected": "쿠팡 고객센터 답변지연 상품 노출 정지"},
    {"sn": "111565", "tag": "gsc_indexing_haehan_ai", "expected": "GSC haehan-ai.kr 색인 미생성"},
    {"sn": "112155", "tag": "smartstore_dormant", "expected": "스마트스토어 휴면 전환"},
    {"sn": "112075", "tag": "coupang_simple_login_registered", "expected": "쿠팡 간편 로그인 등록"},
]

# ── PII 마스킹 ───────────────────────────────────────────────────────


def _redact(text: str) -> str:
    if not text:
        return ""
    # 카드/계좌번호 (4자리×4 또는 13~16자리 연속)
    text = re.sub(r"\b(\d{4})[ -](\d{4})[ -](\d{4})[ -](\d{4})\b", r"\1-****-****-\4", text)
    text = re.sub(r"\b\d{13,16}\b", "[NUMBER_MASKED]", text)
    # 휴대전화 010-1234-5678
    text = re.sub(r"\b01[016789][- .]?\d{3,4}[- .]?\d{4}\b", "010-****-****", text)
    # 주민번호류
    text = re.sub(r"\b\d{6}[- ]?[1-4]\d{6}\b", "[RRN_MASKED]", text)

    # 이메일 — 도메인은 남기고 local-part 일부 마스킹
    def _mask_email(m):
        lp, dom = m.group(1), m.group(2)
        if len(lp) <= 2:
            return f"**@{dom}"
        return f"{lp[:2]}***@{dom}"

    text = re.sub(r"\b([A-Za-z0-9_.+\-]+)@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b", _mask_email, text)
    # 인증번호/OTP 6자리
    text = re.sub(r"(인증번호|OTP|확인번호)[^\d]{0,8}(\d{4,8})", lambda m: f"{m.group(1)} [CODE_MASKED]", text)
    return text


# ── CDP ─────────────────────────────────────────────────────────────


def _list_pages():
    with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/list", timeout=2) as r:
        return [t for t in json.loads(r.read() or b"[]") if t.get("type") == "page"]


def _send(ws, msg_id, method, params=None, timeout=8.0):
    ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
    deadline = time.time() + timeout
    while time.time() < deadline:
        ws.settimeout(max(0.5, deadline - time.time()))
        try:
            raw = ws.recv()
        except Exception:  # noqa: BLE001 - 네이버 메일 우선순위 본문 검토 스크립트(읽기전용, WS 기반 CDP 통신) — 응답수신 실패 시 타임아웃 결과 반환, JSON파싱 실패는 continue, 쓰기 없음
            return {"id": msg_id, "_timeout": True}
        try:
            m = json.loads(raw)
        except Exception:  # noqa: BLE001 - 네이버 메일 우선순위 본문 검토 스크립트(읽기전용, WS 기반 CDP 통신) — 응답수신 실패 시 타임아웃 결과 반환, JSON파싱 실패는 continue, 쓰기 없음
            continue
        if m.get("id") == msg_id:
            return m
    return {"id": msg_id, "_timeout": True}


def _eval(target_id, expr, timeout=8.0):
    for t in _list_pages():
        if t.get("id") == target_id:
            ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=8)
            ev = _send(ws, 1, "Runtime.evaluate", {"expression": expr, "returnByValue": True}, timeout=timeout)
            ws.close()
            val = ev.get("result", {}).get("result", {}).get("value")
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except Exception:  # noqa: BLE001 - 네이버 메일 우선순위 본문 검토 스크립트(읽기전용, WS 기반 CDP 통신) — 응답수신 실패 시 타임아웃 결과 반환, JSON파싱 실패는 continue, 쓰기 없음
                    return val
            return val
    return None


def _navigate(target_id, url):
    for t in _list_pages():
        if t.get("id") == target_id:
            ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=5)
            _send(ws, 10, "Page.navigate", {"url": url}, timeout=5.0)
            ws.close()
            return


def _screenshot(target_id, name):
    for t in _list_pages():
        if t.get("id") == target_id:
            ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=8)
            ev = _send(ws, 2, "Page.captureScreenshot", {"format": "png"}, timeout=10.0)
            ws.close()
            data = ev.get("result", {}).get("data")
            if data:
                p = CAP_DIR / f"{name}.png"
                p.write_bytes(base64.b64decode(data))
                return p
    return None


# ── 본문 추출 ───────────────────────────────────────────────────────

BODY_EXPR = r"""
JSON.stringify((function(){
  // Naver Mail v2 read view — iframe(메일 본문) + 헤더(.mail_view_header)
  const header = {
    subject: (document.querySelector('.mail_view_header .subject, .read_subject, [class*=\"subject\"]')||{}).innerText || '',
    sender_name: (document.querySelector('.mail_view_header .sender_name, .sender_info .name, [class*=\"sender_name\"]')||{}).innerText || '',
    sender_addr: (document.querySelector('.mail_view_header .sender_email, .sender_info .email, [class*=\"sender_email\"]')||{}).innerText || '',
    date: (document.querySelector('.mail_view_header .date, .mail_date, [class*=\"date\"]')||{}).innerText || '',
  };
  // iframe 안 본문
  let body = '', links = [], img_count = 0, has_attach = false;
  const iframe = document.querySelector('iframe#readFrame, iframe[name=\"readFrame\"], iframe[id*=\"read\"], iframe[class*=\"mail_view\"]');
  if (iframe) {
    try {
      const doc = iframe.contentDocument || iframe.contentWindow.document;
      body = (doc.body && doc.body.innerText) || '';
      const anchors = Array.from(doc.querySelectorAll('a[href]'));
      links = anchors.map(a => a.href).filter(h => h && !h.startsWith('mailto:'));
      img_count = doc.querySelectorAll('img').length;
    } catch (e) { body = '[iframe_access_denied: '+(e.message||'')+']'; }
  } else {
    // iframe 없으면 직접
    const c = document.querySelector('.mail_view_content, .read_content, [class*=\"mail_body\"], .mail_view');
    body = c ? (c.innerText||'') : (document.body.innerText||'');
    const anchors = Array.from(document.querySelectorAll('.mail_view_content a[href], .read_content a[href]'));
    links = anchors.map(a => a.href).filter(h => h && !h.startsWith('mailto:'));
  }
  // 첨부 영역
  has_attach = !!document.querySelector('.attach_area, .attachment_area, [class*=\"attach\"]');
  const attach_names = Array.from(document.querySelectorAll('.attach_area .file_name, .attachment .name'))
    .map(e => (e.innerText||'').trim()).filter(Boolean);
  return {
    href: location.href,
    title: document.title,
    header, body: body.slice(0, 12000),
    body_len: body.length,
    links: links.slice(0, 80),
    img_count, has_attach, attach_names,
  };
})())
"""


def _domain(url: str) -> str:
    m = re.match(r"https?://([^/]+)/?", url or "")
    return m.group(1).lower() if m else ""


# 합법 도메인 (피싱 아님)
TRUSTED_DOMAINS = {
    "coupang.com",
    "search.google.com",
    "google.com",
    "navercorp.com",
    "naver.com",
    "smartstore.naver.com",
    "centersettlement.naver.com",
    "search.google.com",
    "wcs.naver.net",
    "search.naver.com",
    "n.news.naver.com",
    "blog.naver.com",
    "kbcard.com",
    "kbmail.kbcard.com",
    "hyundaicard.com",
    "shinhancard.com",
    "lottecardmailcenter.net",
    "wooribank.com",
    "yes24.com",
    "x.com",
}


def _is_phishing_link(url: str) -> tuple[bool, str]:
    d = _domain(url)
    if not d:
        return (False, "")
    # 신뢰 도메인 매칭
    for td in TRUSTED_DOMAINS:
        if d == td or d.endswith("." + td):
            return (False, d)
    # 의심 패턴
    if re.search(r"\.(tk|gq|ml|ga|cf|top|xyz|click|loan)$", d):
        return (True, d)
    return (False, d)


def _find_mail_tab():
    target_id = None
    for t in _list_pages():
        if "mail.naver" in t.get("url", ""):
            target_id = t["id"]
            break
    if not target_id:
        for t in _list_pages():
            if t.get("url") in ("about:blank", "chrome://newtab/"):
                target_id = t["id"]
                break
    return target_id


def _review_target(target_id, tgt):
    sn = tgt["sn"]
    url = f"https://mail.naver.com/v2/popup/read/0/{sn}"
    print(f"\n[#{sn}] navigate → {url}")
    _navigate(target_id, url)
    time.sleep(4.0)
    # 본문 iframe 로딩 대기
    for _ in range(10):
        ready = _eval(
            target_id,
            '(function(){var f=document.querySelector(\'iframe#readFrame, iframe[name="readFrame"], iframe[id*="read"]\'); if(!f) return false; try{var d=f.contentDocument||f.contentWindow.document; return (d&&d.body&&d.body.innerText.length>30);}catch(e){return false;}})()',
            timeout=3.0,
        )
        if ready is True:
            break
        time.sleep(1.0)

    data = _eval(target_id, BODY_EXPR, timeout=8.0)
    if not isinstance(data, dict):
        print(f"  body eval 실패: {str(data)[:160]}")
        return {"sn": sn, "tag": tgt["tag"], "error": "body_eval_failed"}

    body = _redact(data.get("body", ""))
    header = data.get("header") or {}
    links = data.get("links") or []
    link_domains = {}
    phishing_hits = []
    for link in links:
        ph, d = _is_phishing_link(link)
        link_domains[d] = link_domains.get(d, 0) + 1
        if ph:
            phishing_hits.append(link)

    # 스크린샷
    shot = _screenshot(target_id, tgt["tag"])

    res = {
        "sn": sn,
        "tag": tgt["tag"],
        "expected": tgt["expected"],
        "href_final": data.get("href"),
        "subject": header.get("subject") or "",
        "sender_name": header.get("sender_name") or "",
        "sender_addr": _redact(header.get("sender_addr") or ""),
        "date": header.get("date") or "",
        "body_len": data.get("body_len", 0),
        "body_excerpt_redacted": body[:1800],
        "link_domain_counts": link_domains,
        "phishing_suspect_links": phishing_hits[:10],
        "img_count": data.get("img_count", 0),
        "has_attach": data.get("has_attach", False),
        "attach_names": data.get("attach_names", []),
        "screenshot": str(shot) if shot else None,
    }
    print(f"  subject: {res['subject'][:80]}")
    print(
        f"  body_len: {res['body_len']}  links: {len(links)}  img: {res['img_count']}  attach: {res['has_attach']}"
    )
    return res


def _print_results(results):
    for r in results:
        print(f"\n[#{r['sn']}] {r.get('expected', '')}")
        if r.get("error"):
            print(f"  ERROR: {r['error']}")
            continue
        print(f"  제목: {r['subject']}")
        print(f"  발신자: {r['sender_name']}  {r['sender_addr']}")
        print(f"  날짜: {r['date']}")
        print("  본문(요약 발췌, redacted):")
        for line in (r["body_excerpt_redacted"][:1200] or "").splitlines()[:25]:
            if line.strip():
                print(f"    | {line.strip()[:140]}")
        print(f"  링크 도메인: {r['link_domain_counts']}")
        if r["phishing_suspect_links"]:
            print(f"  ⚠️ 피싱 의심: {r['phishing_suspect_links']}")
        print(f"  첨부: {r['has_attach']}  ({r['attach_names']})")


def main():
    sep.assert_main_page_first("https://mail.naver.com/", "naver")

    # mail 탭 확보
    target_id = _find_mail_tab()
    if not target_id:
        print("FAIL: mail tab not found")
        return

    results = []
    for tgt in TARGETS:
        results.append(_review_target(target_id, tgt))

    out = CAP_DIR.parent / "priority_body_review.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[json] {out}")

    # 콘솔 보고
    print("\n" + "=" * 60)
    print("=== 시급 메일 4건 본문 검토 결과 ===")
    print("=" * 60)
    _print_results(results)


if __name__ == "__main__":
    main()
