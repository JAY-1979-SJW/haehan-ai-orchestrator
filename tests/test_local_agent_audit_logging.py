import json

from core.agent_runtime.common import audit, config


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_log_local_event_writes_primary_and_redacts_sensitive_fields(tmp_path, monkeypatch):
    primary = tmp_path / "audit.jsonl"
    monkeypatch.setattr(config, "LOCAL_AUDIT_PATH", primary)

    ok = audit.log_local_event(
        "unit_event",
        token="secret-token",
        nested={"password": "secret-password", "safe": "value"},
    )

    assert ok is True
    rows = _read_jsonl(primary)
    assert rows[0]["event_type"] == "unit_event"
    assert "token" not in rows[0]
    assert rows[0]["nested"] == {"safe": "value"}


def test_log_local_event_falls_back_when_primary_unwritable(tmp_path, monkeypatch):
    not_a_dir = tmp_path / "not_a_dir"
    not_a_dir.write_text("file", encoding="utf-8")
    fallback = tmp_path / "fallback" / "audit.jsonl"
    monkeypatch.setattr(config, "LOCAL_AUDIT_PATH", not_a_dir / "audit.jsonl")
    monkeypatch.setenv("HAEHAN_AGENT_AUDIT_FALLBACK", str(fallback))

    ok = audit.log_local_event("unit_event", safe="value", api_key="secret")

    assert ok is False
    rows = _read_jsonl(fallback)
    assert rows[0]["event_type"] == "local_audit_write_failed"
    assert rows[0]["original_event_type"] == "unit_event"
    assert rows[1]["event_type"] == "unit_event"
    assert rows[1]["audit_write_fallback"] is True
    assert rows[1]["safe"] == "value"
    assert "api_key" not in rows[1]
