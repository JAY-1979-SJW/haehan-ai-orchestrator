"""Chrome 비밀번호 관리자에서 저장된 자격증명을 가져온다.

사용법:
    python scripts/auth/get_credential.py <도메인>
    예) python scripts/auth/get_credential.py gabia.com

동작 순서:
  1. CDP로 chrome://password-manager 열기
  2. 해당 도메인 항목 찾아서 클릭
  3. 비밀번호 표시 버튼 클릭 → Windows PIN 팝업 트리거
  4. 팝업 감지 → 사용자에게 PIN 입력 안내
  5. 팝업 닫힌 후 DOM에서 username/password 읽기
  6. JSON으로 출력
"""

from __future__ import annotations

import contextlib
import json
import sys
import time
import urllib.request
import uuid
from pathlib import Path

import websocket

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CDP_URL = "http://localhost:9222"


def _get_tabs() -> list[dict]:
    return json.loads(urllib.request.urlopen(f"{CDP_URL}/json").read())


def _find_or_create_pwmgr_tab() -> str:
    """chrome://password-manager 탭 ID 반환. 없으면 새로 연다."""
    tabs = _get_tabs()
    for t in tabs:
        if t.get("url", "").startswith("chrome://password-manager"):
            return t["id"]
    # 새 탭 생성
    resp = json.loads(urllib.request.urlopen(f"{CDP_URL}/json/new").read())
    return resp["id"]


def _ws_cmd(ws: websocket.WebSocket, method: str, params: dict | None = None) -> dict:
    mid = uuid.uuid4().int & 0xFFFFFF
    ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
    while True:
        r = json.loads(ws.recv())
        if r.get("id") == mid:
            return r


def _connect(tab_id: str) -> websocket.WebSocket:
    tabs = _get_tabs()
    ws_url = next(t["webSocketDebuggerUrl"] for t in tabs if t["id"] == tab_id)
    return websocket.create_connection(ws_url, timeout=15)


def _navigate_and_wait(ws: websocket.WebSocket, url: str, delay: float = 2.5) -> None:
    _ws_cmd(ws, "Page.navigate", {"url": url})
    time.sleep(delay)


def _eval(ws: websocket.WebSocket, expr: str, await_promise: bool = False) -> str | None:
    params: dict = {"expression": expr}
    if await_promise:
        params["awaitPromise"] = True
        params["timeout"] = 8000
    r = _ws_cmd(ws, "Runtime.evaluate", params)
    return r.get("result", {}).get("result", {}).get("value")


# ---------------------------------------------------------------------------
# Shadow DOM 유틸 — password-manager는 Web Components 기반
# ---------------------------------------------------------------------------
_FIND_ENTRY_JS = """(function(domain) {
    function walkShadow(root, depth) {
        if (!root || depth > 8) return null;
        var kids = root.shadowRoot ? [...root.shadowRoot.querySelectorAll('*')] : [...root.querySelectorAll('*')];
        for (var el of kids) {
            var txt = (el.textContent || '').trim();
            if (txt === domain || txt.includes(domain)) {
                var rect = el.getBoundingClientRect();
                if (rect.width > 10 && rect.height > 5 && rect.height < 100) {
                    return JSON.stringify({tag: el.tagName, x: Math.round(rect.x+rect.width/2), y: Math.round(rect.y+rect.height/2), text: txt.substring(0,60)});
                }
            }
            var found = walkShadow(el, depth+1);
            if (found) return found;
        }
        return null;
    }
    return walkShadow(document.body, 0);
})(%s)"""

