"""eum_send_mail_batch 중복 발송 방지 시험 — 가짜 발송 함수/tmp_path 만 사용(SMTP 접속 없음)."""

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "eum" / "send_mail_batch.py"


@pytest.fixture()
def mod(monkeypatch, tmp_path):
    # import 부작용(.env 로드) 차단: dotenv 를 가짜로 주입
    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.__dict__["load_dotenv"] = lambda *a, **k: False
    monkeypatch.setitem(sys.modules, "dotenv", fake_dotenv)
    spec = importlib.util.spec_from_file_location("eum_send_mail_batch_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setattr(m, "LOG_FILE", tmp_path / "log.json")
    return m


def _rows(n):
    return [{"이메일": f"u{i}@example.com", "업체명": f"c{i}", "공사명": f"p{i}"} for i in range(1, n + 1)]


def _run(mod, rows, send, **kw):
    log = mod.load_sent_log()
    return mod.run_send_loop(mod.select_targets(rows, log), log, send, save=mod.save_log, sleep=lambda s: None, **kw)


def test_crash_midway_keeps_sent_log(mod):
    sent = []

    def send(row):
        if len(sent) == 3:
            raise KeyboardInterrupt
        sent.append(row["이메일"])
        return True

    with pytest.raises(KeyboardInterrupt):
        _run(mod, _rows(6), send)
    saved = json.loads(mod.LOG_FILE.read_text(encoding="utf-8"))
    assert [e["email"] for e in saved["sent"]] == sent
    assert len(saved["sent"]) == 3


def test_rerun_skips_already_sent(mod):
    first = []

    def boom(row):
        if len(first) == 3:
            raise KeyboardInterrupt
        first.append(row["이메일"])
        return True

    with pytest.raises(KeyboardInterrupt):
        _run(mod, _rows(6), boom)
    second = []
    _run(mod, _rows(6), lambda r: second.append(r["이메일"]) or True)
    assert second == ["u4@example.com", "u5@example.com", "u6@example.com"]
    assert not set(first) & set(second)


def test_no_log_file_and_legacy_format(mod):
    assert mod.load_sent_log() == {"sent": [], "failed": []}
    legacy = {"sent": [{"email": " U1@Example.com ", "company": "c", "project": "p", "seq": 1}]}
    mod.LOG_FILE.write_text(json.dumps(legacy), encoding="utf-8")  # failed 키 없는 구 형식
    got = []
    _run(mod, _rows(2), lambda r: got.append(r["이메일"]) or True)
    assert got == ["u2@example.com"]
    saved = json.loads(mod.LOG_FILE.read_text(encoding="utf-8"))
    assert len(saved["sent"]) == 2 and saved["failed"] == []


def test_failed_send_not_recorded_as_sent(mod):
    def send(row):
        if row["이메일"] == "u2@example.com":
            raise OSError("smtp down")
        return True

    _run(mod, _rows(3), send)
    saved = json.loads(mod.LOG_FILE.read_text(encoding="utf-8"))
    assert [e["email"] for e in saved["sent"]] == ["u1@example.com", "u3@example.com"]
    assert [e["email"] for e in saved["failed"]] == ["u2@example.com"]
    # 실패 건은 재실행 시 재시도 대상
    again = []
    _run(mod, _rows(3), lambda r: again.append(r["이메일"]) or True)
    assert again == ["u2@example.com"]


def test_duplicate_recipient_in_same_run_sent_once(mod):
    rows = [*_rows(2), dict(_rows(1)[0], 이메일="U1@example.com")]
    got = []
    _run(mod, rows, lambda r: got.append(r["이메일"]) or True)
    assert got == ["u1@example.com", "u2@example.com"]


def test_atomic_save_leaves_no_tmp(mod):
    mod.save_log({"sent": [], "failed": []})
    assert [p.name for p in mod.LOG_FILE.parent.iterdir()] == ["log.json"]


def test_missing_credentials_raises_before_send(mod, monkeypatch):
    monkeypatch.setattr(mod, "ACCOUNT", None)
    monkeypatch.setattr(mod, "PASSWORD", None)
    with pytest.raises(RuntimeError):
        mod.require_credentials()
    monkeypatch.setattr(mod, "ACCOUNT", "a")
    monkeypatch.setattr(mod, "PASSWORD", "b")
    mod.require_credentials()
