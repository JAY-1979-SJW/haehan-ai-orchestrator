"""
monitor.py 단위 테스트
- FileTailer: 신규 줄 감지, rotation, truncate
- AlertThrottle: 중복 억제, cooldown 만료 후 허용
- ApprovalWatcher: issued 추적, resolved 제거, 재알림 생성
- RetryEngine: 스케줄, due 반환, 최대 초과
- _parse_ops / _parse_audit: 파서 정상/비정상 입력
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / ".."))

import orchestrator_v1.monitoring.monitor as mon

# ── FileTailer ────────────────────────────────────────────────────────────────


class TestFileTailer:
    def test_reads_only_new_lines(self, tmp_path):
        f = tmp_path / "ops.log"
        f.write_text("old line\n", encoding="utf-8")

        tailer = mon.FileTailer(str(f), "ops")
        assert tailer.read_new() == []  # 기존 내용 skip

        f.write_text("old line\nnew line 1\nnew line 2\n", encoding="utf-8")
        lines = tailer.read_new()
        assert lines == ["new line 1", "new line 2"]

    def test_empty_file_returns_nothing(self, tmp_path):
        f = tmp_path / "empty.log"
        f.write_text("", encoding="utf-8")
        tailer = mon.FileTailer(str(f), "x")
        assert tailer.read_new() == []

    def test_missing_file_returns_nothing(self, tmp_path):
        tailer = mon.FileTailer(str(tmp_path / "missing.log"), "x")
        assert tailer.read_new() == []

    def test_truncate_detected(self, tmp_path):
        f = tmp_path / "ops.log"
        f.write_text("line1\nline2\n", encoding="utf-8")
        tailer = mon.FileTailer(str(f), "ops")
        # truncate
        f.write_text("fresh\n", encoding="utf-8")
        lines = tailer.read_new()
        assert "fresh" in lines

    def test_rotation_detected(self, tmp_path):
        f = tmp_path / "ops.log"
        f.write_text("before rotation\n", encoding="utf-8")
        tailer = mon.FileTailer(str(f), "ops")

        # 새 파일로 교체 (inode 변경 시뮬레이션: 삭제 후 재생성)
        f.unlink()
        f.write_text("after rotation\n", encoding="utf-8")
        lines = tailer.read_new()
        assert "after rotation" in lines


# ── Parsers ───────────────────────────────────────────────────────────────────


class TestParsers:
    def test_parse_ops_error(self):
        line = (
            "2026-04-19 10:00:00 [ERROR   ] orchestrator.executor "
            "event=- task=- action=- actor=- | something went wrong"
        )
        result = mon._parse_ops(line)
        assert result is not None
        assert result["level"] == "ERROR"
        assert result["logger"] == "orchestrator.executor"
        assert "something went wrong" in result["message"]

    def test_parse_ops_info(self):
        line = (
            "2026-04-19 10:00:00 [INFO    ] orchestrator.app "
            "event=TASK_RECEIVED task=t1 action=read_file actor=system | ok"
        )
        result = mon._parse_ops(line)
        assert result["level"] == "INFO"

    def test_parse_ops_malformed(self):
        assert mon._parse_ops("not a valid log line") is None
        assert mon._parse_ops("") is None

    def test_parse_audit_valid(self):
        payload = {"event_type": "EXECUTION_FAILED", "task_id": "t1"}
        result = mon._parse_audit(json.dumps(payload))
        assert result["event_type"] == "EXECUTION_FAILED"

    def test_parse_audit_invalid(self):
        assert mon._parse_audit("not json") is None
        assert mon._parse_audit("{bad}") is None


# ── AlertThrottle ─────────────────────────────────────────────────────────────


class TestAlertThrottle:
    def test_first_call_allowed(self):
        t = mon.AlertThrottle(cooldown=60)
        assert t.allow("key1") is True

    def test_second_call_suppressed(self):
        t = mon.AlertThrottle(cooldown=60)
        t.allow("key1")
        assert t.allow("key1") is False

    def test_different_keys_independent(self):
        t = mon.AlertThrottle(cooldown=60)
        t.allow("a")
        assert t.allow("b") is True

    def test_cooldown_expired_allows(self):
        t = mon.AlertThrottle(cooldown=0.01)
        t.allow("key1")
        time.sleep(0.02)
        assert t.allow("key1") is True

    def test_reset_clears_key(self):
        t = mon.AlertThrottle(cooldown=60)
        t.allow("key1")
        t.reset("key1")
        assert t.allow("key1") is True


# ── ApprovalWatcher ───────────────────────────────────────────────────────────


class TestApprovalWatcher:
    def _throttle(self):
        return mon.AlertThrottle(cooldown=0)  # 억제 없이 테스트

    def test_on_issued_tracks(self):
        aw = mon.ApprovalWatcher(self._throttle())
        aw.on_issued({"task_id": "t1", "risk_level": "medium"})
        assert "t1" in aw._pending

    def test_on_issued_duplicate_ignored(self):
        aw = mon.ApprovalWatcher(self._throttle())
        aw.on_issued({"task_id": "t1"})
        aw.on_issued({"task_id": "t1"})  # 중복
        assert len(aw._pending) == 1

    def test_on_resolved_removes(self):
        aw = mon.ApprovalWatcher(self._throttle())
        aw.on_issued({"task_id": "t1"})
        aw.on_resolved("t1")
        assert "t1" not in aw._pending

    def test_reminder_triggers_after_interval(self, monkeypatch):
        aw = mon.ApprovalWatcher(self._throttle())
        # reminder 간격을 0으로 설정
        monkeypatch.setattr(mon, "APPROVAL_REMINDER", 0)
        aw.on_issued({"task_id": "t1", "action_type": "read_file", "risk_level": "medium"})
        # issued_at을 과거로 설정
        aw._pending["t1"]["issued_at"] = time.time() - 1
        alerts = aw.pending_reminders()
        assert len(alerts) == 1
        assert alerts[0]["task_id"] == "t1"

    def test_reminder_max_3_times(self, monkeypatch):
        monkeypatch.setattr(mon, "APPROVAL_REMINDER", 0)
        aw = mon.ApprovalWatcher(self._throttle())
        aw.on_issued({"task_id": "t1"})
        aw._pending["t1"]["issued_at"] = time.time() - 100
        # 3회 소진
        for _ in range(3):
            aw.pending_reminders()
        alerts = aw.pending_reminders()
        assert alerts == []


# ── RetryEngine ───────────────────────────────────────────────────────────────


class TestRetryEngine:
    def test_schedule_returns_true_under_max(self):
        r = mon.RetryEngine(max_retry=3)
        assert r.schedule("t1") is True
        assert r.attempt_count("t1") == 1

    def test_schedule_returns_false_over_max(self):
        r = mon.RetryEngine(max_retry=2)
        r.schedule("t1")
        r.schedule("t1")
        assert r.schedule("t1") is False

    def test_due_returns_task_when_ready(self, monkeypatch):
        r = mon.RetryEngine(max_retry=3)
        monkeypatch.setattr(mon, "_RETRY_BACKOFF", [0, 0, 0])
        r.schedule("t1")
        r._next["t1"] = time.time() - 1  # 즉시 실행 가능
        assert "t1" in r.due()

    def test_due_empty_before_delay(self):
        r = mon.RetryEngine(max_retry=3)
        r._next["t1"] = time.time() + 9999
        assert r.due() == []

    def test_clear_removes_task(self):
        r = mon.RetryEngine(max_retry=3)
        r.schedule("t1")
        r.clear("t1")
        assert r.attempt_count("t1") == 0
        assert "t1" not in r._next


# ── Monitor._on_exec_failed (알림 측 통합) ────────────────────────────────────


class TestMonitorAlerts:
    def test_exec_failed_schedules_retry(self, monkeypatch):
        sent = []
        monkeypatch.setattr(mon, "send_status_message", lambda t: sent.append(t))

        m = mon.Monitor()
        event = {"event_type": "EXECUTION_FAILED", "task_id": "t99", "action_type": "read_file"}
        m._on_exec_failed(event)

        assert m._retry.attempt_count("t99") == 1
        assert any("재시도" in s for s in sent)

    def test_exec_failed_max_retry_sends_manual_alert(self, monkeypatch):
        sent = []
        monkeypatch.setattr(mon, "send_status_message", lambda t: sent.append(t))

        m = mon.Monitor()
        # RetryEngine max를 1로 직접 설정
        m._retry._max = 1
        event = {"event_type": "EXECUTION_FAILED", "task_id": "t88"}
        # 이미 1회 사용한 것처럼 세팅
        m._retry._counts["t88"] = 1
        m._on_exec_failed(event)
        assert any("수동 확인" in s or "최대" in s for s in sent)
