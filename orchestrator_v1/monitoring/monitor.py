"""
운영 감시기 (6단계) — tail -f 형태 실시간 로그 감시
구성:
  FileTailer      — 파일 신규 줄 감지 (inode-safe rotation 지원)
  OpsLogParser    — orchestrator.log 텍스트 파싱
  AuditParser     — audit.jsonl JSONL 파싱
  ErrorDetector   — ERROR/CRITICAL 패턴 감지
  AlertThrottle   — 동일 키 중복 알림 억제
  ApprovalWatcher — APPROVAL_ISSUED 추적 → 미수신 시 재알림
  RetryEngine     — EXECUTION_FAILED 자동 재시도 (백오프)
  Monitor         — 메인 루프 (threading.Event 정지 가능)
"""

import json
import os
import re
import threading
import time
from pathlib import Path

from orchestrator_v1.core.logger import get_logger
from orchestrator_v1.monitoring.telegram_notifier import send_status_message

log = get_logger("monitor")

_BASE_DIR = str(Path(__file__).resolve().parents[2])

# ── 환경변수 설정 ──────────────────────────────────────────────────────────────
POLL_INTERVAL = float(os.environ.get("MONITOR_POLL_INTERVAL", "2"))
ALERT_COOLDOWN = float(os.environ.get("MONITOR_ALERT_COOLDOWN", "120"))
APPROVAL_REMINDER = float(os.environ.get("MONITOR_APPROVAL_REMINDER", "300"))
MAX_RETRY = int(os.environ.get("MONITOR_MAX_RETRY", "3"))
_RETRY_BACKOFF = [30, 60, 120]

WATCH_FILES = {
    "ops": Path(_BASE_DIR) / "logs" / "orchestrator.log",
    "audit": Path(_BASE_DIR) / "logs" / "audit.jsonl",
}


# ── FileTailer ─────────────────────────────────────────────────────────────────


class FileTailer:
    """tail -f 스타일 감시. 시작 시 기존 내용 skip, 이후 신규 줄만 반환."""

    def __init__(self, path: str | Path, name: str):
        self.path = Path(path)
        self.name = name
        self._pos: int = 0
        self._inode: int | None = None
        self._seek_end()

    def _seek_end(self):
        if not self.path.exists():
            return
        try:
            st = self.path.stat()
            self._inode = st.st_ino
            self._pos = st.st_size
        except OSError:
            pass

    def read_new(self) -> list[str]:
        if not self.path.exists():
            self._pos = 0
            self._inode = None
            return []
        try:
            st = self.path.stat()
        except OSError:
            return []

        # 파일 교체(로테이션) 또는 truncate 감지
        if st.st_ino != self._inode:
            log.info("monitor: file rotated — %s", self.name)
            self._inode = st.st_ino
            self._pos = 0
        elif st.st_size < self._pos:
            log.info("monitor: file truncated — %s", self.name)
            self._pos = 0

        if st.st_size == self._pos:
            return []

        try:
            with self.path.open(encoding="utf-8", errors="replace") as f:
                f.seek(self._pos)
                chunk = f.read()
                self._pos = f.tell()
        except OSError as e:
            log.warning("monitor: read error %s — %s", self.name, e)
            return []

        return [l for l in chunk.splitlines() if l.strip()]  # noqa: E741 - 기존 코드 이동(변경 없음)


# ── Parsers ────────────────────────────────────────────────────────────────────

# 2026-04-19 12:34:56 [ERROR   ] orchestrator.xxx event=... | message
_OPS_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
    r"\s+\[(?P<level>[A-Z]+)\s*\]\s+(?P<logger>\S+)"
    r".*?\|\s*(?P<message>.+)$"
)


def _parse_ops(line: str) -> dict | None:
    m = _OPS_RE.match(line)
    if not m:
        return None
    return {
        "ts": m.group("ts"),
        "level": m.group("level").strip(),
        "logger": m.group("logger"),
        "message": m.group("message").strip(),
        "raw": line,
    }


def _parse_audit(line: str) -> dict | None:
    try:
        return json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None


# ── AlertThrottle ──────────────────────────────────────────────────────────────


class AlertThrottle:
    def __init__(self, cooldown: float = ALERT_COOLDOWN):
        self._last: dict[str, float] = {}
        self._cooldown = cooldown

    def allow(self, key: str) -> bool:
        now = time.time()
        if now - self._last.get(key, 0) >= self._cooldown:
            self._last[key] = now
            return True
        return False

    def reset(self, key: str):
        self._last.pop(key, None)


# ── ApprovalWatcher ────────────────────────────────────────────────────────────


