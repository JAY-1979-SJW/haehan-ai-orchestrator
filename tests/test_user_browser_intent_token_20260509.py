"""user_browser_intent_token 단위 테스트."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ai_orchestrator.local_agent.browser.intent_token import (
    INTENT_EXCEEDED,
    INTENT_EXPIRED,
    INTENT_OK,
    SCOPE_INTERACTION,
    add_origin,
    create_intent,
    expire_intent,
    increment_action,
    is_origin_allowed,
    list_active_intents,
    load_intent,
    save_intent,
    validate_intent,
)


def test_create_intent_basic():
    intent = create_intent(
        natural_language="한컴 개발자 센터 SDK 가격 확인",
        allowed_origins=("developer.hancom.com",),
    )
    assert intent.scope == SCOPE_INTERACTION
    assert intent.allowed_origins == ("developer.hancom.com",)
    assert intent.actions_used == 0
    assert intent.intent_id.startswith("intent_")


def test_create_intent_normalizes_url_to_host():
    intent = create_intent(
        natural_language="test",
        allowed_origins=("https://Developer.Hancom.com/notice",),
    )
    assert intent.allowed_origins == ("developer.hancom.com",)


def test_create_intent_empty_natural_language_rejected():
    with pytest.raises(ValueError):
        create_intent(natural_language="", allowed_origins=("a.com",))


def test_create_intent_invalid_scope_rejected():
    with pytest.raises(ValueError):
        create_intent(natural_language="x", allowed_origins=("a.com",), scope="invalid")


def test_create_intent_no_origins_rejected():
    with pytest.raises(ValueError):
        create_intent(natural_language="x", allowed_origins=())


def test_create_intent_max_actions_range():
    with pytest.raises(ValueError):
        create_intent(natural_language="x", allowed_origins=("a.com",), max_actions=0)
    with pytest.raises(ValueError):
        create_intent(natural_language="x", allowed_origins=("a.com",), max_actions=10000)


def test_create_intent_ttl_range():
    with pytest.raises(ValueError):
        create_intent(natural_language="x", allowed_origins=("a.com",), ttl_seconds=0)
    with pytest.raises(ValueError):
        create_intent(natural_language="x", allowed_origins=("a.com",), ttl_seconds=99999999)


def test_create_intent_rejects_password_in_natural_language():
    with pytest.raises(ValueError):
        create_intent(
            natural_language="login with password=secret",
            allowed_origins=("a.com",),
        )


def test_create_intent_rejects_rrn_keyword():
    with pytest.raises(ValueError):
        create_intent(
            natural_language="주민번호 등록 페이지로 가",
            allowed_origins=("a.com",),
        )


def test_validate_intent_ok():
    intent = create_intent(natural_language="x", allowed_origins=("a.com",))
    res = validate_intent(intent)
    assert res["ok"] is True
    assert res["code"] == INTENT_OK
    assert res["remaining_actions"] == 50


def test_validate_intent_expired():
    intent = create_intent(natural_language="x", allowed_origins=("a.com",))
    # 미래 시각으로 검증 → 만료
    future = datetime.now(UTC) + timedelta(hours=2)
    res = validate_intent(intent, now=future)
    assert res["ok"] is False
    assert res["code"] == INTENT_EXPIRED


def test_validate_intent_exceeded():
    intent = create_intent(natural_language="x", allowed_origins=("a.com",), max_actions=2)
    intent = increment_action(intent)
    intent = increment_action(intent)
    res = validate_intent(intent)
    assert res["ok"] is False
    assert res["code"] == INTENT_EXCEEDED


def test_is_origin_allowed_match():
    intent = create_intent(natural_language="x", allowed_origins=("developer.hancom.com",))
    assert is_origin_allowed(intent, "https://developer.hancom.com/docsmenu") is True


def test_is_origin_allowed_subdomain_not_match():
    # 서브도메인은 명시적으로 등록해야만 통과
    intent = create_intent(natural_language="x", allowed_origins=("developer.hancom.com",))
    assert is_origin_allowed(intent, "https://other.hancom.com/x") is False


def test_is_origin_allowed_different_site_blocked():
    intent = create_intent(natural_language="x", allowed_origins=("developer.hancom.com",))
    assert is_origin_allowed(intent, "https://google.com") is False


def test_is_origin_allowed_empty_url():
    intent = create_intent(natural_language="x", allowed_origins=("a.com",))
    assert is_origin_allowed(intent, "") is False


def test_increment_action_returns_new_token():
    intent = create_intent(natural_language="x", allowed_origins=("a.com",))
    new_intent = increment_action(intent)
    assert intent.actions_used == 0
    assert new_intent.actions_used == 1
    assert new_intent.intent_id == intent.intent_id


def test_add_origin():
    intent = create_intent(natural_language="x", allowed_origins=("a.com",))
    intent2 = add_origin(intent, "https://b.com/path")
    assert "b.com" in intent2.allowed_origins
    assert "a.com" in intent2.allowed_origins


def test_add_origin_duplicate_no_op():
    intent = create_intent(natural_language="x", allowed_origins=("a.com",))
    intent2 = add_origin(intent, "a.com")
    assert intent2.allowed_origins == ("a.com",)


def test_save_and_load_intent(tmp_path):
    intent = create_intent(natural_language="저장 테스트", allowed_origins=("a.com", "b.com"))
    save_intent(intent, intent_dir=tmp_path)
    loaded = load_intent(intent.intent_id, intent_dir=tmp_path)
    assert loaded is not None
    assert loaded.intent_id == intent.intent_id
    assert loaded.natural_language == "저장 테스트"
    assert loaded.allowed_origins == ("a.com", "b.com")


def test_load_intent_missing(tmp_path):
    assert load_intent("intent_nonexistent", intent_dir=tmp_path) is None


def test_expire_intent_moves_file(tmp_path):
    intent = create_intent(natural_language="x", allowed_origins=("a.com",))
    save_intent(intent, intent_dir=tmp_path)
    target = expire_intent(intent, intent_dir=tmp_path)
    assert target is not None
    assert target.parent.name == "expired"
    assert not (tmp_path / "active" / f"{intent.intent_id}.json").exists()


def test_list_active_intents(tmp_path):
    assert list_active_intents(intent_dir=tmp_path) == []
    a = create_intent(natural_language="a", allowed_origins=("a.com",))
    b = create_intent(natural_language="b", allowed_origins=("b.com",))
    save_intent(a, intent_dir=tmp_path)
    save_intent(b, intent_dir=tmp_path)
    active = list_active_intents(intent_dir=tmp_path)
    assert len(active) == 2
    assert a.intent_id in active
    assert b.intent_id in active


def test_intent_token_frozen():
    intent = create_intent(natural_language="x", allowed_origins=("a.com",))
    with pytest.raises(Exception):  # FrozenInstanceError
        intent.actions_used = 99


def test_natural_language_truncated_to_500():
    long_text = "가" * 1000
    intent = create_intent(natural_language=long_text, allowed_origins=("a.com",))
    assert len(intent.natural_language) == 500
