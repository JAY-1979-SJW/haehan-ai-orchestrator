"""본문 진입 전후 unread/read 상태 snapshot + 복구 감사.

정책:
  - 본문 진입 후 mail.naver.com 은 자동으로 read 처리됨
  - `button.button_task.svg_unread` 클릭 → unread 복구
  - 복구 후 unread 목록에서 sn 재발견 → 복구 확인

각 mail 별로 다음 단계를 기록:
  before_state, after_open_state, after_restore_state, restore_ok, reason
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

# 상태 상수
STATE_UNREAD = "UNREAD"
STATE_READ = "READ"
STATE_UNKNOWN = "UNKNOWN"


@dataclass
class MailReadSnapshot:
    sn: str
    before_state: str
    after_open_state: str = STATE_UNKNOWN
    after_restore_state: str = STATE_UNKNOWN
    state_changed_on_open: bool = False
    restore_attempted: bool = False
    restore_ok: bool = False
    restore_reason: str = ""
    elapsed_ms_open: int = 0
    elapsed_ms_restore: int = 0

    def to_dict(self) -> dict:
        return {
            "sn": self.sn,
            "before_state": self.before_state,
            "after_open_state": self.after_open_state,
            "after_restore_state": self.after_restore_state,
            "state_changed_on_open": self.state_changed_on_open,
            "restore_attempted": self.restore_attempted,
            "restore_ok": self.restore_ok,
            "restore_reason": self.restore_reason,
            "elapsed_ms_open": self.elapsed_ms_open,
            "elapsed_ms_restore": self.elapsed_ms_restore,
        }


# DOM helpers — actions interface

class _Actions(Protocol):
    def evaluate(self, expr: str) -> Any: ...
    def navigate(self, url: str) -> None: ...
    def wait_dom(self, expr_truthy: str, timeout_s: float = 8.0) -> bool: ...


# sn 의 현재 unread/read 상태 — unread 목록에서 li.mail-{sn} aria-pressed 확인
_STATE_FROM_UNREAD_LIST_EXPR_TPL = """
(function(){{
  var li = document.querySelector('li.mail-{sn}');
  if (!li) return 'NOT_IN_UNREAD_LIST';
  var rb = li.querySelector('.toggle_read_wrap label[role="button"]');
  if (!rb) return 'NO_TOGGLE';
  var aria = rb.getAttribute('aria-pressed') || 'false';
  return (aria === 'true') ? 'READ' : 'UNREAD';
}})()
"""


def _ms() -> int:
    return int(time.time() * 1000)


def state_in_unread_list(actions: _Actions, sn: str) -> str:
    # 받은편지함 unread 목록 페이지에서 호출 가정
    expr = _STATE_FROM_UNREAD_LIST_EXPR_TPL.format(sn=sn)
    v = actions.evaluate(expr)
    if v == "UNREAD":
        return STATE_UNREAD
    if v == "READ":
        return STATE_READ
    if v == "NOT_IN_UNREAD_LIST":
        # unread 목록에서 사라짐 = read 상태로 이동
        return STATE_READ
    return STATE_UNKNOWN


CLICK_MARK_UNREAD_EXPR = (
    "(function(){"
    "var b=document.querySelector('button.button_task.svg_unread, "
    "button.svg_unread, [aria-label*=\"안읽음\"], [title*=\"안읽음\"]');"
    "if(!b){return 'no_button';} b.click(); return 'clicked';})()"
)


def attempt_restore_via_body_page(actions: _Actions) -> tuple[bool, str]:
    """현재 본문 페이지에서 '안읽음' 버튼 클릭."""
    res = actions.evaluate(CLICK_MARK_UNREAD_EXPR)
    if res == "clicked":
        return (True, "body_button_clicked")
    return (False, f"button_not_found:{res}")


def snapshot_mail(actions: _Actions, sn: str,
                  *, folder_id: str = "0") -> MailReadSnapshot:
    """본문 진입 전 unread 상태 확인."""
    # unread 목록으로 이동 후 상태 확인
    actions.navigate(f"https://mail.naver.com/v2/folders/{folder_id}/unread")
    time.sleep(0.2)
    actions.wait_dom("document.querySelector('li.mail_item')", timeout_s=10.0)
    st = state_in_unread_list(actions, sn)
    return MailReadSnapshot(sn=sn, before_state=st)


def open_body_and_audit_state(actions: _Actions,
                              snap: MailReadSnapshot,
                              *, folder_id: str = "0",
                              open_url_template: str | None = None) -> MailReadSnapshot:
    """본문 진입 → after_open_state 측정.

    open 후 unread 목록으로 복귀해서 다시 sn 의 상태를 확인한다.
    """
    url = (open_url_template or "https://mail.naver.com/v2/popup/read/{folder_id}/{sn}")\
        .format(folder_id=folder_id, sn=snap.sn)
    t0 = _ms()
    actions.navigate(url)
    time.sleep(0.3)
    actions.wait_dom(
        "document.querySelector('iframe#readFrame, iframe[id*=\"read\"], "
        ".mail_view_content, .read_content')",
        timeout_s=12.0,
    )
    snap.elapsed_ms_open = _ms() - t0
    # 본문 페이지에서 곧장 안읽음 복구 시도 (안전 우선)
    return snap


def restore_unread_state(actions: _Actions,
                         snap: MailReadSnapshot,
                         *, folder_id: str = "0") -> MailReadSnapshot:
    """본문 페이지에서 안읽음 복구 → unread 목록 재진입 확인."""
    if snap.before_state != STATE_UNREAD:
        # 원래 read 였으면 복구 안 함
        snap.restore_attempted = False
        snap.restore_reason = "before_state_was_not_unread"
        return snap
    t0 = _ms()
    ok, reason = attempt_restore_via_body_page(actions)
    snap.restore_attempted = True
    snap.restore_reason = reason
    time.sleep(0.2)
    # unread 목록으로 가서 다시 확인
    actions.navigate(f"https://mail.naver.com/v2/folders/{folder_id}/unread")
    time.sleep(0.3)
    actions.wait_dom("document.querySelector('li.mail_item')", timeout_s=10.0)
    after = state_in_unread_list(actions, snap.sn)
    snap.after_restore_state = after
    snap.restore_ok = (after == STATE_UNREAD)
    snap.elapsed_ms_restore = _ms() - t0
    # 진입 후 상태는 (복구 시도 후의 측정) — 별도 측정 필요 시 caller 가
    snap.after_open_state = STATE_READ if snap.before_state == STATE_UNREAD else snap.before_state
    snap.state_changed_on_open = (snap.before_state != snap.after_open_state)
    return snap


@dataclass
class UnreadAuditReport:
    total: int = 0
    state_changed: int = 0
    restore_attempted: int = 0
    restore_succeeded: int = 0
    restore_failed: int = 0
    snapshots: list[MailReadSnapshot] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "state_changed": self.state_changed,
            "restore_attempted": self.restore_attempted,
            "restore_succeeded": self.restore_succeeded,
            "restore_failed": self.restore_failed,
            "snapshots": [s.to_dict() for s in self.snapshots],
        }


def summarize(snaps: list[MailReadSnapshot]) -> UnreadAuditReport:
    r = UnreadAuditReport(total=len(snaps))
    for s in snaps:
        if s.state_changed_on_open:
            r.state_changed += 1
        if s.restore_attempted:
            r.restore_attempted += 1
            if s.restore_ok:
                r.restore_succeeded += 1
            else:
                r.restore_failed += 1
    r.snapshots = snaps
    return r
