"""회원 승인 게이트 테스트 — 가입(대기) → 승인 전 차단 → 승인 → 로그인.

L11 Tests. user_db 의 승인 흐름과 정보 노출 방지(비번 오류 시 대기 안내 안 함)를 검증.
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import pytest

import ai_orchestrator.auth.user_db as udb


@pytest.fixture()
def tmp_db(monkeypatch):
    """실제 users.db 를 건드리지 않도록 임시 DB 경로로 교체."""
    path = Path(tempfile.gettempdir()) / f"test_users_{uuid.uuid4().hex}.db"
    monkeypatch.setattr(udb, "_DB_PATH", path)
    yield path
    path.unlink(missing_ok=True)


def test_signup_starts_pending(tmp_db):
    """가입 직후에는 enabled=0(승인 대기)."""
    user = udb.create_user("a@example.com", "홍길동", "password123")
    assert user["enabled"] == 0


def test_login_blocked_before_approval(tmp_db):
    """승인 전에는 자격이 맞아도 로그인 불가."""
    udb.create_user("a@example.com", "홍길동", "password123")
    assert udb.authenticate_user("a@example.com", "password123") is None


def test_pending_hint_only_when_password_correct(tmp_db):
    """비번이 맞고 대기 중일 때만 '승인 대기' 판정 → 비번 오류 시 이메일 노출 방지."""
    udb.create_user("a@example.com", "홍길동", "password123")
    assert udb.is_pending_login("a@example.com", "password123") is True
    assert udb.is_pending_login("a@example.com", "wrong-password") is False
    assert udb.is_pending_login("nobody@example.com", "password123") is False


def test_pending_list_and_approve(tmp_db):
    """대기 목록 → 승인 → 로그인 가능, 목록에서 사라짐."""
    user = udb.create_user("a@example.com", "홍길동", "password123")
    assert len(udb.list_pending_users()) == 1

    assert udb.approve_user(user["id"]) is True

    assert udb.authenticate_user("a@example.com", "password123") is not None
    assert len(udb.list_pending_users()) == 0


def test_approve_unknown_user_returns_false(tmp_db):
    """존재하지 않는 사용자 승인은 False."""
    assert udb.approve_user("nonexistent-id") is False
