"""scripts/browser/agent/universal_actions.py — 범용 CDP 액션 계층.

목적
====
처음 방문하는 웹사이트에도 사이트별 셀렉터 코드 없이 자동화할 수 있도록,
접근성 트리(AXTree) 기반 스냅샷과 ref 기반 액션을 제공한다.
`cdp.py`의 형제 모듈(같은 L4 Browser Engine 계층) — `open_cdp_session()`이 만든
Playwright `page` 객체를 그대로 받아서 동작한다.

원칙
====
1. CSS 셀렉터가 아니라 접근성 트리 노드의 backendDOMNodeId 를 ref 로 매핑한다.
   DOM.getDocument 의 nodeId 는 호출마다 바뀌지만 backendDOMNodeId 는 그 노드가
   무효화(재렌더링·navigate)되기 전까지 안정적이다.
2. 텍스트 입력은 CDP 로 키 이벤트를 직접 흉내내지 않고 Playwright
   `page.keyboard.type()` 을 재사용한다 — React 등 컨트롤드 인풋과의 호환성이
   `.value` 직접 대입보다 실제 키 입력 시뮬레이션 쪽이 안전하다.
3. 이미 아는 사이트는 이 모듈을 거치지 않는다. CLAUDE.md 의
   `tools/hooks/capability_check.py` 필수 실행 규칙으로 기존 사이트 모듈
   (`scripts/naver/*` 등)이 있으면 그쪽을 우선 쓰고, 이 모듈은 처음 보는
   사이트에서만 폴백으로 쓴다.

근거
====
Chrome DevTools Protocol(Accessibility.getFullAXTree/DOM.resolveNode/
DOM.getBoxModel/DOM.scrollIntoViewIfNeeded/Input.dispatchMouseEvent),
Playwright(`BrowserContext.new_cdp_session`) 공식 문서 — 자세한 인용은
docs/specs/2026-09-28_cdp_universal_automation_and_mcp_trigger.md §2 참조.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from weakref import WeakKeyDictionary

logger = logging.getLogger(__name__)

# 구조적 wrapper role — 이름이 있어도 상호작용 대상이 아니라 스냅샷에서 제외한다.
_STRUCTURAL_ROLES = {"generic", "none", "InlineTextBox", "LineBreak"}

# page(Playwright Page 객체) -> {ref: backendDOMNodeId}. navigate() 시 무효화.
_ref_registries: WeakKeyDictionary[Any, dict[str, int]] = WeakKeyDictionary()


class UniversalActionError(RuntimeError):
    """범용 액션 실패(예: 오래된 ref로 act() 시도 — snapshot()을 다시 불러야 함)."""


@dataclass(frozen=True)
class SnapshotNode:
    """접근성 트리에서 살아남은 노드 하나. ref로 act()에 그대로 넘긴다."""

    ref: str
    role: str
    name: str
    value: str | None = None


@dataclass(frozen=True)
class UniversalSnapshot:
    """snapshot() 결과. 문서 순서(document order)의 평평한 목록."""

    nodes: tuple[SnapshotNode, ...]

    def as_text(self) -> str:
        """Claude가 읽고 판단할 텍스트 표현. 예: `[e3] button "장바구니 담기"`."""
        lines = []
        for n in self.nodes:
            extra = f" value={n.value!r}" if n.value else ""
            lines.append(f'[{n.ref}] {n.role} "{n.name}"{extra}')
        return "\n".join(lines)


def _ax_text(ax_value: dict[str, Any] | None) -> str:
    """AXValue({"type": "role", "value": "button"}) 에서 value 만 뽑는다."""
    if not ax_value:
        return ""
    return str(ax_value.get("value", ""))


def snapshot(page: Any, max_depth: int | None = None) -> UniversalSnapshot:
    """접근성 트리 스냅샷을 찍고, 이름이 있는(=상호작용 대상일 가능성이 높은)
    노드에 짧은 ref 를 부여한다. 반환된 ref 는 이 page 에서 다음 navigate() 전까지만
    유효하다 — 페이지가 크게 바뀌면 다시 snapshot() 해야 한다.

    처음 방문하는 사이트에도 사이트별 셀렉터 없이 동작하게 하는 핵심 함수.
    """
    cdp = page.context.new_cdp_session(page)
    try:
        cdp.send("Accessibility.enable")
        params: dict[str, Any] = {}
        if max_depth is not None:
            params["depth"] = max_depth
        result = cdp.send("Accessibility.getFullAXTree", params)
    finally:
        cdp.detach()

    ax_nodes: list[dict[str, Any]] = result.get("nodes", [])
    by_id = {n["nodeId"]: n for n in ax_nodes}
    parent_ids = {cid for n in ax_nodes for cid in (n.get("childIds") or [])}
    root_ids = [n["nodeId"] for n in ax_nodes if n["nodeId"] not in parent_ids]

    flat: list[SnapshotNode] = []
    registry: dict[str, int] = {}
    counter = 0
    seen: set[str] = set()

    def walk(node_id: str, depth: int) -> None:
        nonlocal counter
        if node_id in seen:
            return  # AXTree는 트리이지만 방어적으로 순환 방지
        seen.add(node_id)
        n = by_id.get(node_id)
        if n is None:
            return
        if max_depth is None or depth <= max_depth:
            role = _ax_text(n.get("role"))
            name = _ax_text(n.get("name"))
            backend_id = n.get("backendDOMNodeId")
            if not n.get("ignored", False) and role not in _STRUCTURAL_ROLES and backend_id is not None and name:
                counter += 1
                ref = f"e{counter}"
                registry[ref] = backend_id
                flat.append(SnapshotNode(ref=ref, role=role, name=name, value=_ax_text(n.get("value")) or None))
        for child_id in n.get("childIds") or []:
            walk(child_id, depth + 1)

    for rid in root_ids:
        walk(rid, 0)

    _ref_registries[page] = registry
    logger.info("[universal_actions] snapshot: 노드 %d개(전체 AXNode %d개 중)", len(flat), len(ax_nodes))
    return UniversalSnapshot(tuple(flat))


def act(page: Any, ref: str, action: str, value: str | None = None) -> None:
    """스냅샷의 ref로 클릭/입력/선택한다.

    action: "click" | "fill" | "select"
    value: fill/select 에는 필수, click 에는 무시된다.

    ref가 registry에 없으면(오래됐거나 snapshot()을 먼저 안 부름) UniversalActionError.
    """
    registry = _ref_registries.get(page)
    if not registry or ref not in registry:
        raise UniversalActionError(f"알 수 없는 ref: {ref!r} — snapshot()을 다시 호출하세요.")
    backend_id = registry[ref]

    cdp = page.context.new_cdp_session(page)
    try:
        if action == "click":
            cdp.send("DOM.scrollIntoViewIfNeeded", {"backendNodeId": backend_id})
            box = cdp.send("DOM.getBoxModel", {"backendNodeId": backend_id})
            quad = box["model"]["content"]  # [x1,y1, x2,y2, x3,y3, x4,y4] (4개 꼭짓점)
            cx = (quad[0] + quad[2] + quad[4] + quad[6]) / 4
            cy = (quad[1] + quad[3] + quad[5] + quad[7]) / 4
            for mouse_type in ("mousePressed", "mouseReleased"):
                cdp.send(
                    "Input.dispatchMouseEvent",
                    {"type": mouse_type, "x": cx, "y": cy, "button": "left", "clickCount": 1},
                )
            return

        if action in ("fill", "select") and value is None:
            raise UniversalActionError(f"{action} 액션은 value가 필요합니다.")

        resolved = cdp.send("DOM.resolveNode", {"backendNodeId": backend_id})
        object_id = resolved["object"]["objectId"]

        if action == "fill":
            cdp.send(
                "Runtime.callFunctionOn",
                {"functionDeclaration": "function() { this.focus(); }", "objectId": object_id},
            )
            # 기존 값 제거 후 실키 입력 시뮬레이션(page.keyboard) — CDP로 키 이벤트를
            # 재구현하지 않고 Playwright 기능을 그대로 재사용한다.
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
            page.keyboard.type(value)
            return

        if action == "select":
            cdp.send(
                "Runtime.callFunctionOn",
                {
                    "functionDeclaration": (
                        "function(v) { this.value = v; this.dispatchEvent(new Event('change', {bubbles: true})); }"
                    ),
                    "objectId": object_id,
                    "arguments": [{"value": value}],
                },
            )
            return

        raise UniversalActionError(f"알 수 없는 action: {action!r} (click/fill/select만 지원)")
    finally:
        cdp.detach()


def navigate(page: Any, url: str, *, wait_until: str = "domcontentloaded", timeout_ms: int = 30000) -> None:
    """URL 이동 + 이 page의 ref 레지스트리 무효화(다음 act() 전에 snapshot() 다시 필요)."""
    page.goto(url, wait_until=wait_until, timeout=timeout_ms)
    _ref_registries.pop(page, None)


def screenshot(page: Any) -> bytes:
    """페이지 스크린샷(PNG bytes). vision 보조용 — 기본 경로는 snapshot()/act()."""
    return page.screenshot()
