"""navigator_verify — 입력 검증·상태 확인·팝업 처리."""

from __future__ import annotations

import contextlib

from scripts.browser.navigator.navigator_common import _normalize_text
from scripts.browser.cdp.connection import get_page


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
            except Exception:  # noqa: BLE001 - 페이지/프레임 상태 검증 헬퍼(텍스트/버튼/엘리먼트 존재 확인) - 모든 except 가 (False, 사유) 형태 결과를 반환, 읽기전용 검증 로직
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
        except Exception as e:  # noqa: BLE001 - 페이지/프레임 상태 검증 헬퍼(텍스트/버튼/엘리먼트 존재 확인) - 모든 except 가 (False, 사유) 형태 결과를 반환, 읽기전용 검증 로직
            print(f"  [경고] frame 스캔 실패: {e}")
            continue
        if res["matches"] or res["occurrences_in_innerText"]:
            tag = "[main]" if frame is page.main_frame else f"[iframe:{frame.name or frame.url[:40]}]"
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


_HAS_BUTTON_JS = """(needle) => {
                    const btns = document.querySelectorAll('button, [role=button]');
                    for (const b of btns) {
                        const t = (b.innerText || b.textContent || '').trim();
                        if (t === needle || t.split('\\n').some(l => l.trim() === needle)) return true;
                    }
                    return false;
                }"""


def _check_readystate(page) -> tuple[bool, str]:
    states = []
    for fr in page.frames:
        try:
            states.append(fr.evaluate("() => document.readyState"))
        except Exception:  # noqa: BLE001 - 페이지/프레임 상태 검증 헬퍼(텍스트/버튼/엘리먼트 존재 확인) - 모든 except 가 (False, 사유) 형태 결과를 반환, 읽기전용 검증 로직
            states.append("error")
    ok = all(s == "complete" for s in states)
    return (ok, f"states={states}")


def _check_has_text(page, arg) -> tuple[bool, str]:
    for fr in page.frames:
        try:
            t = fr.evaluate("() => (document.body && document.body.innerText) || ''")
            if arg in t:
                return (True, f"frame={fr.name or 'main'}")
        except Exception:  # noqa: BLE001 - 페이지/프레임 상태 검증 헬퍼(텍스트/버튼/엘리먼트 존재 확인) - 모든 except 가 (False, 사유) 형태 결과를 반환, 읽기전용 검증 로직
            continue
    return (False, "not found in any frame")


def _check_has_button(page, arg) -> tuple[bool, str]:
    for fr in page.frames:
        try:
            if fr.evaluate(_HAS_BUTTON_JS, arg):
                return (True, f"frame={fr.name or 'main'}")
        except Exception:  # noqa: BLE001 - 페이지/프레임 상태 검증 헬퍼(텍스트/버튼/엘리먼트 존재 확인) - 모든 except 가 (False, 사유) 형태 결과를 반환, 읽기전용 검증 로직
            continue
    return (False, "button not found")


def _check_has_element(page, arg) -> tuple[bool, str]:
    for fr in page.frames:
        try:
            ok = fr.evaluate(f"() => !!document.querySelector({arg!r})")
            if ok:
                return (True, f"frame={fr.name or 'main'}")
        except Exception:  # noqa: BLE001 - 페이지/프레임 상태 검증 헬퍼(텍스트/버튼/엘리먼트 존재 확인) - 모든 except 가 (False, 사유) 형태 결과를 반환, 읽기전용 검증 로직
            continue
    return (False, "element not found")


def _eval_check_spec(page, spec: str) -> tuple[bool, str]:
    if ":" in spec:
        kind, arg = spec.split(":", 1)
    else:
        kind, arg = spec, ""
    try:
        if kind == "url_contains":
            return (arg in page.url, page.url)
        if kind == "readystate":
            return _check_readystate(page)
        if kind == "has_text":
            return _check_has_text(page, arg)
        if kind == "has_button":
            return _check_has_button(page, arg)
        if kind == "has_element":
            return _check_has_element(page, arg)
        return (False, f"unknown check kind: {kind}")
    except Exception as e:  # noqa: BLE001 - 페이지/프레임 상태 검증 헬퍼(텍스트/버튼/엘리먼트 존재 확인) - 모든 except 가 (False, 사유) 형태 결과를 반환, 읽기전용 검증 로직
        return (False, f"error: {e}")


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
        return _eval_check_spec(page, spec)

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
        "results": [{"check": spec, "passed": v[0], "reason": v[1]} for spec, v in results.items()],
    }


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
            except Exception:  # noqa: BLE001 - 페이지/프레임 상태 검증 헬퍼(텍스트/버튼/엘리먼트 존재 확인) - 모든 except 가 (False, 사유) 형태 결과를 반환, 읽기전용 검증 로직
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
    with contextlib.suppress(Exception):
        clicked = detected_in_frame.evaluate(click_js)
    _t.sleep(0.5)

    return {
        "detected": True,
        "action": "cancel_clicked" if clicked else "cancel_failed",
        "elapsed_ms": int((_t.time() - start) * 1000),
    }
