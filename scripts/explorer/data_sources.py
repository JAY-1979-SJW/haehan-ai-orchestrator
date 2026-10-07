"""L4 Browser Engine — 탐색 중 데이터 소스·사이트 선언 도구를 **읽기 전용으로 관측**한다.

기준서: docs/specs/2026-10-05_site_map_m9_precise_exploration.md (M9)

- 데이터 소스: 쪽이 로드되는 동안 일어난 GET + XHR/Fetch + HTTP 200 + JSON 응답의 **구조만** 기록한다(값 불저장 — 규칙은 domain.site_map_sources).
- 핸들러는 응답 객체를 **모으기만** 한다. Playwright 동기 API 의 `response` 핸들러 안에서 `resp.json()` 같은 동기 호출을 하면 쪽 이동이 멈춘다
  (2026-10-05 실측: goto 시간 초과). 읽기는 쪽이 열려 있는 동안 `flush` 에서 한다(쪽을 떠나면 본문이 사라질 수 있다).
- 선언 도구(WebMCP, Chrome 조기 미리보기): 선언형 `form[toolname]` 과 명령형 `document.modelContext.getTools()` 를 **읽기만** 한다 — 도구를 실행하지 않는다.
- 요청을 만들지 않는다. 쿠키·토큰·헤더는 읽지 않는다.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any
from urllib.parse import urlsplit

from ai_orchestrator.site_work import site_map_sources as sd

_log = logging.getLogger(__name__)

PENDING_MAX = 60  # 쪽당 모아 두는 응답 상한
BODY_MAX = 1_000_000  # 이보다 큰 응답은 건너뛴다
SETTLE_MS = 1000  # 쪽이 열린 뒤 늦게 오는 XHR 을 기다리는 시간

# 선언형: form[toolname]·tooldescription (WebMCP 선언형 API). 명령형: document.modelContext.getTools — 함수가 있을 때만, 1.5초 안에.
_TOOLS_JS = """async () => {
  const out = [];
  document.querySelectorAll('form[toolname]').forEach(f => {
    const props = {}; const required = [];
    f.querySelectorAll('input[name],select[name],textarea[name]').forEach(el => { props[el.name] = {}; if (el.required) required.push(el.name); });
    out.push({kind: 'declarative', name: f.getAttribute('toolname') || '', description: f.getAttribute('tooldescription') || '', input_schema: {properties: props, required}});
  });
  const mc = document.modelContext || navigator.modelContext;
  if (mc && typeof mc.getTools === 'function') {
    try {
      const tools = await Promise.race([mc.getTools(), new Promise(r => setTimeout(() => r([]), 1500))]);
      (tools || []).forEach(t => out.push({kind: 'imperative', name: t.name || '', description: t.description || '', input_schema: t.inputSchema || {}}));
    } catch (e) { /* 도구를 못 읽어도 탐색은 계속한다 */ }
  }
  return out;
}"""


class ResponseRecorder:
    """탐색 중 응답 구조와 선언 도구를 모은다. `attach` → (쪽마다) `flush` → `detach`."""

    def __init__(self, *, pending_max: int = PENDING_MAX, body_max: int = BODY_MAX, settle_ms: int = SETTLE_MS) -> None:
        self.sources: list[dict[str, Any]] = []
        self.tools: list[dict[str, Any]] = []
        self._pending: list[Any] = []
        self._pending_max, self._body_max, self._settle_ms = pending_max, body_max, settle_ms

    def attach(self, page: Any) -> None:
        """응답 수집을 시작한다. 이 페이지가 이벤트를 지원하지 않아도(시험용 가짜 포함) 탐색은 계속한다."""
        with contextlib.suppress(Exception):
            page.on("response", self._on_response)

    def detach(self, page: Any) -> None:
        with contextlib.suppress(Exception):
            page.remove_listener("response", self._on_response)

    def _on_response(self, resp: Any) -> None:
        """핸들러: 모으기만 한다(동기 호출·본문 읽기 금지)."""
        with contextlib.suppress(Exception):
            req = resp.request
            if (
                req.resource_type in ("xhr", "fetch")
                and req.method == "GET"
                and resp.status == 200
                and len(self._pending) < self._pending_max
            ):
                self._pending.append(resp)

    def flush(self, page: Any | None = None) -> int:
        """쪽이 열려 있는 동안 모아 둔 응답의 구조를 읽어 `sources` 에 더하고 선언 도구를 읽는다 → 새로 읽은 소스 수. 실패는 건너뛴다."""
        if page is not None:
            with contextlib.suppress(Exception):
                page.wait_for_timeout(self._settle_ms)
        pending, self._pending = self._pending, []
        added = 0
        for resp in pending:
            try:
                headers = resp.headers
                if "json" not in str(headers.get("content-type") or ""):
                    continue
                if int(headers.get("content-length") or 0) > self._body_max:
                    continue
                parts = urlsplit(resp.url)
                source = sd.observe(parts.hostname or "", parts.path, parts.query, resp.json())
            except Exception as exc:  # noqa: BLE001 - 읽을 수 없는 응답(본문 없음·JSON 아님)은 건너뛴다
                _log.debug("[sources] 응답 건너뜀: %s", str(exc)[:80])
                continue
            if source:
                self.sources.append(source)
                added += 1
        if page is not None:
            with contextlib.suppress(Exception):
                found = page.evaluate(_TOOLS_JS)
                if isinstance(found, list):
                    self.tools.extend(t for t in found if isinstance(t, dict))
        return added
