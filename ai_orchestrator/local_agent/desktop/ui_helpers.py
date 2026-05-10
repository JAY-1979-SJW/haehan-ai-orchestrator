"""공통 UIA 헬퍼."""
from __future__ import annotations

import psutil

try:
    import uiautomation as auto
    _UIA_AVAILABLE = True
except ImportError:
    _UIA_AVAILABLE = False


def uia_available() -> bool:
    return _UIA_AVAILABLE


def safe_get(ctrl, attr, default=""):
    try:
        v = getattr(ctrl, attr, default)
        return v() if callable(v) else v
    except Exception:
        return default


def ctrl_info(ctrl, depth: int = 0) -> dict:
    try:
        r = ctrl.BoundingRectangle
        rect = {"l": r.left, "t": r.top, "r": r.right, "b": r.bottom,
                "w": r.right - r.left, "h": r.bottom - r.top}
    except Exception:
        rect = {}
    return {
        "depth": depth,
        "type":  safe_get(ctrl, "ControlTypeName"),
        "name":  safe_get(ctrl, "Name", "")[:120],
        "aid":   safe_get(ctrl, "AutomationId", "")[:80],
        "cls":   safe_get(ctrl, "ClassName", "")[:60],
        "off":   safe_get(ctrl, "IsOffscreen", False),
        "rect":  rect,
    }


def deep_walk(ctrl, depth: int = 0, max_depth: int = 12) -> list[dict]:
    if depth >= max_depth:
        return []
    nodes = [ctrl_info(ctrl, depth)]
    if nodes[0]["off"]:
        return nodes
    try:
        children = ctrl.GetChildren()
    except Exception:
        return nodes
    for ch in children[:60]:
        nodes.extend(deep_walk(ch, depth + 1, max_depth))
    return nodes


def find_window_by_process(process_name: str):
    """프로세스명으로 메인 창 반환 (이름 있는 첫 번째)."""
    if not _UIA_AVAILABLE:
        return None
    pids = {p.info["pid"] for p in psutil.process_iter(["pid", "name"])
            if process_name.lower() in (p.info.get("name") or "").lower()}
    if not pids:
        return None
    desktop = auto.GetRootControl()
    for w in desktop.GetChildren():
        try:
            if w.ProcessId in pids and (w.Name or "").strip():
                return w
        except Exception:
            pass
    return None
