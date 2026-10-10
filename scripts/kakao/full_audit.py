"""카카오 4개 앱 전체 현황 서버 확인."""
import json
import re
import sys
import time
from typing import Any

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[2]))
from scripts.browser.cdp.connection import get_page
from scripts.browser.page.page_helper import page_goto

page = get_page()
BASE = 'https://developers.kakao.com/console/app'

APPS = [
    {'id': '1413624', 'name': '해한메이아이출퇴근'},
    {'id': '1395337', 'name': '해한AI'},
    {'id': '1309295', 'name': '해한 AI ERP'},
    {'id': '1303517', 'name': '해한AI입찰분석'},
]

report = []

for app in APPS:
    aid = app['id']
    info: dict[str, Any] = {'id': aid, 'name': app['name']}

    print(f"\n{'='*55}")
    print(f"  {app['name']} (ID: {aid})")
    print(f"{'='*55}")

    # 1. 플랫폼 키 — REST API 키 + Redirect URI 전체
    page_goto(page, f'{BASE}/{aid}/config/platform-key')
    page.wait_for_load_state('networkidle', timeout=10000)

    body = page.inner_text('body')

    # REST API 키 (32자 hex)
    hexes = re.findall(r'\b[0-9a-f]{32}\b', body)
    info['rest_api_keys'] = hexes
    print(f"  REST API 키: {len(hexes)}개")
    for k in hexes: print(f"    - {k}")

    # 키 이름
    key_names = re.findall(r'([A-Za-z가-힣][A-Za-z가-힣\s\-_]{2,30})\n더보기\n[0-9a-f]{{32}}', body)
    info['key_names'] = key_names
    if key_names:
        print(f"  키 이름: {key_names}")

    # Redirect URI — 폼 열기
    uris_by_key = {}
    span_count = page.locator('span:has-text("로그인 리다이렉트 URI")').count()
    print(f"  리다이렉트 URI 배지: {span_count}개")

    for span_idx in range(min(span_count, 4)):
        page_goto(page, f'{BASE}/{aid}/config/platform-key')
        page.wait_for_load_state('networkidle', timeout=10000)
        page.locator('span:has-text("로그인 리다이렉트 URI")').nth(span_idx).click()
        page.wait_for_load_state('networkidle', timeout=5000)
        time.sleep(0.8)

        inp_sel = 'input[placeholder*="oauth"], input[placeholder*="example.com"]'
        inp_count = page.locator(inp_sel).count()
        vals = []
        for i in range(inp_count):
            v = page.locator(inp_sel).nth(i).input_value().strip()
            if v: vals.append(v)
        key_name_inp = page.locator('input[placeholder*="키 이름"]').first.input_value() if page.locator('input[placeholder*="키 이름"]').count() > 0 else f'key_{span_idx}'
        uris_by_key[key_name_inp] = vals
        print(f"  [{key_name_inp}] Redirect URI: {vals}")

    info['redirect_uris'] = uris_by_key
    page.locator('button:has-text("취소")').click() if page.locator('button:has-text("취소")').count() > 0 else None

    # 2. 카카오 로그인 ON/OFF
    page_goto(page, f'{BASE}/{aid}/product/login')
    page.wait_for_load_state('networkidle', timeout=10000)
    login_body = page.inner_text('body')
    login_on = '상태\nON' in login_body or 'ON' in login_body
    info['kakao_login_on'] = login_on
    print(f"  카카오 로그인: {'ON' if login_on else 'OFF'}")

    # 3. 플랫폼 도메인
    page_goto(page, f'{BASE}/{aid}/config')
    page.wait_for_load_state('networkidle', timeout=10000)
    cfg_body = page.inner_text('body')
    domains = re.findall(r'https?://[a-z0-9.\-]+haehan[^\s\n\t]+', cfg_body)
    info['domains'] = list(set(domains))
    print(f"  도메인: {info['domains']}")

    # 4. 동의항목
    page_goto(page, f'{BASE}/{aid}/product/login/scope')
    page.wait_for_load_state('networkidle', timeout=10000)
    scope_body = page.inner_text('body')
    scope = []
    for item in ['닉네임', '프로필 사진', '카카오계정(이메일)', '전화번호']:
        if item in scope_body:
            t = '필수' if f'{item}\n필수' in scope_body else '선택'
            scope.append(f'{item}({t})')
    info['scope'] = scope
    print(f"  동의항목: {scope}")

    report.append(info)
    time.sleep(0.5)

# 저장
import pathlib

out = pathlib.Path('data/kakao_full_audit.json')
out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

print(f"\n\n{'='*55}")
print("  최종 정리")
print(f"{'='*55}")

for r in report:
    print(f"\n[{r['name']} / {r['id']}]")
    print(f"  카카오 로그인: {'ON' if r['kakao_login_on'] else 'OFF'}")
    print(f"  REST API 키: {r['rest_api_keys'][0][:8]}... ({len(r['rest_api_keys'])}개)" if r['rest_api_keys'] else "  REST API 키: 없음")
    for kname, uris in r['redirect_uris'].items():
        print(f"  [{kname}] URI: {uris}")
    print(f"  도메인: {r['domains']}")
    print(f"  동의항목: {r['scope']}")

print(f"\n  저장: {out}")
