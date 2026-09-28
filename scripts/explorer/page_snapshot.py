"""단일 페이지 구조 스냅샷 + JSON 저장.

각 프레임에서 다음 메타데이터를 추출한다:
  - links: text, href, target
  - inputs: tag/type/name/id/placeholder/aria/required/visible
  - buttons: text/id/aria/cls/visible (a, button, [role="button"])
  - forms: id/action/method/name
  - headings: h1/h2/h3 텍스트
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any

from scripts.logger import get_logger
from scripts.web_connector import get_page

_log = get_logger(__name__)


_EXTRACT_FRAME_JS = r"""
() => {
    const links = Array.from(document.querySelectorAll('a')).map(a => ({
        text: (a.innerText || '').trim().slice(0, 80),
        href: a.getAttribute('href') || '',
        target: a.getAttribute('target') || '',
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
    }));
    const buttons = Array.from(document.querySelectorAll('button, [role="button"]')).map(b => ({
        text: (b.innerText || '').trim().slice(0, 60),
        id: b.id || '',
        aria: b.getAttribute('aria-label') || '',
        cls: (b.className || '').toString().slice(0, 80),
        visible: b.offsetParent !== null,
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


def snapshot(page, save_dir: str = "data/sitemap") -> dict[str, Any]:
    """페이지 스냅샷 추출 + 저장. 반환: {path, url, title, frames, counts}.

    Page 상태는 변경하지 않음 (read-only).
    """
    url = page.url
    title = page.title()
    data: dict[str, Any] = {
        "url": url,
        "title": title,
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

    os.makedirs(save_dir, exist_ok=True)
    out_path = os.path.join(save_dir, f"{slugify(url)}.json")
    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)

    data["path"] = out_path
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
