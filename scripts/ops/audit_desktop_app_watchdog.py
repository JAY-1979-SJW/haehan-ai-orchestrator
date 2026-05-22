"""audit_desktop_app_watchdog.py
데스크탑 앱 상시 감사 — 서버·CDP·WS·playwright 상태를 주기적으로 점검.

실행:
    python scripts/ops/audit_desktop_app_watchdog.py           # 기본 60초 간격
    python scripts/ops/audit_desktop_app_watchdog.py --once    # 1회 점검 후 종료
    python scripts/ops/audit_desktop_app_watchdog.py --interval 30

결과:
    data/logs/desktop_watchdog.log  — 상시 기록
    data/inspection/desktop_watchdog/latest.json — 최신 상태 JSON
"""
from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import socket
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
LOG_DIR  = ROOT / "data/logs"
OUT_DIR  = ROOT / "data/inspection/desktop_watchdog"
LOG_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 로깅 설정 ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            LOG_DIR / "desktop_watchdog.log",
            maxBytes=3 * 1024 * 1024, backupCount=3, encoding="utf-8"
        ),
    ],
)
log = logging.getLogger("watchdog")


# ── 개별 점검 함수 ─────────────────────────────────────────────────────────

def check_server() -> dict:
    try:
        r = urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=3)
        return {"ok": True, "status": r.status}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def check_cdp() -> dict:
    s = socket.socket(); s.settimeout(1)
    listening = s.connect_ex(("127.0.0.1", 9222)) == 0; s.close()
    if not listening:
        return {"ok": False, "listening": False}
    try:
        r = urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=3)
        ver = json.loads(r.read())
        return {"ok": True, "listening": True, "browser": ver.get("Browser", "?")}
    except Exception as e:
        return {"ok": False, "listening": True, "error": str(e)}


def check_ws() -> dict:
    import asyncio, websockets as _ws

    async def _connect():
        async with _ws.connect(
            "ws://127.0.0.1:8765/ws/ui",
            open_timeout=4,
            additional_headers={"Origin": "http://127.0.0.1:8765"},
        ) as ws:
            import json as _j
            await ws.send(_j.dumps({"action": "browser_status"}))
            resp = await asyncio.wait_for(ws.recv(), timeout=5)
            data = _j.loads(resp)
            return {
                "ok": True,
                "cdp_alive": data.get("cdp_alive"),
                "tab_count": data.get("tab_count"),
                "message": data.get("message_ko", ""),
            }

    try:
        return asyncio.run(_connect())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def check_playwright() -> dict:
    s = socket.socket(); s.settimeout(1)
    if s.connect_ex(("127.0.0.1", 9222)) != 0:
        s.close()
        return {"ok": False, "error": "CDP 9222 not listening"}
    s.close()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
            tabs = [{"title": p.title()[:40], "url": p.url[:60]}
                    for ctx in b.contexts for p in ctx.pages]
            b.close()
        return {"ok": True, "tab_count": len(tabs), "tabs": tabs}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── 1회 점검 ──────────────────────────────────────────────────────────────

def run_once() -> dict:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log.info("── 점검 시작 %s ──", ts)

    result = {
        "ts": ts,
        "server":     check_server(),
        "cdp":        check_cdp(),
        "ws":         check_ws(),
        "playwright": check_playwright(),
    }

    # 종합 판정
    ok_all = all(result[k]["ok"] for k in ("server", "cdp", "ws", "playwright"))
    result["verdict"] = "PASS" if ok_all else "WARN"

    # 출력
    sv  = result["server"]
    cdp = result["cdp"]
    ws  = result["ws"]
    pw  = result["playwright"]

    log.info("[서버 8765]   %s", "OK" if sv["ok"] else f"FAIL — {sv.get('error','')}")
    log.info("[CDP 9222]    %s  %s", "OK" if cdp["ok"] else "FAIL", cdp.get("browser", cdp.get("error", "")))
    log.info("[WS /ws/ui]   %s  cdp_alive=%s tab_count=%s", "OK" if ws["ok"] else f"FAIL — {ws.get('error','')}",
             ws.get("cdp_alive", "-"), ws.get("tab_count", "-"))
    log.info("[Playwright]  %s  tabs=%s", "OK" if pw["ok"] else f"FAIL — {pw.get('error','')}",
             pw.get("tab_count", "-"))

    if pw.get("tabs"):
        for t in pw["tabs"]:
            log.info("  탭: %s | %s", t["title"], t["url"])

    log.info("── 판정: %s ──", result["verdict"])

    # JSON 저장
    (OUT_DIR / "latest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    hist = OUT_DIR / f"watchdog_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    hist.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    return result


# ── 메인 루프 ─────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="1회 점검 후 종료")
    parser.add_argument("--interval", type=int, default=60, help="점검 간격(초), 기본 60")
    args = parser.parse_args()

    log.info("=== 데스크탑 앱 상시 감사 시작 (interval=%ds) ===", args.interval)

    while True:
        try:
            run_once()
        except Exception as e:
            log.error("점검 중 예외: %s", e)

        if args.once:
            break
        log.info("다음 점검까지 %d초 대기...", args.interval)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
