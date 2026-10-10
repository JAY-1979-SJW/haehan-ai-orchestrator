"""미해결 항목 V2 탐지 — Phase 2.

V1에서 미발견된 영역 보강:
1. mail_search: search_area div 클릭 → 활성화된 input 찾기 → 입력 → Enter
2. mybox_list: file/get으로 root key 획득 → file list API 추정 + 폴더 더블클릭 시뮬레이션

V1 결과 기반:
- mail.naver.com 페이지에 일반 input 0개. div.search_area 클릭 필요
- mybox: api.mybox.naver.com/service/file/get?resourceKey=root 정상 작동
- 그 외 file/list API는 직접 호출/캡처되지 않음 → 폴더 진입 시뮬레이션 필요
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.browser.agent.agent import BrowserAgent

HOOK_JS = """
window.__cap = [];
const _xhrOpen = XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open = function(m, url, ...r) {
    this._capUrl = url; this._capMethod = m;
    return _xhrOpen.apply(this, [m, url, ...r]);
};
const _xhrSend = XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.send = function(...a) {
    this.addEventListener('load', function() {
        try {
            window.__cap.push({
                via: 'xhr', method: this._capMethod, url: this._capUrl,
                status: this.status, body: (this.responseText || '').slice(0, 3000)
            });
        } catch(e) {}
    });
    return _xhrSend.apply(this, a);
};
const _fetch = window.fetch;
window.fetch = async function(...a) {
    const url = typeof a[0] === 'string' ? a[0] : (a[0]?.url || '');
    const method = (a[1]?.method) || 'GET';
    try {
        const resp = await _fetch(...a);
        const clone = resp.clone();
        clone.text().then(b => {
            window.__cap.push({ via: 'fetch', method, url, status: resp.status, body: (b || '').slice(0, 3000) });
        }).catch(() => {});
        return resp;
    } catch(e) {
        window.__cap.push({ via: 'fetch', method, url, error: String(e) });
        throw e;
    }
};
"""


def _read_cap(page) -> list:
    return page.evaluate("() => window.__cap || []")


def _reset_cap(page):
    page.evaluate("() => { window.__cap = []; }")


def _filter(cap, keywords):
    out = []
    for x in cap:
        url = x.get("url", "")
        if any(url.endswith(ext) for ext in (".js", ".css", ".png", ".jpg", ".svg", ".ico", ".woff", ".woff2")):
            continue
        if any(k in url for k in keywords):
            out.append(x)
    return out


def explore_mail_search_v2(page, report: dict):
    """mail_search V2 — search_area 클릭 → input 탐지 → 입력 → Enter."""
    print("\n[1/2] mail_search V2 탐지")
    page.add_init_script(HOOK_JS)

    # 1) 메일 페이지 진입
    page.goto("https://mail.naver.com/v2/folders/0/all")
    time.sleep(4)
    _reset_cap(page)

    # 2) search_area div 클릭
    print("  search_area 클릭 시도")
    clicked = False
    for sel in ["div.search_area", '[class*="search_area"]', '[class="search_area"]']:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click(timeout=3000)
                time.sleep(2)
                clicked = True
                report["mail_search_v2"]["click_selector"] = sel
                print(f"    ✓ 클릭 성공: {sel}")
                break
        except Exception:  # noqa: BLE001 - 네이버 메일검색/마이박스 UI 구조 읽기전용 탐색 v2(아카이브) - 실패시 report 에 error 기록, 쓰기 없음
            continue
    if not clicked:
        # search_area 안의 input/button 직접 찾기
        print("    search_area 내부 모든 클릭 가능 요소 탐색")
        inner_elements = page.evaluate("""() => {
            const sa = document.querySelector('div.search_area, [class*="search_area"]');
            if (!sa) return null;
            return {
                outerHTML: sa.outerHTML.slice(0, 1500),
                children: Array.from(sa.querySelectorAll('*')).slice(0, 30).map(el => ({
                    tag: el.tagName.toLowerCase(),
                    cls: el.className || '',
                    text: (el.innerText || '').trim().slice(0, 40),
                    type: el.type || '',
                    placeholder: el.placeholder || '',
                }))
            };
        }""")
        report["mail_search_v2"]["search_area_inner"] = inner_elements
        if inner_elements:
            print(f"    search_area HTML: {inner_elements.get('outerHTML', '')[:300]!r}")
            for c in (inner_elements.get("children") or [])[:10]:
                print(f"      - {c['tag']} cls={c['cls'][:40]!r} text={c['text']!r}")

    # 3) 클릭 후 input 다시 탐색
    time.sleep(1)
    inputs_after_click = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('input')).map(el => ({
            tag: 'input', type: el.type || '',
            placeholder: el.placeholder || '',
            cls: el.className || '',
            visible: el.offsetWidth > 0 && el.offsetHeight > 0,
        })).filter(e => e.visible);
    }""")
    report["mail_search_v2"]["inputs_after_click"] = inputs_after_click
    print(f"  클릭 후 표시되는 input: {len(inputs_after_click)}개")
    for inp in inputs_after_click[:10]:
        print(f"    - type={inp['type']!r} placeholder={inp['placeholder']!r} cls={inp['cls'][:50]!r}")

    # 4) 첫 번째 visible input에 입력 + Enter
    if inputs_after_click:
        try:
            # 가장 가능성 높은 input 셀렉터 (placeholder/cls)
            first = inputs_after_click[0]
            sel_candidates = []
            if first.get("placeholder"):
                sel_candidates.append(f'input[placeholder="{first["placeholder"]}"]')
            if first.get("type"):
                sel_candidates.append(f'input[type="{first["type"]}"]')
            sel_candidates.append("input:visible")

            for sel in sel_candidates:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        el.click()
                        el.fill("네이버")
                        page.keyboard.press("Enter")
                        time.sleep(5)
                        cap = _filter(_read_cap(page), ("json/", "search", "/list"))
                        if cap:
                            report["mail_search_v2"]["typed_selector"] = sel
                            report["mail_search_v2"]["search_apis"] = cap
                            print(f"  ✓ 검색 트리거 성공: {sel} → API {len(cap)}개")
                            return
                except Exception:  # noqa: BLE001 - 네이버 메일검색/마이박스 UI 구조 읽기전용 탐색 v2(아카이브) - 실패시 report 에 error 기록, 쓰기 없음
                    continue
        except Exception as e:  # noqa: BLE001 - 네이버 메일검색/마이박스 UI 구조 읽기전용 탐색 v2(아카이브) - 실패시 report 에 error 기록, 쓰기 없음
            print(f"  입력 트리거 오류: {e}")

    # 5) 직접 검색 API 패턴 추측 호출
    print("  직접 검색 API 호출 시도")
    direct_apis = page.evaluate("""async () => {
        const q = encodeURIComponent('네이버');
        const candidates = [
            `/json/list?type=search&q=${q}&count=5`,
            `/json/search/list?q=${q}&count=5`,
            `/json/search?q=${q}`,
            `/v2/search/list?q=${q}`,
            `/api/search?q=${q}`,
        ];
        const results = [];
        for (const path of candidates) {
            try {
                const resp = await fetch('https://mail.naver.com' + path, { credentials: 'include' });
                const text = await resp.text();
                results.push({ url: path, status: resp.status, hasBody: text.length > 0,
                               preview: text.slice(0, 300) });
            } catch(e) {
                results.push({ url: path, error: String(e) });
            }
        }
        return results;
    }""")
    report["mail_search_v2"]["direct_api_attempts"] = direct_apis
    for r in direct_apis:
        print(f"    [{r.get('status', 'ERR')}] {r.get('url', '')}: hasBody={r.get('hasBody', False)}")


