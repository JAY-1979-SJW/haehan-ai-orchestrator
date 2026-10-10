"""ErrorRecovery.log_error 회귀 시험 — log_critical(category, message, **metadata) 에
category= 를 다시 넘겨 TypeError("multiple values for argument 'category'") 가 나던 결함."""

from __future__ import annotations

import sqlite3

from scripts.naver.automation import error_recovery as er


def test_log_error_does_not_raise_and_records_error_category(tmp_path, monkeypatch):
    monkeypatch.setattr(er, "DB_PATH", tmp_path / "cdp.db")
    calls: list[tuple[str, str, dict]] = []

    # 실제 log_critical 과 같은 시그니처(위치 인자 category, message + **metadata)의 대체물
    def fake_log_critical(category: str, message: str, **metadata):
        calls.append((category, message, metadata))

    monkeypatch.setattr(er, "log_critical", fake_log_critical)

    rec = er.ErrorRecovery()
    rec.log_error("my_func", ValueError("boom"), attempts=2, recovered=False)

    assert len(calls) == 1
    category, _message, metadata = calls[0]
    assert category == "OTHER"
    assert metadata["error_category"] == er.categorize_error(ValueError("boom"))
    assert metadata["func"] == "my_func"

    conn = sqlite3.connect(str(tmp_path / "cdp.db"))
    try:
        rows = conn.execute("SELECT function_name, attempts, recovered FROM error_log").fetchall()
    finally:
        conn.close()
    assert rows == [("my_func", 2, 0)]
