"""AI 채팅(UniversalChat) 대화기록 영속화 — L7 Persistence.

사용자 지시 '이전 대화기록을 저장해서 볼수 있게 해줘' + '모델 선택 가능하게 해줘'로 신설.

local_agent_registry_common.py의 기존 패턴(스레드 락 보호 인메모리 dict + JSON 파일 스냅샷,
_save_agents_to_disk/_load_agents_from_disk)을 그대로 따른다 — 신규 sqlite DB를 만들지
않는다(이 저장소에 이미 스키마 버전관리 없는 sqlite DB가 25개 있다는 기존 지적,
docs/defect_index.json #14 — 더 늘리지 않기 위해 이 규모(개인 사용자 1명의 채팅 세션 목록)엔
단일 JSON 파일이면 충분).

세션의 claude_session_id는 core/agent_runtime/connection/actions.py::action_run_claude_agent 가 반환하는
session_id를 저장해뒀다가, 같은 세션의 다음 메시지에서 --resume 로 재사용한다(공식
--system-prompt-snapshot 문서 근거 — resume 시 시스템 프롬프트/CLAUDE.md 재렌더링을
건너뛰어 콜드 스타트 지연을 줄인다).
"""

from __future__ import annotations

import contextlib
import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ai_orchestrator.paths import repo_root
from ai_orchestrator.paths.runtime import data_dir

_ROOT = repo_root()
_STORE_PATH = data_dir() / "chat_sessions.json"
_MAX_MESSAGE_TEXT_LEN = 20000  # 저장 폭주 방지(단일 채팅 메시지 상한). 에이전트 결과 전문 상한(result_full 20000)과 같은 값
_MAX_SESSIONS = 500  # 오래된 세션 자동 정리 상한(개인 사용자 1명 기준 충분)

_lock = threading.Lock()
_sessions: dict[str, ChatSession] = {}


@dataclass
class ChatMessage:
    role: str  # "user" | "assistant"
    text: str
    created_at: str
    task_id: str = ""  # local_agent task_id 추적(선택, 디버깅용)


@dataclass
class ChatSession:
    chat_id: str
    title: str
    model: str = ""  # "" = CLI 기본값 사용
    claude_session_id: str = ""  # --resume 재사용용
    created_at: str = ""
    updated_at: str = ""
    messages: list[ChatMessage] = field(default_factory=list)

    def to_summary(self) -> dict:
        return {
            "chat_id": self.chat_id,
            "title": self.title,
            "model": self.model,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message_count": len(self.messages),
        }

    def to_detail(self) -> dict:
        return {
            **self.to_summary(),
            "messages": [
                {"role": m.role, "text": m.text, "created_at": m.created_at, "task_id": m.task_id}
                for m in self.messages
            ],
        }


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _save_to_disk() -> None:
    """호출자가 이미 _lock 을 쥔 상태여야 한다(내부 전용) — 스냅샷 후 락 밖에서 쓰기 원하면
    별도 헬퍼로 분리할 것(local_agent_registry_common.py의 교착 회피 패턴 참고).
    """
    payload = {
        cid: {
            "chat_id": s.chat_id,
            "title": s.title,
            "model": s.model,
            "claude_session_id": s.claude_session_id,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
            "messages": [
                {"role": m.role, "text": m.text, "created_at": m.created_at, "task_id": m.task_id} for m in s.messages
            ],
        }
        for cid, s in _sessions.items()
    }
    try:
        _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _STORE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_STORE_PATH)
    except OSError:
        pass  # 영속화 실패는 비치명적(다음 쓰기 때 재시도), 서버 동작 자체는 막지 않음


def _load_from_disk() -> None:
    if not _STORE_PATH.exists():
        return
    try:
        raw = json.loads(_STORE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    for cid, fields in raw.items():
        try:
            msgs = [
                ChatMessage(
                    role=m["role"],
                    text=m["text"],
                    created_at=m.get("created_at", ""),
                    task_id=m.get("task_id", ""),
                )
                for m in fields.get("messages", [])
            ]
            _sessions[cid] = ChatSession(
                chat_id=fields["chat_id"],
                title=fields.get("title", "새 대화"),
                model=fields.get("model", ""),
                claude_session_id=fields.get("claude_session_id", ""),
                created_at=fields.get("created_at", ""),
                updated_at=fields.get("updated_at", ""),
                messages=msgs,
            )
        except (KeyError, TypeError):
            continue


_load_from_disk()  # 모듈 임포트(서버 기동) 시 1회 복원


def _make_title(first_message: str) -> str:
    text = (first_message or "새 대화").strip().replace("\n", " ")
    return text[:40] + ("…" if len(text) > 40 else "")


def create_session(*, first_message: str = "", model: str = "") -> ChatSession:
    now = _now_iso()
    chat_id = f"chat-{uuid.uuid4().hex[:12]}"
    session = ChatSession(
        chat_id=chat_id,
        title=_make_title(first_message),
        model=model,
        created_at=now,
        updated_at=now,
    )
    with _lock:
        _sessions[chat_id] = session
        # 오래된 세션 자동 정리(상한 초과 시 updated_at 오래된 것부터)
        if len(_sessions) > _MAX_SESSIONS:
            oldest = sorted(_sessions.values(), key=lambda s: s.updated_at)[: len(_sessions) - _MAX_SESSIONS]
            for s in oldest:
                _sessions.pop(s.chat_id, None)
        _save_to_disk()
    return session


def get_session(chat_id: str) -> ChatSession | None:
    with _lock:
        return _sessions.get(chat_id)


def list_sessions() -> list[dict]:
    with _lock:
        items = sorted(_sessions.values(), key=lambda s: s.updated_at, reverse=True)
        return [s.to_summary() for s in items]


def add_message(
    chat_id: str,
    *,
    role: str,
    text: str,
    task_id: str = "",
    claude_session_id: str = "",
) -> ChatSession | None:
    """메시지 추가. claude_session_id가 주어지면(보통 assistant 메시지 완료 시) 같이 갱신해
    다음 메시지의 --resume 재사용에 쓴다(core/agent_runtime/connection/actions.py::action_run_claude_agent 참고).
    """
    if role not in ("user", "assistant"):
        return None
    with _lock:
        session = _sessions.get(chat_id)
        if session is None:
            return None
        now = _now_iso()
        session.messages.append(
            ChatMessage(role=role, text=str(text)[:_MAX_MESSAGE_TEXT_LEN], created_at=now, task_id=task_id)
        )
        session.updated_at = now
        if claude_session_id:
            session.claude_session_id = claude_session_id
        _save_to_disk()
        return session


def set_claude_session_id(chat_id: str, claude_session_id: str) -> None:
    if not claude_session_id:
        return
    with _lock:
        session = _sessions.get(chat_id)
        if session is None:
            return
        session.claude_session_id = claude_session_id
        _save_to_disk()


def delete_session(chat_id: str) -> bool:
    with _lock:
        existed = _sessions.pop(chat_id, None) is not None
        if existed:
            _save_to_disk()
        return existed


def clear() -> None:
    """테스트 전용: 메모리 + 디스크 초기화."""
    with _lock:
        _sessions.clear()
    with contextlib.suppress(OSError):
        _STORE_PATH.unlink(missing_ok=True)


__all__ = [
    "ChatMessage",
    "ChatSession",
    "add_message",
    "clear",
    "create_session",
    "delete_session",
    "get_session",
    "list_sessions",
    "set_claude_session_id",
]