def explore_mybox_v2(page, report: dict):
    """mybox_list V2 — file/get root + 폴더 더블클릭 시뮬레이션."""
    print("\n[2/2] mybox_list V2 탐지")

    # MyBox 진입
    page.goto("https://mybox.naver.com/main/web/my")
    time.sleep(6)
    _reset_cap(page)

    # 1) root resourceKey 획득
    print("  root resourceKey 획득")
    root_info = page.evaluate("""async () => {
        try {
            const resp = await fetch('https://api.mybox.naver.com/service/file/get?resourceKey=root', { credentials: 'include' });
            return await resp.json();
        } catch(e) { return { error: String(e) }; }
    }""")
    report["mybox_v2"]["root_info"] = root_info
    root_key = (root_info.get("result") or {}).get("resourceKey")
    print(f"    root resourceKey: {root_key}")

    # 2) root_key로 다양한 list API 패턴 시도
    if root_key:
        print("  root_key 기반 file list API 시도")
        list_attempts = page.evaluate(f"""async () => {{
            const key = '{root_key}';
            const candidates = [
                `https://api.mybox.naver.com/service/file/list?resourceKey=${{encodeURIComponent(key)}}`,
                `https://api.mybox.naver.com/service/file/list?parentResourceKey=${{encodeURIComponent(key)}}`,
                `https://api.mybox.naver.com/service/file/getList?resourceKey=${{encodeURIComponent(key)}}`,
                `https://api.mybox.naver.com/service/file/getList?parentResourceKey=${{encodeURIComponent(key)}}`,
                `https://api.mybox.naver.com/service/file/getChildren?resourceKey=${{encodeURIComponent(key)}}`,
                `https://api.mybox.naver.com/service/folder/getChildren?resourceKey=${{encodeURIComponent(key)}}`,
                `https://api.mybox.naver.com/service/folder/list?resourceKey=${{encodeURIComponent(key)}}`,
                `https://api.mybox.naver.com/service/file/getResourceList?parentResourceKey=${{encodeURIComponent(key)}}`,
                `https://api.mybox.naver.com/api/v1/file/list?resourceKey=${{encodeURIComponent(key)}}`,
                `https://api.mybox.naver.com/api/v1/folder/${{encodeURIComponent(key)}}/children`,
            ];
            const results = [];
            for (const url of candidates) {{
                try {{
                    const resp = await fetch(url, {{ credentials: 'include' }});
                    const text = await resp.text();
                    let parsed = null;
                    try {{ parsed = JSON.parse(text); }} catch(e) {{}}
                    results.push({{
                        url: url.replace('https://api.mybox.naver.com', ''),
                        status: resp.status,
                        hasResult: !!(parsed && parsed.result),
                        hasList: !!(parsed && parsed.result && (parsed.result.list || parsed.result.children || parsed.result.items)),
                        preview: text.slice(0, 200)
                    }});
                }} catch(e) {{
                    results.push({{ url, error: String(e) }});
                }}
            }}
            return results;
        }}""")
        report["mybox_v2"]["list_api_attempts"] = list_attempts
        for r in list_attempts:
            tag = "✓" if r.get("hasList") else ("?" if r.get("hasResult") else "✗")
            print(f"    {tag} [{r.get('status', 'ERR')}] {r.get('url', '')[:60]}")
            if r.get("hasResult"):
                print(f"      preview: {r.get('preview', '')[:200]!r}")

    # 3) DOM 안에서 폴더/파일 항목 발견 시도 (페이지 상호작용 가능 요소)
    print("  파일 그리드 요소 탐색")
    file_grid = page.evaluate("""() => {
        // Next.js 앱은 data-* 속성이나 role 사용 가능성 높음
        const candidates = [
            '[data-resource-key]', '[data-resourcekey]',
            '[data-file-id]', '[data-folder-id]',
            '[role="gridcell"]', '[role="row"]',
            'div[class*="FileItem"]', 'div[class*="FolderItem"]',
            'div[class*="file-item"]', 'div[class*="folder-item"]',
        ];
        const out = {};
        for (const sel of candidates) {
            const els = document.querySelectorAll(sel);
            if (els.length > 0) {
                out[sel] = {
                    count: els.length,
                    sample: Array.from(els).slice(0, 3).map(el => ({
                        tag: el.tagName.toLowerCase(),
                        cls: el.className || '',
                        attrs: Object.fromEntries(Array.from(el.attributes).map(a => [a.name, a.value.slice(0, 80)])),
                        text: (el.innerText || '').trim().slice(0, 50),
                    }))
                };
            }
        }
        return out;
    }""")
    report["mybox_v2"]["file_grid_elements"] = file_grid
    print(f"    발견된 그리드 셀렉터: {list(file_grid.keys())}")

    # 4) 첫 폴더/파일 더블클릭으로 진입 시도 (실제 list API 호출 트리거)
    _reset_cap(page)
    for sel in file_grid:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.dblclick(timeout=3000)
                time.sleep(4)
                cap = _filter(_read_cap(page), ("api/", "service/", "/list", "/file", "/folder"))
                if cap:
                    report["mybox_v2"]["dblclick_selector"] = sel
                    report["mybox_v2"]["dblclick_apis"] = cap
                    print(f"  ✓ 더블클릭 성공: {sel} → API {len(cap)}개")
                    return
        except Exception:  # noqa: BLE001 - 네이버 메일검색/마이박스 UI 구조 읽기전용 탐색 v2(아카이브) - 실패시 report 에 error 기록, 쓰기 없음
            continue

    # 5) URL navigation 시도 (특정 폴더 ID로)
    _reset_cap(page)
    print("  /main/web/my 외 URL 진입 시도")
    for url in [
        "https://mybox.naver.com/main/web/my/folder/root",
        "https://mybox.naver.com/main/web/photo",
        "https://mybox.naver.com/main/web/document",
    ]:
        try:
            page.goto(url)
            time.sleep(4)
            cap = _filter(_read_cap(page), ("api/", "service/", "/list", "/file"))
            if cap:
                report["mybox_v2"][f"url_{url[-15:]}_apis"] = cap
                print(f"    {url} → API {len(cap)}개")
        except Exception:  # noqa: BLE001 - 네이버 메일검색/마이박스 UI 구조 읽기전용 탐색 v2(아카이브) - 실패시 report 에 error 기록, 쓰기 없음
            pass


