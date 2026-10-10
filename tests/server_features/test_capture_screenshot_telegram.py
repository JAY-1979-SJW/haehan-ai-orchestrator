"""capture_screenshot 텔레그램 승인 메시지 + 버튼 라벨 + 감사 로그 검증.

- build_capture_screenshot_approval_message 는 순수 함수 — 네트워크/외부 앱 호출 없음.
- callback_data 는 기존 "approve|task_id|token_id" / "reject|..." 포맷 유지 (하위호환).

필수 테스트:
  1. dry_run=True  메시지에 "사전 점검" 포함
  2. dry_run=False 메시지에 "실제 화면 캡처" 포함
  3. dry_run=False 메시지에 "1회" 포함
  4. dry_run=False 메시지에 "서버에는 이미지가 업로드되지 않" 안내 포함
  5. 메시지/버튼 어디에도 token 원문(여기선 token_id 그 자체)은 message.text 에 등장하지 않음
  6. device_token / secret / cookie / password 단어 미노출
  7. 전체 경로 / LOCAL_AGENT_SCREENSHOT_DIR / 이미지 파일명 미노출
  8. 버튼 라벨이 dry-run/실제 캡처로 구분
  9. callback_data 포맷은 기존 handle_telegram_update 파서와 호환 (하위호환)
 10. 감사 CAPTURE_SCREENSHOT_APPROVAL_REQUESTED 에 reason/note 축약이 기록됨
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / ".." / ".."))


from ai_orchestrator.notify.telegram_notifier import (
    build_capture_screenshot_approval_message,
    parse_callback_data,
)

# 더미 값 — token 원문 대체. 실제 ApprovalToken 과 무관한 UUID-style 식별자.
_TASK_ID = "lat-tg-0001"
_AGENT_ID = "la-tgtest000"
_TOKEN_ID = "11111111-2222-3333-4444-555555555555"  # noqa: S105 — 테스트용 UUID, 실제 비밀값 아님


def _text(msg: dict) -> str:
    return msg["text"]


def _buttons(msg: dict) -> list[dict]:
    return msg["reply_markup"]["inline_keyboard"][0]


# ── 1. dry_run=True: 사전 점검 표현 포함 ────────────────────────────────


def test_dry_run_message_contains_pre_check_label():
    msg = build_capture_screenshot_approval_message(
        _TASK_ID,
        _AGENT_ID,
        _TOKEN_ID,
        dry_run=True,
    )
    t = _text(msg)
    assert "사전 점검" in t
    assert "capture_screenshot" in t
    assert "HIGH" in t


# ── 2/3/4. dry_run=False: 실제 캡처 + 1회 + 서버 업로드 안내 ───────────


def test_real_capture_message_contains_real_capture_label():
    msg = build_capture_screenshot_approval_message(
        _TASK_ID,
        _AGENT_ID,
        _TOKEN_ID,
        dry_run=False,
    )
    t = _text(msg)
    assert "실제 화면 캡처" in t
    assert "HIGH" in t


def test_real_capture_message_contains_single_execution_phrase():
    msg = build_capture_screenshot_approval_message(
        _TASK_ID,
        _AGENT_ID,
        _TOKEN_ID,
        dry_run=False,
    )
    assert "1회" in _text(msg)


def test_real_capture_message_contains_upload_safety_notice():
    msg = build_capture_screenshot_approval_message(
        _TASK_ID,
        _AGENT_ID,
        _TOKEN_ID,
        dry_run=False,
    )
    t = _text(msg)
    # 공백/글자 조사 흔들림에 관계 없이 핵심 의미가 포함돼야 한다
    assert "서버에는 이미지가 업로드되지 않" in t


def test_dry_run_message_contains_pre_check_guidance():
    msg = build_capture_screenshot_approval_message(
        _TASK_ID,
        _AGENT_ID,
        _TOKEN_ID,
        dry_run=True,
    )
    assert "환경만 점검" in _text(msg)


# ── 5. 메시지 text 에 token 원문 미노출 ────────────────────────────────


def test_message_text_does_not_contain_token_id():
    msg = build_capture_screenshot_approval_message(
        _TASK_ID,
        _AGENT_ID,
        _TOKEN_ID,
        dry_run=True,
        requested_by="ops",
        role="admin",
    )
    # 본문(text) 에는 token_id 가 나타나지 않아야 한다. callback_data 에만 들어간다.
    assert _TOKEN_ID not in _text(msg)


# ── 6/7. 민감어 / 경로 / 파일명 미노출 ─────────────────────────────────

_FORBIDDEN_WORDS = [
    # 비밀/크리덴셜
    "device_token",
    "password",
    "passwd",
    "secret",
    "cookie",
    "client_secret",
    "api_key",
    "authorization",
    # 이미지/경로 흔적
    ".png",
    "screenshot_",
    "LOCAL_AGENT_SCREENSHOT_DIR",
    ".haehan_agent",
    # 자주 쓰이는 로컬 경로 prefix
    "C:\\",
    "C:/Users",
    "/home/",
]


@pytest.mark.parametrize("dry_run", [True, False])
def test_message_contains_no_forbidden_secrets_or_paths(dry_run):
    msg = build_capture_screenshot_approval_message(
        _TASK_ID,
        _AGENT_ID,
        _TOKEN_ID,
        dry_run=dry_run,
        requested_by="ops",
        role="admin",
        reason="check",
        note="operator memo",
    )
    t = _text(msg)
    for bad in _FORBIDDEN_WORDS:
        assert bad not in t, f"금지 문구 노출: {bad!r}"
    # 버튼 라벨에도 금지 문구 없음
    for btn in _buttons(msg):
        for bad in _FORBIDDEN_WORDS:
            assert bad not in btn["text"]


# ── 8. 버튼 라벨 구분 ──────────────────────────────────────────────────


def test_dry_run_button_label():
    msg = build_capture_screenshot_approval_message(
        _TASK_ID,
        _AGENT_ID,
        _TOKEN_ID,
        dry_run=True,
    )
    labels = [b["text"] for b in _buttons(msg)]
    assert "사전 점검 승인" in labels
    assert "거절" in labels
    # 실제 캡처 라벨이 섞이면 안 된다
    assert "1회 캡처 승인" not in labels


def test_real_capture_button_label():
    msg = build_capture_screenshot_approval_message(
        _TASK_ID,
        _AGENT_ID,
        _TOKEN_ID,
        dry_run=False,
    )
    labels = [b["text"] for b in _buttons(msg)]
    assert "1회 캡처 승인" in labels
    assert "거절" in labels
    assert "사전 점검 승인" not in labels


# ── 9. callback_data 하위호환 (기존 파서로 처리 가능) ──────────────────


def test_callback_data_compatible_with_legacy_parser():
    msg = build_capture_screenshot_approval_message(
        _TASK_ID,
        _AGENT_ID,
        _TOKEN_ID,
        dry_run=False,
    )
    btns = _buttons(msg)
    approve = next(b for b in btns if "승인" in b["text"])
    reject = next(b for b in btns if b["text"] == "거절")

    # 기존 "approve|task_id|token_id" / "reject|..." 파서로 정상 파싱되어야 한다
    parsed_a = parse_callback_data(approve["callback_data"])
    assert parsed_a == {"action": "approve", "task_id": _TASK_ID, "token_id": _TOKEN_ID}
    parsed_r = parse_callback_data(reject["callback_data"])
    assert parsed_r == {"action": "reject", "task_id": _TASK_ID, "token_id": _TOKEN_ID}


# ── 10. 메시지에 agent_id / task_id / 요청자 노출 (허용 필드) ──────────


def test_message_contains_required_context_fields():
    msg = build_capture_screenshot_approval_message(
        _TASK_ID,
        _AGENT_ID,
        _TOKEN_ID,
        dry_run=True,
        requested_by="ops1",
        role="owner",
        reason="monthly test",
        note="Q2 check",
    )
    t = _text(msg)
    assert _TASK_ID in t
    assert _AGENT_ID in t
    assert "ops1" in t
    assert "owner" in t
    # reason/note 축약본이 표시된다
    assert "monthly test" in t
    assert "Q2 check" in t


def test_message_truncates_long_reason():
    long_reason = "x" * 500
    msg = build_capture_screenshot_approval_message(
        _TASK_ID,
        _AGENT_ID,
        _TOKEN_ID,
        dry_run=True,
        reason=long_reason,
    )
    t = _text(msg)
    # reason 라인만 추출해 길이 확인 — 전체 500자가 통째로 박히면 안 됨.
    reason_line = next(ln for ln in t.splitlines() if ln.startswith("사유: "))
    # 축약 지시자 또는 길이 제한이 적용됨
    assert len(reason_line) <= 200
    assert "x" * 500 not in t


def test_message_strips_newlines_from_reason():
    injected = "line1\nline2\rline3"
    msg = build_capture_screenshot_approval_message(
        _TASK_ID,
        _AGENT_ID,
        _TOKEN_ID,
        dry_run=True,
        reason=injected,
    )
    t = _text(msg)
    # 한 줄로 합쳐져야 한다 (message 구조 깨짐 방지)
    assert "사유: line1 line2 line3" in t


# ── 11. 감사 로그 reason/note 축약 기록 ────────────────────────────────


@pytest.fixture
def admin_user():
    return {"actor": "admin_test", "role": "admin"}


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    # auth/local_agent_router 를 reload 하지 않는다: reload 하면 get_current_user 가 시험마다 새 객체가 되는데
    # 하위 라우터는 처음 import 된 옛 객체에 묶여 있어 dependency_overrides 가 두 번째 시험부터 안 먹혀
    # 파일 전체 실행 시 등록이 401 이 되고 KeyError: 'agent_id' 가 난다(단독 실행만 통과, 2026-10-04 확인).

    import ai_orchestrator.agent_hub.registry.common as _reg_common
    import ai_orchestrator.agent_hub.registry.facade as _reg
    import ai_orchestrator.audit.audit_logger as _al
    import tools.gates.approval as _ap

    monkeypatch.setattr(_al, "_LOG_PATH", tmp_path / "audit.jsonl")
    monkeypatch.setattr(_ap, "_STORE_PATH", tmp_path / "approval_tokens.jsonl")
    # 2026-09-29 영속화 추가 후 필수: 안 하면 _reg.clear()가 실제 개발 세션의
    # data/local_agent_registry_state.json(실제 등록된 로컬 에이전트 상태)을 테스트마다 지운다.
    monkeypatch.setattr(_reg_common, "_REGISTRY_STATE_PATH", tmp_path / "local_agent_registry_state.json")

    _reg.clear()
    _ap._store.clear()
    _ap.clear_rate_store()

    yield

    _reg.clear()
    _ap._store.clear()
    _ap.clear_rate_store()


def _make_test_client(user_override: dict):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from ai_orchestrator.agent_hub.router.root import local_agent_router
    from tools.gates.auth import get_current_user

    app = FastAPI()
    app.include_router(local_agent_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: user_override
    return TestClient(app, raise_server_exceptions=True)


def _register(client) -> tuple[str, str]:
    reg = client.post(
        "/api/v1/local-agents/register",
        json={
            "host": "tg-test",
            "os_name": "Windows 11",
            "version": "0.1.0",
        },
    ).json()
    return reg["agent_id"], reg["device_token"]


def test_audit_approval_requested_includes_reason_note(admin_user):
    import ai_orchestrator.audit.audit_logger as _al

    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)
    client.post(
        f"/api/v1/local-agents/{agent_id}/capture-screenshot",
        json={"dry_run": False, "reason": "incident-42", "note": "opsmemo"},
    )
    entries = _al.read_recent_logs(limit=200)
    evt = next(e for e in entries if e["event_type"] == "CAPTURE_SCREENSHOT_APPROVAL_REQUESTED")
    # note 안에 reason/note 축약본이 남아 있어야 한다
    assert "reason=incident-42" in evt["note"]
    assert "note=opsmemo" in evt["note"]
    # 금지 흔적은 여전히 없음
    assert ".png" not in evt["note"]
    assert "C:\\" not in evt["note"]
    assert ".haehan_agent" not in evt["note"]


def test_audit_does_not_leak_token_raw_in_event_fields(admin_user):
    import ai_orchestrator.audit.audit_logger as _al

    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    client.post(
        f"/api/v1/local-agents/{agent_id}/capture-screenshot",
        json={"dry_run": True, "reason": "r"},
    )
    raw = _al._LOG_PATH.read_text(encoding="utf-8")
    # device_token 원문이 감사 로그에 남으면 안 됨 (토큰 원문 금지)
    assert token not in raw


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
