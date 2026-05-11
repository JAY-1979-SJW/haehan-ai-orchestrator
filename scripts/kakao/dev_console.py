"""카카오 개발자 센터 자동화"""
from __future__ import annotations

import re
from typing import Any

from .base import task_context, page_goto, page_wait_visible, page_wait_click, page_wait_type, KAKAO_DEV_URL

_BASE = "https://developers.kakao.com"
_APP_ID_RE = re.compile(r"/console/app/(\d+)")


def run(task: str, args: list[str]) -> None:
    """개발자 센터 작업 실행.

    task: list, info, register
    """
    match task:
        case "list":
            _task_list(args)
        case "info":
            _task_info(args)
        case "register":
            _task_register(args)
        case _:
            print(f"  [오류] 알 수 없는 작업: {task}")


def _task_list(args: list[str]) -> None:
    """앱 목록 조회."""
    print("\n[작업] 카카오 개발자 센터 — 앱 목록")
    with task_context("dev-list", args) as page:
        page_goto(page, KAKAO_DEV_URL)
        page_wait_visible(page, '.app-list, [class*="AppList"], [class*="app_list"]', timeout=20000)

        apps = page.evaluate("""() => {
            const items = [];
            document.querySelectorAll('[class*="app_item"], [class*="AppItem"], .app-item').forEach(el => {
                const name = el.querySelector('[class*="name"], [class*="title"], h3, h4')?.innerText?.trim() || '';
                const href = el.querySelector('a')?.href || '';
                const match = href.match(/\\/console\\/app\\/(\\d+)/);
                const id = match ? match[1] : '';
                if (name || id) items.push({name, id});
            });
            return items;
        }""")

        if not apps:
            # 페이지 텍스트로 fallback
            apps = page.evaluate("""() => {
                const links = [...document.querySelectorAll('a[href*="/console/app/"]')];
                return links.map(a => ({
                    name: a.innerText.trim(),
                    id: (a.href.match(/\\/console\\/app\\/(\\d+)/) || [])[1] || ''
                })).filter(x => x.id);
            }""")

        print(f"  앱 수: {len(apps)}")
        for i, app in enumerate(apps, 1):
            print(f"  [{i}] {app['name'][:40]:40s} | ID: {app['id']}")


def _task_info(args: list[str]) -> None:
    """앱 상세 정보 조회."""
    if not args:
        print("  [오류] 사용법: info <app_id>")
        return

    app_id = args[0]
    print(f"\n[작업] 카카오 앱 상세 정보: {app_id}")

    with task_context("dev-info", args) as page:
        page_goto(page, f"{_BASE}/console/app/{app_id}")
        page_wait_visible(page, '[class*="summary"], [class*="Overview"], main', timeout=20000)

        info = page.evaluate("""() => {
            const get = sel => document.querySelector(sel)?.innerText?.trim() || '';
            return {
                name:     get('[class*="app_name"], [class*="AppName"], h2, h1'),
                platform: get('[class*="platform"]'),
                status:   get('[class*="status"], [class*="biz"]'),
            };
        }""")

        print(f"  앱 이름: {info.get('name', '-')}")
        print(f"  플랫폼: {info.get('platform', '-')}")
        print(f"  상태:   {info.get('status', '-')}")


def _task_register(args: list[str]) -> None:
    """앱 등록."""
    if not args:
        print("  [오류] 사용법: register <앱이름>")
        return

    app_name = args[0]
    print(f"\n[작업] 카카오 앱 등록: {app_name}")

    with task_context("dev-register", args) as page:
        page_goto(page, KAKAO_DEV_URL)
        page_wait_visible(page, '[class*="btn_create"], button:has-text("애플리케이션 만들기"), '
                                'a:has-text("애플리케이션 만들기")', timeout=20000)

        if not page_wait_click(page, '[class*="btn_create"], button:has-text("애플리케이션 만들기"), '
                                     'a:has-text("애플리케이션 만들기")'):
            print("  ⚠  앱 만들기 버튼 못 찾음")
            return

        page_wait_visible(page, 'input[placeholder*="앱 이름"], input[name*="name"]', timeout=10000)
        page_wait_type(page, 'input[placeholder*="앱 이름"], input[name*="name"]', app_name)

        if page_wait_click(page, 'button:has-text("저장"), button[type="submit"]'):
            page_wait_visible(page, '[class*="app_item"], [class*="AppItem"]', timeout=15000)
            print(f"  ✓ 앱 등록 완료: {app_name}")
        else:
            print("  ⚠  저장 버튼 못 찾음")