def main():
    out_dir = Path(__file__).resolve().parents[1] / "data" / "reports" / "local_agent"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"explore_unresolved_v2_{ts}.json"

    report = {"timestamp": ts, "mail_search_v2": {}, "mybox_v2": {}}

    print("=" * 70)
    print("  Phase 2 미해결 항목 탐지")
    print("=" * 70)

    with BrowserAgent() as a:
        try:
            explore_mail_search_v2(a._page, report)
        except Exception as e:  # noqa: BLE001 - 네이버 메일검색/마이박스 UI 구조 읽기전용 탐색 v2(아카이브) - 실패시 report 에 error 기록, 쓰기 없음
            print(f"  메일검색 V2 탐지 오류: {e}")
            import traceback

            traceback.print_exc()
            report["mail_search_v2"]["error"] = str(e)

        try:
            explore_mybox_v2(a._page, report)
        except Exception as e:  # noqa: BLE001 - 네이버 메일검색/마이박스 UI 구조 읽기전용 탐색 v2(아카이브) - 실패시 report 에 error 기록, 쓰기 없음
            print(f"  MyBox V2 탐지 오류: {e}")
            import traceback

            traceback.print_exc()
            report["mybox_v2"]["error"] = str(e)

    out_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n결과 저장: {out_file}")
    print("=" * 70)


if __name__ == "__main__":
    main()
