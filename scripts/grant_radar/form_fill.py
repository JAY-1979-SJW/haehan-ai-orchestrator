"""form_fill.py — 정부 신청폼 자동입력 (CDP, 제출 직전 정지).

stdin으로 JSON 요청을 받아 CDP(9222)의 대상 탭에 초안을 입력한다.
  요청: {"url_substr": "data.go.kr", "text": "...", "confirm": false, "target_index": null}
  - confirm=false: 채울 필드 계획만 반환(dry-run), 입력 안 함
  - confirm=true : 선택 필드(기본=가장 큰 textarea)에 text 입력
  ★ submit/제출/등록 버튼은 절대 클릭하지 않음 — 최종 제출은 사용자.

L5 Site Module / L4 Browser Engine. 외부 발행/제출 없음.

실행(라우터가 subprocess로 호출):
    echo '{"url_substr":"data.go.kr","text":"...","confirm":false}' | python -m scripts.grant_radar.form_fill
"""

from __future__ import annotations

import json
import logging
import sys

CDP = "http://127.0.0.1:9222"

# 후보 필드 탐지 + 최적 대상 선정(가장 큰 textarea > 가장 긴 text input)
_PLAN_JS = """
(tagBest) => {
  const cands = [...document.querySelectorAll('textarea, input[type=text], input:not([type])')]
    .filter(e => e.offsetParent !== null && !e.disabled && !e.readOnly);
  const desc = cands.map((e, i) => {
    let label = '';
    if (e.id) { const l = document.querySelector(`label[for="${e.id}"]`); if (l) label = l.innerText.trim(); }
    if (!label) label = e.getAttribute('aria-label') || e.placeholder || e.name || '';
    return { i, tag: e.tagName, label: (label || '').slice(0, 40), value_len: (e.value || '').length,
             area: e.tagName === 'TEXTAREA' ? (e.rows || 0) * (e.cols || 0) || 9999 : 0 };
  });
  // 최적: textarea 중 area 최대, 없으면 text input 중 첫 개
  let best = -1, bestArea = -1;
  desc.forEach(d => { if (d.tag === 'TEXTAREA' && d.area > bestArea) { bestArea = d.area; best = d.i; } });
  if (best < 0 && desc.length) best = desc[0].i;
  if (tagBest && best >= 0) cands[best].setAttribute('data-haehan-fill', '1');
  return { fields: desc.slice(0, 20), best };
}
"""


def run(req: dict) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        return {"ok": False, "reason": f"playwright_missing:{e}"}

    url_substr = (req.get("url_substr") or "").strip()
    text = req.get("text") or ""
    confirm = bool(req.get("confirm"))

    with sync_playwright() as pw:
        try:
            b = pw.chromium.connect_over_cdp(CDP, timeout=30000)
        except Exception as e:
            return {"ok": False, "reason": f"cdp_connect_failed:{e}"}
        ctx = b.contexts[0]
        pages = ctx.pages
        target = None
        if url_substr:
            target = next((p for p in pages if url_substr in p.url), None)
        if not target:
            return {"ok": False, "reason": "target_tab_not_found", "open_urls": [p.url[:80] for p in pages]}

        result = target.evaluate(_PLAN_JS, confirm)
        fields = result.get("fields", [])
        best = result.get("best", -1)

        if not confirm:
            return {"ok": False, "need_confirm": True, "url": target.url, "fields": fields, "best": best}

        if best < 0:
            return {"ok": False, "reason": "no_fillable_field", "url": target.url}

        # 선택 필드에 입력 (submit 클릭 없음)
        try:
            loc = target.locator('[data-haehan-fill="1"]')
            loc.fill(text)
            target.evaluate(
                "() => { const e=document.querySelector('[data-haehan-fill]'); if(e) e.removeAttribute('data-haehan-fill'); }"
            )
        except Exception as e:
            return {"ok": False, "reason": f"fill_failed:{e}", "url": target.url}

        return {
            "ok": True,
            "url": target.url,
            "filled_index": best,
            "filled_len": len(text),
            "note": "입력만 완료. 제출 버튼은 사용자가 직접 누르세요.",
        }


def main() -> int:
    try:
        req = json.loads(sys.stdin.read() or "{}")
    except Exception:
        logging.getLogger(__name__).warning("요청 JSON 파싱 실패", exc_info=True)
        req = {}
    print(json.dumps(run(req), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
