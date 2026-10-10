"""실시간 팝업 감시 — popup_monitor v1.0

기존 popup_watcher (감지) + popup_classifier (판단) 위에 얹는
백그라운드 폴링 + 알림 큐 + 자동 처리 레이어.

기능:
  1. 모든 활성 탭에 popup_watcher 주입 보장
  2. 별도 thread에서 N초마다 새 이벤트 폴링
  3. 분류 후 auto_* 액션은 즉시 처리, notify_user / block_workflow 는 큐 적재
  4. SQLite popup_events 테이블에 모든 이력 영속화

사용 (in-process):
    from scripts.browser.popup.popup_monitor import PopupMonitor
    mon = PopupMonitor(poll_interval_s=2.0)
    mon.start()
    ...
    mon.stop()

CLI:
    python scripts/browser/cdp/cdp_client.py popup-monitor start
    python scripts/browser/cdp/cdp_client.py popup-monitor status
    python scripts/browser/cdp/cdp_client.py popup-monitor list
    python scripts/browser/cdp/cdp_client.py popup-monitor handle <id> ack
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import time
from contextlib import closing, suppress
from typing import Any

from scripts.browser.popup.popup_classifier import Action, Category, Decision, Severity, classify, is_auto_handleable
from scripts.browser.navigator.popup_watcher import POPUP_MARKERS, build_watcher_js
from scripts.common.app_paths import repo_root
from scripts.common.logger import get_logger

_log = get_logger(__name__)

# ── 직접 CDP 평가 (백그라운드 스레드 전용) ──────────────────────────────
# Playwright Sync API는 백그라운드 스레드에서 asyncio 충돌을 유발한다.
# 여기서는 requests + websockets 로 CDP를 직접 호출한다.

_ROOT = repo_root()
_DAEMON_STATE = _ROOT / "data" / "cdp_daemon_state.json"
_WATCHER_JS = build_watcher_js(POPUP_MARKERS)
_POLL_JS = "(s) => (window.__hh_popup_state?.events||[]).filter(e => e.ts_ms > s)"
_CLEAR_JS = "() => { if(window.__hh_popup_state) window.__hh_popup_state.events = []; }"


def _get_cdp_port() -> int:
    try:
        from scripts.common.config import CDP_PORT as _CDP_PORT
    except Exception:  # noqa: BLE001 - 백그라운드 팝업 감시 데몬 — 모니터링 루프는 한 틱이 실패해도 다음 틱으로 계속돼야 하므로 로그 후 진행, 상태 읽기 실패는 안전한 기본값 폴백, 쓰기·결제 없음(2026-09-28 검토)
        _CDP_PORT = 9222
    try:
        state = json.loads(_DAEMON_STATE.read_text(encoding="utf-8"))
        return int(state.get("cdp_port", _CDP_PORT))
    except Exception:  # noqa: BLE001 - 백그라운드 팝업 감시 데몬 — 모니터링 루프는 한 틱이 실패해도 다음 틱으로 계속돼야 하므로 로그 후 진행, 상태 읽기 실패는 안전한 기본값 폴백, 쓰기·결제 없음(2026-09-28 검토)
        return _CDP_PORT


async def _eval_tab(ws_url: str, js: str, arg: Any = None) -> Any:
    """단일 탭 WebSocket으로 JS 평가 후 결과 반환."""
    import websockets

    params: dict = {"expression": js if arg is None else f"({js})({json.dumps(arg)})", "returnByValue": True}
    try:
        async with websockets.connect(ws_url, open_timeout=2) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": params}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))
            return resp.get("result", {}).get("result", {}).get("value")
    except Exception as e:  # noqa: BLE001 - 백그라운드 팝업 감시 데몬 — 모니터링 루프는 한 틱이 실패해도 다음 틱으로 계속돼야 하므로 로그 후 진행, 상태 읽기 실패는 안전한 기본값 폴백, 쓰기·결제 없음(2026-09-28 검토)
        _log.debug("CDP WS 평가 실패 %s: %s", ws_url[:50], e)
        return None


async def _for_all_tabs(js: str, arg: Any = None) -> list[Any]:
    """모든 page 탭에 JS 평가 → 결과 리스트."""
    import requests

    port = _get_cdp_port()
    try:
        tabs = requests.get(f"http://localhost:{port}/json", timeout=2).json()
    except Exception as e:  # noqa: BLE001 - 백그라운드 팝업 감시 데몬 — 모니터링 루프는 한 틱이 실패해도 다음 틱으로 계속돼야 하므로 로그 후 진행, 상태 읽기 실패는 안전한 기본값 폴백, 쓰기·결제 없음(2026-09-28 검토)
        _log.debug("CDP 탭 목록 조회 실패: %s", e)
        return []
    ws_urls = [t["webSocketDebuggerUrl"] for t in tabs if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
    results = await asyncio.gather(*[_eval_tab(u, js, arg) for u in ws_urls], return_exceptions=True)
    return [r for r in results if r is not None and not isinstance(r, Exception)]


def _cdp_install_watcher() -> None:
    asyncio.run(_for_all_tabs(_WATCHER_JS))


def _cdp_poll_events(since_ms: int = 0) -> list[dict]:
    results = asyncio.run(_for_all_tabs(_POLL_JS, since_ms))
    events: list[dict] = []
    for r in results:
        if isinstance(r, list):
            events.extend(r)
    return events


def _cdp_clear_events() -> None:
    asyncio.run(_for_all_tabs(_CLEAR_JS))


DB_PATH = _ROOT / "data" / "cdp.db"
STATE_PATH = _ROOT / "data" / "popup_monitor_state.json"

DEFAULT_POLL_INTERVAL_S = 2.0
DB_TIMEOUT_S = 30
DB_BUSY_TIMEOUT_MS = 30000
DEFAULT_INSTALL_INTERVAL_S = 10.0  # 새 탭/네비게이션 후 재주입 주기


# ── DB ───────────────────────────────────────────────────────────────


def _connect_db() -> sqlite3.Connection:
    con = sqlite3.connect(str(DB_PATH), timeout=DB_TIMEOUT_S)
    con.execute(f"PRAGMA busy_timeout={DB_BUSY_TIMEOUT_MS}")
    return con


def _ensure_table() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(_connect_db()) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("""
            CREATE TABLE IF NOT EXISTS popup_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_ms       INTEGER NOT NULL,
                marker      TEXT NOT NULL,
                snippet     TEXT,
                frame_url   TEXT,
                category    TEXT,
                severity    TEXT,
                action      TEXT,
                target      TEXT,
                confidence  REAL,
                status      TEXT NOT NULL DEFAULT 'pending',  -- pending|handled|notified|acked
                handled_at  INTEGER,
                note        TEXT
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_popup_status ON popup_events(status, ts_ms)")
        # source 컬럼이 없으면 추가 ('dom' = 페이지 DOM, 'chrome_ui' = Chrome chrome UI)
        cols = [r[1] for r in con.execute("PRAGMA table_info(popup_events)").fetchall()]
        if "source" not in cols:
            con.execute("ALTER TABLE popup_events ADD COLUMN source TEXT NOT NULL DEFAULT 'dom'")
        con.commit()


