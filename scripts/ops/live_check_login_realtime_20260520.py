"""ORCHESTRATOR_LOGIN_FLOW_LIVE_CHECK — A + B + C 실시간 감시.

A: /ws/ui WS 이벤트 tail (login_state_change / login_action_started /
   login_target_selected / logged_in_detected / command_auto_resumed /
   popup_detected / challenge_required / browser_action_result)
B: CDP /json/list 1초 폴링 — target id/url/title diff
C: 로그인 페이지 Runtime.evaluate 폴링 — 로그인 진행/실패/추가인증 문구

보안:
- 쿠키/토큰/PW/OTP 원문 절대 출력 금지
- 세션 추정은 'has_session_cookie: bool' 만
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import urllib.request

import websockets

CDP_PORT = 9222
WS_URL = "ws://127.0.0.1:8765/ws/ui"

WS_TYPES = {
    "browser_start_result",
    "browser_status",
    "tab_list",
    "tab_added",
    "tab_removed",
    "tab_updated",
    "browser_action_started",
    "browser_action_completed",
    "browser_action_result",
    "login_state_change",
    "login_state_changed",
    "login_action_started",
    "login_target_selected",
    "logged_in_detected",
    "command_auto_resumed",
    "popup_detected",
    "popup_closed",
    "auth_popup_detected",
    "challenge_required",
}

# 로그인 완료 신호 (URL/HTML 패턴)
LOGGED_IN_URL_HINT = ("www.naver.com", "/main", "mypage", "section.blog")
ERR_PHRASES = (
    "비밀번호",
    "아이디",
    "확인",
    "재시도",
    "잠금",
    "보안",
    "캡차",
    "captcha",
    "차단",
    "오류",
    "다시 시도",
)
CHALLENGE_PHRASES = (
    "SMS",
    "휴대전화",
    "추가 인증",
    "본인 확인",
    "보안 인증",
    "QR",
    "이메일 인증",
    "OTP",
)


def fetch_targets() -> list[dict]:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{CDP_PORT}/json/list",
            timeout=1.0,
        ) as r:
            data = json.loads(r.read().decode("utf-8") or "[]")
    except Exception:  # noqa: BLE001 - 로그인 흐름 실시간 감시(WS/CDP 읽기전용) - 쿠키/토큰 원문 출력 금지 명시, 예외 시 빈 목록/False/타임아웃 반환
        return []
    return [t for t in data if isinstance(t, dict)]


def activate_target(target_id: str) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{CDP_PORT}/json/activate/{target_id}",
            timeout=1.0,
        ):
            return True
    except Exception:  # noqa: BLE001 - 로그인 흐름 실시간 감시(WS/CDP 읽기전용) - 쿠키/토큰 원문 출력 금지 명시, 예외 시 빈 목록/False/타임아웃 반환
        return False


async def _eval_on_target(ws_url: str, expr: str) -> dict | None:
    import websockets as _ws

    try:
        async with _ws.connect(ws_url, max_size=4 * 1024 * 1024) as conn:
            await conn.send(
                json.dumps(
                    {
                        "id": 1,
                        "method": "Runtime.evaluate",
                        "params": {"expression": expr, "returnByValue": True},
                    }
                )
            )
            raw = await asyncio.wait_for(conn.recv(), timeout=3.0)
            r = json.loads(raw)
            return r.get("result", {}).get("result", {}).get("value")
    except Exception as exc:  # noqa: BLE001 - 로그인 흐름 실시간 감시(WS/CDP 읽기전용) - 쿠키/토큰 원문 출력 금지 명시, 예외 시 빈 목록/False/타임아웃 반환
        return {"_err": str(exc)[:120]}


PAGE_EXPR = r"""
(() => {
  const txt = (document.body && document.body.innerText) || "";
  const err_phrases = ["비밀번호","아이디","확인","재시도","잠금","보안","캡차","captcha","차단","오류","다시 시도"];
  const ch_phrases = ["SMS","휴대전화","추가 인증","본인 확인","보안 인증","QR","이메일 인증","OTP"];
  function pick(arr){ const hits=[]; for(const p of arr){ if(txt.indexOf(p)>=0) hits.push(p);} return hits;}
  const has_id_form = !!document.querySelector('#id, input[name="id"]');
  const has_pw_form = !!document.querySelector('#pw, input[name="pw"], input[type="password"]');
  const has_login_btn = !!document.querySelector('.btn_login, button[type="submit"]');
  // 로그인 완료 signal (naver 메인/마이페이지/프로필)
  const has_logout = /로그아웃/.test(txt);
  const has_mypage = /마이페이지|MY|내 정보/.test(txt);
  const has_profile_link = !!document.querySelector('a[href*="mypage"], a[href*="logout"]');
  // 쿠키 존재 여부만 (값 출력 금지)
  const cookies = document.cookie || "";
  const has_naver_session_cookie = /NID_SES|NID_AUT|NID_JKL/.test(cookies);
  return JSON.stringify({
    href: location.href,
    title: document.title,
    has_id_form,
    has_pw_form,
    has_login_btn,
    has_logout,
    has_mypage,
    has_profile_link,
    has_naver_session_cookie,
    err_hits: pick(err_phrases),
    challenge_hits: pick(ch_phrases),
    body_len: txt.length,
  });
})()
"""


async def ws_tail() -> None:
    try:
        async with websockets.connect(WS_URL, max_size=4 * 1024 * 1024) as conn:
            print(f"[A] WS connected {WS_URL}", flush=True)
            while True:
                raw = await conn.recv()
                try:
                    ev = json.loads(raw)
                except Exception:  # noqa: BLE001 - 로그인 흐름 실시간 감시(WS/CDP 읽기전용) - 쿠키/토큰 원문 출력 금지 명시, 예외 시 빈 목록/False/타임아웃 반환
                    continue
                et = ev.get("type", "")
                if et in WS_TYPES:
                    # 민감 키 제거
                    safe = {k: v for k, v in ev.items() if k not in ("cookies", "token", "auth")}
                    print(f"[A] {et} :: {json.dumps(safe, ensure_ascii=False)[:400]}", flush=True)
                elif et == "system":
                    # 노이즈성 reconnect 메시지는 1회만
                    pass
    except Exception as exc:  # noqa: BLE001 - 로그인 흐름 실시간 감시(WS/CDP 읽기전용) - 쿠키/토큰 원문 출력 금지 명시, 예외 시 빈 목록/False/타임아웃 반환
        print(f"[A] WS error: {exc}", flush=True)


async def cdp_poll() -> None:
    prev: dict[str, tuple[str, str]] = {}  # tid -> (url, title)
    activated_once: set[str] = set()
    while True:
        rows = fetch_targets()
        cur: dict[str, tuple[str, str]] = {}
        for t in rows:
            if t.get("type") != "page":
                continue
            tid = t.get("id", "")
            cur[tid] = (t.get("url", ""), t.get("title", ""))
        # 새 target
        for tid, (u, ti) in cur.items():
            if tid not in prev:
                print(f"[B] +tab id={tid[:8]} url={u[:120]} title={ti[:60]}", flush=True)
                # 처음 본 nid.naver 타겟은 앞으로 가져오기
                if "nid.naver.com" in u and tid not in activated_once:
                    ok = activate_target(tid)
                    activated_once.add(tid)
                    print(f"[B] activateTarget({tid[:8]}) → {ok}", flush=True)
            else:
                pu, pti = prev[tid]
                if pu != u:
                    print(f"[B] url id={tid[:8]} {pu[:80]} -> {u[:120]}", flush=True)
                if pti != ti:
                    print(f"[B] title id={tid[:8]} {pti[:40]} -> {ti[:80]}", flush=True)
        # 제거 target
        for tid in prev:
            if tid not in cur:
                print(f"[B] -tab id={tid[:8]}", flush=True)
        prev = cur
        await asyncio.sleep(1.0)


async def page_poll() -> None:
    last_sig = ""
    while True:
        rows = fetch_targets()
        # nid.naver 또는 가장 최근 page target 선택
        target = None
        for t in rows:
            if t.get("type") == "page" and "naver.com" in t.get("url", ""):
                target = t
                break
        if target is None:
            for t in rows:
                if t.get("type") == "page" and t.get("url", "") != "about:blank":
                    target = t
                    break
        if target is None:
            await asyncio.sleep(1.0)
            continue
        ws_url = target.get("webSocketDebuggerUrl", "")
        if not ws_url:
            await asyncio.sleep(1.0)
            continue
        val = await _eval_on_target(ws_url, PAGE_EXPR)
        if not val:
            await asyncio.sleep(1.0)
            continue
        if isinstance(val, dict) and val.get("_err"):
            print(f"[C] eval_err: {val['_err']}", flush=True)
            await asyncio.sleep(1.0)
            continue
        try:
            data = json.loads(val) if isinstance(val, str) else val
        except Exception:  # noqa: BLE001 - 로그인 흐름 실시간 감시(WS/CDP 읽기전용) - 쿠키/토큰 원문 출력 금지 명시, 예외 시 빈 목록/False/타임아웃 반환
            data = {"raw": str(val)[:200]}
        sig = (
            f"{data.get('href', '')}|{data.get('title', '')}|"
            f"{int(bool(data.get('has_logout')))}|{int(bool(data.get('has_naver_session_cookie')))}|"
            f"{','.join(data.get('err_hits') or [])}|{','.join(data.get('challenge_hits') or [])}"
        )
        if sig != last_sig:
            # 판정 라벨
            label = "LOGIN_REQUIRED"
            if data.get("has_logout") or data.get("has_naver_session_cookie"):
                label = "LOGGED_IN_LIKELY"
            elif data.get("challenge_hits"):
                label = "CHALLENGE_REQUIRED"
            elif data.get("err_hits"):
                label = "LOGIN_ERROR_SHOWN"
            print(
                f"[C] {label} href={data.get('href', '')[:120]} title={data.get('title', '')[:60]} "
                f"id_form={data.get('has_id_form')} pw_form={data.get('has_pw_form')} "
                f"logout={data.get('has_logout')} mypage={data.get('has_mypage')} "
                f"session_cookie={data.get('has_naver_session_cookie')} "
                f"err={data.get('err_hits')} challenge={data.get('challenge_hits')}",
                flush=True,
            )
            last_sig = sig
        await asyncio.sleep(1.0)


async def main() -> None:
    print("[boot] A+B+C realtime monitor 시작 — Ctrl+C 또는 timeout 으로 종료", flush=True)
    await asyncio.gather(ws_tail(), cdp_poll(), page_poll())


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
