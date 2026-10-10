"""지도 기반 실행기 — 저장된 사이트 업무 지도의 조회(read) 절차를 결정론적으로 재생한다 (L6 어댑터).

기준서: docs/specs/2026-10-04_site_task_map_m5_runner.md

- `execute_task` 는 Playwright 페이지 하나를 받아 절차(navigate·change·click)를 재생하고 결과 표를 읽어 돌려준다(저장 없음, 시험·실사이트 확인용).
- `run_task` 는 새 전용 탭에서 `execute_task` 를 실행하고 결과를 지도에 기록한다: 성공 → verified(+결과 표 **열 이름**만), 요소를 못 찾음 → stale.
  입력값·결과 행은 지도에 저장하지 않는다. 사용자 탭은 건드리지 않고(전용 탭), 지도의 호스트와 다른 호스트로는 이동하지 않는다.
- `read` 업무만 실행한다(서버 쪽 판정: `site_task_map.validate_run_request`).
"""

from __future__ import annotations

import contextlib
import json
import threading
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from ai_orchestrator.site_work import site_map_menu as menu
from ai_orchestrator.site_work import site_task_map as tm
from ai_orchestrator.site_work import site_task_map_store as store

RUN_BUDGET_S = 25.0  # 앱의 call_api 호출 상한(30초) 안에서 끝낸다
STEP_TIMEOUT_MS = 8000
NAV_TIMEOUT_MS = 20000
MIN_GAP_S = 2.0  # 같은 호스트 호출 사이 최소 간격(사이트 부담 제한)
ROWS_MAX = 50
CELL_MAX = 120

_host_locks: dict[str, threading.Lock] = {}
_last_run: dict[str, float] = {}
_guard = threading.Lock()


class StepMismatch(Exception):
    """지도의 요소를 화면에서 찾지 못했다 → 구조가 바뀐 것(stale)."""


class StepFailed(Exception):
    """실행을 끝내지 못했다. 지도가 틀렸다는 뜻은 아니다."""


# ── 요소 찾기 ──────────────────────────────────────────────────────────────


def _label_of(selector: str) -> str | None:
    for prefix in ("aria/", "text/"):
        if selector.startswith(prefix):
            return selector[len(prefix) :]
    return None


def _find_field(page: Any, selectors: list[list[str]]) -> Any:
    """입력칸: 선택자를 앞에서부터 시도(CSS → 접근성 이름/라벨/placeholder). 없으면 StepMismatch."""
    for group in selectors:
        first = group[0] if group else ""
        label = _label_of(first)
        candidates = [page.get_by_label(label), page.get_by_placeholder(label)] if label else [page.locator(first)]
        for locator in candidates:
            if locator.count() > 0:
                return locator.first
    raise StepMismatch("입력칸을 찾지 못했습니다: " + " | ".join(g[0] for g in selectors if g))


def _click_candidates(page: Any, selectors: list[list[str]]) -> list[Any]:
    """클릭 후보(같은 이름이 여럿일 수 있다): 링크 → 버튼 → 글자 순으로 처음 찾아지는 종류의 전부."""
    for group in selectors:
        label = _label_of(group[0]) if group else None
        if not label:
            continue
        for locator in (
            page.get_by_role("link", name=label, exact=True),
            page.get_by_role("button", name=label, exact=True),
            page.get_by_text(label, exact=True),
        ):
            count = locator.count()
            if count > 0:
                return [locator.nth(i) for i in range(count)]
    # 정확히 일치하는 요소가 없으면 부분 일치로 한 번 더 찾는다: 저장된 이름은 안정적인 앞부분(첫 줄)이라, 사이트가 이름 뒤에 붙이는
    # 수치·문구가 바뀌어도 재개가 깨지지 않게 한다(Playwright 역할+이름 로케이터의 기본 일치가 부분 일치). 읽기 업무 실행기라 위험 등급 강제는 그대로다.
    for group in selectors:
        label = _label_of(group[0]) if group else None
        if not label or len(label) < 2:
            continue
        for locator in (page.get_by_role("link", name=label), page.get_by_role("button", name=label)):
            count = locator.count()
            if count > 0:
                return [locator.nth(i) for i in range(count)]
    raise StepMismatch("클릭할 요소를 찾지 못했습니다: " + " | ".join(g[0] for g in selectors if g))


