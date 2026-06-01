"""Haehan AI 로컬 CDP 에이전트.

서버 WebSocket에 연결해서 CDP 명령을 수신하고 로컬 Chrome에서 실행합니다.

실행:
    python scripts/local_agent.py --license <LICENSE_KEY> --server wss://autowork.haehan-ai.kr
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

ROOT = Path(__file__).resolve().parents[1]
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

            if name == "collect_products":
                import time as _t

                from scripts.naver.smartstore import NaverSmartStore

                t0 = _t.monotonic()
                result = NaverSmartStore(page).list_products(limit=inputs.get("limit", 50))
                result["duration_ms"] = int((_t.monotonic() - t0) * 1000)
                # 서버 캐시 저장 (선택)
                return result

            if name == "collect_orders":
                from scripts.naver.smartstore import NaverSmartStore

                return NaverSmartStore(page).list_orders(limit=inputs.get("limit", 50))

            if name == "collect_settlements":
                from scripts.naver.smartstore import NaverSmartStore

                return NaverSmartStore(page).list_settlements(limit=inputs.get("limit", 30))

            if name == "collect_reviews":
                from scripts.naver.smartstore import NaverSmartStore

                return NaverSmartStore(page).list_reviews(limit=inputs.get("limit", 30))

            if name == "collect_stats":
                from scripts.naver.smartstore import NaverSmartStore

                return NaverSmartStore(page).stats()

            if name == "open_seller_center":
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

            if name == "auto_register_product":
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

            if name == "edit_product":
                from scripts.naver.smartstore.product.form_runner import ProductFormRunner

                product_id = inputs.get("product_id")
                fields = {k: v for k, v in inputs.items() if k != "product_id"}
                fields["save"] = False
                ed_page = next((p for p in ctx.pages if f"products/{product_id}" in p.url), None) or ctx.new_page()
                ed_page.bring_to_front()
                result = ProductFormRunner(ed_page).edit(product_id, fields)
                return {**result, "dry_run": True}

            if name == "popup_handle":
                from scripts.naver.smartstore.navigation.cdp_popup_manager import CdpPopupManager

                mgr = CdpPopupManager()
                mgr.unblock(ctx, origin="https://sell.smartstore.naver.com")
                return mgr.handle_page(page, auto_confirm=True)

            return {"ok": False, "error": f"알 수 없는 도구: {name}"}

    except Exception as e:
        return {"ok": False, "error": str(e), "hint": "로컬 Chrome CDP가 실행 중인지 확인하세요"}


# ── WebSocket 에이전트 ────────────────────────────────────────────────────────


def run_agent(server_url: str, license_key: str, retry_interval: int = 5):
    ws_url = f"{server_url}/api/v1/smartstore/agent/ws?license={license_key}"
    print(f"[에이전트] 서버 연결 중: {ws_url}")

    def on_message(ws, message):
        try:
            msg = json.loads(message)
            if msg.get("type") == "connected":
                print(f"[에이전트] 연결됨 — agent_id={msg.get('agent_id')} plan={msg.get('plan')}")
                return

            if msg.get("type") == "tool_call":
                req_id = msg["request_id"]
                tool = msg["tool"]
                inputs = msg.get("inputs", {})
                print(f"[에이전트] 도구 실행: {tool} {inputs}")
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
        except Exception as e:
            print(f"[에이전트] 오류: {e}")
            traceback.print_exc()

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
        except Exception as e:
            print(f"[에이전트] 예외: {e}")
        time.sleep(retry_interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Haehan AI 로컬 CDP 에이전트")
    parser.add_argument("--license", required=True, help="라이선스 키")
    parser.add_argument("--server", default="wss://autowork.haehan-ai.kr", help="서버 WS URL")
    parser.add_argument("--retry", type=int, default=5, help="재연결 대기(초)")
    parser.add_argument("--parent-pid", type=int, default=0, help="부모(Electron) PID — 종료 시 자동 종료")
    args = parser.parse_args()

    if args.parent_pid:
        _watch_parent(args.parent_pid)

    run_agent(args.server, args.license, args.retry)