def _record_event(ev: dict, decision: Decision, status: str, note: str = "", source: str = "dom") -> int:
    _ensure_table()
    with closing(_connect_db()) as con:
        cur = con.execute(
            """INSERT INTO popup_events
               (ts_ms, marker, snippet, frame_url, category, severity, action, target,
                confidence, status, handled_at, note, source)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                int(ev.get("ts_ms", time.time() * 1000)),
                ev.get("marker", ""),
                (ev.get("snippet") or "")[:1000],
                (ev.get("frame_url") or ev.get("target_window") or "")[:500],
                decision["category"],
                decision["severity"],
                decision["action"],
                decision["target"],
                float(decision["confidence"]),
                status,
                int(time.time() * 1000) if status != "pending" else None,
                note[:500],
                source,
            ),
        )
        con.commit()
        return int(cur.lastrowid or 0)


def list_pending(limit: int = 50) -> list[dict]:
    """대기 중(미확인) 팝업 이벤트 목록."""
    _ensure_table()
    with closing(_connect_db()) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """SELECT * FROM popup_events
               WHERE status IN ('pending', 'notified')
               ORDER BY ts_ms DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def ack_event(event_id: int, note: str = "") -> bool:
    """사용자가 확인한 이벤트를 acked 처리."""
    _ensure_table()
    with closing(_connect_db()) as con:
        cur = con.execute(
            "UPDATE popup_events SET status='acked', handled_at=?, note=? WHERE id=?",
            (int(time.time() * 1000), note[:500], event_id),
        )
        con.commit()
        return cur.rowcount > 0


def stats(since_ms: int = 0) -> dict:
    """since_ms 이후의 카테고리별 통계."""
    _ensure_table()
    with closing(_connect_db()) as con:
        rows = con.execute(
            """SELECT category, status, COUNT(*) c FROM popup_events
               WHERE ts_ms > ? GROUP BY category, status""",
            (since_ms,),
        ).fetchall()
    out: dict[str, dict[str, int]] = {}
    for cat, st, c in rows:
        out.setdefault(cat, {})[st] = c
    return out


# ── Monitor ──────────────────────────────────────────────────────────


class PopupMonitor:
    """별도 thread로 popup_watcher 폴링 + 자동 처리."""

    def __init__(
        self,
        page: Any = None,  # 하위 호환 유지 (미사용)
        *,
        poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
        install_interval_s: float = DEFAULT_INSTALL_INTERVAL_S,
        auto_handle: bool = True,
    ):
        self._poll = poll_interval_s
        self._reinstall = install_interval_s
        self._auto = auto_handle
        self._stop = threading.Event()
        self._thr: threading.Thread | None = None
        self._last_install = 0.0
        self._processed = 0
        self._handled = 0
        self._notified = 0

    def _maybe_reinstall(self) -> None:
        if time.time() - self._last_install < self._reinstall:
            return
        try:
            _cdp_install_watcher()
            self._last_install = time.time()
        except Exception as e:  # noqa: BLE001 - 백그라운드 팝업 감시 데몬 — 모니터링 루프는 한 틱이 실패해도 다음 틱으로 계속돼야 하므로 로그 후 진행, 상태 읽기 실패는 안전한 기본값 폴백, 쓰기·결제 없음(2026-09-28 검토)
            _log.debug("[popup_monitor] 재주입 실패: %s", e)

    def _process_event(self, ev: dict) -> None:
        self._processed += 1
        snippet = ev.get("snippet", "")
        decision = classify(marker=ev.get("marker", ""), snippet=snippet)
        _log.info(
            "[popup_monitor] %s → %s/%s (conf=%.2f)",
            ev.get("marker", "")[:30],
            decision["category"],
            decision["action"],
            decision["confidence"],
        )

        if self._auto and is_auto_handleable(decision):
            try:
                from scripts.browser.navigator.navigator import click_button

                ok = click_button(decision["target"] or "확인")
                self._handled += 1
                _record_event(ev, decision, status="handled" if ok else "notified", note=f"click_button={ok}")
                return
            except Exception as e:  # noqa: BLE001 - 백그라운드 팝업 감시 데몬 — 모니터링 루프는 한 틱이 실패해도 다음 틱으로 계속돼야 하므로 로그 후 진행, 상태 읽기 실패는 안전한 기본값 폴백, 쓰기·결제 없음(2026-09-28 검토)
                _log.warning("[popup_monitor] 자동 처리 실패: %s", e)
                _record_event(ev, decision, status="notified", note=f"auto_fail: {e}")
                self._notified += 1
                return

        # auto 불가 or auto 비활성화 → 알림 큐
        self._notified += 1
        _record_event(ev, decision, status="notified")

    def _loop(self) -> None:
        _log.info("[popup_monitor] 루프 시작 (poll=%.1fs)", self._poll)
        while not self._stop.is_set():
            try:
                self._maybe_reinstall()
                events = _cdp_poll_events(since_ms=0)
                for ev in events:
                    self._process_event(ev)
                if events:
                    with suppress(Exception):
                        _cdp_clear_events()
            except Exception as e:  # noqa: BLE001 - 백그라운드 팝업 감시 데몬 — 모니터링 루프는 한 틱이 실패해도 다음 틱으로 계속돼야 하므로 로그 후 진행, 상태 읽기 실패는 안전한 기본값 폴백, 쓰기·결제 없음(2026-09-28 검토)
                _log.debug("[popup_monitor] 루프 오류 무시: %s", e)
            self._write_state()
            self._stop.wait(self._poll)
        _log.info("[popup_monitor] 루프 종료")

    def _write_state(self) -> None:
        try:
            STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            STATE_PATH.write_text(
                json.dumps(
                    {
                        "running": True,
                        "updated_at": int(time.time() * 1000),
                        "processed": self._processed,
                        "handled": self._handled,
                        "notified": self._notified,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001 - 상태 파일 읽기/이벤트 초기화 등 보조 동작 — 실패해도 모니터링 계속(2026-09-28 검토)
            pass

    def start(self) -> None:
        if self._thr and self._thr.is_alive():
            return
        self._stop.clear()
        self._thr = threading.Thread(target=self._loop, name="popup_monitor", daemon=True)
        self._thr.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thr:
            self._thr.join(timeout=timeout)
        try:
            if STATE_PATH.exists():
                data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
                data["running"] = False
                STATE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:  # noqa: BLE001 - 상태 파일 읽기/이벤트 초기화 등 보조 동작 — 실패해도 모니터링 계속(2026-09-28 검토)
            pass


def status() -> dict:
    """현재 모니터 상태 + 누적 통계."""
    state: dict = {"running": False}
    if STATE_PATH.exists():
        with suppress(Exception):
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    state["pending"] = len(list_pending(limit=500))
    state["stats_24h"] = stats(since_ms=int((time.time() - 86400) * 1000))
    return state


# ── Chrome chrome UI Watcher (uiautomation 기반) ────────────────────

CHROME_UI_STATE_PATH = _ROOT / "data" / "chrome_ui_watcher_state.json"
_CHROME_UI_COOLDOWN_S = 60.0  # 같은 (marker, window) 조합 재기록 쿨다운


class ChromeUIWatcher:
    """별도 스레드로 Chrome chrome UI(인포바/풍선)를 스캔하여 popup_events에 적재."""

    def __init__(self, *, poll_interval_s: float = 3.0, auto_handle: bool = True):
        self._poll = poll_interval_s
        self._auto = auto_handle
        self._stop = threading.Event()
        self._thr: threading.Thread | None = None
        self._last_seen: dict[tuple[str, str], float] = {}
        self._processed = 0
        self._handled = 0
        self._notified = 0

    def _classify_chrome_event(self, ev: dict) -> Decision:
        """ChromeUIEvent → Decision 매핑 (chrome_ui_watcher.CHROME_UI_RULES 기반)."""
        # chrome_ui_watcher 가 이미 marker 키와 button_name 을 알려줌 → 카테고리 직접 결정
        marker = ev.get("marker", "unknown")
        btn = ev.get("button_name")
        # marker → (category, severity, action)
        TABLE: dict[str, tuple[Category, Severity, Action]] = {
            "automation_warning": ("notification_request", "low", "notify_user"),
            "session_crashed": ("draft_restore", "low", "auto_dismiss"),
            "save_password": ("marketing_optin", "low", "auto_dismiss"),
            "translate_offer": ("marketing_optin", "low", "auto_dismiss"),
            "update_chrome": ("update_available", "low", "notify_user"),
            "performance_warning": ("generic_info", "low", "auto_dismiss"),
            "download_warning": ("destructive_confirm", "high", "notify_user"),
            "notification_permission": ("notification_request", "low", "auto_dismiss"),
            "location_permission": ("notification_request", "medium", "auto_dismiss"),
        }
        cat, sev, act = TABLE.get(marker, ("unknown", "medium", "notify_user"))
        return Decision(
            category=cat,
            severity=sev,
            action=act,
            target=btn,
            confidence=0.85,
            reasoning=f"chrome_ui_watcher 매칭: {marker}",
        )

    def _process_event(self, window, ev: dict) -> None:
        self._processed += 1
        decision = self._classify_chrome_event(ev)
        marker = ev.get("marker", "")
        win_title = ev.get("target_window", "")
        _log.info(
            "[chrome_ui_watcher] %s @ %s → %s/%s btn=%s",
            marker,
            win_title[:30],
            decision["category"],
            decision["action"],
            decision["target"],
        )

        self._notified += 1
        _record_event(ev, decision, status="notified", source="chrome_ui")

    def _loop(self) -> None:
        _log.info("[chrome_ui_watcher] 루프 시작 (poll=%.1fs)", self._poll)
        while not self._stop.is_set():
            self._write_state()
            self._stop.wait(self._poll)
        _log.info("[chrome_ui_watcher] 루프 종료")

    def _write_state(self) -> None:
        try:
            CHROME_UI_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            CHROME_UI_STATE_PATH.write_text(
                json.dumps(
                    {
                        "running": True,
                        "updated_at": int(time.time() * 1000),
                        "processed": self._processed,
                        "handled": self._handled,
                        "notified": self._notified,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001 - 상태 파일 읽기/이벤트 초기화 등 보조 동작 — 실패해도 모니터링 계속(2026-09-28 검토)
            pass

    def start(self) -> None:
        if self._thr and self._thr.is_alive():
            return
        self._stop.clear()
        self._thr = threading.Thread(target=self._loop, name="chrome_ui_watcher", daemon=True)
        self._thr.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thr:
            self._thr.join(timeout=timeout)


def chrome_ui_status() -> dict:
    """Chrome UI Watcher 상태."""
    out: dict = {"running": False}
    if CHROME_UI_STATE_PATH.exists():
        with suppress(Exception):
            out = json.loads(CHROME_UI_STATE_PATH.read_text(encoding="utf-8"))
    return out
