"""로컬 에이전트 audit log payload builder (Phase 2-1).

audit 이벤트의 note/payload 구성 로직을 centralize하여
반복을 제거하고 token redaction 정책을 일관되게 적용한다.

원칙:
  - 순수 함수: 실제 log_event 호출 없음, side effect 없음
  - 민감값 제거: token_id 원문 절대 미포함, password/secret/cookie 미포함
  - public_id 중심: approval_public_id 만 기록 (token_id는 서버 내부용)
"""


def build_approval_note(
    agent_id: str,
    approval_public_id: str | None = None,
    reason: str | None = None,
) -> str:
    """approval/rejection audit note 구성.

    token_id 원문 절대 미포함.
    approval_public_id는 UUID 형식의 public 식별자 (secret 아님).
    """
    parts = [f"agent_id={agent_id}"]

    if reason:
        parts.append(f"reason={reason}")

    if approval_public_id:
        parts.append(f"approval_public_id={approval_public_id}")

    return " ".join(parts)


def build_replay_note(
    agent_id: str,
    current_status: str,
) -> str:
    """이미 결정된 작업 재시도 (replay) audit note.

    승인된 task를 다시 승인하거나 거절하려는 시도 추적.
    """
    return f"agent_id={agent_id} current_status={current_status}"


def build_task_note(
    agent_id: str,
    status: str,
) -> str:
    """task 생성/queued 시 기본 audit note."""
    return f"agent_id={agent_id} status={status}"


def build_screenshot_approval_note(
    agent_id: str,
    dry_run: bool,
    reason: str | None = None,
    note: str | None = None,
    approval_public_id: str | None = None,
) -> str:
    """capture_screenshot approval 요청/승인/거절 시 상세 audit note.

    dry_run 상태, reason, note, approval_public_id 정보를 축약하여 포함.
    token_id 원문/파일명/경로는 절대 미포함.
    """
    parts = [f"agent_id={agent_id}", f"dry_run={dry_run}"]

    if reason:
        # 축약 (보통 100자 이내)
        shortened = str(reason)[:100]
        parts.append(f"reason={shortened}")

    if note:
        # 축약 (보통 100자 이내)
        shortened = str(note)[:100]
        parts.append(f"note={shortened}")

    if approval_public_id:
        parts.append(f"approval_public_id={approval_public_id}")

    return " ".join(parts)
