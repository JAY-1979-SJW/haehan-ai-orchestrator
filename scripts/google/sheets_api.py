"""Google Sheets OOP 인터페이스.

사용:
    sh = SheetsAPI(page)
    sh.new(title="매출 분석")
    sh.write_cells(url, [["A", "B"], [1, 2]], start="A1")
    sh.read_cells(url, range="A1:C10")
"""

from __future__ import annotations

import time
from typing import Any

from playwright.sync_api import Page

from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger

_log = get_logger(__name__)


class SheetsAPI:
    """Google Sheets 자동화."""

    SHEETS_HOME = "https://docs.google.com/spreadsheets/u/0/"

    def __init__(self, page: Page):
        self.page = page

    def recent(self, limit: int = 20) -> list[dict]:
        """최근 시트."""
        # 2026-09-29: _cdp_page() 가 매번 새(콜드) 탭을 여는 것으로 바뀌어(탭 하이재킹
        # 버그 수정) 기존 20000ms/wait_until 기본값(load)로는 종종 타임아웃 — 완화.
        self.page.goto(self.SHEETS_HOME, timeout=45000, wait_until="domcontentloaded")
        time.sleep(3)
        try:
            return (
                self.page.evaluate(
                    """(limit) => {
                    const out = [];
                    // [data-id] 는 홈스크린 시트 항목뿐 아니라 전역 데이터를 담은
                    // <script data-id="_gd"> 요소도 매칭한다(2026-09-29 실측 확인,
                    // window.WIZ_global_data 텍스트가 시트명으로 오추출됨) — script 태그와
                    // window. 로 시작하는 값을 제외해 실제 시트 항목만 남긴다.
                    document.querySelectorAll('[data-id]').forEach(el => {
                        if (out.length >= limit) return;
                        if (el.tagName === 'SCRIPT') return;
                        const name = el.querySelector('[data-tooltip], .docs-homescreen-list-item-title')?.innerText
                                    || (el.innerText || '').split('\\n')[0];
                        const id = el.getAttribute('data-id') || '';
                        if (name && !name.trim().startsWith('window.')) {
                            out.push({name: name.substring(0, 80), id,
                                      url: `https://docs.google.com/spreadsheets/d/${id}/edit`});
                        }
                    });
                    return out;
                }""",
                    limit,
                )
                or []
            )
        except Exception:  # noqa: BLE001 - Google Sheets 브라우저 자동화 — 최근시트 조회/생성/셀쓰기/셀읽기 각각 실패 시 {ok: False, error}를 반환, 시트 삭제 등 위험 동작 없음.
            return []

    def new(self, title: str = "") -> dict:
        """새 시트 생성."""
        self.page.goto("https://docs.google.com/spreadsheets/create", timeout=20000)
        time.sleep(5)
        url = self.page.url
        try:
            if title:
                title_el = self.page.locator('input.docs-title-input, [aria-label*="제목"]').first
                title_el.click(timeout=3000)
                self.page.keyboard.press("Control+a")
                self.page.keyboard.type(title, delay=20)
                self.page.keyboard.press("Enter")
                time.sleep(1)
            log_critical("OTHER", f"Sheets 새 시트: {title[:30]}", url=url, mode="sheets_new")
            return {"ok": True, "title": title, "url": url}
        except Exception as e:  # noqa: BLE001 - Google Sheets 브라우저 자동화 — 최근시트 조회/생성/셀쓰기/셀읽기 각각 실패 시 {ok: False, error}를 반환, 시트 삭제 등 위험 동작 없음.
            return {"ok": False, "error": str(e)[:100], "url": url}

    def open_sheet(self, url: str) -> dict:
        self.page.goto(url, timeout=20000)
        time.sleep(4)
        return {"ok": True, "url": url}

    def write_cells(self, url: str, data: list[list[Any]], start: str = "A1") -> dict:
        """2D 배열을 시트에 입력. 탭/줄바꿈 페이스트 방식."""
        self.open_sheet(url)
        try:
            # 이름 상자에 시작 셀 입력 → Enter로 이동
            name_box = self.page.locator(
                '#t-name-box, input[aria-label*="이름 상자"], input[aria-label*="Name box"]'
            ).first
            name_box.click(timeout=3000)
            name_box.fill(start, timeout=2000)
            self.page.keyboard.press("Enter")
            time.sleep(1)

            # 클립보드 거치지 않고 직접 타이핑 (속도 느리지만 안정)
            # 행 단위로 입력 + Enter
            for row in data:
                for i, cell in enumerate(row):
                    self.page.keyboard.type(str(cell), delay=10)
                    if i < len(row) - 1:
                        self.page.keyboard.press("Tab")
                self.page.keyboard.press("Enter")
                # 다음 행 시작 위치로 (Home 후 줄 아래는 자동)
                time.sleep(0.1)
            time.sleep(1)
            log_critical("OTHER", f"Sheets 입력: {len(data)}행", start=start, mode="sheets_write")
            return {"ok": True, "rows": len(data), "start": start}
        except Exception as e:  # noqa: BLE001 - Google Sheets 브라우저 자동화 — 최근시트 조회/생성/셀쓰기/셀읽기 각각 실패 시 {ok: False, error}를 반환, 시트 삭제 등 위험 동작 없음.
            return {"ok": False, "error": str(e)[:100]}

    def read_cells(self, url: str, range_a1: str = "A1:Z100") -> dict:
        """범위 셀 읽기 (텍스트 추출)."""
        self.open_sheet(url)
        try:
            # 이름 상자에 범위 입력
            name_box = self.page.locator(
                '#t-name-box, input[aria-label*="이름 상자"], input[aria-label*="Name box"]'
            ).first
            name_box.click(timeout=3000)
            name_box.fill(range_a1, timeout=2000)
            self.page.keyboard.press("Enter")
            time.sleep(1)
            # Ctrl+C → 클립보드 (사용 안 함, DOM 추출)
            data = (
                self.page.evaluate(
                    """() => {
                    const cells = [];
                    document.querySelectorAll('.cell-input, [class*="row-headers"] + div > div').forEach(el => {
                        const t = (el.innerText || '').trim();
                        if (t) cells.push(t.substring(0, 100));
                    });
                    return cells.slice(0, 500);
                }"""
                )
                or []
            )
            return {"ok": True, "cells": data, "count": len(data)}
        except Exception as e:  # noqa: BLE001 - Google Sheets 브라우저 자동화 — 최근시트 조회/생성/셀쓰기/셀읽기 각각 실패 시 {ok: False, error}를 반환, 시트 삭제 등 위험 동작 없음.
            return {"ok": False, "error": str(e)[:100]}