# 우선순위: ① 입력칸과 같은 폼 안에서 입력칸 뒤 ② 같은 폼 안 ③ 입력칸 뒤 ④ 전체 — 각 단계에서는 문서 순서로 가장 가까운 것.
# (폼 하나가 페이지 전체를 감싸는 사이트에서도 머리글 검색이 아닌 입력칸 뒤의 본문 검색을 고르고,
#  선택 상자·옵션이 끼어 거리가 벌어져도 같은 폼의 제출 컨트롤을 놓치지 않는다)
_NEAREST_JS = """([anchor, candidates]) => {
  const all = Array.from(document.querySelectorAll('*'));
  const a = all.indexOf(anchor);
  const scored = candidates.map((el, i) => ({ i, d: all.indexOf(el) - a, same: !!(anchor.form && anchor.form.contains(el)) }));
  const sameForm = scored.filter(c => c.same);
  const after = list => list.filter(c => c.d > 0);
  const nearest = list => list.reduce((b, c) => (b === null || Math.abs(c.d) < Math.abs(b.d)) ? c : b, null);
  for (const tier of [after(sameForm), sameForm, after(scored), scored]) { if (tier.length) return nearest(tier).i; }
  return 0;
}"""


def _pick_nearest(page: Any, candidates: list[Any], anchor: Any | None) -> Any:
    """같은 이름의 후보가 여럿이면 마지막으로 입력한 칸의 같은 폼·그 뒤에 있는 것을 우선한다(머리글 검색창이 아닌 본문 검색)."""
    if len(candidates) == 1 or anchor is None:
        return candidates[0]
    handles = [c.element_handle() for c in candidates]
    index = page.evaluate(_NEAREST_JS, [anchor.element_handle(), handles])
    return candidates[int(index)]


# ── 결과 표 읽기 ───────────────────────────────────────────────────────────

_TABLE_JS = """([rowsMax, cellMax]) => {
  const clean = x => (x || '').replace(/\\s+/g, ' ').trim().slice(0, cellMax);
  let best = null, bestScore = 0;
  for (const table of document.querySelectorAll('table')) {
    const rows = Array.from(table.rows);
    if (rows.length < 2) continue;
    // 머리글: thead 첫 행 → 전부 th 인 첫 행 → (th 가 전혀 없으면) 첫 행을 머리글로 추정
    let headRow = null, guessed = false;
    if (table.tHead && table.tHead.rows[0]) headRow = table.tHead.rows[0];
    else if (Array.from(rows[0].cells).length && Array.from(rows[0].cells).every(c => c.tagName === 'TH')) headRow = rows[0];
    else if (!table.querySelector('th')) { headRow = rows[0]; guessed = true; }
    const bodyRows = rows.filter(r => r !== headRow && !(table.tHead && table.tHead.contains(r)));
    if (!bodyRows.length) continue;
    const width = Math.max(...bodyRows.slice(0, 5).map(r => r.cells.length));
    if (width < 2) continue;
    const score = bodyRows.length * width;
    if (score > bestScore) { bestScore = score; best = { bodyRows, headRow, width, guessed }; }
  }
  if (!best) return null;
  // 머리글의 칸 병합(colspan)을 펼쳐 데이터 칸과 맞춘다: "제목"이 2칸이면 ["제목", "제목(2)"]
  let headers = [];
  if (best.headRow) {
    for (const c of Array.from(best.headRow.cells)) {
      const label = clean(c.innerText);
      headers.push(label);
      for (let k = 2; k <= (c.colSpan || 1); k++) headers.push(label ? label + '(' + k + ')' : '');
    }
  }
  if (headers.length < best.width) { for (let i = headers.length; i < best.width; i++) headers.push('칸' + (i + 1)); }
  if (headers.length > best.width) headers = headers.slice(0, best.width);
  const data = best.bodyRows.slice(0, rowsMax).map(r => Array.from(r.cells).map(c => clean(c.innerText)));
  const sig = best.bodyRows.length + '|' + best.bodyRows.slice(0, 2).map(r => clean(r.innerText).slice(0, 60)).join('/');
  return { headers, rows: data, truncated: best.bodyRows.length > rowsMax, total: best.bodyRows.length, header_guessed: best.guessed, signature: sig };
}"""

RESULT_WAIT_S = 8.0  # 클릭 뒤 결과 표가 갱신되기를 기다리는 최대 시간(비동기로 그려지는 사이트)
RESULT_POLL_MS = 400


ITEMS_MAX = 30
ITEM_TEXT_MAX = 200
CONTENT_BYTES_MAX = 8000

