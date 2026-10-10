"""AI 채팅 대화기록 저장소(chat_sessions) + 빌더(_build_claude_command) 단위 테스트."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_orchestrator.tasks import chat_sessions as store
from core.agent_runtime.connection.actions import _build_claude_command


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    # 실제 data/chat_sessions.json 을 건드리지 않도록 경로를 임시 폴더로 바꾼다.
    monkeypatch.setattr(store, "_STORE_PATH", tmp_path / "chat_sessions.json")
    store._sessions.clear()
    yield
    store._sessions.clear()


def test_create_add_and_title_truncate():
    s = store.create_session(first_message="가" * 50, model="opus")
    assert s.title.endswith("…") and len(s.title) == 41
    assert s.model == "opus"
    out = store.add_message(s.chat_id, role="user", text="안녕")
    assert out is not None and len(out.messages) == 1


def test_invalid_role_and_unknown_chat_rejected():
    s = store.create_session()
    assert store.add_message(s.chat_id, role="system", text="x") is None
    assert store.add_message("chat-nope", role="user", text="x") is None


def test_message_length_capped():
    s = store.create_session()
    store.add_message(s.chat_id, role="user", text="a" * (store._MAX_MESSAGE_TEXT_LEN + 5000))
    assert len(s.messages[0].text) == store._MAX_MESSAGE_TEXT_LEN


def test_claude_session_id_saved_for_resume():
    s = store.create_session()
    store.add_message(s.chat_id, role="assistant", text="ok", claude_session_id="sess-1")
    assert store.get_session(s.chat_id).claude_session_id == "sess-1"


def test_persist_and_reload_roundtrip():
    s = store.create_session(first_message="영속화")
    store.add_message(s.chat_id, role="user", text="hi", task_id="t1")
    store._sessions.clear()
    store._load_from_disk()
    restored = store.get_session(s.chat_id)
    assert restored is not None
    assert restored.messages[0].task_id == "t1"


def test_delete_and_list_order():
    a = store.create_session(first_message="a")
    b = store.create_session(first_message="b")
    store.add_message(a.chat_id, role="user", text="newer")
    assert store.list_sessions()[0]["chat_id"] == a.chat_id
    assert store.delete_session(b.chat_id) is True
    assert store.delete_session(b.chat_id) is False


def test_session_cap_evicts_oldest(monkeypatch):
    monkeypatch.setattr(store, "_MAX_SESSIONS", 2)
    first = store.create_session(first_message="1")
    store.create_session(first_message="2")
    store.create_session(first_message="3")
    assert len(store._sessions) == 2
    assert store.get_session(first.chat_id) is None


def test_build_claude_command_model_resume_and_separator():
    cmd = _build_claude_command(
        root=Path("."),
        prompt="-x 프롬프트",
        max_budget_usd=1.0,
        model="sonnet",
        resume_session_id="sess-1",
        allowed_tools=["a", "b"],
    )
    assert cmd[cmd.index("--model") + 1] == "sonnet"
    assert cmd[cmd.index("--resume") + 1] == "sess-1"
    assert cmd[-2:] == ["--", "-x 프롬프트"]  # 옵션 파싱 차단 구분자 유지


def test_build_claude_command_omits_optional_flags():
    cmd = _build_claude_command(
        root=Path("."), prompt="p", max_budget_usd=1.0, model="", resume_session_id="", allowed_tools=[]
    )
    assert "--model" not in cmd and "--resume" not in cmd and "--allowedTools" not in cmd
