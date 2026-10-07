"""dev_reg_audit_log: JSONL append-only 감사 로그 단위 테스트.

안전 필드 whitelist, 민감값 차단, tmp_path 격리를 검증한다.
외부 HTTP/DB/subprocess 없음.
"""

from __future__ import annotations

import importlib
import json

import pytest

from ai_orchestrator.dev_reg import dev_reg_audit_log as al


@pytest.fixture(autouse=True)
def _reload_module():
    importlib.reload(al)
    yield


# ── 기본 기록 ────────────────────────────────────────────────────


def test_append_run_creates_file(tmp_path):
    p = tmp_path / "audit.jsonl"
    al.append_run({"result": "PASS", "pending_count": 0}, path=p)
    assert p.exists()


def test_append_run_writes_valid_json(tmp_path):
    p = tmp_path / "audit.jsonl"
    al.append_run({"result": "PASS", "pending_count": 2}, path=p)
    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["result"] == "PASS"
    assert rec["pending_count"] == 2


def test_append_run_is_append_only(tmp_path):
    p = tmp_path / "audit.jsonl"
    al.append_run({"result": "PASS", "pending_count": 1}, path=p)
    al.append_run({"result": "FAIL", "recent_failed": 3}, path=p)
    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2
    assert json.loads(lines[0])["result"] == "PASS"
    assert json.loads(lines[1])["result"] == "FAIL"


# ── 안전 필드 whitelist ─────────────────────────────────────────


def test_safe_fields_whitelist_only(tmp_path):
    p = tmp_path / "audit.jsonl"
    record = {
        "result": "WARN",
        "pending_count": 1,
        "warning_codes": ["W001"],
        "injected_secret": "should-not-appear",
        "token": "raw-token-value",
        "api_key": "key-xyz",
    }
    al.append_run(record, path=p)
    stored = json.loads(p.read_text(encoding="utf-8").strip())
    assert "result" in stored
    assert "pending_count" in stored
    assert "warning_codes" in stored
    for bad in ("injected_secret", "token", "api_key"):
        assert bad not in stored, f"민감 필드 누출: {bad}"


def test_no_sensitive_raw_values_stored(tmp_path):
    p = tmp_path / "audit.jsonl"
    al.append_run(
        {
            "result": "PASS",
            "password": "supersecret",
            "cookie": "session_abc",
            "session": "tok_xyz",
            "access_token": "eyJhbGci",
        },
        path=p,
    )
    text = p.read_text(encoding="utf-8")
    for bad_val in ("supersecret", "session_abc", "tok_xyz", "eyJhbGci"):
        assert bad_val not in text, f"민감값 원문 저장: {bad_val}"


def test_all_allowed_fields_stored(tmp_path):
    p = tmp_path / "audit.jsonl"
    record = {
        "run_at": "2026-01-01T00:00:00+00:00",
        "result": "PASS",
        "pending_count": 0,
        "expired_pending_count": 0,
        "expiry_soon_count": 0,
        "recent_executed": 1,
        "recent_rejected": 0,
        "recent_failed": 0,
        "warning_count": 0,
        "warning_codes": [],
        "alert_sent": False,
        "alert_type": "NONE",
        "retry_candidate": False,
    }
    al.append_run(record, path=p)
    stored = json.loads(p.read_text(encoding="utf-8").strip())
    for field in record:
        assert field in stored, f"허용 필드 누락: {field}"


# ── 경로 격리 (운영 경로 미사용) ─────────────────────────────────


def test_custom_path_used(tmp_path, monkeypatch):
    custom = tmp_path / "custom_dir" / "run.jsonl"
    al.append_run({"result": "PASS"}, path=custom)
    assert custom.exists()


def test_default_path_not_touched_when_custom_given(tmp_path, monkeypatch):
    default = tmp_path / "not_used.jsonl"
    monkeypatch.setattr(al, "default_audit_log_path", lambda: default)
    custom = tmp_path / "custom.jsonl"
    al.append_run({"result": "PASS"}, path=custom)
    assert not default.exists(), "사용자 지정 경로가 있으면 기본 경로를 건드리지 않아야 함"


# ── OSError 내성 ─────────────────────────────────────────────────


def test_oserror_does_not_raise(tmp_path):
    bad_path = tmp_path / "nonexistent_dir" / "sub" / "audit.jsonl"
    # 중간 디렉터리가 없어도 mkdir(parents=True)로 생성해야 정상
    al.append_run({"result": "PASS"}, path=bad_path)
    assert bad_path.exists()


def test_readonly_dir_oserror_silenced(tmp_path):
    import stat

    ro_dir = tmp_path / "readonly"
    ro_dir.mkdir()
    ro_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)
    bad_path = ro_dir / "nested" / "audit.jsonl"
    try:
        al.append_run({"result": "PASS"}, path=bad_path)
    except Exception as exc:  # noqa: BLE001 - 테스트 코드 - append_run 호출이 OSError를 삼키지 않고 실제로 전파하는지 검증하는 테스트, 실패 시 pytest.fail로 명시적 실패 처리
        pytest.fail(f"OSError가 외부로 전파됨: {exc}")
    finally:
        ro_dir.chmod(stat.S_IRWXU)


# ── load_recent_runs ─────────────────────────────────────────────


def test_load_recent_runs_empty_path(tmp_path):
    p = tmp_path / "missing.jsonl"
    result = al.load_recent_runs(5, path=p)
    assert result == []


def test_load_recent_runs_returns_newest_first(tmp_path):
    p = tmp_path / "audit.jsonl"
    for i in range(5):
        al.append_run({"result": "PASS", "pending_count": i}, path=p)
    runs = al.load_recent_runs(3, path=p)
    assert len(runs) == 3
    assert runs[0]["pending_count"] == 4
    assert runs[1]["pending_count"] == 3
    assert runs[2]["pending_count"] == 2
