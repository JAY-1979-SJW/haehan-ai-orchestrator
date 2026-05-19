"""
desktop/audit_desktop.py — 데스크 앱 상시 감사 스크립트

실행:
    python -m desktop.audit_desktop           # 1회 감사
    python -m desktop.audit_desktop --watch   # 60초 주기 상시 감사
    python -m desktop.audit_desktop --dry     # dry-run (수정 없이 판정만)

판정 기준:
    PASS  — 모든 항목 정상
    WARN  — 일부 항목 비정상이지만 앱 동작 가능
    FAIL  — 앱 동작 불가 수준 이상
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import socket
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
UI_DIST = Path(__file__).parent / "ui_dist"
LOG_FILE = ROOT / "data" / "logs" / "app.log"
LOCAL_URL = "http://127.0.0.1:8765"
WS_URL    = "ws://127.0.0.1:8765/ws/ui"
PROXY_URL = f"{LOCAL_URL}/proxy/admin/"
AUTOWORK  = "https://autowork.haehan-ai.kr"

Status = Literal["PASS", "WARN", "FAIL"]


@dataclass
class AuditItem:
    name: str
    status: Status
    detail: str


@dataclass
class AuditReport:
    items: list[AuditItem] = field(default_factory=list)
    ts: float = field(default_factory=time.time)

    def add(self, name: str, status: Status, detail: str) -> None:
        self.items.append(AuditItem(name, status, detail))

    @property
    def verdict(self) -> Status:
        if any(i.status == "FAIL" for i in self.items): return "FAIL"
        if any(i.status == "WARN" for i in self.items): return "WARN"
        return "PASS"

    def print(self) -> None:
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.ts))
        print(f"\n{'='*52}")
        print(f"  데스크 앱 감사 리포트  {ts}")
        print(f"{'='*52}")
        for item in self.items:
            icon = {"PASS": "✅", "WARN": "⚠️ ", "FAIL": "❌"}[item.status]
            print(f"  {icon} [{item.status}] {item.name}")
            if item.status != "PASS":
                print(f"        → {item.detail}")
        print(f"{'='*52}")
        verdict_icon = {"PASS": "✅", "WARN": "⚠️ ", "FAIL": "❌"}[self.verdict]
        print(f"  최종 판정: {verdict_icon} {self.verdict}")
        print(f"{'='*52}\n")


# ── 개별 감사 항목 ────────────────────────────────────────────────────────────

def audit_port(report: AuditReport) -> None:
    """포트 8765 LISTENING 확인."""
    try:
        s = socket.create_connection(("127.0.0.1", 8765), timeout=2)
        s.close()
        report.add("포트 8765 LISTENING", "PASS", "")
    except OSError:
        report.add("포트 8765 LISTENING", "FAIL", "local_server가 실행되지 않음")


def audit_static(report: AuditReport) -> None:
    """index.html 서빙 및 타이틀 확인."""
    try:
        with urllib.request.urlopen(f"{LOCAL_URL}/", timeout=5) as r:
            body = r.read().decode(errors="ignore")
        if "Haehan AI" in body:
            report.add("index.html 서빙", "PASS", "")
        else:
            report.add("index.html 서빙", "WARN", "타이틀 'Haehan AI' 미확인")
    except Exception as e:
        report.add("index.html 서빙", "FAIL", str(e))


def audit_ui_dist(report: AuditReport) -> None:
    """ui_dist 빌드 결과물 존재 확인."""
    js_files = list(UI_DIST.glob("assets/*.js"))
    css_files = list(UI_DIST.glob("assets/*.css"))
    if js_files and css_files:
        js_kb = js_files[0].stat().st_size // 1024
        report.add("ui_dist 빌드", "PASS", f"JS {js_kb}KB")
    else:
        report.add("ui_dist 빌드", "FAIL", f"JS={len(js_files)}개 CSS={len(css_files)}개 — npm run build 필요")


def audit_proxy(report: AuditReport) -> None:
    """프록시 /proxy/admin/ 응답 및 X-Frame-Options 제거 확인."""
    try:
        req = urllib.request.Request(PROXY_URL)
        with urllib.request.urlopen(req, timeout=10) as r:
            xfo = r.headers.get("X-Frame-Options", "")
            body = r.read(100).decode(errors="ignore")
        if xfo:
            report.add("프록시 X-Frame-Options 제거", "FAIL", f"헤더 여전히 존재: {xfo}")
        elif "<!DOCTYPE" in body or "<html" in body.lower():
            report.add("프록시 X-Frame-Options 제거", "PASS", "헤더 제거됨, HTML 정상")
        else:
            report.add("프록시 X-Frame-Options 제거", "WARN", f"예상치 않은 응답: {body[:60]}")
    except Exception as e:
        report.add("프록시 X-Frame-Options 제거", "WARN", f"autowork 미응답 또는 서버 미기동: {e}")


def audit_log_file(report: AuditReport) -> None:
    """app.log 존재 및 최근 1시간 내 기록 확인."""
    if not LOG_FILE.exists():
        report.add("app.log 존재", "WARN", f"{LOG_FILE} 없음")
        return
    stat = LOG_FILE.stat()
    age_h = (time.time() - stat.st_mtime) / 3600
    if age_h < 1:
        report.add("app.log 최신성", "PASS", f"최근 {age_h*60:.0f}분 전 갱신")
    elif age_h < 24:
        report.add("app.log 최신성", "WARN", f"{age_h:.1f}시간 전 마지막 기록")
    else:
        report.add("app.log 최신성", "WARN", f"{age_h:.0f}시간 전 — 앱이 오래 미실행")


async def audit_websocket(report: AuditReport) -> None:
    """WebSocket 연결 및 메뉴 로드 확인."""
    try:
        import websockets  # type: ignore
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"action": "load_menu", "user_id": "default", "role": "admin"}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            items = resp.get("items", [])
            sections = {i.get("section") for i in items}
            required = {"AI 대화", "업무 조회", "관리 웹", "시스템"}
            missing = required - sections
            if missing:
                report.add("WebSocket 메뉴", "WARN", f"누락 섹션: {missing}")
            else:
                report.add("WebSocket 메뉴", "PASS", f"{len(items)}개 항목, 4개 섹션")
    except Exception as e:
        report.add("WebSocket 메뉴", "FAIL", str(e))


def audit_settings_file(report: AuditReport) -> None:
    """user_settings ALL_MENU_ITEMS 섹션 필드 확인."""
    try:
        import importlib, sys
        sys.path.insert(0, str(ROOT))
        spec = importlib.util.spec_from_file_location("us", Path(__file__).parent / "user_settings.py")
        us = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(us)  # type: ignore
        items = us.ALL_MENU_ITEMS
        missing_section = [i["id"] for i in items if not i.get("section")]
        if missing_section:
            report.add("메뉴 section 필드", "WARN", f"section 없음: {missing_section}")
        else:
            report.add("메뉴 section 필드", "PASS", f"{len(items)}개 항목 모두 section 있음")
    except Exception as e:
        report.add("메뉴 section 필드", "WARN", str(e))


# ── 메인 감사 실행 ─────────────────────────────────────────────────────────────

async def run_audit() -> AuditReport:
    report = AuditReport()
    # 동기 항목
    audit_port(report)
    audit_static(report)
    audit_ui_dist(report)
    audit_proxy(report)
    audit_log_file(report)
    audit_settings_file(report)
    # 비동기 항목
    await audit_websocket(report)
    return report


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    parser = argparse.ArgumentParser(description="데스크 앱 상시 감사")
    parser.add_argument("--watch", action="store_true", help="60초 주기 반복 실행")
    parser.add_argument("--dry",   action="store_true", help="dry-run — 판정만, 수정 없음")
    args = parser.parse_args()

    async def once() -> AuditReport:
        r = await run_audit()
        r.print()
        return r

    if args.watch:
        print("상시 감사 시작 (60초 주기, Ctrl+C 종료)")
        while True:
            asyncio.run(once())
            try:
                time.sleep(60)
            except KeyboardInterrupt:
                print("감사 종료")
                break
    else:
        report = asyncio.run(once())
        if report.verdict == "FAIL":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
