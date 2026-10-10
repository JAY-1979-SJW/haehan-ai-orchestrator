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

이 패키지는 재수출을 하지 않는다(재수출은 순환 import 의 원인) — 필요한 이름은 하위 모듈에서 직접 import 한다:
- `ai_orchestrator.browser_tool.router`: route_browser_task, route_browser_task_with_params
- `ai_orchestrator.browser_tool.schemas`: BrowserTask, BrowserResult, BrowserActionName, BrowserBackendName
"""
