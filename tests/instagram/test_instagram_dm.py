"""Instagram 댓글->키워드->비공개DM 자동화 — rule engine, dedup, kill switch 최소 검증."""

from __future__ import annotations

import importlib
import sys

import pytest

from ai_orchestrator.connectors.instagram import instagram_dm_db as db
from ai_orchestrator.connectors.instagram import instagram_dm_rule_engine as rule_engine
from ai_orchestrator.connectors.instagram import instagram_dm_service as service


def test_token_store_uses_file_encryption_on_non_windows(tmp_path, monkeypatch):
    """서버(non-Windows) 배포 시 keyring 대신 Fernet 파일 저장으로 분기되는지 확인."""
    from cryptography.fernet import Fernet

    real_platform = sys.platform
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    ts = importlib.reload(importlib.import_module("ai_orchestrator.connectors.instagram.instagram_dm_token_store"))
    try:
        assert ts._USE_KEYRING is False
        monkeypatch.setattr(ts, "_STORE_PATH", tmp_path / "tokens.enc.json")

        ts.save_token("ig999", "secret-token-value")
        assert ts.load_token("ig999") == "secret-token-value"

        ts.delete_token("ig999")
        assert ts.load_token("ig999") is None
    finally:
        sys.platform = real_platform  # 재로드 전 원래 플랫폼으로 복원(win32 분기 회복)
        importlib.reload(ts)


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "instagram_dm_test.db")
    db.init_db()
    return db


def _make_account(tmp_db, automation_enabled=True):
    acc_id = tmp_db.upsert_account(
        instagram_user_id="ig123",
        username="tester",
        account_type="BUSINESS",
        encrypted_access_token="keyring-ref",  # noqa: S106 — 참조 마커, 실제 토큰 아님
    )
    tmp_db.set_account_automation_enabled(acc_id, automation_enabled)
    return acc_id


# ---- keyword normalization / matching ----


def test_normalize_text_collapses_whitespace_and_case():
    assert rule_engine.normalize_text("  PDF 자료   주세요 ") == "pdf 자료 주세요"


def test_positive_keyword_match():
    rules = [
        {
            "id": "r1",
            "enabled": True,
            "priority": 100,
            "scope_type": "ALL_MEDIA",
            "media_id": None,
            "keywords": ["자료"],
            "exclusion_keywords": [],
            "created_at": "1",
        }
    ]
    result = rule_engine.evaluate(
        account_automation_enabled=True, comment_text="자료 좀 받을 수 있나요?", media_id=None, rules=rules
    )
    assert result.matched
    assert result.matched_keyword == "자료"


def test_exclusion_keyword_blocks_match():
    rules = [
        {
            "id": "r1",
            "enabled": True,
            "priority": 100,
            "scope_type": "ALL_MEDIA",
            "media_id": None,
            "keywords": ["자료"],
            "exclusion_keywords": ["광고"],
            "created_at": "1",
        }
    ]
    result = rule_engine.evaluate(
        account_automation_enabled=True, comment_text="자료 광고하지 마세요", media_id=None, rules=rules
    )
    assert not result.matched


def test_specific_media_takes_priority_over_all_media():
    rules = [
        {
            "id": "all",
            "enabled": True,
            "priority": 1,
            "scope_type": "ALL_MEDIA",
            "media_id": None,
            "keywords": ["자료"],
            "exclusion_keywords": [],
            "created_at": "1",
            "reply_message": "ALL",
        },
        {
            "id": "specific",
            "enabled": True,
            "priority": 100,
            "scope_type": "SPECIFIC_MEDIA",
            "media_id": "m1",
            "keywords": ["자료"],
            "exclusion_keywords": [],
            "created_at": "2",
            "reply_message": "SPECIFIC",
        },
    ]
    result = rule_engine.evaluate(
        account_automation_enabled=True, comment_text="자료 주세요", media_id="m1", rules=rules
    )
    assert result.matched
    assert result.rule["id"] == "specific"


def test_account_disabled_short_circuits():
    rules = [
        {
            "id": "r1",
            "enabled": True,
            "priority": 100,
            "scope_type": "ALL_MEDIA",
            "media_id": None,
            "keywords": ["자료"],
            "exclusion_keywords": [],
            "created_at": "1",
        }
    ]
    result = rule_engine.evaluate(
        account_automation_enabled=False, comment_text="자료 주세요", media_id=None, rules=rules
    )
    assert not result.matched
    assert result.reason == "ACCOUNT_DISABLED"


