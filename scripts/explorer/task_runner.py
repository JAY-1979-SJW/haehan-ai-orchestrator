"""지도 기반 실행기 — 저장된 사이트 업무 지도의 조회(read) 절차를 결정론적으로 재생한다 (L6 어댑터).

기준서: docs/specs/2026-10-04_site_task_map_m5_runner.md

- `execute_task` 는 Playwright 페이지 하나를 받아 절차(navigate·change·click)를 재생하고 결과 표를 읽어 돌려준다(저장 없음, 시험·실사이트 확인용).
- `run_task` 는 새 전용 탭에서 `execute_task` 를 실행하고 결과를 지도에 기록한다: 성공 → verified(+결과 표 **열 이름**만), 요소를 못 찾음 → stale.
  입력값·결과 행은 지도에 저장하지 않는다. 사용자 탭은 건드리지 않고(전용 탭), 지도의 호스트와 다른 호스트로는 이동하지 않는다.
- `read` 업무만 실행한다(서버 쪽 판정: `site_task_map.validate_run_request`).
"""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from ai_orchestrator.domain import site_task_map as tm
from ai_orchestrator.persistence import site_task_map_store as store

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
  const clean = t => (t || '').replace(/\\s+/g, ' ').trim().slice(0, cellMax);
  let best = null, bestScore = 0;
  for (const table of document.querySelectorAll('table')) {
    const rows = Array.from(table.rows);
    if (rows.length < 2) continue;
    const headCells = Array.from(rows[0].cells);
    if (headCells.length < 2) continue;
    const score = rows.length * headCells.length;
    if (score > bestScore) { bestScore = score; best = { table, rows, headCells }; }
  }
  if (!best) return null;
  const headers = best.headCells.map(c => clean(c.innerText));
  const data = best.rows.slice(1, rowsMax + 1).map(r => Array.from(r.cells).map(c => clean(c.innerText)));
  return { headers, rows: data, truncated: best.rows.length - 1 > rowsMax };
}"""


def read_result_table(page: Any) -> dict[str, Any] | None:
    result = page.evaluate(_TABLE_JS, [ROWS_MAX, CELL_MAX])
    return result if isinstance(result, dict) else None


# ── 절차 재생 ──────────────────────────────────────────────────────────────


def _same_host(url: str, host: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and (parsed.hostname or "").lower() == host.lower()


def _check_deadline(deadline: float, clock: Callable[[], float]) -> None:
    if clock() > deadline:
        raise StepFailed(f"{RUN_BUDGET_S:g}초 안에 끝내지 못했습니다")


def _step_navigate(page: Any, host: str, step: dict[str, Any]) -> None:
    url = str(step.get("url") or "")
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
    for step in task["steps"]:
        _check_deadline(deadline, clock)
        kind = step.get("type")
        if kind == "navigate":
            _step_navigate(page, host, step)
        elif kind == "change":
            anchor = _step_change(page, step, values) or anchor
        elif kind == "click":
            _step_click(page, host, step, anchor)
        else:
            raise StepFailed(f"실행할 수 없는 단계 종류: {kind}")
        done += 1
    table = read_result_table(page)
    return {"steps_done": done, "url": page.url, "tables": [table] if table else []}


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
        start_url = next((str(s.get("url")) for s in task["steps"] if s.get("type") == "navigate"), task["url"])
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
        else:
            outcome.update(state=task["state"], note="절차는 모두 실행했지만 결과 표가 없습니다(조회 결과가 없거나 표가 아닌 화면) — 상태는 바꾸지 않았습니다")
        return outcome
    finally:
        lock.release()


@contextlib.contextmanager
def private_tab_scope(start_url: str):
    """운영용 페이지 범위: 공유 브라우저에 새 전용 탭을 열고(`cdp_tabs`), 끝나면 그 탭만 닫는다. 브라우저 스레드 안에서만 쓴다."""
    from scripts import cdp_tabs
    from scripts.explorer.task_mapper import open_private_tab
    from scripts.web_connector import get_context

    page, handle = open_private_tab(get_context(), start_url)
    try:
        yield page
    finally:
        with contextlib.suppress(Exception):
            cdp_tabs.close_tab(handle)


def run_task_in_browser(host: str, task_id: str, values: dict[str, str]) -> dict[str, Any]:
    """서비스에 주입하는 운영용 실행기: 공유 브라우저 스레드에서 전용 탭으로 실행한다."""
    from scripts.web_connector import run_on_browser_thread

    return run_on_browser_thread(lambda: run_task(host, task_id, values, page_scope=private_tab_scope), timeout=int(RUN_BUDGET_S) + 40)
