"""Naver 전 항목 main-page-first 라이브 검증.

site_entry_policy 를 직접 호출하여 각 사이트의 main_url 로 navigate,
SPA 렌더 대기 후 judge_login_state 로 판정.
"""
from __future__ import annotations

import json
import time
import urllib.request

import websocket

from core.agent_runtime.policy import site_entry_policy as sep

CDP_PORT = 9222
SITES = ["naver", "naver_blog", "naver_cafe"]

PAGE_EXPR = r"""
JSON.stringify((function(){
  const txt = (document.body && document.body.innerText) || '';
  const has_login_btn = !!document.querySelector('a[href*="nidlogin.login"]');
  const has_logout = /로그아웃/.test(txt) || !!document.querySelector('a[href*="nidlogout"], a[href*="logout"]');
  const has_mypage_link = !!document.querySelector('a[href*="mypage"], a[href*="my.naver"]');
  const has_user_menu = !!document.querySelector('.gnb_my_namebox, .user_info, .MyView-module__my_area___JjDmw, .link_my, [class*="my_area"], [class*="user_menu"]');
  const has_id_form = !!document.querySelector('#id, input[name="id"]');
  const has_pw_form = !!document.querySelector('#pw, input[name="pw"], input[type="password"]');
  const has_relogin_msg = /다시 로그인|세션이 만료|로그인이 필요/.test(txt);
  const has_naver_session_cookie = /NID_SES|NID_AUT/.test(document.cookie||'');
  return {
    href: location.href, title: document.title, body_len: txt.length,
    has_login_btn, has_logout, has_mypage_link, has_user_menu,
    has_id_form, has_pw_form, has_relogin_msg, has_naver_session_cookie,
    body_top: txt.replace(/\s+/g,' ').slice(0,240),
  };
})())
"""


def _ws_browser() -> str:
    with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=2) as r:
        return json.loads(r.read())["webSocketDebuggerUrl"]


def _list_pages() -> list[dict]:
    with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/list", timeout=2) as r:
        rows = json.loads(r.read() or b"[]")
    return [t for t in rows if t.get("type") == "page"]


def _send(ws, msg_id, method, params=None, timeout=5.0):
    ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
    deadline = time.time() + timeout
    while time.time() < deadline:
        ws.settimeout(max(0.5, deadline - time.time()))
        try:
            raw = ws.recv()
        except Exception:  # noqa: BLE001 - 네이버 메인 first-live 검증 smoke 테스트 - CDP 평가 실패 시 timeout/None 반환
            return {"id": msg_id, "_timeout": True}
        try:
            m = json.loads(raw)
        except Exception:  # noqa: BLE001 - 네이버 메인 first-live 검증 smoke 테스트 - CDP 평가 실패 시 timeout/None 반환
            continue
        if m.get("id") == msg_id:
            return m
    return {"id": msg_id, "_timeout": True}


def _good_signal(ev):
    val = ev.get("result", {}).get("result", {}).get("value")
    if isinstance(val, str) and val:
        try:
            obj = json.loads(val)
        except Exception:  # noqa: BLE001 - 네이버 메인 first-live 검증 smoke 테스트 - CDP 평가 실패 시 timeout/None 반환
            obj = None
        if obj and obj.get("href") and not obj["href"].startswith("about:") and obj.get("body_len", 0) > 50:
            return obj
    return None


def _eval_until_signal(target_id, expr, max_wait=18.0):
    deadline = time.time() + max_wait
    last = None
    while time.time() < deadline:
        for t in _list_pages():
            if t.get("id") != target_id:
                continue
            try:
                w = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=5)
            except Exception:  # noqa: BLE001 - 네이버 메인 first-live 검증 smoke 테스트 - CDP 평가 실패 시 timeout/None 반환
                break
            ev = _send(w, 1, "Runtime.evaluate",
                       {"expression": expr, "returnByValue": True}, timeout=6.0)
            w.close()
            last = ev
            _early = _good_signal(ev)
            if _early is not None:
                return _early
            break
        time.sleep(1.0)
    # 마지막 obj 반환 (body 비어있어도)
    if last:
        val = last.get("result", {}).get("result", {}).get("value")
        if isinstance(val, str):
            try:
                return json.loads(val)
            except Exception:  # noqa: BLE001 - 네이버 메인 first-live 검증 smoke 테스트 - CDP 평가 실패 시 timeout/None 반환
                pass
    return {"_no_signal": True}


def _navigate(target_id: str, url: str) -> None:
    for t in _list_pages():
        if t.get("id") == target_id:
            w = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=5)
            _send(w, 10, "Page.navigate", {"url": url}, timeout=5.0)
            w.close()
            return


def main():
    # 본 검증 가드 — 로그인 URL 직접 진입 금지 확인
    try:
        sep.assert_main_page_first("https://nid.naver.com/nidlogin.login", "naver")
        print("[GUARD] FAIL — forbidden URL 가 통과됐다")
        return
    except ValueError:
        print("[GUARD] PASS — nidlogin.login 직접 진입 차단됨")

    # about:blank 탭 확보
    target_id = None
    for t in _list_pages():
        if t.get("url") == "about:blank":
            target_id = t["id"]
            break
    if not target_id:
        bws = websocket.create_connection(_ws_browser(), timeout=8)
        new = _send(bws, 1, "Target.createTarget", {"url": "about:blank"}, timeout=5.0)
        target_id = new.get("result", {}).get("targetId")
        bws.close()

    results = []
    for site_key in SITES:
        first_url, _follow = sep.resolve_entry(site_key)
        print(f"\n[SITE] {site_key} → first={first_url}")
        _navigate(target_id, first_url)
        time.sleep(2.0)
        data = _eval_until_signal(target_id, PAGE_EXPR, max_wait=20.0)
        if data.get("_no_signal"):
            print("  no_signal (body 미생성)")
        # 정책 판정
        state = sep.judge_login_state(site_key, data)
        out = {
            "site_key": site_key,
            "first_url": first_url,
            "final_url": data.get("href"),
            "title": data.get("title"),
            "body_len": data.get("body_len"),
            "has_session_cookie": bool(data.get("has_naver_session_cookie")),
            "has_logout": bool(data.get("has_logout")),
            "has_mypage_link": bool(data.get("has_mypage_link")),
            "has_user_menu": bool(data.get("has_user_menu")),
            "has_id_form": bool(data.get("has_id_form")),
            "has_pw_form": bool(data.get("has_pw_form")),
            "has_login_btn_to_nid": bool(data.get("has_login_btn")),
            "has_relogin_msg": bool(data.get("has_relogin_msg")),
            "policy_judge": state,
            "body_top": (data.get("body_top") or "")[:160],
        }
        results.append(out)
        print(json.dumps(out, ensure_ascii=False, indent=2))

    states = [r["policy_judge"] for r in results]
    if all(s == sep.STATE_LOGGED_IN for s in states):
        verdict = "PASS_NAVER_MAIN_FIRST_ALL_LOGGED_IN"
    elif sep.STATE_SESSION_EXPIRED in states:
        verdict = "WARN_SESSION_EXPIRED"
    elif sep.STATE_LOGIN_REQUIRED in states:
        verdict = "WARN_LOGIN_REQUIRED"
    else:
        verdict = "WARN_UNKNOWN_STATE"
    print("\n=== VERDICT ===")
    print(json.dumps({"verdict": verdict, "states": states}, ensure_ascii=False))

    # 탭 리셋
    _navigate(target_id, "about:blank")


if __name__ == "__main__":
    main()
