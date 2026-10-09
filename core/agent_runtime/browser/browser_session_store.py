"""자동화 브라우저 세션/탭 상태 store (최소 구현).

본 공정 범위:
  - 브라우저 1세션 + 탭 N개의 in-memory 스냅샷.
  - tab_id = CDP target_id.
  - 닫힌 탭(target_id 부재) 에 명령이 들어오면 상위 호출자가 TAB_CLOSED 응답.
  - 운영 DB write 없음. 데몬 재실행 시 빈 상태로 시작.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

# 상태 enum
BROWSER_NOT_STARTED = "BROWSER_NOT_STARTED"
BROWSER_RUNNING = "BROWSER_RUNNING"
BROWSER_CLOSED = "BROWSER_CLOSED"

TAB_OPEN = "TAB_OPEN"
TAB_ACTIVE = "TAB_ACTIVE"
TAB_CLOSED = "TAB_CLOSED"
TAB_ORPHANED = "ORPHANED"
TAB_ERROR = "ERROR"


@dataclass
class TabRecord:
    tab_id: str  # CDP target_id
    url: str = ""
    title: str = ""
    task_id: str = ""
    opened_by: str = ""
    created_at: float = 0.0
    last_seen_at: float = 0.0
    status: str = TAB_OPEN
    login_state: str = "LOGIN_UNKNOWN"
    login_state_changed_at: float = 0.0
    role: str = ""  # "" | "work" | "login_target"


@dataclass
class BrowserSession:
    browser_session_id: str
    started_at: float
    status: str = BROWSER_RUNNING
    tabs: dict[str, TabRecord] = field(default_factory=dict)


class BrowserSessionStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._session: BrowserSession | None = None

    # ── 브라우저 라이프사이클 ──────────────────────────────────────

    def start_session(self) -> BrowserSession:
        with self._lock:
            self._session = BrowserSession(
                browser_session_id=f"bs_{uuid.uuid4().hex[:12]}",
                started_at=time.time(),
                status=BROWSER_RUNNING,
            )
            snapshot: dict[str, Any] = {
                "browser_session_id": self._session.browser_session_id,
                "started_at": self._session.started_at,
                "status": self._session.status,
                "tabs": {},
            }
            return BrowserSession(**snapshot)

    def mark_browser_closed(self) -> None:
        with self._lock:
            if self._session is None:
                return
            self._session.status = BROWSER_CLOSED
            for tab in self._session.tabs.values():
                tab.status = TAB_CLOSED
                tab.last_seen_at = time.time()

    def clear(self) -> None:
        with self._lock:
            self._session = None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            if self._session is None:
                return {"status": BROWSER_NOT_STARTED, "tabs": []}
            return {
                "browser_session_id": self._session.browser_session_id,
                "status": self._session.status,
                "started_at": self._session.started_at,
                "tabs": [
                    {
                        "tab_id": t.tab_id,
                        "url": t.url,
                        "title": t.title,
                        "task_id": t.task_id,
                        "opened_by": t.opened_by,
                        "status": t.status,
                        "created_at": t.created_at,
                        "last_seen_at": t.last_seen_at,
                    }
                    for t in self._session.tabs.values()
                ],
            }

    # ── 탭 관리 ────────────────────────────────────────────────────

    def upsert_tab(
        self,
        tab_id: str,
        *,
        url: str = "",
        title: str = "",
        task_id: str = "",
        opened_by: str = "",
        status: str = TAB_OPEN,
    ) -> TabRecord:
        if not tab_id:
            raise ValueError("tab_id is required")
        with self._lock:
            if self._session is None:
                self._session = BrowserSession(
                    browser_session_id=f"bs_{uuid.uuid4().hex[:12]}",
                    started_at=time.time(),
                    status=BROWSER_RUNNING,
                )
            now = time.time()
            existing = self._session.tabs.get(tab_id)
            if existing is None:
                rec = TabRecord(
                    tab_id=tab_id, url=url, title=title, task_id=task_id,
                    opened_by=opened_by, status=status,
                    created_at=now, last_seen_at=now,
                )
            else:
                rec = existing
                if url:
                    rec.url = url
                if title:
                    rec.title = title
                if task_id:
                    rec.task_id = task_id
                if opened_by:
                    rec.opened_by = opened_by
                rec.status = status
                rec.last_seen_at = now
            self._session.tabs[tab_id] = rec
            return TabRecord(**rec.__dict__)

    def set_login_state(self, tab_id: str, login_state: str) -> TabRecord | None:
        with self._lock:
            if self._session is None:
                return None
            rec = self._session.tabs.get(tab_id)
            if rec is None:
                return None
            if rec.login_state != login_state:
                rec.login_state = login_state
                rec.login_state_changed_at = time.time()
            rec.last_seen_at = time.time()
            return TabRecord(**rec.__dict__)

    def set_tab_role(self, tab_id: str, role: str) -> None:
        with self._lock:
            if self._session is None:
                return
            rec = self._session.tabs.get(tab_id)
            if rec is None:
                return
            rec.role = role
            rec.last_seen_at = time.time()

    def mark_tab_closed(self, tab_id: str) -> TabRecord | None:
        with self._lock:
            if self._session is None:
                return None
            rec = self._session.tabs.get(tab_id)
            if rec is None:
                return None
            rec.status = TAB_CLOSED
            rec.last_seen_at = time.time()
            return TabRecord(**rec.__dict__)

    def get_tab(self, tab_id: str) -> TabRecord | None:
        with self._lock:
            if self._session is None:
                return None
            rec = self._session.tabs.get(tab_id)
            if rec is None:
                return None
            return TabRecord(**rec.__dict__)

    def list_tabs(self, *, include_closed: bool = False) -> list[TabRecord]:
        with self._lock:
            if self._session is None:
                return []
            tabs = [TabRecord(**t.__dict__) for t in self._session.tabs.values()]
        if not include_closed:
            tabs = [t for t in tabs if t.status != TAB_CLOSED]
        return tabs

    # ── target diff (팝업/새 창 감지) ────────────────────────────

    def diff_targets(self, current_ids: list[str]) -> dict[str, list[str]]:
        """현재 CDP target_id 목록과 store 의 알려진 탭을 비교.

        Returns:
            {"added": [...], "removed": [...]} — added 는 새 탭(팝업/창 후보),
            removed 는 알려진 tab_id 중 사라진 것.
        """
        current = set(current_ids or [])
        with self._lock:
            known = set(self._session.tabs.keys()) if self._session else set()
        added = sorted(current - known)
        removed = sorted(known - current)
        return {"added": added, "removed": removed}


# ── 모듈 레벨 기본 store ────────────────────────────────────────────

default_store = BrowserSessionStore()