class ApprovalWatcher:
    """APPROVAL_ISSUED 추적 → reminder_interval 마다 재알림 (최대 3회)."""

    def __init__(self, throttle: AlertThrottle):
        self._pending: dict[str, dict] = {}
        self._throttle = throttle

    def on_issued(self, event: dict):
        task_id = event.get("task_id")
        if not task_id or task_id in self._pending:
            return
        self._pending[task_id] = {
            "issued_at": time.time(),
            "event": event,
            "reminded": 0,
        }
        log.info("monitor: approval tracking start task_id=%s risk=%s", task_id, event.get("risk_level", "-"))

    def on_resolved(self, task_id: str):
        if task_id in self._pending:
            del self._pending[task_id]
            log.info("monitor: approval resolved task_id=%s", task_id)

    def pending_reminders(self) -> list[dict]:
        alerts = []
        now = time.time()
        for task_id, info in list(self._pending.items()):
            reminded = info["reminded"]
            if reminded >= 3:
                continue
            elapsed = now - info["issued_at"]
            threshold = APPROVAL_REMINDER * (reminded + 1)
            if elapsed >= threshold:
                key = f"approval_reminder:{task_id}:{reminded}"
                if self._throttle.allow(key):
                    info["reminded"] += 1
                    alerts.append(
                        {
                            "task_id": task_id,
                            "elapsed": int(elapsed),
                            "event": info["event"],
                            "count": info["reminded"],
                        }
                    )
        return alerts


# ── RetryEngine ────────────────────────────────────────────────────────────────


class RetryEngine:
    """EXECUTION_FAILED 자동 재시도 — 지수 백오프."""

    def __init__(self, max_retry: int = MAX_RETRY):
        self._counts: dict[str, int] = {}
        self._next: dict[str, float] = {}
        self._max = max_retry

    def schedule(self, task_id: str) -> bool:
        count = self._counts.get(task_id, 0)
        if count >= self._max:
            return False
        delay = _RETRY_BACKOFF[min(count, len(_RETRY_BACKOFF) - 1)]
        self._counts[task_id] = count + 1
        self._next[task_id] = time.time() + delay
        log.info("monitor: retry scheduled task_id=%s attempt=%d/%d delay=%ds", task_id, count + 1, self._max, delay)
        return True

    def due(self) -> list[str]:
        now = time.time()
        ready = [tid for tid, t in list(self._next.items()) if now >= t]
        for tid in ready:
            del self._next[tid]
        return ready

    def attempt_count(self, task_id: str) -> int:
        return self._counts.get(task_id, 0)

    def clear(self, task_id: str):
        self._counts.pop(task_id, None)
        self._next.pop(task_id, None)


# ── Monitor ────────────────────────────────────────────────────────────────────