def test_render_template_substitutes_known_vars_only():
    out = rule_engine.render_template(
        "{{username}}님, '{{keyword}}' 감사합니다 {{unknown}}", username="dasan", keyword="자료"
    )
    assert out == "dasan님, '자료' 감사합니다 {{unknown}}"


# ---- DB dedup ----


def test_comment_event_dedup(tmp_db):
    acc_id = _make_account(tmp_db)
    eid1, is_new1 = tmp_db.insert_comment_event_if_new(
        instagram_account_id=acc_id,
        comment_id="c1",
        media_id="m1",
        media_product_type="REEL",
        commenter_ig_scoped_id="u1",
        commenter_username="user1",
        comment_text="자료 주세요",
        normalized_text="자료 주세요",
        comment_created_at=None,
        raw_payload={},
    )
    eid2, is_new2 = tmp_db.insert_comment_event_if_new(
        instagram_account_id=acc_id,
        comment_id="c1",
        media_id="m1",
        media_product_type="REEL",
        commenter_ig_scoped_id="u1",
        commenter_username="user1",
        comment_text="자료 주세요",
        normalized_text="자료 주세요",
        comment_created_at=None,
        raw_payload={},
    )
    assert is_new1 is True
    assert is_new2 is False
    assert eid1 == eid2


def test_reply_slot_reserved_once(tmp_db):
    acc_id = _make_account(tmp_db)
    eid, _ = tmp_db.insert_comment_event_if_new(
        instagram_account_id=acc_id,
        comment_id="c1",
        media_id=None,
        media_product_type=None,
        commenter_ig_scoped_id="u1",
        commenter_username="user1",
        comment_text="자료",
        normalized_text="자료",
        comment_created_at=None,
        raw_payload={},
    )
    rid1, reserved1 = tmp_db.try_reserve_reply_slot(
        instagram_account_id=acc_id,
        comment_event_id=eid,
        comment_id="c1",
        rule_id=None,
        request_message="hi",
    )
    rid2, reserved2 = tmp_db.try_reserve_reply_slot(
        instagram_account_id=acc_id,
        comment_event_id=eid,
        comment_id="c1",
        rule_id=None,
        request_message="hi",
    )
    assert reserved1 is True
    assert reserved2 is False
    assert rid1 == rid2


# ---- kill switch (GLOBAL) ----


def test_global_kill_switch_blocks_send(tmp_db, monkeypatch):
    monkeypatch.delenv("INSTAGRAM_DM_ENABLED", raising=False)  # 기본값 false
    monkeypatch.setenv("INSTAGRAM_DM_DRY_RUN", "true")
    acc_id = _make_account(tmp_db, automation_enabled=True)
    tmp_db.create_rule(
        instagram_account_id=acc_id,
        name="test",
        scope_type="ALL_MEDIA",
        media_id=None,
        reply_message="안녕 {{username}}",
        keywords=["자료"],
    )
    eid, _ = tmp_db.insert_comment_event_if_new(
        instagram_account_id=acc_id,
        comment_id="c1",
        media_id=None,
        media_product_type=None,
        commenter_ig_scoped_id="u1",
        commenter_username="user1",
        comment_text="자료 주세요",
        normalized_text="자료 주세요",
        comment_created_at=None,
        raw_payload={},
    )
    service.process_comment_event(eid, instagram_account_id=acc_id)
    logs = tmp_db.list_reply_logs(acc_id)
    assert len(logs) == 1
    assert logs[0]["status"] == "BLOCKED"
    assert logs[0]["blocked_reason"] == "GLOBAL_DISABLED"


def test_dry_run_records_without_calling_api(tmp_db, monkeypatch):
    monkeypatch.setenv("INSTAGRAM_DM_ENABLED", "true")
    monkeypatch.setenv("INSTAGRAM_DM_DRY_RUN", "true")
    acc_id = _make_account(tmp_db, automation_enabled=True)
    tmp_db.create_rule(
        instagram_account_id=acc_id,
        name="test",
        scope_type="ALL_MEDIA",
        media_id=None,
        reply_message="안녕 {{username}}",
        keywords=["자료"],
    )
    eid, _ = tmp_db.insert_comment_event_if_new(
        instagram_account_id=acc_id,
        comment_id="c1",
        media_id=None,
        media_product_type=None,
        commenter_ig_scoped_id="u1",
        commenter_username="user1",
        comment_text="자료 주세요",
        normalized_text="자료 주세요",
        comment_created_at=None,
        raw_payload={},
    )
    service.process_comment_event(eid, instagram_account_id=acc_id)
    logs = tmp_db.list_reply_logs(acc_id)
    assert logs[0]["status"] == "DRY_RUN"
