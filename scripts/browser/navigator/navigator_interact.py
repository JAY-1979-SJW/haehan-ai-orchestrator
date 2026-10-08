"""navigator_interact — 사용자 입력·클릭·이미지 붙여넣기."""

from __future__ import annotations

import contextlib
import time

from scripts.browser.navigator.navigator_common import _find_element_in_frames
from scripts.browser.cdp.connection import get_page
from scripts.common.op_log import log_op

_TYPE_FINDER_JS = """(needle) => {
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


_NATIVE_SET_JS = """(e, val) => {
                e.focus();
                const nativeSetter = Object.getOwnPropertyDescriptor(
                    Object.getPrototypeOf(e), 'value'
                );
                if (nativeSetter && nativeSetter.set) {
                    nativeSetter.set.call(e, val);
                } else {
                    e.value = val;
                }
                e.dispatchEvent(new Event('input',  {bubbles: true}));
                e.dispatchEvent(new Event('change', {bubbles: true}));
            }"""


def _wait_for_element(page, finder, target):
    # 요소 등장 대기 (최대 10초) — Smart Editor 로드 시간 대응
    frame, handle = None, None
    deadline = time.time() + 10
    while time.time() < deadline:
        frame, handle = _find_element_in_frames(page, finder, target)
        if frame is not None:
            break
        time.sleep(0.5)
    return frame, handle


def _set_input_value(handle, text):
    # Vue.js/React 반응형 폼 대응: nativeInputValueSetter로 value 설정 후 input/change 이벤트 발행
    handle.evaluate(_NATIVE_SET_JS, text)
    time.sleep(0.15)


def _set_clipboard_text(text) -> bool:
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
        return True
    except Exception as ce:  # noqa: BLE001 - 범용 페이지 상호작용 헬퍼(클립보드 붙여넣기/클릭/타입) - 실패시 False 반환 또는 폴백 방법 시도, 클립보드 내용 자체를 로그에 남기지 않아 자격증명 노출 없음
        print(f"  [경고] 클립보드 설정 실패: {ce}")
        return False


def _text_present(frame, handle, text) -> bool:
    # 4. paste 결과 검증 — handle 자체 + child + 전체 페이지 모두 확인
    # handle 자신의 innerText (child span 포함)
    try:
        h_text = handle.evaluate("e => e.innerText || e.textContent || ''")
        if text[:10] in h_text:
            return True
    except Exception:  # noqa: BLE001 - 범용 페이지 상호작용 헬퍼(클립보드 붙여넣기/클릭/타입) - 실패시 False 반환 또는 폴백 방법 시도, 클립보드 내용 자체를 로그에 남기지 않아 자격증명 노출 없음
        pass
    # 폴백: 페이지 전체 검색
    snippet = text[:30] if len(text) >= 10 else text
    for fr in frame.page.frames:
        try:
            if snippet in fr.evaluate("() => (document.body && document.body.innerText) || ''"):
                return True
        except Exception:  # noqa: BLE001 - 범용 페이지 상호작용 헬퍼(클립보드 붙여넣기/클릭/타입) - 실패시 False 반환 또는 폴백 방법 시도, 클립보드 내용 자체를 로그에 남기지 않아 자격증명 노출 없음
            continue
    return False


def _fill_contenteditable(frame, handle, text, clear):
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

    clipboard_ok = _set_clipboard_text(text)

    # 3. Ctrl+V (paste) — Smart Editor의 정식 paste 핸들러로 라우팅
    if clipboard_ok:
        frame.page.keyboard.press("Control+V")
        time.sleep(1.5)  # Smart Editor 렌더 대기 (child span 생성)

    if clipboard_ok and _text_present(frame, handle, text):
        pass  # paste 성공 — 폴백 절대 안 함
    elif not clipboard_ok:
        # 클립보드 자체 실패 시에만 폴백
        try:
            frame.page.keyboard.insert_text(text)
            time.sleep(0.5)
        except Exception:  # noqa: BLE001 - 범용 페이지 상호작용 헬퍼(클립보드 붙여넣기/클릭/타입) - 실패시 False 반환 또는 폴백 방법 시도, 클립보드 내용 자체를 로그에 남기지 않아 자격증명 노출 없음
            handle.evaluate("(e, t) => { e.focus(); document.execCommand('insertText', false, t); }", text)


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
    # 범용 페이지 상호작용 헬퍼 - 탭 포커스 실패시 폴백 방법 시도, 클립보드 내용은 로그에 남기지 않음
    with contextlib.suppress(Exception):
        page.bring_to_front()  # 키 이벤트가 정확히 이 탭으로 가도록 보장
    print(f"입력 시도: target='{target}' text='{text[:40]}...' ({page.url})")
    print("=" * 60)


    frame, handle = _wait_for_element(page, _TYPE_FINDER_JS, target)
    if frame is None:
        print("✗ 매칭 요소 없음 (10초 대기 후에도)")
        print("=" * 60)
        return False

    tag = handle.evaluate("e => e.tagName.toLowerCase()")
    print(f"  매칭: <{tag}> in frame '{frame.name or frame.url[:40]}'")

    try:
        handle.evaluate("e => e.scrollIntoView({block:'center'})")
        if tag in ("input", "textarea"):
            _set_input_value(handle, text)
        else:
            _fill_contenteditable(frame, handle, text, clear)

        # 입력 결과 검증 — 표준 verify_input 사용 (page 재사용으로 중첩 회피)
        from scripts.browser.navigator.navigator_verify import verify_input

        v = verify_input(text, timeout_s=3.0, page=page)
        mark = "✓" if v["found"] else "⚠"
        print(f"{mark} 입력 결과: found={v['found']} where={v['where']} ({v['elapsed_ms']}ms)")
        if v["found"]:
            print(f"  실제값: '{v['actual']}'")
        print("=" * 60)
        return v["found"]
    except Exception as e:  # noqa: BLE001 - 범용 페이지 상호작용 헬퍼(클립보드 붙여넣기/클릭/타입) - 실패시 False 반환 또는 폴백 방법 시도, 클립보드 내용 자체를 로그에 남기지 않아 자격증명 노출 없음
        print(f"⚠ 입력 실패: {e}")
        print("=" * 60)
        return False


def click_link(text: str, timeout_ms: int = 15000) -> bool:
    """현재 페이지에서 텍스트가 일치하는 링크를 찾아 클릭하고 navigation 대기.

    매칭 우선순위: 정확 일치 > 시작 일치 > 부분 일치 (보이는 링크 중에서만)
    클릭 후 새 탭이 열리면 그 탭으로 page 객체 갱신은 하지 않음 (현 탭 기준).
    """
    print("=" * 60)
    page = get_page()
    print(f"링크 클릭 시도: '{text}' (현재: {page.url})")
    print("=" * 60)

    target = page.evaluate(
        """(needle) => {
        const all = Array.from(document.querySelectorAll('a'))
            .filter(a => a.offsetParent && (a.innerText || a.textContent || '').trim());
        const items = all.map(a => ({
            text: (a.innerText || a.textContent || '').trim(),
            href: a.href,
            target: a.target || '',
        }));
        const exact   = items.find(i => i.text === needle);
        const starts  = items.find(i => i.text.startsWith(needle));
        const partial = items.find(i => i.text.includes(needle));
        const hit = exact || starts || partial;
        return hit || null;
    }""",
        text,
    )

    if not target:
        print("✗ 매칭되는 링크 없음")
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
        except Exception as e:  # noqa: BLE001 - 범용 페이지 상호작용 헬퍼(클립보드 붙여넣기/클릭/타입) - 실패시 False 반환 또는 폴백 방법 시도, 클립보드 내용 자체를 로그에 남기지 않아 자격증명 노출 없음
            print(f"⚠ expect_page 실패: {e}")
    else:
        # 같은 탭 케이스: navigation 이벤트 대기
        try:
            with page.expect_navigation(timeout=timeout_ms, wait_until="domcontentloaded"):
                page.evaluate(click_js, text)
            new_page = page
        except Exception:  # noqa: BLE001 - 범용 페이지 상호작용 헬퍼(클립보드 붙여넣기/클릭/타입) - 실패시 False 반환 또는 폴백 방법 시도, 클립보드 내용 자체를 로그에 남기지 않아 자격증명 노출 없음
            if page.url != url_before and page.url != "about:blank":
                new_page = page

    if new_page is None:
        print(f"⚠ 이동 감지 안 됨 (target={target_attr or '동일창'})")
        print(f"  현재 URL: {page.url}")
        print("=" * 60)
        return False

    # 범용 페이지 상호작용 헬퍼 - 로딩 대기 실패시 무시하고 계속 진행(폴백)
    with contextlib.suppress(Exception):
        new_page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    where = "새 탭" if new_page is not page else "현재 탭"
    print(f"✓ 이동 완료 ({where}): {new_page.url}")
    print("=" * 60)
    from scripts.browser.navigator.navigator_scan import scan_page

    scan_page()
    return True


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
        print("✗ 매칭 버튼 없음")
        print("=" * 60)
        log_op("click_button", ok=False, message="매칭 버튼 없음", text=text, url=page.url)
        return False

    btn_text = handle.evaluate("e => (e.innerText || e.textContent || '').trim()")
    print(f"  매칭: '{btn_text[:40]}' in frame '{frame.name or frame.url[:40]}'")

    try:
        handle.evaluate("e => e.scrollIntoView({block:'center'})")
        handle.evaluate("e => e.click()")
        print("✓ 클릭 완료")
    except Exception as e:  # noqa: BLE001 - 범용 페이지 상호작용 헬퍼(클립보드 붙여넣기/클릭/타입) - 실패시 False 반환 또는 폴백 방법 시도, 클립보드 내용 자체를 로그에 남기지 않아 자격증명 노출 없음
        print(f"⚠ 클릭 실패: {e}")
        print("=" * 60)
        log_op("click_button", ok=False, message=str(e), text=text, url=page.url)
        return False

    # 결과 감지 (URL 변경 / 새 탭)
    time.sleep(1)
    from scripts.browser.navigator.navigator_scan import scan_page

    if page.url != url_before:
        print(f"  → URL 변경: {page.url}")
        log_op("click_button", ok=True, text=text, result="url_change", url=page.url)
        scan_page()
        return True
    new_pages = set(page.context.pages) - pages_before
    if new_pages:
        new = next(iter(new_pages))
        print(f"  → 새 탭: {new.url}")
        log_op("click_button", ok=True, text=text, result="new_tab", url=new.url)
        scan_page()
        return True
    print("  → 페이지 변화 없음 (모달/AJAX 가능성)")
    print("=" * 60)
    log_op("click_button", ok=True, text=text, result="no_nav", url=page.url)
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
        print("✗ 대상 element 없음")
        return False

    # 2. 클릭으로 활성화
    box = handle.bounding_box()
    if box:
        frame.page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    time.sleep(0.5)

    # 3. 이미지를 CF_DIB로 클립보드에 설정
    try:
        import io

        import win32clipboard
        import win32con
        from PIL import Image

        img: Image.Image = Image.open(img_path)
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
    except Exception as e:  # noqa: BLE001 - 범용 페이지 상호작용 헬퍼(클립보드 붙여넣기/클릭/타입) - 실패시 False 반환 또는 폴백 방법 시도, 클립보드 내용 자체를 로그에 남기지 않아 자격증명 노출 없음
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