class Monitor:
    def __init__(self):
        self._tailers = {name: FileTailer(path, name) for name, path in WATCH_FILES.items()}
        self._throttle = AlertThrottle()
        self._approval = ApprovalWatcher(self._throttle)
        self._retry = RetryEngine()
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        log.info(
            "monitor: started poll=%.1fs cooldown=%.0fs approval_reminder=%.0fs max_retry=%d",
            POLL_INTERVAL,
            ALERT_COOLDOWN,
            APPROVAL_REMINDER,
            MAX_RETRY,
        )
        _alert(
            "🟢 *[감시기 시작]* orchestrator monitor 가동\n"
            f"• poll: {POLL_INTERVAL}s  cooldown: {ALERT_COOLDOWN}s\n"
            f"• approval_reminder: {APPROVAL_REMINDER}s  max_retry: {MAX_RETRY}"
        )

        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as exc:
                log.error("monitor: tick unhandled — %s", exc, exc_info=True)
            self._stop.wait(POLL_INTERVAL)

        log.info("monitor: stopped")

    # ── tick ──────────────────────────────────────────────────────────────────

    def _tick(self):
        self._process_ops()
        self._process_audit()
        self._check_approval_reminders()
        self._run_due_retries()

    def _process_ops(self):
        for line in self._tailers["ops"].read_new():
            parsed = _parse_ops(line)
            if not parsed:
                continue
            if parsed["level"] in ("ERROR", "CRITICAL"):
                self._on_ops_error(parsed)

    def _process_audit(self):
        for line in self._tailers["audit"].read_new():
            event = _parse_audit(line)
            if not event:
                continue
            et = event.get("event_type", "")
            task_id = event.get("task_id", "-")

            if et == "APPROVAL_ISSUED":
                self._approval.on_issued(event)
                _alert(
                    f"🔔 *[승인 요청 발생]*\n"
                    f"• task_id: `{task_id}`\n"
                    f"• action: {event.get('action_type', '-')}\n"
                    f"• risk: *{event.get('risk_level', '-')}*\n"
                    f"_대시보드에서 승인/거부하세요._"
                )

            elif et in ("APPROVAL_GRANTED", "APPROVAL_REJECTED"):
                self._approval.on_resolved(task_id)
                icon = "✅" if et == "APPROVAL_GRANTED" else "❌"
                _alert(
                    f"{icon} *[승인 결정]*\n• task_id: `{task_id}`\n• 결과: *{et}*\n• actor: {event.get('actor', '-')}"
                )

            elif et == "EXECUTION_FAILED":
                self._on_exec_failed(event)

            elif et == "EXECUTION_BLOCKED":
                key = f"blocked:{task_id}"
                if self._throttle.allow(key):
                    _alert(
                        f"🚫 *[실행 차단]*\n"
                        f"• task_id: `{task_id}`\n"
                        f"• risk: {event.get('risk_level', '-')}\n"
                        f"• 사유: {str(event.get('note', ''))[:200]}"
                    )

    def _check_approval_reminders(self):
        for item in self._approval.pending_reminders():
            ev = item["event"]
            _alert(
                f"⏳ *[승인 대기 재알림]* {item['elapsed']}초 경과 "
                f"({item['count']}/3회)\n"
                f"• task_id: `{item['task_id']}`\n"
                f"• action: {ev.get('action_type', '-')}\n"
                f"• risk: *{ev.get('risk_level', '-')}*\n"
                f"_대시보드에서 승인/거부하세요._"
            )

    def _run_due_retries(self):
        for task_id in self._retry.due():
            self._do_retry(task_id)

    # ── 이벤트 핸들러 ──────────────────────────────────────────────────────────

    def _on_ops_error(self, parsed: dict):
        key = f"ops_error:{parsed['logger']}:{parsed['message'][:60]}"
        if not self._throttle.allow(key):
            return
        _alert(
            f"🔴 *[운영 에러]* [{parsed['level']}]\n• {parsed['ts']} {parsed['logger']}\n• {parsed['message'][:300]}"
        )

    def _on_exec_failed(self, event: dict):
        task_id = event.get("task_id", "-")
        scheduled = self._retry.schedule(task_id)
        attempt = self._retry.attempt_count(task_id)
        key = f"exec_failed:{task_id}"
        if self._throttle.allow(key):
            suffix = (
                f"• 자동 재시도: {attempt}/{MAX_RETRY} "
                f"({_RETRY_BACKOFF[min(attempt - 1, len(_RETRY_BACKOFF) - 1)]}초 후)"
                if scheduled
                else "• 최대 재시도 도달 — 수동 확인 필요"
            )
            _alert(
                f"⚠️ *[실행 실패]*\n"
                f"• task_id: `{task_id}`\n"
                f"• action: {event.get('action_type', '-')}\n"
                f"• note: {str(event.get('note', ''))[:200]}\n"
                f"{suffix}"
            )

    def _do_retry(self, task_id: str):
        attempt = self._retry.attempt_count(task_id)
        log.info("monitor: retry executing task_id=%s attempt=%d", task_id, attempt)
        try:
            from orchestrator_v1.tasks.executor import execute_task

            result = execute_task(task_id)
            status = result.get("status", "UNKNOWN")

            if status in ("EXECUTED", "PREVIEW_ONLY"):
                log.info("monitor: retry success task_id=%s status=%s", task_id, status)
                self._retry.clear(task_id)
                self._throttle.reset(f"exec_failed:{task_id}")
                _alert(
                    f"✅ *[재시도 성공]*\n• task_id: `{task_id}`\n• status: {status}  attempt: {attempt}/{MAX_RETRY}"
                )

            elif status == "BLOCKED":
                log.warning("monitor: retry blocked task_id=%s", task_id)
                self._retry.clear(task_id)
                _alert(f"🚫 *[재시도 차단]* 정책상 실행 불가\n• task_id: `{task_id}`")

            else:
                # 재실패 — 다음 백오프로 재스케줄
                if not self._retry.schedule(task_id):
                    _alert(
                        f"🔴 *[재시도 최종 실패]* {attempt}/{MAX_RETRY} 모두 실패\n"
                        f"• task_id: `{task_id}` — 수동 개입 필요"
                    )

        except Exception as exc:
            log.error("monitor: retry exception task_id=%s — %s", task_id, exc, exc_info=True)
            _alert(f"🔴 *[재시도 예외]*\n• task_id: `{task_id}`\n• {str(exc)[:200]}")


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────


def _alert(text: str):
    log.info("monitor: alert → %s", text[:120].replace("\n", " "))
    send_status_message(text)


def run_monitor():
    log.info("monitor: workdir=%s", _BASE_DIR)
    m = Monitor()
    try:
        m.run()
    except KeyboardInterrupt:
        m.stop()
        log.info("monitor: stopped by keyboard interrupt")
