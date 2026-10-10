"""
inbox 관련 최소 테스트
- 메일 1건 inbox 저장
- 동일 메일 중복 저장 방지
- 필수 필드 누락 방어
- source_type=email 저장 검증
- 앱 부팅 가능 여부
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import orchestrator_v1.inbox.inbox_store as inbox_store

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_inbox(tmp_path):
    return str(tmp_path / "inbox.jsonl")


_SAMPLE = {
    "external_id": "<test-001@hiworks.com>",
    "sender": "sender@example.com",
    "title": "테스트 메일 제목",
    "body_raw": "본문 내용입니다.",
    "received_at": "2026-04-22T10:00:00",
    "source_account": "user@company.com",
}


# ── 1. 메일 1건 inbox 저장 ────────────────────────────────────────────────────


def test_save_mail_single(tmp_inbox):
    result = inbox_store.save_mail(**_SAMPLE, path=tmp_inbox)

    assert result["status"] == "saved"
    assert result["external_id"] == _SAMPLE["external_id"]

    items = inbox_store.list_inbox(path=tmp_inbox)
    assert len(items) == 1
    item = items[0]
    assert item["source_type"] == "email"
    assert item["status"] == "new"
    assert item["linked_task_id"] is None
    assert item["external_id"] == _SAMPLE["external_id"]
    assert item["sender"] == _SAMPLE["sender"]
    assert item["title"] == _SAMPLE["title"]
    assert item["source_account"] == _SAMPLE["source_account"]
    assert "saved_at" in item


# ── 2. 동일 메일 중복 저장 방지 ───────────────────────────────────────────────


def test_duplicate_prevention(tmp_inbox):
    r1 = inbox_store.save_mail(**_SAMPLE, path=tmp_inbox)
    r2 = inbox_store.save_mail(**_SAMPLE, path=tmp_inbox)

    assert r1["status"] == "saved"
    assert r2["status"] == "skipped"
    assert r2["reason"] == "duplicate"

    items = inbox_store.list_inbox(path=tmp_inbox)
    assert len(items) == 1


def test_different_account_not_duplicate(tmp_inbox):
    """같은 external_id라도 source_account가 다르면 별개 항목."""
    inbox_store.save_mail(**_SAMPLE, path=tmp_inbox)

    other = {**_SAMPLE, "source_account": "other@company.com"}
    result = inbox_store.save_mail(**other, path=tmp_inbox)
    assert result["status"] == "saved"

    items = inbox_store.list_inbox(path=tmp_inbox)
    assert len(items) == 2


# ── 3. 필수 필드 누락 방어 ────────────────────────────────────────────────────


@pytest.mark.parametrize("missing_field", ["external_id", "source_account", "sender", "title"])
def test_required_field_missing(tmp_inbox, missing_field):
    kwargs = {**_SAMPLE}
    kwargs[missing_field] = ""
    with pytest.raises(ValueError):
        inbox_store.save_mail(**kwargs, path=tmp_inbox)


# ── 4. source_type=email 저장 검증 ────────────────────────────────────────────


def test_source_type_email(tmp_inbox):
    inbox_store.save_mail(**_SAMPLE, path=tmp_inbox)
    items = inbox_store.list_inbox(source_type="email", path=tmp_inbox)
    assert len(items) == 1
    assert items[0]["source_type"] == "email"


def test_source_type_filter(tmp_inbox):
    """source_type 필터가 다른 타입을 제외하는지 검증."""
    inbox_store.save_mail(**_SAMPLE, path=tmp_inbox)
    items = inbox_store.list_inbox(source_type="telegram", path=tmp_inbox)
    assert len(items) == 0


# ── 5. 앱 부팅 가능 여부 ──────────────────────────────────────────────────────


def test_app_boot(monkeypatch):
    """dashboard.create_app()이 예외 없이 Flask 앱을 반환하는지 확인."""
    monkeypatch.setenv("ORCH_DASHBOARD_USER", "test_user")
    monkeypatch.setenv("ORCH_DASHBOARD_PASSWORD", "test_pass")

    from orchestrator_v1.monitoring.dashboard import create_app

    app = create_app()
    assert app is not None

    # inbox blueprint가 등록되었는지 확인
    registered = [bp for bp in app.blueprints]
    assert "inbox" in registered


# ── 6. JSONL 파일 형식 검증 ───────────────────────────────────────────────────


def test_jsonl_format(tmp_inbox):
    """저장 파일이 유효한 JSONL인지 확인."""
    inbox_store.save_mail(**_SAMPLE, path=tmp_inbox)

    with Path(tmp_inbox).open("r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]

    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["source_type"] == "email"
    assert parsed["status"] == "new"
