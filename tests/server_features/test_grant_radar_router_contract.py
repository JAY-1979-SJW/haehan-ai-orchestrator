"""grant_radar 라우터/스캔 계약 테스트: 로그 추가, 응답 key·반환값 불변."""

import logging
import subprocess
import types

from ai_orchestrator.connectors import grant_radar_router as gr
from scripts.grant_radar import scan as scan_mod


def test_load_company_failure_logs_and_returns_empty(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(gr, "COMPANY_FILE", tmp_path / "missing.json")
    with caplog.at_level(logging.WARNING, logger=gr.logger.name):
        assert gr._load_company() == {}
    assert any(r.levelno == logging.WARNING and r.exc_info for r in caplog.records)


def test_load_report_items_failure_logs_and_returns_empty(tmp_path, monkeypatch, caplog):
    bad = tmp_path / "r.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(gr, "REPORT_FILE", bad)
    with caplog.at_level(logging.WARNING, logger=gr.logger.name):
        assert gr._load_report_items() == []
    assert any(r.exc_info for r in caplog.records)


def test_trigger_scan_exec_error_keeps_reason(monkeypatch):
    def boom(*a, **k):
        raise OSError("x")

    monkeypatch.setattr(gr.subprocess, "run", boom)
    assert gr.trigger_scan() == {"ok": False, "reason": "exec_error"}
    assert gr._scan_running is False


def test_trigger_scan_timeout_and_ok_keys(monkeypatch):
    def to(*a, **k):
        raise subprocess.TimeoutExpired("c", 1)

    monkeypatch.setattr(gr.subprocess, "run", to)
    assert gr.trigger_scan() == {"ok": False, "reason": "timeout"}
    monkeypatch.setattr(gr.subprocess, "run", lambda *a, **k: types.SimpleNamespace(returncode=0))
    assert gr.trigger_scan() == {"ok": True, "scan_rc": 0, "report_rc": 0}


def test_extract_failure_recorded_in_errors():
    class P:
        def evaluate(self, *a):
            raise RuntimeError("bad")

    errs: list = []
    assert scan_mod._extract(P(), {"key": "k", "mode": "rows"}, errs) == []
    assert errs and "k" in errs[0]
    assert scan_mod._extract(P(), {"key": "k", "mode": "rows"}) == []
