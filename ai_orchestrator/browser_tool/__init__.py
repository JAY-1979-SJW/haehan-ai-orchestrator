"""Browser Tool Protocol - Unified browser automation interface.

This module provides a centralized router for browser automation tasks,
supporting multiple backends and a unified policy framework.

Future backends:
- server_playwright: Server-side web automation via Playwright
- local_agent: Local PC browser control via WebSocket
- hwp: HWP document automation
- excel: Excel spreadsheet automation
- cad: CAD application automation

In current stage (BROWSER-ARCH-2A), only mock backend is active.
"""
from __future__ import annotations

from .router import route_browser_task, route_browser_task_with_params
from .schemas import BrowserActionName, BrowserBackendName, BrowserResult, BrowserTask

__all__ = [
    "BrowserTask",
    "BrowserResult",
    "BrowserActionName",
    "BrowserBackendName",
    "route_browser_task",
    "route_browser_task_with_params",
]
