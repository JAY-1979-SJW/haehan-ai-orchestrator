"""scripts/common/publish_guard.py 단위 테스트 — 텔레그램 전송은 항상 mock, 실제 발송 금지."""

from __future__ import annotations

import scripts.common.publish_guard as pg


def test_guarded_publish_success_passthrough(monkeypatch):
    """성공 경로는 기록·알림을 건드리지 않고 그대로 통과한다."""
    calls = []
    monkeypatch.setattr(pg, "log_op", lambda *a, **k: calls.append((a, k)))
    monkeypatch.setattr(pg, "_notify", lambda *a, **k: calls.append("notify"))

    with pg.guarded_publish("test_op"):
        pass

    assert calls == []


def test_guarded_publish_failure_records_and_notifies_then_reraises(monkeypatch):
    logged = {}
    notified = {}

    def fake_log_op(op_name, *, ok, message="", **meta):
        logged["op_name"] = op_name
        logged["ok"] = ok
        logged["message"] = message

    def fake_notify(text):
        notified["text"] = text

    monkeypatch.setattr(pg, "log_op", fake_log_op)
    monkeypatch.setattr(pg, "_notify", fake_notify)

    raised = False
    try:
        with pg.guarded_publish("ig_publish"):
            raise RuntimeError("boom")
    except RuntimeError as exc:
        raised = True
        assert str(exc) == "boom"

    assert raised, "원래 예외가 다시 raise 되어야 한다"
    assert logged["op_name"] == "ig_publish"
    assert logged["ok"] is False
    assert "RuntimeError" in logged["message"]
    assert "boom" in notified["text"]


def test_guarded_publish_notify_false_skips_telegram(monkeypatch):
    notified = []
    monkeypatch.setattr(pg, "log_op", lambda *a, **k: None)
    monkeypatch.setattr(pg, "_notify", lambda *a, **k: notified.append(1))

    try:
        with pg.guarded_publish("op", notify=False):
            raise ValueError("x")
    except ValueError:
        pass

    assert notified == []


def test_guarded_publish_telegram_failure_does_not_break_flow(monkeypatch):
    """알림 전송 자체가 예외를 던져도 원래 예외 전파는 유지되어야 한다."""
    monkeypatch.setattr(pg, "log_op", lambda *a, **k: None)

    def boom_notify(text):
        raise ConnectionError("network down")

    monkeypatch.setattr(pg, "_notify", boom_notify)

    raised = False
    try:
        with pg.guarded_publish("op"):
            raise RuntimeError("original")
    except RuntimeError as exc:
        raised = True
        assert str(exc) == "original"
    assert raised


def test_notify_skips_when_telegram_unconfigured(monkeypatch):
    """send_message 가 미설정으로 skipped 응답을 주면 stderr 에러 출력이 없어야 한다."""
    import ai_orchestrator.core.telegram_sender as ts

    monkeypatch.setattr(ts, "send_message", lambda text: {"ok": False, "skipped": True})
    # 예외 없이 완료되면 성공
    pg._notify("test message")


def test_guarded_decorator_success_returns_value_unchanged(monkeypatch):
    monkeypatch.setattr(pg, "log_op", lambda *a, **k: None)
    monkeypatch.setattr(pg, "_notify", lambda *a, **k: None)

    @pg.guarded("op")
    def fn(x):
        return x * 2

    assert fn(3) == 6


def test_guarded_decorator_exception_records_notifies_reraises(monkeypatch):
    logged = {}
    monkeypatch.setattr(
        pg, "log_op", lambda op_name, *, ok, message="", **k: logged.update(op_name=op_name, ok=ok, message=message)
    )
    notified = []
    monkeypatch.setattr(pg, "_notify", lambda text: notified.append(text))

    @pg.guarded("op_exc")
    def fn():
        raise ValueError("bad")

    raised = False
    try:
        fn()
    except ValueError:
        raised = True
    assert raised
    assert logged["ok"] is False
    assert notified


def test_guarded_decorator_ok_fn_false_records_failure_but_returns_result(monkeypatch):
    """반환형 실패(예: {"ok": False})는 기록·알림하지만 반환값 자체는 바꾸지 않는다."""
    logged = {}
    monkeypatch.setattr(
        pg, "log_op", lambda op_name, *, ok, message="", **k: logged.update(op_name=op_name, ok=ok, message=message)
    )
    notified = []
    monkeypatch.setattr(pg, "_notify", lambda text: notified.append(text))

    @pg.guarded("op_ret", ok_fn=lambda r: r["ok"])
    def fn():
        return {"ok": False, "reason": "x"}

    result = fn()
    assert result == {"ok": False, "reason": "x"}
    assert logged["ok"] is False
    assert notified


def test_guarded_decorator_ok_fn_true_no_record(monkeypatch):
    calls = []
    monkeypatch.setattr(pg, "log_op", lambda *a, **k: calls.append("log"))
    monkeypatch.setattr(pg, "_notify", lambda *a, **k: calls.append("notify"))

    @pg.guarded("op_ok", ok_fn=lambda r: r["ok"])
    def fn():
        return {"ok": True}

    fn()
    assert calls == []
