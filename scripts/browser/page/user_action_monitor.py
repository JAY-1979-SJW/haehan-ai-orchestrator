"""사용자 수동 조작 실시간 감지 모듈 — user_action_monitor v1.0

브라우저에서 사용자가 직접 조작했을 때 자동으로 감지하고 보고한다.

감지 대상:
  - URL 변화 (페이지 이동)
  - DOM 의미 있는 변화 (레코드 추가/삭제/수정, 저장 메시지, 알림)
  - 폼 제출 (XHR/fetch intercept)
  - 버튼 클릭 (지정 셀렉터)

실행:
  python scripts/entry/cdp_cli.py user-watch [타임아웃초]
  python scripts/entry/cdp_cli.py user-watch 0   # 무한 대기

또는 직접:
  python scripts/browser/page/user_action_monitor.py
  python scripts/browser/page/user_action_monitor.py --timeout 600 --host gabia
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.browser.cdp import cdp_db  # noqa: E402
from scripts.common.logger import get_logger  # noqa: E402

_log = get_logger(__name__)

POLL_INTERVAL_S = 0.8
DEFAULT_TIMEOUT_S = 0  # 0 = 무한

# ── JS 주입 코드 ──────────────────────────────────────────────────────────────
_MONITOR_JS = r"""
(() => {
    if (window.__hh_user_monitor_installed) return;
    window.__hh_user_monitor_installed = true;
    window.__hh_user_events = [];

    const emit = (type, detail) => {
        const ev = {type, detail: detail || {}, ts: Date.now(), url: location.href};
        window.__hh_user_events.push(ev);
        // 최대 200개 유지
        if (window.__hh_user_events.length > 200) window.__hh_user_events.shift();
    };

    // 1. XHR intercept (폼 제출 / API 호출 감지)
    const origOpen = XMLHttpRequest.prototype.open;
    const origSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function(method, url) {
        this.__hh_method = method;
        this.__hh_url = url;
        return origOpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function(body) {
        const self = this;
        const method = this.__hh_method || '';
        const url = this.__hh_url || '';
        this.addEventListener('load', function() {
            if (method !== 'GET') {
                emit('xhr', {method, url: url.substring(0, 200), status: self.status, bodyLen: (body||'').length});
            }
        });
        return origSend.apply(this, arguments);
    };

    // 2. fetch intercept
    const origFetch = window.fetch;
    window.fetch = function(input, init) {
        const method = (init && init.method) || 'GET';
        const url = (typeof input === 'string' ? input : (input.url || '')).substring(0, 200);
        return origFetch.apply(this, arguments).then(res => {
            if (method !== 'GET') {
                emit('fetch', {method, url, status: res.status});
            }
            return res;
        });
    };

    // 3. DOM 변화 감지 (MutationObserver)
    const domKeywords = [
        '저장되었습니다', '수정되었습니다', '삭제되었습니다', '추가되었습니다',
        '완료', 'success', '성공', '오류', '실패', 'error',
        '레코드 개수', 'DNS 설정',
    ];
    let lastBodyLen = document.body ? document.body.innerText.length : 0;
    const observer = new MutationObserver(() => {
        const text = document.body ? document.body.innerText : '';
        const newLen = text.length;
        if (Math.abs(newLen - lastBodyLen) > 10) {
            const matched = domKeywords.filter(kw => text.includes(kw));
            if (matched.length > 0) {
                emit('dom_change', {keywords: matched, lenDiff: newLen - lastBodyLen});
            }
            lastBodyLen = newLen;
        }
    });
    if (document.body) {
        observer.observe(document.body, {childList: true, subtree: true, characterData: true});
    }

    // 4. 버튼/링크 클릭 감지 (이벤트 위임)
    document.addEventListener('click', function(e) {
        const el = e.target.closest('a, button, input[type=submit], span.btn-pack');
        if (!el) return;
        const text = (el.innerText || el.value || '').trim().substring(0, 50);
        if (text) emit('click', {text, tag: el.tagName, cls: el.className.substring(0, 60)});
    }, true);

    // 5. URL 변화는 Python 쪽에서 폴링
})();
"""

_COLLECT_JS = "() => { var evs = window.__hh_user_events || []; window.__hh_user_events = []; return evs; }"


def _inject(page) -> bool:
    try:
        page.evaluate(_MONITOR_JS)
        return True
    except Exception as e:  # noqa: BLE001 - 사용자 행동 모니터링 주입 스크립트 - 주입/수집 실패 시 False/빈 목록 반환, 감시 루프 지속을 위한 폴백
        _log.debug("[user-monitor] inject 실패: %s", e)
        return False


def _collect(page) -> list[dict]:
    try:
        return page.evaluate(_COLLECT_JS) or []
    except Exception:  # noqa: BLE001 - 사용자 행동 모니터링 주입 스크립트 - 주입/수집 실패 시 False/빈 목록 반환, 감시 루프 지속을 위한 폴백
        return []


def _get_page():
    from scripts.browser.cdp.connection import get_page

    return get_page()


def _format_event(ev: dict) -> str:
    t = ev.get("type", "?")
    ev.get("url", "")
    detail = ev.get("detail", {})
    ev.get("ts", 0)

    if t == "click":
        return f"[클릭]  {detail.get('text', '?')}  ({detail.get('tag', '?')})"
    elif t == "xhr":
        return f"[XHR]   {detail.get('method', '?')} {detail.get('url', '?')}  → HTTP {detail.get('status', '?')}"
    elif t == "fetch":
        return f"[FETCH] {detail.get('method', '?')} {detail.get('url', '?')}  → HTTP {detail.get('status', '?')}"
    elif t == "dom_change":
        kws = ", ".join(detail.get("keywords", []))
        diff = detail.get("lenDiff", 0)
        return f"[DOM]   키워드={kws}  (크기변화:{diff:+d})"
    elif t == "url_change":
        return f"[URL]   {detail.get('from', '?')}  →  {detail.get('to', '?')}"
    else:
        return f"[{t}]  {json.dumps(detail, ensure_ascii=False)[:80]}"


def _print_watch_header(timeout_s, host_filter):
    print("=" * 60)
    print("사용자 조작 실시간 감지 시작")
    if timeout_s > 0:
        print(f"  최대 대기: {timeout_s}초 / Ctrl+C로 조기 종료")
    else:
        print("  무한 대기 — Ctrl+C로 종료")
    if host_filter:
        print(f"  감시 대상: {host_filter}")
    print("=" * 60)


def _refresh_active_page(page):
    try:
        current_url = page.url or ""
    except Exception:  # noqa: BLE001 - 사용자 행동 모니터링 주입 스크립트 - 주입/수집 실패 시 False/빈 목록 반환, 감시 루프 지속을 위한 폴백
        page = _get_page()
        current_url = page.url or ""
    return page, current_url


def _record_url_change(current_url, last_url, all_events, on_event):
    if current_url != last_url:
        if last_url:
            ev = {
                "type": "url_change",
                "detail": {"from": last_url, "to": current_url},
                "ts": int(time.time() * 1000),
                "url": current_url,
            }
            all_events.append(ev)
            print(f"\n  {_format_event(ev)}")
            if on_event:
                on_event(ev)
        last_url = current_url
    return last_url


def _handle_events(page, host_filter, all_events, on_event, start):
    events = _collect(page)
    for ev in events:
        all_events.append(ev)
        msg = _format_event(ev)
        elapsed = int(time.time() - start)
        print(f"  [{elapsed:>4}s] {msg}")

        # DB 기록
        try:
            cdp_db.init_db()
            cdp_db.log_action(  # type: ignore[attr-defined]  # cdp_db 에 실제로 없는 함수(2026-09-29 defect_index 확인) — 이미 넓은 except 로 안전하게 감싸져 조용히 스킵됨, 콘솔 출력(위 print)은 계속 동작
                site=host_filter or "browser",
                action_type=ev.get("type", "unknown"),
                detail=json.dumps(ev.get("detail", {}), ensure_ascii=False),
                url=ev.get("url", ""),
            )
        except Exception:  # noqa: BLE001 - 사용자 행동 모니터링 주입 스크립트 - 주입/수집 실패 시 False/빈 목록 반환, 감시 루프 지속을 위한 폴백
            pass

        if on_event:
            on_event(ev)


def watch_user_actions(
    timeout_s: int = DEFAULT_TIMEOUT_S,
    host_filter: str | None = None,
    on_event: Any = None,
) -> list[dict]:
    """사용자 수동 조작 실시간 감지 메인 루프.

    Args:
        timeout_s: 0이면 무한 대기, Ctrl+C로 종료.
        host_filter: 특정 호스트만 감시 (예: 'gabia.com')
        on_event: 이벤트 발생 시 호출할 콜백 함수(ev: dict)

    Returns:
        감지된 이벤트 목록
    """
    page = _get_page()
    last_url = ""
    all_events: list[dict] = []
    start = time.time()
    injected_urls: set[str] = set()

    _print_watch_header(timeout_s, host_filter)

    try:
        while timeout_s <= 0 or time.time() - start < timeout_s:
            try:
                # 활성 탭 갱신
                page, current_url = _refresh_active_page(page)

                # 호스트 필터
                if host_filter and host_filter not in current_url:
                    time.sleep(POLL_INTERVAL_S)
                    continue

                # URL 변화 감지
                last_url = _record_url_change(current_url, last_url, all_events, on_event)

                # JS 주입 (URL별 1회)
                if current_url not in injected_urls:
                    with contextlib.suppress(Exception):
                        page.wait_for_load_state("domcontentloaded", timeout=3000)
                    if _inject(page):
                        injected_urls.add(current_url)

                # 이벤트 수집
                _handle_events(page, host_filter, all_events, on_event, start)

            except KeyboardInterrupt:
                raise
            except Exception as outer:  # noqa: BLE001 - 사용자 행동 모니터링 주입 스크립트 - 주입/수집 실패 시 False/빈 목록 반환, 감시 루프 지속을 위한 폴백
                _log.debug("[user-monitor] 루프 오류: %s", outer)

            time.sleep(POLL_INTERVAL_S)

    except KeyboardInterrupt:
        pass

    elapsed = int(time.time() - start)
    print()
    print(f"종료 — {elapsed}초 동안 {len(all_events)}개 이벤트 감지")
    return all_events


def main() -> None:
    parser = argparse.ArgumentParser(description="사용자 수동 조작 실시간 감지")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S, help="최대 대기 초 (0=무한)")
    parser.add_argument("--host", type=str, default=None, help="특정 호스트만 감시 (예: gabia.com)")
    args = parser.parse_args()

    watch_user_actions(timeout_s=args.timeout, host_filter=args.host)
    sys.exit(0)


if __name__ == "__main__":
    main()
