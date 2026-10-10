"""navigator_scan — 페이지/링크 스캔 기능."""

from __future__ import annotations

from scripts.browser.cdp.connection import get_page


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
    data: dict[str, list] = {"links": [], "inputs": [], "buttons": [], "editables": [], "iframes": []}
    frame_count = 0
    for frame in page.frames:
        try:
            part = frame.evaluate(scan_js)
        except Exception as e:  # noqa: BLE001 - 페이지의 모든 프레임을 순회하며 링크/입력/버튼 등을 읽기전용으로 수집하는 스캐너 — 개별 프레임 스캔 실패를 경고 로그로 남기고 continue로 다음 프레임 계속.
            print(f"  [경고] frame 스캔 실패 ({frame.url[:50]}): {e}")
            continue
        frame_count += 1
        frame_tag = "[main]" if frame is page.main_frame else f"[iframe:{frame.name or frame.url[:40]}]"
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

    show("LINKS", data["links"], lambda l: f"{l.get('_frame', ''):<24} {l['text'][:30]:<32} → {l['href'][:50]}")  # noqa: E741
    show(
        "INPUTS",
        data["inputs"],
        lambda i: (
            f"{i.get('_frame', ''):<24} <{i['tag']} type={i['type']} name={i['name']} id={i['id']}> ph='{i['placeholder'][:25]}' val='{i['value_preview']}'"
        ),
    )
    show(
        "BUTTONS",
        data["buttons"],
        lambda b: f"{b.get('_frame', ''):<24} '{b['text'][:30]}' aria='{b['aria'][:25]}' id={b['id']}",
    )
    show(
        "EDITABLES",
        data["editables"],
        lambda e: (
            f"{e.get('_frame', ''):<24} <{e['tag']} id={e['id']} ce={e.get('ce', '')} role={e.get('role', '')}> cls='{e.get('cls', '')[:25]}' ph='{e.get('placeholder', '')[:25]}' aria='{e['aria'][:20]}' preview='{e['preview']}'"
        ),
    )
    show("IFRAMES", data["iframes"], lambda f: f"id={f['id']} name={f['name']} src={f['src'][:80]}")

    print("=" * 60)
    print("✓ 조회 완료 — 다음 명령 입력")
    print("=" * 60)
    return data
