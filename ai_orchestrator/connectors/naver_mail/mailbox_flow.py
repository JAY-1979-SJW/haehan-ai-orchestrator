"""L6 — 네이버 메일함 화면의 업무 흐름(workflows: 같은 L6 의 scheduled_job_actions 처럼 scripts 어댑터를 쓴다): 계정 확인, 조회 위임, 보내기 2단계(준비 → 사용자 확인 → 전송).

기준서: docs/specs/2026-10-01_naver_mailbox_tab.md
- 보내기는 `prepare_send` 로 내용을 검증·보관한 뒤 확인 토큰을 돌려주고, 화면의 확인 창에서 사용자가 "전송"을 눌러야
  `confirm_send(token)` 이 실제로 보낸다. 토큰은 1회용이고 10분 뒤 사라진다(메모리 보관, 디스크 저장 없음).
- 이 API 로 AI 가 임의로 보내는 용도가 아니다(AI 경유 발송은 예약 작업 `naver_mail_send` 의 회차 승인만 사용).
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from datetime import date
from typing import Any

from ai_orchestrator.connectors.naver_mail import new_policy as mail_new_policy
from scripts.naver.blog.accounts import BLOG_ACCOUNTS
from scripts.naver.mail.imap import attachments as att
from scripts.naver.mail.imap import imap_mailbox as mailbox
from scripts.naver.mail.imap import sender
from scripts.naver.mail.imap.protocol import load_password

# 라우터가 어댑터를 직접 import 하지 않도록 필요한 이름을 다시 내보낸다
ListQuery = mailbox.ListQuery
Upload = att.Upload
PER_PAGE_DEFAULT = mailbox.PER_PAGE_DEFAULT
MAX_UPLOAD_FILE_BYTES = att.MAX_UPLOAD_FILE_BYTES

TOKEN_TTL_SEC = 600
MAX_PENDING = 10


class ServiceError(ValueError):
    """사용자에게 그대로 보일 수 있는 입력 오류."""


@dataclass
class _Pending:
    draft: sender.Draft
    expires_at: float


_pending: dict[str, _Pending] = {}
_lock = threading.Lock()


def accounts() -> list[dict[str, Any]]:
    """메일함에서 고를 수 있는 네이버 계정(앱 비밀번호가 설정된 계정만 ready)."""
    return [{"account": a, "ready": bool(load_password(a))} for a in sorted(BLOG_ACCOUNTS)]


def require_account(account: str) -> str:
    if account not in BLOG_ACCOUNTS:
        raise ServiceError(f"등록되지 않은 네이버 계정: {account}")
    return account


def folders(account: str) -> dict[str, Any]:
    return mailbox.list_folders(require_account(account))


def messages(account: str, q: mailbox.ListQuery) -> dict[str, Any]:
    return mailbox.list_messages(require_account(account), q)


def message(account: str, folder: str, uid: int) -> dict[str, Any]:
    return mailbox.get_message(require_account(account), folder, uid)


def attachment(account: str, folder: str, uid: int, index: int) -> dict[str, Any]:
    return mailbox.get_attachment(require_account(account), folder, uid, index)


def mark_seen(account: str, folder: str, uids: int | list[int], seen: bool) -> dict[str, Any]:
    return mailbox.set_seen(require_account(account), folder, uids, seen)


def trash(account: str, folder: str, uids: int | list[int]) -> dict[str, Any]:
    return mailbox.move_to_trash(require_account(account), folder, uids)


def move(account: str, folder: str, uids: int | list[int], dest: str) -> dict[str, Any]:
    return mailbox.move_messages(require_account(account), folder, uids, dest)


def purge(account: str, folder: str, uids: int | list[int]) -> dict[str, Any]:
    """영구 삭제(휴지통·스팸만). 화면에서 확인을 마친 뒤에만 호출한다."""
    return mailbox.purge(require_account(account), folder, uids)


def empty(account: str, folder: str) -> dict[str, Any]:
    return mailbox.empty_folder(require_account(account), folder)


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as e:
        raise ServiceError("날짜는 YYYY-MM-DD 형식이어야 합니다") from e


# ── 보내기 2단계 ────────────────────────────────────────────────────────


def _forwarded_uploads(account: str, forward: dict[str, Any] | None) -> list[att.Upload]:
    """전달할 때 원본 메일의 첨부를 서버가 직접 가져와 붙인다(화면으로 내려보냈다 다시 올리지 않는다)."""
    if not forward:
        return []
    folder, uid, indexes = str(forward.get("folder", "")), int(forward.get("uid", 0)), forward.get("indices") or []
    out = []
    for index in indexes:
        got = mailbox.get_attachment(account, folder, uid, int(index))
        if not got["ok"]:
            raise ServiceError("원본 첨부를 가져오지 못했습니다: " + str(got.get("message", "")))
        out.append(att.Upload(got["filename"], got["content_type"], got["data"]))
    return out


def prepare_send(  # noqa: PLR0913 - 화면 입력 그대로(받는 사람·참조·숨은참조·제목·본문·첨부·답장/전달 정보)
    account: str,
    *,
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
    uploads: list[att.Upload] | None = None,
    in_reply_to: str = "",
    references: str = "",
    forward: dict[str, Any] | None = None,
    html: str = "",
) -> dict[str, Any]:
    """내용을 검증하고 확인 토큰과 확인 창에 보여 줄 요약을 돌려준다. 이 단계에서는 아무것도 전송하지 않는다."""
    require_account(account)
    all_uploads = [*(uploads or []), *_forwarded_uploads(account, forward)]
    try:
        draft = sender.make_draft(
            account,
            to,
            subject,
            body,
            cc=cc,
            bcc=bcc,
            uploads=all_uploads,
            in_reply_to=in_reply_to,
            references=references,
            html=html,
        )
    except ValueError as e:
        raise ServiceError(str(e)) from e
    token = secrets.token_urlsafe(24)
    now = time.time()
    with _lock:
        for key in [k for k, v in _pending.items() if v.expires_at <= now]:
            del _pending[key]
        if len(_pending) >= MAX_PENDING:
            raise ServiceError("확인 대기 중인 메일이 너무 많습니다. 잠시 후 다시 시도하세요")
        _pending[token] = _Pending(draft, now + TOKEN_TTL_SEC)
    return {
        "token": token,
        "expires_in": TOKEN_TTL_SEC,
        "summary": {
            "from": f"{account}@naver.com",
            "to": draft.to,
            "cc": draft.cc,
            "bcc": draft.bcc,
            "subject": draft.subject,
            "body_preview": draft.body[:200],
            "rich": bool(draft.html),
            "inline_images": len(draft.inline_images),
            "attachments": [{"filename": u.filename, "size": len(u.data)} for u in draft.uploads],
        },
    }


def confirm_send(token: str) -> dict[str, Any]:
    """확인 창에서 사용자가 "전송"을 눌렀을 때만 호출된다. 토큰은 1회용."""
    with _lock:
        pending = _pending.pop(token, None)
    if pending is None or pending.expires_at <= time.time():
        raise ServiceError("확인 시간이 지났거나 이미 처리된 메일입니다. 다시 '보내기'를 눌러 주세요")
    return sender.send_draft(pending.draft)


def cancel_send(token: str) -> bool:
    with _lock:
        return _pending.pop(token, None) is not None


def inbox_watch(account: str, prev_uidnext: int | None = None, prev_uidvalidity: int | None = None) -> dict[str, Any]:
    """새 메일 알림용 받은편지함 상태 + 이전 확인값 대비 새 메일 수(읽기 전용, AI 기준점과 무관)."""
    cur = mailbox.inbox_status(require_account(account))
    if not cur.get("ok"):
        return cur
    prev = None if prev_uidnext is None or prev_uidvalidity is None else {"uidnext": prev_uidnext, "uidvalidity": prev_uidvalidity}
    verdict = mail_new_policy.new_since(prev, cur)
    return {**cur, "reset": verdict["reset"], "new_count": verdict["count"], "new_label": mail_new_policy.count_label(verdict["count"])}
