"""단일 페이지 구조 스냅샷 + JSON 저장.

각 프레임에서 다음 메타데이터를 추출한다:
  - links: text, href, target, visible
  - inputs: tag/type/name/id/placeholder/aria/required/visible
  - buttons: text/id/aria/cls/visible (a, button, [role="button"])
  - forms: id/action/method/name
  - headings: h1/h2/h3 텍스트
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.common.logger import get_logger
from scripts.browser.cdp.connection import get_page

_log = get_logger(__name__)


_EXTRACT_FRAME_JS = r"""
() => {
    // 소속 폼 키: "<문서 내 폼 순번>:<id 또는 name>" (폼 밖이면 빈 문자열) — 업무 지도가 컨트롤을 폼별로 묶는 데 쓴다
    const formKey = el => {
        const f = el.closest('form');
        // f.id 는 폼 안에 name="id" 입력창이 있으면 그 요소를 가리키므로 속성 값을 직접 읽는다
        return f ? Array.from(document.forms).indexOf(f) + ':' + (f.getAttribute('id') || f.getAttribute('name') || '') : '';
    };
    // 문서 안 위치(요소 순번): 페이지 전체를 감싸는 폼에서도 "입력창 근처의 컨트롤"만 고를 수 있게 한다
    const order = new Map(Array.from(document.querySelectorAll('*')).map((e, i) => [e, i]));
    // 버튼이 속한 ARIA 랜드마크(사이트 공통 메뉴 판별용). header/footer 는 article·section·main 안이면 banner/contentinfo 가 아니다(HTML-AAM).
    const landmarkOf = (el) => {
        const r = el.closest('[role="navigation"],[role="banner"],[role="contentinfo"],[role="complementary"],[role="main"],[role="search"],nav,header,footer,aside,main');
        if (!r) return '';
        const role = r.getAttribute('role');
        if (role) return role;
        const t = r.tagName;
        if (t === 'NAV') return 'navigation';
        if (t === 'ASIDE') return 'complementary';
        if (t === 'MAIN') return 'main';
        const scoped = r.parentElement && r.parentElement.closest('article,section,main,aside,nav');
        if (t === 'HEADER') return scoped ? '' : 'banner';
        if (t === 'FOOTER') return scoped ? '' : 'contentinfo';
        return '';
    };
    // 메뉴 목록 판별(M8): 링크가 li 의 직계 자식일 때만 그 목록(ul/ol)을 그룹으로 본다 — 상품 카드처럼 깊이 들어간 링크는 메뉴가 아니다.
    const listGroup = a => (a.parentElement && a.parentElement.tagName === 'LI' && a.parentElement.parentElement) ? String(order.get(a.parentElement.parentElement)) : '';
    const links = Array.from(document.querySelectorAll('a')).map(a => ({
        abs: a.href || '',
        landmark: landmarkOf(a),
        group: listGroup(a),
        text: (a.innerText || '').trim().slice(0, 80),
        href: a.getAttribute('href') || '',
        target: a.getAttribute('target') || '',
        visible: a.offsetParent !== null,
        form: formKey(a),
        pos: order.get(a),
    })).filter(l => l.text || l.href);
    const inputs = Array.from(document.querySelectorAll('input, textarea, select')).map(e => ({
        tag: e.tagName,
        type: e.getAttribute('type') || '',
        name: e.getAttribute('name') || '',
        id: e.id || '',
        placeholder: e.getAttribute('placeholder') || '',
        aria: e.getAttribute('aria-label') || '',
        required: e.required || false,
        visible: e.offsetParent !== null,
        form: formKey(e),
        pos: order.get(e),
    }));
    // 편집 영역(contenteditable·role=textbox)도 입력창이다(블로그 에디터 등). 이름이 없어 문서 순번으로 정한다.
    const editables = Array.from(document.querySelectorAll('[contenteditable="true"], [role="textbox"]')).filter(e => !e.closest('input, textarea')).map((e, i) => ({
        tag: 'EDITABLE',
        type: 'editable',
        name: e.getAttribute('name') || 'editable_' + (i + 1),
        id: e.id || '',
        placeholder: e.getAttribute('data-placeholder') || e.getAttribute('placeholder') || '',
        aria: e.getAttribute('aria-label') || '',
        required: false,
        visible: e.offsetParent !== null,
        form: formKey(e),
        pos: order.get(e),
    }));
    inputs.push(...editables);
    // <input type="submit|button|image"> 도 버튼이다(흔한 검색 폼: 입력창 + submit 입력). 글자는 value·alt·title 에서 읽는다.
    const buttons = Array.from(document.querySelectorAll('button, [role="button"], input[type="submit"], input[type="button"], input[type="image"]')).map(b => ({
        text: (b.innerText || b.value || b.alt || b.title || '').trim().slice(0, 60),
        id: b.id || '',
        aria: b.getAttribute('aria-label') || '',
        cls: (b.className || '').toString().slice(0, 80),
        visible: b.offsetParent !== null,
        landmark: landmarkOf(b),
        form: formKey(b),
        pos: order.get(b),
    })).filter(b => b.text || b.aria);
    const forms = Array.from(document.querySelectorAll('form')).map(f => ({
        id: f.id || '',
        action: f.getAttribute('action') || '',
        method: f.getAttribute('method') || 'get',
        name: f.getAttribute('name') || '',
    }));
    const headings = Array.from(document.querySelectorAll('h1, h2, h3')).map(h => ({
        level: h.tagName,
        text: (h.innerText || '').trim().slice(0, 100),
    }));
    return {links, inputs, buttons, forms, headings};
}
"""


def slugify(url: str) -> str:
    s = url.replace("https://", "").replace("http://", "")
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", s)[:120]


def collect(page) -> dict[str, Any]:
    """페이지 구조 수집만 한다(파일 저장 없음). 반환 dict 는 snapshot() 저장본과 같은 모양."""
    url = page.url
    data: dict[str, Any] = {
        "url": url,
        "title": page.title(),
        "captured_at": datetime.now().isoformat(),
        "frames": [],
    }

    _log.info("[explorer] 페이지 스냅샷 시작: %s", url)

    for i, f in enumerate(page.frames):
        try:
            info = f.evaluate(_EXTRACT_FRAME_JS)
            counts = {k: len(info[k]) for k in ("links", "inputs", "buttons", "forms", "headings")}
            data["frames"].append({"idx": i, "url": f.url, **info, "counts": counts})
            _log.debug(
                "[explorer] 프레임[%d] 추출 완료: %d links, %d inputs, %d buttons",
                i,
                counts["links"],
                counts["inputs"],
                counts["buttons"],
            )
        except Exception as e:  # noqa: BLE001 - iframe 프레임 정보 추출(page.evaluate) 실패를 data에 error로 기록하고 다음 프레임 계속 처리 - 읽기전용 페이지 스냅샷, 실패한 프레임만 누락될 뿐 위험 조작 없음
            data["frames"].append({"idx": i, "url": f.url, "error": str(e)})
            _log.warning("[explorer] 프레임[%d] 추출 실패: %s", i, e)
    return data


def snapshot(page, save_dir: str = "data/sitemap") -> dict[str, Any]:
    """페이지 스냅샷 추출 + 저장. 반환: {path, url, title, frames, counts}.

    Page 상태는 변경하지 않음 (read-only).
    """
    data = collect(page)
    Path(save_dir).mkdir(parents=True, exist_ok=True)
    out_path = Path(save_dir) / f"{slugify(data['url'])}.json"
    with out_path.open("w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)

    data["path"] = str(out_path)
    _log.info("[explorer] 페이지 스냅샷 저장: %s", out_path)
    return data


def run_cli(args: list[str]) -> None:
    """CLI: explore page [save_dir]."""
    save_dir = args[0] if args else "data/sitemap"
    _log.info("[explorer] CLI 페이지 스냅샷 요청")
    page = get_page()
    r = snapshot(page, save_dir=save_dir)
    print(f"\n✓ 스냅샷 저장: {r['path']}")
    print(f"  URL: {r['url']}")
    print(f"  제목: {r['title']}")
    for fr in r["frames"]:
        if "counts" in fr:
            c = fr["counts"]
            print(
                f"  프레임[{fr['idx']}] links={c['links']} inputs={c['inputs']} "
                f"buttons={c['buttons']} forms={c['forms']} headings={c['headings']}"
            )
        else:
            print(f"  프레임[{fr['idx']}] error: {fr.get('error')}")