# 표가 아닌 결과(상품 카드·목록)를 읽는다(M8): 메뉴 영역(navigation·complementary·banner·contentinfo)을 뺀 본문에서
# 같은 부모 아래 같은 태그·클래스 형제가 3개 이상인 반복 구조 중 "개수 × 글자 길이" 점수가 가장 큰 것을 항목 목록으로 본다.
_CONTENT_JS = r"""([itemsMax, textMax]) => {
  const clean = s => (s || '').replace(/[\u0000-\u001f\u007f]+/g, ' ').replace(/\s+/g, ' ').trim();
  const lm = el => {
    const r = el.closest('[role="navigation"],[role="banner"],[role="contentinfo"],[role="complementary"],nav,header,footer,aside');
    if (!r) return '';
    const role = r.getAttribute('role'); if (role) return role;
    const t = r.tagName; if (t === 'NAV') return 'navigation'; if (t === 'ASIDE') return 'complementary';
    const scoped = r.parentElement && r.parentElement.closest('article,section,main,aside,nav');
    if (t === 'HEADER') return scoped ? '' : 'banner'; if (t === 'FOOTER') return scoped ? '' : 'contentinfo'; return '';
  };
  const menuArea = el => ['navigation', 'complementary', 'banner', 'contentinfo'].includes(lm(el));
  const sameHost = href => { try { return new URL(href, location.href).hostname === location.hostname; } catch (e) { return false; } };
  const headings = Array.from(document.querySelectorAll('h1,h2,h3')).filter(h => h.offsetParent !== null).map(h => clean(h.innerText).slice(0, 100)).filter(Boolean).slice(0, 10);
  let best = null, bestScore = 0;
  for (const p of document.querySelectorAll('ol,ul,div,section,tbody')) {
    if (menuArea(p)) continue;
    const kids = Array.from(p.children).filter(k => k.offsetParent !== null);
    if (kids.length < 3) continue;
    const groups = {};
    kids.forEach(k => { (groups[k.tagName + '.' + (k.className || '')] = groups[k.tagName + '.' + (k.className || '')] || []).push(k); });
    for (const g of Object.values(groups)) {
      if (g.length < 3 || !g.some(k => k.querySelector('a[href]'))) continue;
      const score = g.length * Math.min(120, Math.max(...g.map(k => clean(k.innerText).length)));
      if (score > bestScore) { bestScore = score; best = g; }
    }
  }
  const items = (best || []).slice(0, itemsMax).map(k => {
    const a = k.querySelector('a[href]');
    return { text: clean(k.innerText).slice(0, textMax), label: a ? clean(a.getAttribute('title') || '').slice(0, 120) : '', href: a && sameHost(a.href) ? a.href : '' };
  }).filter(i => i.text);
  const nx = document.querySelector('a[rel~="next"], li.next a, a[aria-label*="next" i], a[aria-label*="다음"]');
  return { title: clean(document.title).slice(0, 120), headings, items, total_items: best ? best.length : 0, next_url: nx && sameHost(nx.href) ? nx.href : '' };
}"""


def read_page_content(page: Any, host: str) -> dict[str, Any] | None:
    """표가 없는 화면의 제목·소제목·반복 항목·다음 쪽 주소. 항목이 하나도 없고 소제목도 없으면 None. 값은 응답에만 담고 지도에는 저장하지 않는다."""
    raw = page.evaluate(_CONTENT_JS, [ITEMS_MAX, ITEM_TEXT_MAX])
    if not isinstance(raw, dict):
        return None
    items = [dict(i, href=menu.same_host_url(str(i.get("href") or ""), host) or "") for i in raw.get("items", [])]
    while items and len(json.dumps(items, ensure_ascii=False)) > CONTENT_BYTES_MAX:
        items.pop()
    if not items and not raw.get("headings"):
        return None
    next_url = menu.same_host_url(str(raw.get("next_url") or ""), host) or ""
    return {
        "title": raw.get("title", ""),
        "url": page.url,
        "headings": raw.get("headings", []),
        "items": items,
        "total_items": raw.get("total_items", len(items)),
        "next_url": next_url,
    }


def read_result_table(page: Any) -> dict[str, Any] | None:
    result = page.evaluate(_TABLE_JS, [ROWS_MAX, CELL_MAX])
    return result if isinstance(result, dict) else None


def wait_for_result_table(
    page: Any,
    before_signature: str | None,
    *,
    clock: Callable[[], float] = time.monotonic,
    timeout_s: float = RESULT_WAIT_S,
) -> tuple[dict[str, Any] | None, str]:
    """결과 표를 읽는다. 클릭 전 화면에도 표가 있었다면 **내용이 바뀐 표**가 나타날 때까지 기다린다(비동기 갱신).

    반환 (표, 상태): 상태는 'fresh'(새로 그려진 표 또는 이동 후 표) / 'unchanged'(제한 시간 안에 갱신을 확인하지 못함 — 표는 이전 화면의 것일 수 있어
    결과로 내놓지 않는다) / 'none'(표 없음).
    """
    deadline = clock() + timeout_s
    seen: dict[str, Any] | None = None
    while True:
        seen = read_result_table(page)
        if seen and (before_signature is None or seen.get("signature") != before_signature):
            return seen, "fresh"
        if clock() >= deadline:
            break
        page.wait_for_timeout(RESULT_POLL_MS)
    return (None, "unchanged") if seen else (None, "none")


