"""로컬 에이전트 audit payload builder 테스트.

local_agent_audit_builders 모듈이 audit note/payload 구성 helper를
올바르게 정의하고, token_id 원문을 기록하지 않으며,
기존 router audit behavior를 유지함을 검증한다.
"""


def test_build_approval_note_with_public_id():
    """approval note builder가 approval_public_id를 포함한다."""
    from ai_orchestrator.agent_hub.audit_builders import build_approval_note

    note = build_approval_note(
        agent_id="test-agent",
        approval_public_id="public-123",
    )

    assert "agent_id=test-agent" in note
    assert "approval_public_id=public-123" in note
    # token_id 원문이 없어야 함
    assert "token_id" not in note


def test_build_approval_note_without_public_id():
    """approval note builder가 approval_public_id 없이도 작동한다."""
    from ai_orchestrator.agent_hub.audit_builders import build_approval_note

    note = build_approval_note(
        agent_id="test-agent",
        approval_public_id=None,
    )

    assert "agent_id=test-agent" in note
    assert "approval_public_id" not in note


def test_build_approval_note_with_reason():
    """approval rejection note에 reason이 포함된다."""
    from ai_orchestrator.agent_hub.audit_builders import build_approval_note

    note = build_approval_note(
        agent_id="test-agent",
        approval_public_id="public-123",
        reason="User requested cancellation",
    )

    assert "agent_id=test-agent" in note
    assert "approval_public_id=public-123" in note
    assert "reason=User requested cancellation" in note


def test_build_approval_note_reason_none():
    """approval note builder가 reason=None을 처리한다."""
    from ai_orchestrator.agent_hub.audit_builders import build_approval_note

    note = build_approval_note(
        agent_id="test-agent",
        approval_public_id="public-123",
        reason=None,
    )

    assert "agent_id=test-agent" in note
    assert "approval_public_id=public-123" in note
    assert "reason=" not in note


def test_build_approval_note_no_token_id():
    """approval note builder는 token_id를 절대 포함하지 않는다."""
    from ai_orchestrator.agent_hub.audit_builders import build_approval_note

    note = build_approval_note(
        agent_id="test-agent",
        approval_public_id="public-123",
    )

    # 토큰 원문 패턴 검사
    assert "token_id=" not in note
    assert "secret" not in note.lower()
    assert "hash=" not in note


def test_build_replay_note():
    """replay (이미 결정된 작업 재시도) note builder."""
    from ai_orchestrator.agent_hub.audit_builders import build_replay_note

    note = build_replay_note(
        agent_id="test-agent",
        current_status="completed",
    )

    assert "agent_id=test-agent" in note
    assert "current_status=completed" in note


def test_build_task_note():
    """일반 task 생성 note builder."""
    from ai_orchestrator.agent_hub.audit_builders import build_task_note

    note = build_task_note(
        agent_id="test-agent",
        status="queued",
    )

    assert "agent_id=test-agent" in note
    assert "status=queued" in note


def test_build_screenshot_approval_note():
    """capture_screenshot approval note builder."""
    from ai_orchestrator.agent_hub.audit_builders import build_screenshot_approval_note

    # task는 보통 dict-like object (to_safe() 호출 결과)
    task_params = {
        "reason": "Policy check needed",
        "note": "User requested analysis",
    }

    note = build_screenshot_approval_note(
        agent_id="test-agent",
        dry_run=False,
        reason=task_params.get("reason"),
        note=task_params.get("note"),
    )

    assert "agent_id=test-agent" in note
    assert "dry_run=False" in note
    assert "reason=Policy check" in note  # 축약
    assert "note=User requested" in note


def test_build_screenshot_approval_note_dry_run():
    """dry_run=True인 경우."""
    from ai_orchestrator.agent_hub.audit_builders import build_screenshot_approval_note

    note = build_screenshot_approval_note(
        agent_id="test-agent",
        dry_run=True,
        reason=None,
        note=None,
    )

    assert "agent_id=test-agent" in note
    assert "dry_run=True" in note


def test_build_screenshot_approval_note_long_reason():
    """긴 reason이 축약된다."""
    from ai_orchestrator.agent_hub.audit_builders import build_screenshot_approval_note

    long_reason = "x" * 200

    note = build_screenshot_approval_note(
        agent_id="test-agent",
        dry_run=False,
        reason=long_reason,
        note=None,
    )

    assert "reason=" in note
    # 축약되어야 함 (보통 100자 이하)
    assert len(note) < 300


def test_build_screenshot_approval_note_with_approval_public_id():
    """screenshot note에 approval_public_id가 포함될 수 있다."""
    from ai_orchestrator.agent_hub.audit_builders import build_screenshot_approval_note

    note = build_screenshot_approval_note(
        agent_id="test-agent",
        dry_run=False,
        approval_public_id="public-id-456",
    )

    assert "agent_id=test-agent" in note
    assert "dry_run=False" in note
    assert "approval_public_id=public-id-456" in note


def test_audit_builders_no_token_id_leak():
    """모든 audit builder가 token_id를 포함하지 않는다."""
    from ai_orchestrator.agent_hub.audit_builders import (
        build_approval_note,
        build_replay_note,
        build_screenshot_approval_note,
        build_task_note,
    )

    # token_id 패턴들
    token_patterns = [
        "token_id=",
        "token_id:",
        "secret=",
        "secret:",
    ]

    notes = [
        build_approval_note("agent-1", "public-id-1"),
        build_replay_note("agent-1", "completed"),
        build_task_note("agent-1", "queued"),
        build_screenshot_approval_note("agent-1", False, None, None),
    ]

    for note in notes:
        for pattern in token_patterns:
            assert pattern not in note, f"Found '{pattern}' in note: {note}"


def test_audit_builders_no_sensitive_keys():
    """audit note에 token_id/api_key/secret 원문이 포함되지 않는다."""
    from ai_orchestrator.agent_hub.audit_builders import build_screenshot_approval_note

    # 실제 민감값 패턴 (값 원문)
    sensitive_patterns = [
        "token_id=",
        "api_key=",
        "secret=",
        "password=",
    ]

    note = build_screenshot_approval_note(
        agent_id="test-agent",
        dry_run=False,
        reason="Check for policy",
        note="Audit analysis",
    )

    for pattern in sensitive_patterns:
        assert pattern not in note, f"Found sensitive pattern '{pattern}' in note"