_FIND_SHOW_BTN_JS = """(function() {
    // "비밀번호 표시" 또는 eye 아이콘 버튼 찾기 (shadow DOM 포함)
    function walk(root, depth) {
        if (!root || depth > 10) return null;
        var sr = root.shadowRoot;
        var children = sr ? [...sr.querySelectorAll('*')] : [...(root.children || [])];
        for (var el of children) {
            var aria = (el.getAttribute('aria-label') || '').toLowerCase();
            var title = (el.getAttribute('title') || '').toLowerCase();
            var txt = (el.textContent || '').trim().toLowerCase();
            if (aria.includes('show') || aria.includes('표시') || aria.includes('비밀번호') ||
                title.includes('show') || title.includes('표시') ||
                (el.tagName === 'CR-ICON-BUTTON' && (aria.includes('show') || aria.includes('visibility')))) {
                var rect = el.getBoundingClientRect();
                if (rect.width > 5 && rect.height > 5) {
                    return JSON.stringify({tag: el.tagName, x: Math.round(rect.x+rect.width/2), y: Math.round(rect.y+rect.height/2), aria: aria});
                }
            }
            var found = walk(el, depth+1);
            if (found) return found;
        }
        return null;
    }
    return walk(document.body, 0);
})()"""

_READ_CREDENTIAL_JS = """(function() {
    // 현재 페이지에서 username/password 값 읽기
    function walk(root, depth) {
        if (!root || depth > 10) return null;
        var sr = root.shadowRoot;
        var children = sr ? [...sr.querySelectorAll('*')] : [...(root.children || [])];
        var result = {};
        for (var el of children) {
            var val = el.value || '';
            var type = (el.type || '').toLowerCase();
            var aria = (el.getAttribute('aria-label') || '').toLowerCase();
            if (type === 'text' && val && (aria.includes('user') || aria.includes('사용자') || aria.includes('아이디') || aria.includes('이름'))) {
                result.username = val;
            }
            if ((type === 'password' || type === 'text') && val && (aria.includes('password') || aria.includes('비밀번호'))) {
                result.password = val;
            }
            var sub = walk(el, depth+1);
            if (sub) {
                if (!result.username && sub.username) result.username = sub.username;
                if (!result.password && sub.password) result.password = sub.password;
            }
        }
        return Object.keys(result).length ? result : null;
    }
    return JSON.stringify(walk(document.body, 0) || {});
})()"""


_GET_PASSWORD_LIST_JS = """new Promise((resolve) => {
    chrome.passwordsPrivate.getSavedPasswordList((entries) => {
        resolve(JSON.stringify(entries.map(e => ({
            id: e.id,
            username: e.username,
            urls: e.affiliatedDomains ? e.affiliatedDomains.map(d => d.name) : []
        }))));
    });
})"""

_REQUEST_PLAINTEXT_JS = """new Promise((resolve, reject) => {
    chrome.passwordsPrivate.requestPlaintextPassword(%d, 'VIEW', (plaintext) => {
        if (chrome.runtime.lastError) {
            reject(chrome.runtime.lastError.message);
        } else {
            resolve(plaintext);
        }
    });
})"""


def _match_domain(urls: list[str], domain: str) -> bool:
    dl = domain.lower()
    return any(dl in u.lower() or u.lower() in dl for u in urls)


