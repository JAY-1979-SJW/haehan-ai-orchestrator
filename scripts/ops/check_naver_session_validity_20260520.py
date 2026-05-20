"""ORCHESTRATOR_LOGIN_SESSION_VALIDITY_CHECK_01 — Naver 세션 유효성 검증.

원칙:
- nidlogin.login 으로 직접 진입 금지
- www.naver.com / myInfo.naver 진입 후 페이지 신호로 판정
- 쿠키 값/PW/토큰 출력 금지 (존재 여부만)
"""
from __future__ import annotations

import json
import time
import urllib.request

import websocket

CDP_PORT = 9222
TARGETS = [
    ("naver_main", "https://www.naver.com/"),
    ("naver_blog_main", "https://section.blog.naver.com/BlogHome.naver"),
    ("naver_cafe_main", "https://section.cafe.naver.com/"),
]


def _ws_browser() -> str:
    with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=2) as r:
        return json.loads(r.read())["webSocketDebuggerUrl"]


def _list_pages() -> list[dict]:
    with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/list", timeout=2) as r:
        rows = json.loads(r.read() or b"[]")
    return [t for t in rows if t.get("type") == "page"]


def _send(ws, msg_id: int, method: str, params: dict | None = None,
          timeout: float = 8.0) -> dict:
    ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
    deadline = time.time() + timeout
    while time.time() < deadline:
        ws.settimeout(max(0.5, deadline - time.time()))
        try:
            raw = ws.recv()
        except Exception:
            return {"id": msg_id, "_timeout": True}
        try:
            m = json.loads(raw)
        except Exception:
            continue
        if m.get("id") == msg_id:
            return m
    return {"id": msg_id, "_timeout": True}


PAGE_EXPR = r"""
JSON.stringify((function(){
  const txt = (document.body && document.body.innerText) || '';
  const has_login_btn = !!document.querySelector('a.MyView-module__link_login___HpHMW, a[href*="nidlogin.login"], .link_login, #login_btn, .btn_login');
  const has_logout = /로그아웃/.test(txt) || !!document.querySelector('a[href*="nidlogout"], a[href*="logout"]');
  const has_mypage_link = !!document.querySelector('a[href*="mypage"], a[href*="my.naver"], a[href*="myInfo"]');
  const has_user_menu = !!document.querySelector('.MyView-module__my_area___JjDmw, .gnb_my_namebox, .user_info, .MyView-module__btn_setting___YyyaZ');
  const has_id_form = !!document.querySelector('#id, input[name="id"]');
  const has_pw_form = !!document.querySelector('#pw, input[name="pw"], input[type="password"]');
  const has_relogin_msg = /다시 로그인|세션이 만료|로그인이 필요/.test(txt);
  const has_naver_session_cookie = /NID_SES|NID_AUT/.test(document.cookie||'');
  return {
    href: location.href,
    title: document.title,
    has_login_btn,
    has_logout,
    has_mypage_link,
    has_user_menu,
    has_id_form,
    has_pw_form,
    has_relogin_msg,
    has_naver_session_cookie,
    body_len: txt.length,
    body_top: txt.replace(/\s+/g,' ').slice(0,300),
  };
})())
"""


def _judge(s: dict) -> str:
    if s.get("has_id_form") and s.get("has_pw_form"):
        if s.get("has_relogin_msg"):
            return "SESSION_EXPIRED"
        return "LOGIN_REQUIRED"
    if "nidlogin.login" in (s.get("href") or ""):
        return "LOGIN_REQUIRED"
    if s.get("has_logout") or s.get("has_user_menu"):
        return "LOGGED_IN"
    if s.get("has_login_btn") and not (s.get("has_logout") or s.get("has_user_menu")):
        return "LOGIN_REQUIRED"
    return "LOGIN_UNKNOWN"


def _eval_with_retry(target_id: str, expr: str, max_wait: float = 15.0) -> dict:
    """매번 fresh WS 로 evaluate — execution context 가 새 페이지로 전환되길 기다린다."""
    deadline = time.time() + max_wait
    last_ev = None
    while time.time() < deadline:
        for t in _list_pages():
            if t.get("id") != target_id:
                continue
            try:
                w = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=5)
            except Exception:
                break
            ev = _send(w, 1, "Runtime.evaluate",
                       {"expression": expr, "returnByValue": True}, timeout=5.0)
            w.close()
            last_ev = ev
            val = ev.get("result", {}).get("result", {}).get("value")
            if isinstance(val, str) and val:
                try:
                    obj = json.loads(val)
                    href = obj.get("href") or ""
                    # about:blank 면 아직 로드 안됨
                    if href and not href.startswith("about:"):
                        return obj
                except Exception:
                    pass
            break
        time.sleep(0.8)
    return {"_raw_ev": str(last_ev)[:300] if last_ev else "no_response"}


def main() -> None:
    # 기존 about:blank 탭 재사용
    target_id = None
    for t in _list_pages():
        if t.get("url") == "about:blank":
            target_id = t.get("id")
            break
    if not target_id:
        # 없으면 새로 만든다
        bws = websocket.create_connection(_ws_browser(), timeout=8)
        new = _send(bws, 1, "Target.createTarget", {"url": "about:blank"}, timeout=5.0)
        target_id = new.get("result", {}).get("targetId")
        bws.close()
    if not target_id:
        print(json.dumps({"ok": False, "error": "no_target"}))
        return

    results = []
    for label, url in TARGETS:
        # navigate
        for t in _list_pages():
            if t.get("id") == target_id:
                w = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=5)
                _send(w, 10, "Page.navigate", {"url": url}, timeout=5.0)
                w.close()
                break
        time.sleep(3.0)
        data = _eval_with_retry(target_id, PAGE_EXPR, max_wait=15.0)
        # 출력에서 body_top 너무 길면 자름
        out = {
            "label": label,
            "navigated_to": url,
            "final_url": data.get("href"),
            "title": data.get("title"),
            "has_session_cookie": bool(data.get("has_naver_session_cookie")),
            "has_login_btn": bool(data.get("has_login_btn")),
            "has_id_form": bool(data.get("has_id_form")),
            "has_pw_form": bool(data.get("has_pw_form")),
            "has_logout": bool(data.get("has_logout")),
            "has_mypage_link": bool(data.get("has_mypage_link")),
            "has_user_menu": bool(data.get("has_user_menu")),
            "has_relogin_msg": bool(data.get("has_relogin_msg")),
            "login_state": _judge(data),
            "body_len": data.get("body_len"),
            "body_top_redacted": (data.get("body_top") or "")[:200],
        }
        results.append(out)
        print(json.dumps(out, ensure_ascii=False, indent=2))

    # 종합 판정
    states = [r["login_state"] for r in results]
    if all(s == "LOGGED_IN" for s in states):
        verdict = "PASS_SESSION_VALIDITY_CONFIRMED"
    elif "SESSION_EXPIRED" in states:
        verdict = "WARN_SESSION_EXPIRED_OR_RELOGIN_REQUIRED"
    elif "LOGIN_REQUIRED" in states:
        verdict = "WARN_SESSION_EXPIRED_OR_RELOGIN_REQUIRED"
    else:
        verdict = "FAIL_SESSION_VALIDITY_CHECK"
    print(json.dumps({"verdict": verdict, "states": states}, ensure_ascii=False))

    # 검증 후 탭은 about:blank 로 reset
    for t in _list_pages():
        if t.get("id") == target_id:
            try:
                w = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=5)
                _send(w, 88, "Page.navigate", {"url": "about:blank"}, timeout=3.0)
                w.close()
            except Exception:
                pass
            break


if __name__ == "__main__":
    main()
