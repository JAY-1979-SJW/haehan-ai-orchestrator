"""Chrome UI 감시 프로세스 — chrome_ui_monitor v1.0

별도 독립 프로세스에서 Windows UI Automation으로 Chrome UI 팝업 감시.
cdp_daemon의 daemon thread가 아닌 별도 프로세스에서 실행되므로
IDE/터미널 세션과 무관함.

사용:
    python scripts/cdp_client.py chrome-ui-monitor start
    python scripts/cdp_client.py chrome-ui-monitor status
    python scripts/cdp_client.py chrome-ui-monitor stop
"""

from __future__ import annotations

import json
import signal
import threading
import time
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[3]

from scripts.browser.popup.popup_classifier import (  # noqa: E402 - REPO_ROOT 계산 이후 임포트하는 기존 구조(이번 BLE001 작업과 무관)
    classify,
    is_auto_handleable,
)
from scripts.browser.navigator.popup_monitor import (  # noqa: E402 - REPO_ROOT 계산 이후 임포트하는 기존 구조(이번 BLE001 작업과 무관)
    _record_event,
)
from scripts.common.logger import get_logger  # noqa: E402 - REPO_ROOT 이후 import

_log = get_logger(__name__)

STATE_FILE = REPO_ROOT / "data" / "runtime" / "chrome_ui_monitor_state.json"
_stop_event = threading.Event()


def _save_state(data: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def run_monitor(poll_interval_s: float = 3.0, auto_handle: bool = True) -> None:
    """독립 프로세스로 Chrome UI Watcher 실행."""
    _log.info("=" * 60)
    _log.info("  Chrome UI Monitor (독립 프로세스)")
    _log.info("  PID: %d", __import__("os").getpid())
    _log.info("  Poll interval: %.1fs", poll_interval_s)
    _log.info("=" * 60)

    def _signal_handler(signum: int, frame: Any) -> None:
        _log.info("신호 수신: %d → 종료", signum)
        _stop_event.set()

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    _save_state(
        {
            "running": True,
            "pid": __import__("os").getpid(),
            "started_at": time.time(),
            "processed": 0,
            "handled": 0,
            "notified": 0,
        }
    )

    processed = 0
    handled = 0
    notified = 0
    last_seen: dict[tuple[str, str], float] = {}
    COOLDOWN_S = 60.0

    while not _stop_event.is_set():
        try:
            from scripts.chrome_ui_watcher import scan_all

            pairs = scan_all()
            now = time.time()

            for window, events in pairs:
                win_title = (window.Name or "")[:120]
                for ev in events:
                    key = (ev["marker"], win_title)
                    if now - last_seen.get(key, 0) < COOLDOWN_S:
                        continue
                    last_seen[key] = now

                    processed += 1
                    marker = ev.get("marker", "unknown")
                    snippet = ev.get("snippet", "")
                    decision = classify(marker=marker, snippet=snippet)

                    _log.info(
                        "[chrome_ui_monitor] %s @ %s → %s/%s",
                        marker,
                        win_title[:30],
                        decision["category"],
                        decision["action"],
                    )

                    if auto_handle and is_auto_handleable(decision) and decision["target"]:
                        try:
                            from scripts.chrome_ui_watcher import click_button_in_window

                            ok = click_button_in_window(window, decision["target"])
                            _record_event(
                                cast(dict, ev),
                                decision,
                                status="handled" if ok else "notified",
                                note=f"chrome_ui click={ok}",
                                source="chrome_ui",
                            )
                            if ok:
                                handled += 1
                            else:
                                notified += 1
                        except Exception as e:  # noqa: BLE001 - 크롬 UI 이벤트 모니터 -- 자동 처리 실패 시 사용자에게 알림(notified)으로 안전하게 폴백(자동실행 강행 아님), 루프 자체 오류는 디버그 로깅 후 무시하고 폴링 계속
                            _log.warning("[chrome_ui_monitor] 자동 처리 실패: %s", e)
                            _record_event(cast(dict, ev), decision, status="notified", source="chrome_ui")
                            notified += 1
                    else:
                        _record_event(cast(dict, ev), decision, status="notified", source="chrome_ui")
                        notified += 1

            _save_state(
                {
                    "running": True,
                    "pid": __import__("os").getpid(),
                    "updated_at": time.time(),
                    "processed": processed,
                    "handled": handled,
                    "notified": notified,
                }
            )
        except Exception as e:  # noqa: BLE001 - 크롬 UI 이벤트 모니터 -- 자동 처리 실패 시 사용자에게 알림(notified)으로 안전하게 폴백(자동실행 강행 아님), 루프 자체 오류는 디버그 로깅 후 무시하고 폴링 계속
            _log.debug("[chrome_ui_monitor] 루프 오류 무시: %s", e)

        _stop_event.wait(timeout=poll_interval_s)

    _log.info("Chrome UI Monitor 종료")
    _save_state(
        {
            "running": False,
            "pid": __import__("os").getpid(),
            "stopped_at": time.time(),
            "processed": processed,
            "handled": handled,
            "notified": notified,
        }
    )


if __name__ == "__main__":
    import sys

    poll_interval = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0
    run_monitor(poll_interval_s=poll_interval)
