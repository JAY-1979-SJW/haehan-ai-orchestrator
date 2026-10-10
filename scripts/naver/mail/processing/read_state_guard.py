"""읽음 상태 보존 가드.

모드:
  LIST_ONLY  — 본문 열람 금지. 목록 메타데이터만 수집. 메일 상태 변경 0.
  UNREAD_ONLY— LIST_ONLY 와 동일하지만 '안읽음' 필터 적용 후 수집.
  FULL_READ  — 우선순위 N건 본문 열람. 원래 안읽었던 메일은 본문 후 mark-as-unread 시도.

금지 동작 (전부 실패하면 caller 가 호출 자체를 못함):
  send/delete/move/spam/star/label_change/download.
본 모듈은 차단 API 만 제공 — 실제 enforce 는 caller (collector) 가 사용한다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from scripts.common.gate import check as gate_check

# 모드 상수
MODE_LIST_ONLY = "LIST_ONLY"
MODE_UNREAD_ONLY = "UNREAD_ONLY"
MODE_FULL_READ = "FULL_READ"
MODE_ALL = "ALL"

# 절대 호출 금지 동작 (collector 가 호출 시 RuntimeError)
ALLOWED_ACTIONS = frozenset(
    {
        "read",
        "list",
        "search",
        "open_body",
        "compose",
        "draft",
        "reply",
        "reply_all",
        "forward",
        "edit_draft",
    }
)

APPROVAL_GATED_ACTIONS: dict[str, str] = {
    "send": "naver_mail_send",
    "delete": "naver_mail_delete",
    "trash": "naver_mail_delete",
    "move": "naver_mail_move",
    "archive": "naver_mail_move",
    "spam": "naver_mail_move",
    "star": "naver_mail_move",
    "important": "naver_mail_move",
    "label": "naver_mail_move",
    "unlabel": "naver_mail_move",
}

FORBIDDEN_ACTIONS = frozenset(
    {
        "download_attachment",
        "open_attachment",
        "screenshot_body",
    }
)


class ForbiddenActionError(RuntimeError):
    pass


def assert_action_allowed(action: str, *, force: bool = False, **metadata: Any) -> None:
    if action in ALLOWED_ACTIONS:
        return
    gate_name = APPROVAL_GATED_ACTIONS.get(action)
    if gate_name:
        gate_check(gate_name, force=force, mail_action=action, **metadata)
        return
    if action in FORBIDDEN_ACTIONS:
        raise ForbiddenActionError(f"FORBIDDEN_ACTION_BLOCKED: {action!r} — 정책상 금지된 동작입니다.")


def assert_mode_valid(mode: str) -> None:
    if mode not in (MODE_LIST_ONLY, MODE_UNREAD_ONLY, MODE_FULL_READ, MODE_ALL):
        raise ValueError(f"UNKNOWN_MODE: {mode!r}")


def list_only_assert_no_body_eval(callable_log: list[str]) -> None:
    """LIST_ONLY 모드 검증 — caller 가 호출 로그를 넘기면 본문 열람 호출이 있는지 확인."""
    body_calls = [c for c in callable_log if "read_body" in c or "popup/read" in c or "Page.captureScreenshot" in c]
    if body_calls:
        raise ForbiddenActionError(f"LIST_ONLY_MODE_VIOLATED: body 열람 호출 {len(body_calls)}건: {body_calls[:3]}")


# ── FULL_READ 안읽음 복구 계획 ───────────────────────────────────────


@dataclass
class RestoreTarget:
    sn: str
    was_unread: bool
    restored: bool = False
    restore_error: str = ""


@dataclass
class FullReadPlan:
    targets: list[RestoreTarget] = field(default_factory=list)
    restore_attempted: int = 0
    restore_succeeded: int = 0
    restore_failed: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def all_restored(self) -> bool:
        # 원래 안읽었던 것 전부 복구됐는지
        need = [t for t in self.targets if t.was_unread]
        return all(t.restored for t in need) if need else True


def plan_full_read(items: list[Any], max_bodies: int = 3) -> FullReadPlan:
    """item.sn / item.is_unread 가 있는 dataclass-like 객체 리스트.

    상위 N건 (원래 호출자가 우선순위로 정렬해 전달) 만 본문 열람 대상.
    원래 안읽었던 메일만 복구 plan에 등록.
    """
    plan = FullReadPlan()
    for it in items[:max_bodies]:
        sn = getattr(it, "sn", "") or ""
        was_unread = bool(getattr(it, "is_unread", False))
        if sn:
            plan.targets.append(RestoreTarget(sn=sn, was_unread=was_unread))
    if max_bodies > 3:
        plan.notes.append("max_bodies>3_제한초과")
    return plan


def attempt_restore_unread(
    plan: FullReadPlan,
    mark_unread_fn: Callable[[str], bool],
) -> FullReadPlan:
    """plan 의 was_unread=True 인 sn 들에 대해 mark-as-unread 시도.

    mark_unread_fn: (sn) -> bool (성공/실패). caller 가 CDP 클릭 등 주입.
    """
    for t in plan.targets:
        if not t.was_unread:
            continue
        plan.restore_attempted += 1
        try:
            ok = bool(mark_unread_fn(t.sn))
            t.restored = ok
            if ok:
                plan.restore_succeeded += 1
            else:
                plan.restore_failed += 1
                t.restore_error = "mark_unread_returned_false"
        except Exception as exc:  # noqa: BLE001 - 읽음상태 복원 실패를 restore_failed=True로 명시 기록(fail-closed), 안읽음 카운트 조회 실패시 -1(무효값)로 반환해 성공으로 위장하지 않음
            plan.restore_failed += 1
            t.restored = False
            t.restore_error = str(exc)[:120]
    return plan


# ── 안읽은 건수 전/후 비교 ───────────────────────────────────────────


@dataclass
class UnreadCountSnapshot:
    before: int = -1
    after: int = -1
    delta: int = 0  # before - after (양수면 줄어든 것)
    preserved: bool = True  # FULL_READ 모드에서만 의미 있음


def snapshot_unread_count(get_count_fn: Callable[[], int]) -> int:
    try:
        return int(get_count_fn())
    except Exception:  # noqa: BLE001 - 읽음상태 복원 실패를 restore_failed=True로 명시 기록(fail-closed), 안읽음 카운트 조회 실패시 -1(무효값)로 반환해 성공으로 위장하지 않음
        return -1
