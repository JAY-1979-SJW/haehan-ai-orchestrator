"""통합 페이지 이동 모듈 — 도메인 별칭/URL을 받아 CDP 브라우저 탭을 전환.

사용법:
    python scripts/cdp_client.py goto <별칭_or_URL>

예시:
    goto naver        → https://www.naver.com/
    goto gmail        → https://mail.google.com/
    goto calendar     → https://calendar.google.com/
    goto https://...  → URL 직접
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

from scripts.web_connector import get_page
from scripts.login_check import is_logged_in_by_cookie

ROOT = Path(__file__).resolve().parents[1]
SESSION_BACKUP_DIR = ROOT / "data" / "browser_sessions" / "backups"

# 도메인 별칭 → URL
ALIAS: dict[str, str] = {
    # 네이버
    "naver":      "https://www.naver.com/",
    "naver-blog": "https://blog.naver.com/",
    "naver-mail": "https://mail.naver.com/",
    "naver-cafe": "https://cafe.naver.com/",
    "blog":       "https://blog.naver.com/",
    # 구글
    "google":     "https://www.google.com/",
    "gmail":      "https://mail.google.com/",
    "calendar":   "https://calendar.google.com/",
    "drive":      "https://drive.google.com/",
    "docs":       "https://docs.google.com/",
    "sheets":     "https://sheets.google.com/",
    "slides":     "https://slides.google.com/",
    "youtube":    "https://www.youtube.com/",
    # 카카오/다음
    "kakao":      "https://www.kakaocorp.com/",
    "kakao-dev":  "https://developers.kakao.com/",
    "daum":       "https://www.daum.net/",
    # 기타
    "tistory":    "https://www.tistory.com/",
    "github":     "https://github.com/",
}


def resolve(target: str) -> str:
    """별칭 또는 URL을 정규 URL로 변환."""
    t = target.strip().lower()
    if t in ALIAS:
        return ALIAS[t]
    if target.startswith(("http://", "https://")):
        return target
    if "." in target and " " not in target:
        return f"https://{target}"
    raise ValueError(
        f"알 수 없는 별칭/URL: {target}\n"
        f"등록된 별칭: {', '.join(sorted(ALIAS))}"
    )


def goto(target: str, timeout_ms: int = 60000, auto_scan: bool = True, handle_popups: bool = True) -> None:
    """대상 페이지로 활성 탭 이동. 탭은 닫지 않고 그대로 둠. 성공 시 자동 scan_page().

    Args:
        target: 별칭 또는 URL
        timeout_ms: 페이지 로드 타임아웃
        auto_scan: 이동 후 페이지 스캔 실행 여부
        handle_popups: 페이지 진입 시 팝업 자동 처리 여부
    """
    url = resolve(target)
    print("=" * 60)
    print(f"페이지 전환: {target} → {url}")
    print("=" * 60)
    page = get_page()
    page.goto(url, timeout=timeout_ms)
    print(f"✓ 이동 완료: {page.url}")

    # 팝업 자동 처리
    if handle_popups:
        try:
            from scripts.popup_detector import handle_page_popups
            result = handle_page_popups(page)
            if result.get("had_popup"):
                print(f"✓ 팝업 처리 완료 ({result.get('popups_closed')}개)")
        except Exception as e:
            print(f"⚠️  팝업 처리 실패: {e}")

    print("=" * 60)
    if auto_scan:
        scan_page()


def wait_login(site: str, timeout_s: int = 300, interval_s: int = 3) -> bool:
    """사이트 로그인 완료를 폴링으로 감지. 완료 시 True, 타임아웃 시 False."""
    print("=" * 60)
    print(f"로그인 감지 대기: {site} (최대 {timeout_s}초, {interval_s}초 간격)")
    print("=" * 60)
    page = get_page()
    deadline = time.time() + timeout_s
    elapsed = 0
    while time.time() < deadline:
        if is_logged_in_by_cookie(page, site):
            print(f"✓ 로그인 감지됨 ({elapsed}초 경과)")
            print("=" * 60)
            return True
        time.sleep(interval_s)
        elapsed += interval_s
        if elapsed % 30 == 0:
            print(f"  대기 중... {elapsed}초 경과")
    print(f"✗ 타임아웃 — {timeout_s}초 내 로그인 감지 안 됨")
    print("=" * 60)
    return False


def scan_links() -> list[dict]:
    """현재 활성 탭의 모든 <a> 링크를 수집해 반환.

    반환 항목: {text, href, visible}
    - text: 링크 표시 텍스트(strip)
    - href: 절대 URL
    - visible: 화면에 보이는지 여부(offsetParent 기준)
    """
    print("=" * 60)
    page = get_page()
    print(f"링크 스캔: {page.url}")
    print("=" * 60)

    links = page.evaluate("""() => {
        const out = [];
        for (const a of document.querySelectorAll('a')) {
            const text = (a.innerText || a.textContent || '').trim();
            const href = a.href || '';
            const visible = !!a.offsetParent;
            if (!href) continue;
            out.push({ text, href, visible });
        }
        return out;
    }""")

    visible = [l for l in links if l["visible"] and l["text"]]
    print(f"총 링크: {len(links)}개 / 보임+텍스트있음: {len(visible)}개")
    print("-" * 60)
    for i, l in enumerate(visible[:50], 1):
        text = l["text"].replace("\n", " ")[:30]
        href = l["href"][:60]
        print(f"  [{i:3}] {text:<32} → {href}")
    if len(visible) > 50:
        print(f"  ... 외 {len(visible) - 50}개")
    print("=" * 60)
    return links


def scan_page() -> dict:
    """현재 활성 탭의 모든 인터랙티브 요소를 카테고리별로 수집해 출력.

    카테고리: links, inputs, buttons, editables, iframes
    """
    page = get_page()
    print("=" * 60)
    print(f"페이지 전체 조회: {page.url}")
    print(f"제목: {page.title()}")
    print("=" * 60)

    scan_js = """() => {
        const txt = el => (el.innerText || el.textContent || '').trim();
        const vis = el => !!el.offsetParent;

        const links = Array.from(document.querySelectorAll('a'))
            .filter(a => vis(a) && txt(a) && a.href)
            .map(a => ({ text: txt(a), href: a.href, target: a.target || '' }));

        const inputs = Array.from(document.querySelectorAll('input, textarea'))
            .filter(vis)
            .map(i => ({
                tag: i.tagName.toLowerCase(),
                type: i.type || '',
                name: i.name || '',
                id: i.id || '',
                placeholder: i.placeholder || '',
                value_preview: (i.value || '').slice(0, 30),
            }));

        const buttons = Array.from(document.querySelectorAll('button, [role=button]'))
            .filter(vis)
            .map(b => ({
                text: txt(b),
                aria: b.getAttribute('aria-label') || '',
                id: b.id || '',
            }))
            .filter(b => b.text || b.aria);

        // 편집영역은 fixed positioning 등으로 offsetParent가 null일 수 있어 vis() 필터 완화 (display:none/visibility만 제외)
        const isShown = el => {
            const s = getComputedStyle(el);
            return s.display !== 'none' && s.visibility !== 'hidden';
        };
        const editableSet = new Set();
        for (const sel of ['[contenteditable]', '[role=textbox]', '[data-placeholder]']) {
            for (const el of document.querySelectorAll(sel)) {
                if (isShown(el) && el.getAttribute('contenteditable') !== 'false') {
                    editableSet.add(el);
                }
            }
        }
        const editables = Array.from(editableSet).map(e => ({
            tag: e.tagName.toLowerCase(),
            id: e.id || '',
            cls: (e.className && typeof e.className === 'string') ? e.className.slice(0, 40) : '',
            ce: e.getAttribute('contenteditable') || '',
            role: e.getAttribute('role') || '',
            placeholder: e.getAttribute('data-placeholder') || e.getAttribute('placeholder') || '',
            aria: e.getAttribute('aria-label') || '',
            preview: txt(e).slice(0, 50),
        }));

        const iframes = Array.from(document.querySelectorAll('iframe'))
            .filter(vis)
            .map(f => ({
                id: f.id || '',
                name: f.name || '',
                src: f.src || '',
            }));

        return { links, inputs, buttons, editables, iframes };
    }"""

    # 모든 프레임(메인 + iframe들)을 순회하며 누적 수집
    data = {"links": [], "inputs": [], "buttons": [], "editables": [], "iframes": []}
    frame_count = 0
    for frame in page.frames:
        try:
            part = frame.evaluate(scan_js)
        except Exception as e:
            print(f"  [경고] frame 스캔 실패 ({frame.url[:50]}): {e}")
            continue
        frame_count += 1
        frame_tag = f"[main]" if frame is page.main_frame else f"[iframe:{frame.name or frame.url[:40]}]"
        for cat in ("links", "inputs", "buttons", "editables"):
            for item in part[cat]:
                item["_frame"] = frame_tag
                data[cat].append(item)
        # iframe 메타는 메인에서만 (중복 방지)
        if frame is page.main_frame:
            data["iframes"] = part["iframes"]

    print(f"스캔된 프레임 수: {frame_count}")

    def show(label, items, fmt, limit=20):
        print(f"\n[{label}] {len(items)}개")
        for i, it in enumerate(items[:limit], 1):
            print(f"  {i:2}. {fmt(it)}")
        if len(items) > limit:
            print(f"  ... 외 {len(items) - limit}개")

    show("LINKS", data["links"],
         lambda l: f"{l.get('_frame',''):<24} {l['text'][:30]:<32} → {l['href'][:50]}")
    show("INPUTS", data["inputs"],
         lambda i: f"{i.get('_frame',''):<24} <{i['tag']} type={i['type']} name={i['name']} id={i['id']}> ph='{i['placeholder'][:25]}' val='{i['value_preview']}'")
    show("BUTTONS", data["buttons"],
         lambda b: f"{b.get('_frame',''):<24} '{b['text'][:30]}' aria='{b['aria'][:25]}' id={b['id']}")
    show("EDITABLES", data["editables"],
         lambda e: f"{e.get('_frame',''):<24} <{e['tag']} id={e['id']} ce={e.get('ce','')} role={e.get('role','')}> cls='{e.get('cls','')[:25]}' ph='{e.get('placeholder','')[:25]}' aria='{e['aria'][:20]}' preview='{e['preview']}'")
    show("IFRAMES", data["iframes"],
         lambda f: f"id={f['id']} name={f['name']} src={f['src'][:80]}")

    print("=" * 60)
    print("✓ 조회 완료 — 다음 명령 입력")
    print("=" * 60)
    return data


def click_link(text: str, timeout_ms: int = 15000) -> bool:
    """현재 페이지에서 텍스트가 일치하는 링크를 찾아 클릭하고 navigation 대기.

    매칭 우선순위: 정확 일치 > 시작 일치 > 부분 일치 (보이는 링크 중에서만)
    클릭 후 새 탭이 열리면 그 탭으로 page 객체 갱신은 하지 않음 (현 탭 기준).
    """
    print("=" * 60)
    page = get_page()
    print(f"링크 클릭 시도: '{text}' (현재: {page.url})")
    print("=" * 60)

    target = page.evaluate(f"""(needle) => {{
        const all = Array.from(document.querySelectorAll('a'))
            .filter(a => a.offsetParent && (a.innerText || a.textContent || '').trim());
        const items = all.map(a => ({{
            text: (a.innerText || a.textContent || '').trim(),
            href: a.href,
            target: a.target || '',
        }}));
        const exact   = items.find(i => i.text === needle);
        const starts  = items.find(i => i.text.startsWith(needle));
        const partial = items.find(i => i.text.includes(needle));
        const hit = exact || starts || partial;
        return hit || null;
    }}""", text)

    if not target:
        print(f"✗ 매칭되는 링크 없음")
        print("=" * 60)
        return False

    print(f"  매칭: '{target['text']}' → {target['href']}")

    context = page.context
    url_before = page.url
    target_attr = (target.get("target") or "").lower() if isinstance(target, dict) else ""

    click_js = """(needle) => {
        const all = Array.from(document.querySelectorAll('a'))
            .filter(a => a.offsetParent && (a.innerText || a.textContent || '').trim());
        const exact   = all.find(a => (a.innerText || a.textContent || '').trim() === needle);
        const starts  = all.find(a => (a.innerText || a.textContent || '').trim().startsWith(needle));
        const partial = all.find(a => (a.innerText || a.textContent || '').trim().includes(needle));
        (exact || starts || partial).click();
    }"""

    new_page = None
    if target_attr == "_blank":
        # 새 탭 케이스: expect_page 컨텍스트 매니저로 신뢰성 있게 감지
        try:
            with context.expect_page(timeout=timeout_ms) as new_page_info:
                page.evaluate(click_js, text)
            new_page = new_page_info.value
        except Exception as e:
            print(f"⚠ expect_page 실패: {e}")
    else:
        # 같은 탭 케이스: navigation 이벤트 대기
        try:
            with page.expect_navigation(timeout=timeout_ms, wait_until="domcontentloaded"):
                page.evaluate(click_js, text)
            new_page = page
        except Exception:
            if page.url != url_before and page.url != "about:blank":
                new_page = page

    if new_page is None:
        print(f"⚠ 이동 감지 안 됨 (target={target_attr or '동일창'})")
        print(f"  현재 URL: {page.url}")
        print("=" * 60)
        return False

    try:
        new_page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    except Exception:
        pass
    where = "새 탭" if new_page is not page else "현재 탭"
    print(f"✓ 이동 완료 ({where}): {new_page.url}")
    print("=" * 60)
    scan_page()
    return True


def _find_element_in_frames(page, finder_js: str, arg):
    """모든 프레임을 순회하며 finder_js로 매칭되는 element handle 반환. (frame, handle) 또는 (None, None)."""
    for frame in page.frames:
        try:
            handle = frame.evaluate_handle(finder_js, arg)
            # JS가 null을 반환하면 handle은 'null' jsHandle
            if handle.evaluate("e => e !== null"):
                return frame, handle
        except Exception:
            continue
    return None, None


def type_into(target: str, text: str, clear: bool = True) -> bool:
    """대상 입력칸/편집영역에 텍스트 입력.

    매칭 우선순위(현재 페이지의 모든 프레임에서 검색):
      1) <input>/<textarea>의 name == target
      2) <input>/<textarea>의 id == target
      3) placeholder 부분 일치
      4) [contenteditable]의 aria-label/id/data-placeholder 부분 일치
      5) 첫 번째 보이는 [contenteditable] (target == "body" 인 경우)
    """
    print("=" * 60)
    page = get_page()
    try:
        page.bring_to_front()  # 키 이벤트가 정확히 이 탭으로 가도록 보장
    except Exception:
        pass
    print(f"입력 시도: target='{target}' text='{text[:40]}...' ({page.url})")
    print("=" * 60)

    finder = """(needle) => {
        const isShown = el => {
            const s = getComputedStyle(el);
            return s.display !== 'none' && s.visibility !== 'hidden';
        };
        const onScreen = el => {
            const r = el.getBoundingClientRect();
            return r.x > -1000 && r.y > -1000 && r.width > 0 && r.height > 0;
        };
        const inTitleChain = el => {
            for (let p = el; p; p = p.parentElement) {
                const c = (p.className || '').toString();
                if (c.includes('documentTitle')) return true;
            }
            return false;
        };

        // Naver Smart Editor 전용: title/body는 se-text-paragraph 기반
        if (needle === 'title' || needle === 'body') {
            const paras = Array.from(document.querySelectorAll('p.se-text-paragraph, .se-text-paragraph'))
                .filter(el => isShown(el) && onScreen(el));
            if (needle === 'title') {
                // 반드시 documentTitle 체인 안에 있어야 함 — 없으면 null (대기 루프 트리거)
                return paras.find(p => inTitleChain(p)) || null;
            } else {
                // body: documentTitle 아닌 paragraph (없으면 마지막 paragraph)
                if (paras.length) return paras.find(p => !inTitleChain(p)) || paras[paras.length - 1];
            }
            return null;
        }

        // 1~3. input/textarea
        for (const sel of [`input[name="${needle}"]`, `textarea[name="${needle}"]`,
                           `input[id="${needle}"]`, `textarea[id="${needle}"]`]) {
            const el = document.querySelector(sel);
            if (el && isShown(el)) return el;
        }
        for (const el of document.querySelectorAll('input, textarea')) {
            if (!isShown(el)) continue;
            const ph = el.placeholder || '';
            if (ph.includes(needle)) return el;
        }
        // 4. contenteditable by attribute match
        for (const el of document.querySelectorAll('[contenteditable]')) {
            if (!isShown(el) || !onScreen(el) || el.getAttribute('contenteditable') === 'false') continue;
            const id = el.id || '';
            const aria = el.getAttribute('aria-label') || '';
            const ph = el.getAttribute('data-placeholder') || '';
            if (id.includes(needle) || aria.includes(needle) || ph.includes(needle)) return el;
        }
        return null;
    }"""

    # 요소 등장 대기 (최대 10초) — Smart Editor 로드 시간 대응
    frame, handle = None, None
    deadline = time.time() + 10
    while time.time() < deadline:
        frame, handle = _find_element_in_frames(page, finder, target)
        if frame is not None:
            break
        time.sleep(0.5)
    if frame is None:
        print(f"✗ 매칭 요소 없음 (10초 대기 후에도)")
        print("=" * 60)
        return False

    tag = handle.evaluate("e => e.tagName.toLowerCase()")
    print(f"  매칭: <{tag}> in frame '{frame.name or frame.url[:40]}'")

    try:
        handle.evaluate("e => e.scrollIntoView({block:'center'})")
        if tag in ("input", "textarea"):
            handle.evaluate("e => { e.focus(); e.value = ''; e.dispatchEvent(new Event('input', {bubbles:true})); }")
            frame.page.keyboard.type(text, delay=20)
        else:
            # contenteditable / Smart Editor paragraph: 클립보드 paste 1순위
            # 1. 마우스 클릭으로 에디터 활성화 (실제 좌표 클릭)
            box = handle.bounding_box()
            if box:
                cx = box["x"] + box["width"] / 2
                cy = box["y"] + box["height"] / 2
                frame.page.mouse.click(cx, cy)
            else:
                handle.evaluate("e => e.click()")
            time.sleep(0.3)

            # 2. clear=True 면 triple-click으로 단일 paragraph 선택 후 Delete
            if clear and box:
                frame.page.mouse.click(cx, cy, click_count=3)
                time.sleep(0.2)
                frame.page.keyboard.press("Delete")
                time.sleep(0.3)

            # 2. Windows 클립보드에 텍스트 설정 — pywin32로 CF_UNICODETEXT 직접 (BOM 오염 없음)
            try:
                import win32clipboard
                import win32con
                win32clipboard.OpenClipboard()
                try:
                    win32clipboard.EmptyClipboard()
                    win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
                finally:
                    win32clipboard.CloseClipboard()
                clipboard_ok = True
            except Exception as ce:
                print(f"  [경고] 클립보드 설정 실패: {ce}")
                clipboard_ok = False

            # 3. Ctrl+V (paste) — Smart Editor의 정식 paste 핸들러로 라우팅
            if clipboard_ok:
                frame.page.keyboard.press("Control+V")
                time.sleep(1.5)  # Smart Editor 렌더 대기 (child span 생성)

            # 4. paste 결과 검증 — handle 자체 + child + 전체 페이지 모두 확인
            def _text_present() -> bool:
                # handle 자신의 innerText (child span 포함)
                try:
                    h_text = handle.evaluate("e => e.innerText || e.textContent || ''")
                    if text[:10] in h_text:
                        return True
                except Exception:
                    pass
                # 폴백: 페이지 전체 검색
                snippet = text[:30] if len(text) >= 10 else text
                for fr in frame.page.frames:
                    try:
                        if snippet in fr.evaluate("() => (document.body && document.body.innerText) || ''"):
                            return True
                    except Exception:
                        continue
                return False

            if clipboard_ok and _text_present():
                pass  # paste 성공 — 폴백 절대 안 함
            elif not clipboard_ok:
                # 클립보드 자체 실패 시에만 폴백
                try:
                    frame.page.keyboard.insert_text(text)
                    time.sleep(0.5)
                except Exception:
                    handle.evaluate("(e, t) => { e.focus(); document.execCommand('insertText', false, t); }", text)

        # 입력 결과 검증 — 표준 verify_input 사용 (page 재사용으로 중첩 회피)
        v = verify_input(text, timeout_s=3.0, page=page)
        mark = "✓" if v["found"] else "⚠"
        print(f"{mark} 입력 결과: found={v['found']} where={v['where']} ({v['elapsed_ms']}ms)")
        if v["found"]:
            print(f"  실제값: '{v['actual']}'")
        print("=" * 60)
        return v["found"]
    except Exception as e:
        print(f"⚠ 입력 실패: {e}")
        print("=" * 60)
        return False




def click_button(text: str, timeout_ms: int = 10000) -> bool:
    """버튼 텍스트/aria-label 매칭으로 클릭. 모든 프레임 검색.

    매칭 우선순위: 정확 텍스트 > 텍스트 부분 일치 > aria-label 부분 일치
    클릭 후 URL 변경/새 탭 감지 시 scan_page 자동 실행.
    """
    print("=" * 60)
    page = get_page()
    url_before = page.url
    pages_before = set(page.context.pages)
    print(f"버튼 클릭 시도: '{text}' ({page.url})")
    print("=" * 60)

    finder = """(needle) => {
        const txt = el => (el.innerText || el.textContent || '').trim();
        const isShown = el => {
            const s = getComputedStyle(el);
            return s.display !== 'none' && s.visibility !== 'hidden';
        };
        const all = Array.from(document.querySelectorAll('button, [role=button]'))
            .filter(isShown);
        // 1) 정확 일치 (line by line — 여러 줄 텍스트 버튼 대응)
        const exact = all.find(b => {
            const t = txt(b);
            return t === needle || t.split('\\n').some(line => line.trim() === needle);
        });
        if (exact) return exact;
        // 2) aria-label 정확 일치
        const ariaExact = all.find(b => (b.getAttribute('aria-label') || '').trim() === needle);
        if (ariaExact) return ariaExact;
        // 3) 짧은 텍스트(≤3자)는 부분 매칭 금지 — '취소' 가 '취소선' 잡는 사고 방지
        if (needle.length <= 3) return null;
        // 4) 부분 매칭
        const partial = all.find(b => txt(b).includes(needle));
        if (partial) return partial;
        const aria = all.find(b => (b.getAttribute('aria-label') || '').includes(needle));
        return aria || null;
    }"""

    frame, handle = _find_element_in_frames(page, finder, text)
    if frame is None:
        print(f"✗ 매칭 버튼 없음")
        print("=" * 60)
        return False

    btn_text = handle.evaluate("e => (e.innerText || e.textContent || '').trim()")
    print(f"  매칭: '{btn_text[:40]}' in frame '{frame.name or frame.url[:40]}'")

    try:
        handle.evaluate("e => e.scrollIntoView({block:'center'})")
        handle.evaluate("e => e.click()")
        print(f"✓ 클릭 완료")
    except Exception as e:
        print(f"⚠ 클릭 실패: {e}")
        print("=" * 60)
        return False

    # 결과 감지 (URL 변경 / 새 탭)
    time.sleep(1)
    if page.url != url_before:
        print(f"  → URL 변경: {page.url}")
        scan_page()
        return True
    new_pages = set(page.context.pages) - pages_before
    if new_pages:
        new = next(iter(new_pages))
        print(f"  → 새 탭: {new.url}")
        scan_page()
        return True
    print("  → 페이지 변화 없음 (모달/AJAX 가능성)")
    print("=" * 60)
    return True


def paste_image(image_path: str, target: str = "body") -> bool:
    """이미지를 클립보드에 올리고 대상 편집영역에 Ctrl+V로 붙여넣기.

    image_path: PNG/JPG 등 PIL이 열 수 있는 모든 형식
    target: 'body' (기본), 'title', 또는 contenteditable의 id/aria
    """
    from pathlib import Path as _P
    img_path = _P(image_path)
    if not img_path.exists():
        print(f"✗ 이미지 파일 없음: {img_path}")
        return False

    print("=" * 60)
    page = get_page()
    page.bring_to_front()
    print(f"이미지 paste: {img_path.name} → target='{target}' ({page.url})")
    print("=" * 60)

    # 1. 대상 element 찾기 (type_into와 동일 finder 사용)
    finder = """(needle) => {
        const isShown = el => {
            const s = getComputedStyle(el);
            return s.display !== 'none' && s.visibility !== 'hidden';
        };
        const onScreen = el => {
            const r = el.getBoundingClientRect();
            return r.x > -1000 && r.y > -1000 && r.width > 0 && r.height > 0;
        };
        const inTitleChain = el => {
            for (let p = el; p; p = p.parentElement) {
                if ((p.className || '').toString().includes('documentTitle')) return true;
            }
            return false;
        };
        if (needle === 'title' || needle === 'body') {
            const paras = Array.from(document.querySelectorAll('p.se-text-paragraph, .se-text-paragraph'))
                .filter(el => isShown(el) && onScreen(el));
            if (paras.length) {
                if (needle === 'title') return paras.find(p => inTitleChain(p)) || paras[0];
                return paras.find(p => !inTitleChain(p)) || paras[paras.length - 1];
            }
        }
        return null;
    }"""
    frame, handle = _find_element_in_frames(page, finder, target)
    if frame is None:
        print(f"✗ 대상 element 없음")
        return False

    # 2. 클릭으로 활성화
    box = handle.bounding_box()
    if box:
        frame.page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    time.sleep(0.5)

    # 3. 이미지를 CF_DIB로 클립보드에 설정
    try:
        from PIL import Image
        import io
        import win32clipboard
        import win32con
        img = Image.open(img_path)
        if img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, "BMP")
        # CF_DIB = BMP without 14-byte file header
        dib = buf.getvalue()[14:]
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32con.CF_DIB, dib)
        finally:
            win32clipboard.CloseClipboard()
        print(f"  클립보드 설정 완료 ({img.size[0]}x{img.size[1]}, {len(dib):,} bytes)")
    except Exception as e:
        print(f"✗ 클립보드 설정 실패: {e}")
        return False

    # 4. Ctrl+V
    frame.page.keyboard.press("Control+V")
    time.sleep(3.0)  # 이미지 업로드 + 렌더 대기

    # 5. 검증 — img 태그가 frame에 새로 추가되었는지
    img_count = frame.evaluate("() => document.querySelectorAll('img').length")
    print(f"✓ Ctrl+V 전송 완료 (현재 frame img 개수: {img_count})")
    print("=" * 60)
    return True


def handle_draft_restore_popup(timeout_s: float = 5.0, page=None) -> dict:
    """Naver 블로그 '작성 중인 글' 복원 팝업 탐지 + 처리.

    탐지 신호:
      - '작성 중인 글' 또는 '이어서 작성' 텍스트
      - 같은 화면에 '취소' + '확인' 버튼 동시 존재
    동작:
      - 팝업 감지되면 '취소' 클릭 (새 글로 시작)
      - 미감지 시 스킵 (정상)
    반환: {detected, action, elapsed_ms}
    """
    import time as _t
    if page is None:
        page = get_page()
    start = _t.time()
    deadline = start + timeout_s

    detect_js = """() => {
        const body = (document.body && document.body.innerText) || '';
        const hasMarker = body.includes('작성 중인 글') || body.includes('이어서 작성');
        if (!hasMarker) return { detected: false };
        // 동일 영역에 취소+확인 버튼 존재 확인
        const btns = Array.from(document.querySelectorAll('button'))
            .filter(b => { const s = getComputedStyle(b); return s.display !== 'none' && s.visibility !== 'hidden'; })
            .map(b => (b.innerText || '').trim());
        const hasCancel = btns.some(t => t === '취소');
        const hasOk = btns.some(t => t === '확인');
        return { detected: hasCancel && hasOk, marker_text: body.slice(0, 200) };
    }"""

    detected_in_frame = None
    while _t.time() < deadline:
        for fr in page.frames:
            try:
                r = fr.evaluate(detect_js)
                if r.get("detected"):
                    detected_in_frame = fr
                    break
            except Exception:
                continue
        if detected_in_frame:
            break
        _t.sleep(0.3)

    if not detected_in_frame:
        return {
            "detected": False,
            "action": "skip",
            "elapsed_ms": int((_t.time() - start) * 1000),
        }

    # 취소 클릭 — frame 안에서 정확 매칭만
    click_js = """() => {
        const btn = Array.from(document.querySelectorAll('button'))
            .filter(b => { const s = getComputedStyle(b); return s.display !== 'none' && s.visibility !== 'hidden'; })
            .find(b => (b.innerText || '').trim() === '취소');
        if (btn) { btn.click(); return true; }
        return false;
    }"""
    clicked = False
    try:
        clicked = detected_in_frame.evaluate(click_js)
    except Exception:
        pass
    _t.sleep(0.5)

    return {
        "detected": True,
        "action": "cancel_clicked" if clicked else "cancel_failed",
        "elapsed_ms": int((_t.time() - start) * 1000),
    }


def is_ready(checks: list[str], timeout_s: float = 2.0, page=None) -> dict:
    """페이지가 지정 조건을 모두 만족할 때까지 짧게 폴링.

    checks 형식 (각 항목 문자열):
      url_contains:<문자열>     — page.url에 포함
      readystate                 — document.readyState === 'complete' (모든 프레임)
      has_text:<문자열>          — body.innerText에 포함 (모든 프레임)
      has_button:<텍스트>        — 정확히 일치하는 버튼 존재
      has_element:<CSS셀렉터>    — CSS 셀렉터 매칭 요소 존재 (모든 프레임)

    반환: {ok, elapsed_ms, results: [{check, passed, reason}]}
    """
    import time as _t
    if page is None:
        page = get_page()
    start = _t.time()
    deadline = start + timeout_s

    def _eval_check(spec: str) -> tuple[bool, str]:
        if ":" in spec:
            kind, arg = spec.split(":", 1)
        else:
            kind, arg = spec, ""
        try:
            if kind == "url_contains":
                return (arg in page.url, page.url)
            if kind == "readystate":
                states = []
                for fr in page.frames:
                    try:
                        states.append(fr.evaluate("() => document.readyState"))
                    except Exception:
                        states.append("error")
                ok = all(s == "complete" for s in states)
                return (ok, f"states={states}")
            if kind == "has_text":
                for fr in page.frames:
                    try:
                        t = fr.evaluate("() => (document.body && document.body.innerText) || ''")
                        if arg in t:
                            return (True, f"frame={fr.name or 'main'}")
                    except Exception:
                        continue
                return (False, "not found in any frame")
            if kind == "has_button":
                js = """(needle) => {
                    const btns = document.querySelectorAll('button, [role=button]');
                    for (const b of btns) {
                        const t = (b.innerText || b.textContent || '').trim();
                        if (t === needle || t.split('\\n').some(l => l.trim() === needle)) return true;
                    }
                    return false;
                }"""
                for fr in page.frames:
                    try:
                        if fr.evaluate(js, arg):
                            return (True, f"frame={fr.name or 'main'}")
                    except Exception:
                        continue
                return (False, "button not found")
            if kind == "has_element":
                for fr in page.frames:
                    try:
                        ok = fr.evaluate(f"() => !!document.querySelector({arg!r})")
                        if ok:
                            return (True, f"frame={fr.name or 'main'}")
                    except Exception:
                        continue
                return (False, "element not found")
            return (False, f"unknown check kind: {kind}")
        except Exception as e:
            return (False, f"error: {e}")

    results: dict = {}
    while _t.time() < deadline:
        results = {}
        all_ok = True
        for spec in checks:
            ok, reason = _eval_check(spec)
            results[spec] = (ok, reason)
            if not ok:
                all_ok = False
        if all_ok:
            break
        _t.sleep(0.3)

    elapsed_ms = int((_t.time() - start) * 1000)
    ok = all(v[0] for v in results.values()) if results else False
    return {
        "ok": ok,
        "elapsed_ms": elapsed_ms,
        "results": [
            {"check": spec, "passed": v[0], "reason": v[1]}
            for spec, v in results.items()
        ],
    }


def _normalize_text(s: str) -> str:
    """공백/투명문자 정규화 — Smart Editor가 paste 텍스트를 NBSP 등으로 변환하는 케이스 대응."""
    if not s:
        return ""
    return (
        s.replace(" ", " ")  # NBSP
         .replace("​", "")    # zero-width space
         .replace("‌", "")    # ZWNJ
         .replace("‍", "")    # ZWJ
         .replace("\t", " ")
    )


def verify_input(text: str, timeout_s: float = 3.0, page=None) -> dict:
    """입력된 텍스트가 현재 탭의 어느 프레임/element에 들어갔는지 확인.

    공백 정규화로 NBSP·zero-width 변환 영향 제거.
    모든 프레임 순회. timeout_s까지 0.3초 간격 재시도.

    page: 호출자가 이미 가진 page 객체를 넘기면 sync_playwright 중첩 회피.
          미지정 시 새로 get_page() 호출.

    반환: {found, where, actual, elapsed_ms}
    """
    import time as _t
    if page is None:
        page = get_page()
    target_n = _normalize_text(text)
    snippet = target_n[:30] if len(target_n) >= 10 else target_n
    start = _t.time()
    deadline = start + timeout_s

    finder_js = """(needleN) => {
        const norm = s => (s || '').replace(/\\u00a0/g, ' ').replace(/\\u200b/g, '').replace(/\\u200c/g, '').replace(/\\u200d/g, '').replace(/\\t/g, ' ');
        const isShown = el => {
            const s = getComputedStyle(el);
            return s.display !== 'none' && s.visibility !== 'hidden';
        };
        // 텍스트 노드를 직접 가진 element 중 최단 매칭
        for (const el of document.querySelectorAll('*')) {
            if (!isShown(el)) continue;
            const own = norm(Array.from(el.childNodes).filter(n => n.nodeType === 3).map(n => n.textContent||'').join(''));
            if (own && own.includes(needleN)) {
                return {
                    tag: el.tagName.toLowerCase(),
                    id: el.id || '',
                    cls: (typeof el.className === 'string' ? el.className : '').slice(0, 40),
                    actual: own.slice(0, 100),
                };
            }
        }
        // 폴백: body.innerText 전체 매칭만이라도 확인
        const all = norm((document.body && document.body.innerText) || '');
        if (all.includes(needleN)) {
            return { tag: 'body', id: '', cls: '', actual: all.slice(0, 100) };
        }
        return null;
    }"""

    while _t.time() < deadline:
        for fr in page.frames:
            try:
                hit = fr.evaluate(finder_js, snippet)
            except Exception:
                continue
            if hit:
                frame_tag = "main" if fr is page.main_frame else f"iframe:{fr.name or fr.url[:30]}"
                where = f"{frame_tag} <{hit['tag']}#{hit['id']}.{hit['cls']}>"
                return {
                    "found": True,
                    "where": where,
                    "actual": hit["actual"],
                    "elapsed_ms": int((_t.time() - start) * 1000),
                }
        _t.sleep(0.3)

    return {
        "found": False,
        "where": None,
        "actual": "",
        "elapsed_ms": int((_t.time() - start) * 1000),
    }


def verify_text(needle: str) -> list[dict]:
    """모든 프레임에서 주어진 텍스트가 들어있는 element 위치를 추적.

    각 매칭: frame, tag, id, classes, ce(contenteditable), visible, rect, full_text
    실제로 화면에 보이는지(visible), 어디에 들어갔는지 검증.
    """
    print("=" * 60)
    page = get_page()
    print(f"텍스트 추적: '{needle}' ({page.url})")
    print("=" * 60)

    finder_js = """(needle) => {
        const results = [];
        const isShown = el => {
            const s = getComputedStyle(el);
            return s.display !== 'none' && s.visibility !== 'hidden';
        };
        // NBSP/zero-width 공백 정규화
        const norm = s => (s || '').replace(/\\u00a0/g, ' ').replace(/\\u200b/g, '').replace(/\\t/g, ' ');
        const needleN = norm(needle);
        const allText = norm((document.body || document.documentElement).innerText || '');
        const hits = (allText.match(new RegExp(needleN.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&'), 'g')) || []).length;
        // 텍스트 노드를 가진 leaf-ish element만 추적
        const walk = (root) => {
            for (const el of root.querySelectorAll('*')) {
                const own = norm(Array.from(el.childNodes)
                    .filter(n => n.nodeType === 3)
                    .map(n => n.textContent || '').join(''));
                if (own.includes(needleN)) {
                    const r = el.getBoundingClientRect();
                    results.push({
                        tag: el.tagName.toLowerCase(),
                        id: el.id || '',
                        cls: (typeof el.className === 'string' ? el.className : '').slice(0, 50),
                        ce: el.getAttribute('contenteditable') || '',
                        shown: isShown(el),
                        rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
                        own: own.slice(0, 80),
                    });
                }
            }
        };
        walk(document);
        return { occurrences_in_innerText: hits, matches: results };
    }"""

    all_results = []
    total_occurrences = 0
    for frame in page.frames:
        try:
            res = frame.evaluate(finder_js, needle)
        except Exception as e:
            print(f"  [경고] frame 스캔 실패: {e}")
            continue
        if res["matches"] or res["occurrences_in_innerText"]:
            tag = f"[main]" if frame is page.main_frame else f"[iframe:{frame.name or frame.url[:40]}]"
            print(f"\n{tag}")
            print(f"  innerText 내 총 매칭: {res['occurrences_in_innerText']}회")
            total_occurrences += res["occurrences_in_innerText"]
            for m in res["matches"][:10]:
                vis_mark = "✓보임" if m["shown"] and m["rect"]["w"] > 0 and m["rect"]["h"] > 0 else "✗숨김"
                print(f"  - <{m['tag']} id={m['id']} ce={m['ce']}> cls='{m['cls']}' {vis_mark} rect={m['rect']}")
                print(f"    own='{m['own']}'")
            if len(res["matches"]) > 10:
                print(f"  ... 외 {len(res['matches']) - 10}개")
            all_results.append({"frame": tag, "data": res})

    print("=" * 60)
    if total_occurrences == 0:
        print(f"✗ 텍스트 '{needle}' 어디에도 없음")
    else:
        print(f"✓ 총 매칭: {total_occurrences}회 (모든 프레임 합산)")
    print("=" * 60)
    return all_results


def write_blog_post(
    title: str,
    body: str,
    image_path: str | None = None,
    save_draft: bool = True,
) -> bool:
    """Naver 블로그 글 1편 자동 작성 (제목 + 본문 + 선택 이미지 + 임시저장).

    각 단계를 별도 subprocess로 cdp_client.py 명령 실행 — Playwright sync 중첩 회피.
    발행은 절대 자동 안 함. 임시저장까지만 수행.
    """
    import subprocess
    import sys as _sys
    print("=" * 60)
    print(f"블로그 글 작성 시작")
    print(f"  제목: {title!r}  본문: {body[:40]!r}  이미지: {image_path or '없음'}  임시저장: {save_draft}")
    print("=" * 60)

    script = str(ROOT / "scripts" / "cdp_client.py")
    py = _sys.executable

    def _run(args: list[str], label: str, soft: bool = False) -> bool:
        print(f"\n--- {label} ---")
        r = subprocess.run([py, script] + args, cwd=str(ROOT))
        ok = r.returncode == 0
        if soft and not ok:
            print(f"--- {label} (스킵, 해당 없음) ---")
        else:
            print(f"--- {label} {'✓' if ok else '✗'} (exit={r.returncode}) ---")
        return ok

    # 1. 글쓰기 페이지 진입 (현재 URL 무관 — goto는 idempotent)
    _run(["goto", "https://blog.naver.com/skyjwsin?Redirect=Write"], "글쓰기 페이지 이동")
    time.sleep(2)

    # 1.5. 헬스 프로브 — Smart Editor 로드 완료까지 대기
    if not _run(["is-ready", "url_contains:blog.naver", "readystate",
                 "has_element:.se-text-paragraph", "has_button:저장"],
                "에디터 준비 헬스 체크"):
        print("\n⛔ 에디터 로드 안 됨 — 후속 단계 중단")
        return False

    # 2. 임시저장 복원 모달 처리 — 전용 핸들러 (탐지 + 취소 클릭, 없으면 스킵)
    _run(["handle-draft-popup"], "복원 팝업 처리", soft=True)
    time.sleep(0.5)

    # 3. 제목 + 즉시 검증
    ok_t = _run(["type-into", "title", title], "제목 입력")
    time.sleep(0.5)
    ok_t_v = _run(["verify-input", title[:15]], "제목 즉시 검증") if ok_t else False
    if not (ok_t and ok_t_v):
        print(f"\n⛔ 제목 입력/검증 실패 → 후속 단계 중단 (본문/이미지/저장 실행 안 함)")
        print("=" * 60)
        return False

    # 4. 본문 + 즉시 검증
    ok_b = _run(["type-into", "body", body], "본문 입력")
    time.sleep(0.5)
    ok_b_v = _run(["verify-input", body[:15]], "본문 즉시 검증") if ok_b else False
    if not (ok_b and ok_b_v):
        print(f"\n⛔ 본문 입력/검증 실패 → 이미지/저장 중단")
        print("=" * 60)
        return False

    # 5. 이미지 paste
    if image_path:
        _run(["paste-image", image_path, "body"], "이미지 paste")
        time.sleep(1)

    # 6. 임시저장
    if save_draft:
        _run(["click-button", "저장"], "임시저장")
        time.sleep(1)

    print("\n" + "=" * 60)
    print("✓ 블로그 글 작성 흐름 완료")
    print("=" * 60)
    return True


def save_session(label: str | None = None) -> Path:
    """현재 CDP 컨텍스트의 쿠키/localStorage를 storage_state.json으로 저장.

    label 미지정 시 타임스탬프 사용.
    저장 경로: data/browser_sessions/backups/{label}.json
    """
    SESSION_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    name = label or datetime.now().strftime("session_%Y%m%d_%H%M%S")
    out_path = SESSION_BACKUP_DIR / f"{name}.json"

    print("=" * 60)
    print(f"세션 저장: {out_path}")
    print("=" * 60)

    page = get_page()
    page.context.storage_state(path=str(out_path))

    # 저장 내용 요약
    import json
    data = json.loads(out_path.read_text(encoding="utf-8"))
    cookies = data.get("cookies", [])
    origins = data.get("origins", [])
    domains = sorted({c.get("domain", "") for c in cookies})
    print(f"✓ 저장 완료 ({out_path.stat().st_size:,} bytes)")
    print(f"  쿠키: {len(cookies)}개 / 도메인: {len(domains)}")
    print(f"  localStorage origin: {len(origins)}개")
    print("=" * 60)
    return out_path
