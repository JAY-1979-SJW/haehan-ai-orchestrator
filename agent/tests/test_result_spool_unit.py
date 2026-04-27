"""agent.result_spool — 단위 테스트.

api_client 는 stub 으로 대체해 네트워크 없이 enqueue / list / flush 경로와
idempotency-key 기반 중복 방지를 검증한다.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


# ──────────────────────────────────────────────────────────────────
# enqueue / list
# ──────────────────────────────────────────────────────────────────
def test_enqueue_creates_file_and_is_listed(tmp_path):
    from agent import result_spool as rs
    target = rs.enqueue_failed_result(
        tmp_path,
        {"id": "t-1", "idempotency_key": "KEY-A", "ok": False},
    )
    assert target.exists()
    files = rs.list_spooled_results(tmp_path)
    assert len(files) == 1
    assert files[0] == target
    body = json.loads(target.read_text(encoding="utf-8"))
    assert body["id"] == "t-1"


def test_enqueue_dedupes_on_idempotency_key(tmp_path):
    from agent import result_spool as rs
    a = rs.enqueue_failed_result(
        tmp_path, {"idempotency_key": "KEY-X", "ok": False, "data": {"n": 1}},
    )
    b = rs.enqueue_failed_result(
        tmp_path, {"idempotency_key": "KEY-X", "ok": False, "data": {"n": 2}},
    )
    assert a == b
    # 같은 파일이 유지되고 내용은 첫 enqueue 기준 (덮어쓰지 않음)
    body = json.loads(a.read_text(encoding="utf-8"))
    assert body["data"] == {"n": 1}
    assert len(rs.list_spooled_results(tmp_path)) == 1


def test_list_spooled_empty_when_no_dir(tmp_path):
    from agent import result_spool as rs
    assert rs.list_spooled_results(tmp_path / "missing") == []


def test_enqueue_handles_key_with_bad_chars(tmp_path):
    from agent import result_spool as rs
    p = rs.enqueue_failed_result(
        tmp_path, {"idempotency_key": "a/b\\c:d?", "ok": False},
    )
    assert p.exists()
    # 파일명이 안전하게 정규화됨
    assert "/" not in p.name and "\\" not in p.name
    assert ":" not in p.name and "?" not in p.name


# ──────────────────────────────────────────────────────────────────
# flush
# ──────────────────────────────────────────────────────────────────
def test_flush_sends_all_and_deletes_on_success(tmp_path, monkeypatch):
    from agent import result_spool as rs
    from agent import api_client

    sent: list[dict] = []

    def _ok(api_url, token, body):
        sent.append(body)
        return None

    monkeypatch.setattr(api_client, "report_result", _ok)

    rs.enqueue_failed_result(tmp_path, {"idempotency_key": "A", "id": "t1"})
    rs.enqueue_failed_result(tmp_path, {"idempotency_key": "B", "id": "t2"})

    n = rs.flush_spooled_results(tmp_path, "http://x", "tok")
    assert n == 2
    assert {s.get("id") for s in sent} == {"t1", "t2"}
    assert rs.list_spooled_results(tmp_path) == []


def test_flush_stops_on_api_failure_keeps_remainder(tmp_path, monkeypatch):
    from agent import result_spool as rs
    from agent import api_client

    calls = {"n": 0}

    def _fail(api_url, token, body):
        calls["n"] += 1
        return api_client.API_UNREACHABLE

    monkeypatch.setattr(api_client, "report_result", _fail)

    rs.enqueue_failed_result(tmp_path, {"idempotency_key": "A", "id": "t1"})
    rs.enqueue_failed_result(tmp_path, {"idempotency_key": "B", "id": "t2"})

    n = rs.flush_spooled_results(tmp_path, "http://x", "tok")
    assert n == 0
    # 첫 건에서 실패했으므로 단 1회만 호출
    assert calls["n"] == 1
    # 파일은 모두 유지
    assert len(rs.list_spooled_results(tmp_path)) == 2


def test_flush_discards_corrupt_files_and_continues(tmp_path, monkeypatch):
    from agent import result_spool as rs
    from agent import api_client

    # 손상 파일 하나 + 정상 파일 하나
    corrupt = tmp_path / ("CORRUPT" + rs._FILE_SUFFIX)
    corrupt.parent.mkdir(parents=True, exist_ok=True)
    corrupt.write_text("{invalid json", encoding="utf-8")
    rs.enqueue_failed_result(tmp_path, {"idempotency_key": "GOOD", "id": "t1"})

    sent: list[dict] = []
    monkeypatch.setattr(
        api_client, "report_result",
        lambda api_url, token, body: (sent.append(body), None)[1],
    )

    n = rs.flush_spooled_results(tmp_path, "http://x", "tok")
    assert n == 1
    assert [s.get("id") for s in sent] == ["t1"]
    # 손상 파일은 조용히 삭제, 정상 파일도 전송 후 삭제
    assert rs.list_spooled_results(tmp_path) == []
    assert not corrupt.exists()


def test_flush_empty_spool_returns_zero(tmp_path, monkeypatch):
    from agent import result_spool as rs
    from agent import api_client

    called = {"n": 0}
    monkeypatch.setattr(
        api_client, "report_result",
        lambda *a, **k: called.__setitem__("n", called["n"] + 1) or None,
    )
    n = rs.flush_spooled_results(tmp_path, "http://x", "tok")
    assert n == 0
    assert called["n"] == 0  # 큐가 비어 있으므로 서버 호출 없음


def test_flush_no_api_url_returns_zero(tmp_path, monkeypatch):
    from agent import result_spool as rs
    from agent import api_client
    called = {"n": 0}
    monkeypatch.setattr(
        api_client, "report_result",
        lambda *a, **k: called.__setitem__("n", called["n"] + 1) or None,
    )
    rs.enqueue_failed_result(tmp_path, {"idempotency_key": "A", "id": "t"})
    n = rs.flush_spooled_results(tmp_path, "", "tok")
    assert n == 0
    assert called["n"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