# ── 절차 재생 ──────────────────────────────────────────────────────────────


def _same_host(url: str, host: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and (parsed.hostname or "").lower() == host.lower()


def _check_deadline(deadline: float, clock: Callable[[], float]) -> None:
    if clock() > deadline:
        raise StepFailed(f"{RUN_BUDGET_S:g}초 안에 끝내지 못했습니다")


def _step_navigate(page: Any, host: str, step: dict[str, Any], values: dict[str, str] | None = None) -> None:
    url = tm.substitute(str(step.get("url") or ""), values or {})  # 주소 열기 업무의 {{url}} 자리(고정 주소는 그대로)
    if url is None:
        raise StepFailed("열 주소(url)가 필요합니다")
    if not _same_host(url, host):
        raise StepFailed("지도의 호스트와 다른 주소로는 이동하지 않습니다")
    try:
        page.goto(url, timeout=NAV_TIMEOUT_MS, wait_until="domcontentloaded")
    except Exception as exc:
        raise StepFailed(f"페이지를 열지 못했습니다: {type(exc).__name__}") from exc


def _step_change(page: Any, step: dict[str, Any], values: dict[str, str]) -> Any | None:
    """입력 단계. 값을 주지 않은 칸은 건너뛴다(None). 입력한 칸을 돌려준다(다음 클릭의 기준)."""
    value = tm.substitute(str(step.get("value") or ""), values)
    if value is None:
        return None
    field = _find_field(page, step.get("selectors") or [])
    try:
        if str(field.evaluate("e => e.tagName")).upper() == "SELECT":
            field.select_option(label=value, timeout=STEP_TIMEOUT_MS)
        else:
            field.fill(value, timeout=STEP_TIMEOUT_MS)
    except Exception as exc:
        raise StepFailed(f"입력하지 못했습니다: {type(exc).__name__}") from exc
    return field


def _step_click(page: Any, host: str, step: dict[str, Any], anchor: Any | None) -> None:
    target = _pick_nearest(page, _click_candidates(page, step.get("selectors") or []), anchor)
    try:
        target.click(timeout=STEP_TIMEOUT_MS)
        with contextlib.suppress(Exception):  # 화면 이동이 없는 결과 갱신(AJAX)도 있다
            page.wait_for_load_state("domcontentloaded", timeout=NAV_TIMEOUT_MS)
        page.wait_for_timeout(800)
    except Exception as exc:
        raise StepFailed(f"클릭하지 못했습니다: {type(exc).__name__}") from exc
    if not _same_host(page.url, host):
        raise StepFailed("클릭 뒤 다른 호스트로 이동해 중단했습니다")


def execute_task(
    page: Any,
    host: str,
    task: dict[str, Any],
    values: dict[str, str],
    *,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """절차를 재생하고 결과 표를 읽는다. 저장하지 않는다. 구조 불일치는 StepMismatch, 그 밖의 실패는 StepFailed."""
    deadline = clock() + RUN_BUDGET_S
    anchor: Any | None = None
    done = 0
    before_signature: str | None = None  # 마지막 클릭 직전의 표 지문(없으면 None)
    for step in task["steps"]:
        _check_deadline(deadline, clock)
        kind = step.get("type")
        if kind == "navigate":
            _step_navigate(page, host, step, values)
        elif kind == "change":
            anchor = _step_change(page, step, values) or anchor
        elif kind == "click":
            previous = read_result_table(page)
            before_signature = previous.get("signature") if previous else None
            _step_click(page, host, step, anchor)
        else:
            raise StepFailed(f"실행할 수 없는 단계 종류: {kind}")
        done += 1
    if all(s.get("type") == "navigate" for s in task["steps"]):  # 이동만 하는 업무(주소 열기): 갱신을 기다릴 게 없으니 바로 읽는다(표 없는 화면에서 8초 대기 방지)
        table = read_result_table(page)
        freshness = "fresh" if table else "none"
    else:
        table, freshness = wait_for_result_table(page, before_signature, clock=clock)
    if table:
        table = {k: v for k, v in table.items() if k != "signature"}  # 내부 비교용 값은 응답에 싣지 않는다
    result: dict[str, Any] = {"steps_done": done, "url": page.url, "tables": [table] if table else [], "result_state": freshness}
    if not table and freshness == "none":  # 표가 없는 화면: 제목·반복 항목(상품 카드·목록)·다음 쪽 주소를 읽는다
        content = read_page_content(page, host)
        if content:
            result["page"] = {k: v for k, v in content.items() if k != "items"}
            result["items"] = content["items"]
    return result


# ── 기록과 실행 ────────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _host_lock(host: str) -> threading.Lock:
    with _guard:
        return _host_locks.setdefault(host, threading.Lock())


def run_task(
    host: str,
    task_id: str,
    values: dict[str, str],
    *,
    page_scope: Callable[[str], Any],
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """업무를 실행하고 결과를 지도에 기록한다. `page_scope(시작 주소)` 는 (페이지를 주는) 컨텍스트 매니저 — 끝나면 그 탭을 닫는다."""
    site_map = store.load(host)
    task = next((t for t in site_map["tasks"] if t["id"] == task_id), None)
    if task is None:
        raise ValueError("업무를 찾을 수 없습니다")
    tm.validate_run_request(task, values)  # 이중 방어: 서비스가 이미 검증했어도 실행기도 위험 등급을 다시 본다
    lock = _host_lock(host)
    if not lock.acquire(timeout=RUN_BUDGET_S):
        raise ValueError("같은 사이트에서 다른 실행이 진행 중입니다")
    try:
        wait = MIN_GAP_S - (clock() - _last_run.get(host, -1e9))
        if wait > 0:
            sleep(wait)
        start_url = next((str(s.get("url")) for s in task["steps"] if s.get("type") == "navigate" and "{{" not in str(s.get("url"))), task["url"])
        outcome: dict[str, Any] = {"ok": False, "task_id": task_id, "host": host}
        try:
            with page_scope(start_url) as page:
                outcome.update(execute_task(page, host, task, values, clock=clock), ok=True)
        except StepMismatch as exc:
            store.save(tm.mark_failed(store.load(host), task_id, now=_now()))
            outcome.update(error=f"화면이 지도와 다릅니다 — 재탐색이 필요합니다: {exc}", state="stale")
            return outcome
        except StepFailed as exc:
            outcome.update(error=str(exc), state=task["state"])
            return outcome
        finally:
            _last_run[host] = clock()
        updated = store.load(host)
        if outcome["tables"]:
            updated = tm.apply_outputs(updated, task_id, outcome["tables"][0]["headers"], now=_now())
            updated = tm.mark_verified(updated, task_id, now=_now())
            store.save(updated)
            outcome["state"] = tm.STATE_VERIFIED
        elif outcome.get("items"):  # 표는 없지만 반복 항목을 읽었다 — 값은 저장하지 않고 동작한 업무로만 표시한다
            store.save(tm.mark_verified(updated, task_id, now=_now()))
            outcome["state"] = tm.STATE_VERIFIED
        else:
            if outcome.get("result_state") == "unchanged":
                note = "절차는 실행했지만 결과 화면이 갱신됐는지 확인하지 못했습니다(이전 화면의 표일 수 있어 결과로 내놓지 않았습니다) — 상태는 바꾸지 않았습니다"
            else:
                note = "절차는 모두 실행했지만 결과 표가 없습니다(조회 결과가 없거나 표가 아닌 화면) — 상태는 바꾸지 않았습니다"
            outcome.update(state=task["state"], note=note)
        return outcome
    finally:
        lock.release()


@contextlib.contextmanager
def private_tab_scope(start_url: str):
    """운영용 페이지 범위: 공유 브라우저에 새 전용 탭을 열고(`cdp_tabs`), 끝나면 그 탭만 닫는다. 브라우저 스레드 안에서만 쓴다."""
    from scripts.browser.cdp import cdp_tabs
    from scripts.browser.cdp.connection import get_context
    from scripts.explorer.task_mapper import open_private_tab

    page, handle = open_private_tab(get_context(), start_url)
    try:
        yield page
    finally:
        with contextlib.suppress(Exception):
            cdp_tabs.close_tab(handle)


def run_task_in_browser(host: str, task_id: str, values: dict[str, str]) -> dict[str, Any]:
    """서비스에 주입하는 운영용 실행기: 공유 브라우저 스레드에서 전용 탭으로 실행한다."""
    from scripts.browser.cdp.connection import run_on_browser_thread

    return run_on_browser_thread(lambda: run_task(host, task_id, values, page_scope=private_tab_scope), timeout=int(RUN_BUDGET_S) + 40)