def _request_plaintext_password(tab_id, match, password_result, eval_done):
    # 별도 WebSocket 연결 — PIN 입력 대기 동안 타임아웃 없이 유지
    ws2: websocket.WebSocket | None = None
    try:
        tabs2 = _get_tabs()
        ws_url2 = next(t["webSocketDebuggerUrl"] for t in tabs2 if t["id"] == tab_id)
        ws2 = websocket.create_connection(ws_url2, timeout=300)  # 5분
        js = _REQUEST_PLAINTEXT_JS % match["id"]
        r = _ws_cmd(
            ws2,
            "Runtime.evaluate",
            {
                "expression": js,
                "awaitPromise": True,
                "timeout": 240000,  # CDP 내부 타임아웃 4분
            },
        )
        val = r.get("result", {}).get("result", {}).get("value")
        if val is not None:
            password_result["password"] = val
        else:
            err = r.get("result", {}).get("exceptionDetails", {})
            print(f"[get_credential] 비밀번호 취득 실패: {err}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 - Chrome 저장 자격증명 조회 CLI - 사용자가 직접 실행, Windows PIN 팝업으로 본인 인증 필요. except는 WebSocket/CDP 통신 실패만 감싸며 로그에 예외 타입만 출력, 실제 조회 결과(JSON 출력)는 도구의 의도된 동작
        print(f"[get_credential] _request_password 오류: {exc}", file=sys.stderr)
    finally:
        if ws2:
            # WebSocket 연결 종료(cleanup) 실패는 무시 — 실제 조회 결과(JSON 출력)와 무관
            with contextlib.suppress(Exception):
                ws2.close()
        eval_done.set()


def get_credential(domain: str) -> dict:
    from scripts.browser.popup.windows_auth_popup_monitor import (
        notify_user,
        wait_for_popup,
        wait_for_popup_close,
    )

    tab_id = _find_or_create_pwmgr_tab()
    ws = _connect(tab_id)

    try:
        # 1. chrome://password-manager로 이동
        _navigate_and_wait(ws, "chrome://password-manager/passwords", delay=2.0)

        # 2. passwordsPrivate API로 저장 목록 조회
        list_json = _eval(ws, _GET_PASSWORD_LIST_JS, await_promise=True)
        if not list_json:
            print("[get_credential] ERROR: 비밀번호 목록 조회 실패", file=sys.stderr)
            return {}

        entries = json.loads(list_json)
        match = next((e for e in entries if _match_domain(e["urls"], domain)), None)
        if not match:
            print(
                f"[get_credential] '{domain}' 항목 없음. 저장된 도메인: "
                + ", ".join(u for e in entries for u in e["urls"]),
                file=sys.stderr,
            )
            return {}

        print(
            f"[get_credential] 항목 발견: id={match['id']}, username={match['username']}, urls={match['urls']}",
            file=sys.stderr,
        )

        # 3. requestPlaintextPassword → Windows PIN 팝업 트리거
        print("[get_credential] 비밀번호 열람 요청 (Windows 인증 팝업 예상)...", file=sys.stderr)

        # 팝업 감지를 백그라운드에서 시작하기 위해 비동기 요청 먼저
        # JS 평가는 팝업이 뜨면 block되므로 별도 스레드로 실행
        import threading

        password_result: dict = {}
        eval_done = threading.Event()

        t = threading.Thread(
            target=_request_plaintext_password,
            args=(tab_id, match, password_result, eval_done),
            daemon=True,
        )
        t.start()

        # 4. 팝업 감지 → 사용자 안내
        # requestPlaintextPassword 직후 팝업이 이미 떠있을 수 있으므로
        # 짧은 간격으로 먼저 체크 후, 없으면 최대 60초 대기
        from scripts.browser.popup.windows_auth_popup_monitor import (
            notify_popup_gone,
            wait_for_popup,
            wait_for_popup_close,
        )

        print("[get_credential] Windows 인증 팝업 감지 대기 (최대 60초)...", file=sys.stderr)
        popup_appeared = wait_for_popup(timeout=60.0, poll=0.2)

        if popup_appeared:
            stop_beep = notify_user(domain)  # 알림음 시작, stop_evt 반환
            print("[get_credential] 팝업 감지됨 — PIN 입력 대기 (최대 180초)...", file=sys.stderr)
            wait_for_popup_close(timeout=180.0)
            if stop_beep is not None:
                stop_beep.set()  # 알림음 중단
            notify_popup_gone(domain)
            time.sleep(1.0)
        else:
            print(
                "[get_credential] 팝업 미감지 (60초 경과) — "
                "requestPlaintextPassword가 인증 없이 완료되었거나 팝업 제목이 다를 수 있음",
                file=sys.stderr,
            )

        eval_done.wait(timeout=15.0)

        cred = {
            "username": match["username"],
            "password": password_result.get("password", ""),
            "domain": domain,
        }
        return cred

    finally:
        ws.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/auth/get_credential.py <domain>")
        sys.exit(1)

    domain = sys.argv[1]
    result = get_credential(domain)
    print(json.dumps(result, ensure_ascii=False, indent=2))
