"""Haehan AI 로컬 CDP 에이전트.

서버 WebSocket에 연결해서 CDP 명령을 수신하고 로컬 Chrome에서 실행합니다.

실행:
    python core/agent_runtime/runtime/local_agent.py --license <LICENSE_KEY> --server wss://autowork.haehan-ai.kr
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import traceback
from pathlib import Path

_BOOT = Path(__file__).resolve().parents[3]  # 정본을 import 하기 전 sys.path 부트스트랩(G5 예외: scripts/ 독립 실행)
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402

ROOT = repo_root()
sys.path.insert(0, str(ROOT))


def _parent_alive(pid: int) -> bool:
    """부모 프로세스(Electron) 생존 여부."""
    if pid <= 0:
        return True
    if sys.platform == "win32":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        k = ctypes.windll.kernel32
        handle = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(handle, ctypes.byref(code))
        k.CloseHandle(handle)
        return bool(ok) and code.value == STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _watch_parent(parent_pid: int, interval: int = 3) -> None:
    """부모 PID가 사라지면 에이전트를 즉시 종료 (고아 프로세스 방지).

    Electron이 정상 종료 시엔 taskkill로 정리되지만, 강제 종료·크래시 시
    before-quit가 실행되지 않아 고아가 남던 문제를 막는다.
    """

    def loop():
        while True:
            if not _parent_alive(parent_pid):
                print("[에이전트] 부모 프로세스 종료 감지 — 자동 종료")
                os._exit(0)
            time.sleep(interval)

    threading.Thread(target=loop, daemon=True).start()


try:
    import websocket  # pip install websocket-client
except ImportError:
    print("[ERROR] websocket-client 미설치: pip install websocket-client")
    sys.exit(1)

# ── CDP 도구 실행 ─────────────────────────────────────────────────────────────


# tool → 소속 사이트(site_id). 미등록 tool은 None(=제한 안 받음).
_TOOL_SITE: dict[str, str] = {
    "collect_products": "naver",
    "collect_orders": "naver",
    "collect_settlements": "naver",
    "collect_reviews": "naver",
    "collect_stats": "naver",
    "open_seller_center": "naver",
    "auto_register_product": "naver",
    "edit_product": "naver",
    "popup_handle": "naver",
}


def _site_allowed(tool: str, enabled_sites: set[str] | None) -> bool:
    """enabled_sites 가 비어있으면 제한 없음(기존/owner 보존).
    값이 있으면 tool 소속 사이트가 목록에 있을 때만 허용. 미등록 tool은 항상 허용.
    """
    if not enabled_sites:
        return True
    site = _TOOL_SITE.get(tool)
    if site is None:
        return True
    return site in enabled_sites


def _tool_collect_products(page, ctx, inputs: dict) -> dict:
    import time as _t

    from scripts.naver.smartstore import NaverSmartStore

    t0 = _t.monotonic()
    result = NaverSmartStore(page).list_products(limit=inputs.get("limit", 50))
    result["duration_ms"] = int((_t.monotonic() - t0) * 1000)
    # 서버 캐시 저장 (선택)
    return result


def _tool_collect_orders(page, ctx, inputs: dict) -> dict:
    from scripts.naver.smartstore import NaverSmartStore

    return NaverSmartStore(page).list_orders(limit=inputs.get("limit", 50))


def _tool_collect_settlements(page, ctx, inputs: dict) -> dict:
    from scripts.naver.smartstore import NaverSmartStore

    return NaverSmartStore(page).list_settlements(limit=inputs.get("limit", 30))


def _tool_collect_reviews(page, ctx, inputs: dict) -> dict:
    from scripts.naver.smartstore import NaverSmartStore

    return NaverSmartStore(page).list_reviews(limit=inputs.get("limit", 30))


def _tool_collect_stats(page, ctx, inputs: dict) -> dict:
    from scripts.naver.smartstore import NaverSmartStore

    return NaverSmartStore(page).stats()


def _tool_open_seller_center(page, ctx, inputs: dict) -> dict:
    URLS = {
        "dashboard": "https://sell.smartstore.naver.com/#/home/dashboard",
        "list": "https://sell.smartstore.naver.com/#/products/list",
        "register": "https://sell.smartstore.naver.com/#/products/new",
        "orders": "https://sell.smartstore.naver.com/#/order/list",
        "settlement": "https://sell.smartstore.naver.com/#/settlement/main",
        "reviews": "https://sell.smartstore.naver.com/#/review/list",
        "stats": "https://sell.smartstore.naver.com/#/analytics/dashboard",
    }
    url = URLS.get(inputs.get("page_key", "dashboard"))
    if not url:
        return {"ok": False, "error": f"알 수 없는 page_key: {inputs.get('page_key')}"}
    page.bring_to_front()
    page.goto(url, timeout=15000, wait_until="domcontentloaded")
    return {"ok": True, "url": url}


def _tool_auto_register_product(page, ctx, inputs: dict) -> dict:
    from scripts.naver.smartstore.product.form_runner import ProductFormRunner

    data = {**inputs, "save": False, "require_confirm": False}
    REGISTER_URL = "https://sell.smartstore.naver.com/#/products/create"
    reg_page = next((p for p in ctx.pages if "products/create" in p.url), None)
    if not reg_page:
        reg_page = ctx.new_page()
        reg_page.goto(REGISTER_URL, timeout=20000, wait_until="domcontentloaded")
    reg_page.bring_to_front()
    result = ProductFormRunner(reg_page).run(data, skip_open=True)
    return {**result, "dry_run": True}


def _tool_edit_product(page, ctx, inputs: dict) -> dict:
    from scripts.naver.smartstore.product.form_runner import ProductFormRunner

    product_id = inputs.get("product_id")
    # ws tool_call 메시지의 inputs 는 검증 없이 그대로 들어온다 — ai_orchestrator/server/
    # mcp_server.py 의 자매 구현 _edit_product() 는 product_id 누락을 미리 막는데(MCP
    # inputSchema 도 required 선언) 이 local_agent 경로엔 그 가드가 없어 누락되면 그대로
    # ProductFormRunner.edit(None, ...) 까지 흘러갔다(앱 결함). 같은 가드를 추가.
    if not product_id:
        return {"ok": False, "error": "product_id 필수"}
    fields = {k: v for k, v in inputs.items() if k != "product_id"}
    fields["save"] = False
    ed_page = next((p for p in ctx.pages if f"products/{product_id}" in p.url), None) or ctx.new_page()
    ed_page.bring_to_front()
    result = ProductFormRunner(ed_page).edit(product_id, fields)
    return {**result, "dry_run": True}


def _tool_popup_handle(page, ctx, inputs: dict) -> dict:
    from scripts.naver.smartstore.navigation.cdp_popup_manager import CdpPopupManager

    mgr = CdpPopupManager()
    mgr.unblock(ctx, origin="https://sell.smartstore.naver.com")
    return mgr.handle_page(page, auto_confirm=True)


_CDP_TOOL_HANDLERS = {
    "collect_products": _tool_collect_products,
    "collect_orders": _tool_collect_orders,
    "collect_settlements": _tool_collect_settlements,
    "collect_reviews": _tool_collect_reviews,
    "collect_stats": _tool_collect_stats,
    "open_seller_center": _tool_open_seller_center,
    "auto_register_product": _tool_auto_register_product,
    "edit_product": _tool_edit_product,
    "popup_handle": _tool_popup_handle,
}


def _run_cdp_tool(name: str, inputs: dict) -> dict:
    """로컬 Chrome CDP에서 도구를 실행합니다."""
    try:
        from playwright.sync_api import sync_playwright

        cdp = "http://127.0.0.1:9222"

        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(cdp)
            ctx = browser.contexts[0]
            page = ctx.pages[0]

            sys.path.insert(0, str(ROOT))

            handler = _CDP_TOOL_HANDLERS.get(name)
            if handler is not None:
                return handler(page, ctx, inputs)

            return {"ok": False, "error": f"알 수 없는 도구: {name}"}

    except Exception as e:  # noqa: BLE001 - 로컬 에이전트 CDP 명령 실행/WebSocket 루프 — 알 수 없는 도구 호출 실패는 에러 dict로 반환, 루프 중 예외는 로그 남기고 재시도 대기 후 계속(무한 크래시 방지용 방어 코드)
        return {"ok": False, "error": str(e), "hint": "로컬 Chrome CDP가 실행 중인지 확인하세요"}


# ── WebSocket 에이전트 ────────────────────────────────────────────────────────


def _handle_tool_call(ws, msg: dict, enabled_sites: set[str] | None) -> None:
    """서버의 tool_call 메시지를 실행하고 tool_result 로 응답."""
    req_id = msg["request_id"]
    tool = msg["tool"]
    inputs = msg.get("inputs", {})
    print(f"[에이전트] 도구 실행: {tool} {inputs}")
    if not _site_allowed(tool, enabled_sites):
        site = _TOOL_SITE.get(tool, tool)
        print(f"[에이전트] 거부: '{site}' 사이트 미활성")
        result = {
            "ok": False,
            "error": "site_not_enabled",
            "site": site,
            "hint": f"'{site}' 사이트가 활성화되지 않았습니다. 사이트 설정에서 켜세요.",
        }
    else:
        result = _run_cdp_tool(tool, inputs)
    print(f"[에이전트] 결과: ok={result.get('ok')}")
    ws.send(
        json.dumps(
            {
                "type": "tool_result",
                "request_id": req_id,
                "result": result,
            }
        )
    )


def _on_agent_message(ws, message, enabled_sites: set[str] | None) -> None:
    """WebSocket 메시지 1건 처리. 예외는 로그만 남기고 삼킨다."""
    try:
        msg = json.loads(message)
        if msg.get("type") == "connected":
            print(f"[에이전트] 연결됨 — agent_id={msg.get('agent_id')} plan={msg.get('plan')}")
            return

        if msg.get("type") == "tool_call":
            _handle_tool_call(ws, msg, enabled_sites)
    except Exception as e:  # noqa: BLE001 - 로컬 에이전트 CDP 명령 실행/WebSocket 루프 — 알 수 없는 도구 호출 실패는 에러 dict로 반환, 루프 중 예외는 로그 남기고 재시도 대기 후 계속(무한 크래시 방지용 방어 코드)
        print(f"[에이전트] 오류: {e}")
        traceback.print_exc()


def run_agent(server_url: str, license_key: str, retry_interval: int = 5, enabled_sites: set[str] | None = None):
    ws_url = f"{server_url}/api/v1/smartstore/agent/ws?license={license_key}"
    print(f"[에이전트] 서버 연결 중: {ws_url}")
    if enabled_sites:
        print(f"[에이전트] 활성 사이트 제한: {sorted(enabled_sites)}")

    def on_message(ws, message):
        _on_agent_message(ws, message, enabled_sites)

    def on_error(ws, error):
        print(f"[에이전트] WS 오류: {error}")

    def on_close(ws, code, msg):
        print(f"[에이전트] 연결 종료 ({code}) — {retry_interval}초 후 재연결")

    while True:
        try:
            ws = websocket.WebSocketApp(
                ws_url,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )
            ws.run_forever(ping_interval=30, ping_timeout=10)
        except KeyboardInterrupt:
            print("[에이전트] 종료")
            break
        except Exception as e:  # noqa: BLE001 - 로컬 에이전트 CDP 명령 실행/WebSocket 루프 — 알 수 없는 도구 호출 실패는 에러 dict로 반환, 루프 중 예외는 로그 남기고 재시도 대기 후 계속(무한 크래시 방지용 방어 코드)
            print(f"[에이전트] 예외: {e}")
        time.sleep(retry_interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Haehan AI 로컬 CDP 에이전트")
    parser.add_argument("--license", required=True, help="라이선스 키")
    parser.add_argument("--server", default="wss://autowork.haehan-ai.kr", help="서버 WS URL")
    parser.add_argument("--retry", type=int, default=5, help="재연결 대기(초)")
    parser.add_argument("--parent-pid", type=int, default=0, help="부모(Electron) PID — 종료 시 자동 종료")
    parser.add_argument("--enabled-sites", default="", help="활성 사이트 id 쉼표목록(비면 제한 없음)")
    args = parser.parse_args()

    if args.parent_pid:
        _watch_parent(args.parent_pid)

    enabled = {s.strip() for s in args.enabled_sites.split(",") if s.strip()}
    run_agent(args.server, args.license, args.retry, enabled_sites=enabled)
