"""scripts/common/logger.py 의 회전 핸들러 시험 — 여러 프로세스가 같은 로그를 열고 있어 회전이 막혀도(WinError 32) 기록이 이어져야 한다.

2026-10-04 앱 실검증에서 data/logs/app.log 회전이 112회 실패했다(표준 RotatingFileHandler 는 막히면 줄마다 재시도하고 오류를 낸다).
"""

from __future__ import annotations

import logging

from scripts.common.logger import _BlockedRotateSafeHandler


def _record(msg: str) -> logging.LogRecord:
    return logging.LogRecord("t", logging.INFO, __file__, 1, msg, None, None)


def _handler(tmp_path, max_bytes: int = 200) -> _BlockedRotateSafeHandler:
    h = _BlockedRotateSafeHandler(tmp_path / "app.log", maxBytes=max_bytes, backupCount=2, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(message)s"))
    return h


def test_blocked_rotation_keeps_logging_without_errors(tmp_path, monkeypatch):
    h = _handler(tmp_path)
    errors: list = []
    monkeypatch.setattr(h, "handleError", lambda record: errors.append(record))
    attempts: list = []

    def blocked(source, dest):
        attempts.append(source)
        raise PermissionError(32, "다른 프로세스가 파일을 사용 중")

    monkeypatch.setattr(h, "rotate", blocked)

    for i in range(30):  # 200바이트를 훌쩍 넘겨 회전 조건이 계속 참인 상황
        h.emit(_record(f"line-{i:02d} " + "x" * 30))
    h.close()

    assert errors == []  # 오류가 밖으로 새지 않는다
    assert len(attempts) == 1  # 막힌 동안은 줄마다 재시도하지 않는다
    text = (tmp_path / "app.log").read_text(encoding="utf-8")
    assert all(f"line-{i:02d}" in text for i in range(30))  # 기록은 한 줄도 빠지지 않는다


def test_rotation_resumes_after_retry_window(tmp_path, monkeypatch):
    h = _handler(tmp_path)
    real_rotate = h.rotate
    monkeypatch.setattr(h, "rotate", lambda s, d: (_ for _ in ()).throw(PermissionError(32, "busy")))
    for i in range(10):
        h.emit(_record(f"a-{i} " + "x" * 40))
    assert not (tmp_path / "app.log.1").exists()  # 막혀서 회전 못 함

    monkeypatch.setattr(h, "rotate", real_rotate)  # 파일이 풀림
    h._blocked_until = 0.0  # 재시도 대기 시간이 지난 것으로 본다
    h.emit(_record("b-after " + "x" * 40))
    h.close()

    assert (tmp_path / "app.log.1").exists()  # 이제 회전된다


def test_normal_rotation_unchanged(tmp_path):
    h = _handler(tmp_path)
    for i in range(10):
        h.emit(_record(f"n-{i} " + "x" * 40))
    h.close()
    assert (tmp_path / "app.log.1").exists()
