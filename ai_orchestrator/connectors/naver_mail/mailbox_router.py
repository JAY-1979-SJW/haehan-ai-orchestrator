"""네이버 메일함 라우터 (L8) — HTTP 처리만. 업무 흐름은 connectors/naver_mail/mailbox_flow.

기준서: docs/specs/2026-10-01_naver_mailbox_tab.md
  GET  /naver-mailbox/accounts                       — 고를 수 있는 계정
  GET  /naver-mailbox/folders?account=               — 목차(폴더 + 안 읽은 수)
  GET  /naver-mailbox/messages?account=&folder=&page=&filter=&q=&since=&before=
  GET  /naver-mailbox/message?account=&folder=&uid=  — 상세(열어도 읽음 표시 불변)
  GET  /naver-mailbox/attachment?account=&folder=&uid=&index=&inline=0|1
  POST /naver-mailbox/flags    {account, folder, uid|uids, seen}  — 읽음/안 읽음 표시(최대 100통)
  POST /naver-mailbox/trash    {account, folder, uid|uids}        — 휴지통으로 이동
  POST /naver-mailbox/move     {account, folder, uid|uids, dest}  — 다른 폴더로 이동
  POST /naver-mailbox/purge    {account, folder, uid|uids}        — 영구 삭제(휴지통·스팸에서만)
  POST /naver-mailbox/empty    {account, folder}                  — 휴지통/스팸 비우기
  POST /naver-mailbox/send/prepare   (multipart) — 검증 + 확인 토큰. 전송하지 않는다
  POST /naver-mailbox/send/confirm   {token}     — 확인 창에서 "전송"을 눌렀을 때만
  POST /naver-mailbox/send/cancel    {token}

  GET  /naver-mailbox/new?account=&limit=&advance=            — 새 메일(기준점 이후) 헤더          [AI 허용]
  GET  /naver-mailbox/message/compact?account=&folder=&uid=   — AI 용 가벼운 메일 상세(텍스트만)   [AI 허용]
  POST /naver-mailbox/drafts   {account,to,subject,…}          — **승인 대기 초안 만들기(전송 없음)** [AI 허용]
  GET  /naver-mailbox/drafts?account=&all=                     — 초안 목록                          [AI 허용]
  GET  /naver-mailbox/drafts/{id}                              — 초안 1개
  POST /naver-mailbox/drafts/{id}/send                         — **사람이 카드 버튼으로만** 보내기   [AI 허용 아님]
  POST /naver-mailbox/drafts/{id}/cancel                       — 초안 취소                          [AI 허용 아님]
  GET  /naver-mailbox/instructions?account=  ·  POST /naver-mailbox/instructions {account,text}  — 업무 지침

IMAP/SMTP 는 블로킹이라 엔드포인트를 `def` 로 둔다(FastAPI 가 스레드풀에서 실행).
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi import Path as PathParam
from pydantic import BaseModel

from ai_orchestrator.connectors.naver_mail import drafts_workflow as drafts
from ai_orchestrator.connectors.naver_mail import mailbox_flow as service
from tools.gates.auth import require_role

naver_mailbox_router = APIRouter(prefix="/naver-mailbox", tags=["naver-mailbox"])
_ADMIN = Depends(require_role("admin", "owner"))

_STATUS = {
    "bad_filter": 400,
    "bad_uid": 400,
    "same_folder": 400,
    "not_purgeable": 400,
    "already_in_trash": 400,
    "not_found": 404,
    "folder_not_found": 404,
    "too_large": 413,
    "no_password": 409,
    "auth_failed": 502,
    "connect_failed": 502,
}


def _ok(result: dict[str, Any]) -> dict[str, Any]:
    """어댑터 결과가 실패면 HTTP 오류로 바꾼다(비밀번호·본문은 결과에 없다)."""
    if result.get("ok"):
        return result
    raise HTTPException(
        status_code=_STATUS.get(result.get("error", ""), 400),
        detail=result.get("message", "요청을 처리하지 못했습니다"),
    )


def _bad(e: service.ServiceError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(e))


class MessageRef(BaseModel):
    """메일 지정 — 한 통은 `uid`, 여러 통은 `uids`(최대 100)."""

    account: str
    folder: str
    uid: int | None = None
    uids: list[int] | None = None

    def ids(self) -> list[int]:
        return list(self.uids) if self.uids else ([self.uid] if self.uid else [])


class FlagBody(MessageRef):
    seen: bool


class MoveBody(MessageRef):
    dest: str


class FolderRef(BaseModel):
    account: str
    folder: str


class TokenBody(BaseModel):
    token: str


@naver_mailbox_router.get("/accounts")
def list_accounts(_: dict = _ADMIN):
    return {"accounts": service.accounts()}


@naver_mailbox_router.get("/folders")
def list_folders(account: str, _: dict = _ADMIN):
    try:
        return _ok(service.folders(account))
    except service.ServiceError as e:
        raise _bad(e) from e


@naver_mailbox_router.get("/messages")
def list_messages(  # noqa: PLR0913 - 쿼리 파라미터가 곧 검색 조건
    account: str,
    folder: str = "INBOX",
    page: int = 1,
    per_page: int = service.PER_PAGE_DEFAULT,
    filter: str = "all",
    q: str = "",
    since: str | None = None,
    before: str | None = None,
    _: dict = _ADMIN,
):
    try:
        query = service.ListQuery(
            folder, page, per_page, filter, q, service.parse_date(since), service.parse_date(before)
        )
        return _ok(service.messages(account, query))
    except service.ServiceError as e:
        raise _bad(e) from e


@naver_mailbox_router.get("/message")
def get_message(account: str, folder: str, uid: int, _: dict = _ADMIN):
    try:
        return _ok(service.message(account, folder, uid))
    except service.ServiceError as e:
        raise _bad(e) from e


def _content_disposition(kind: str, filename: str) -> str:
    return f"{kind}; filename*=UTF-8''{urllib.parse.quote(filename, safe='')}"


@naver_mailbox_router.get("/attachment")
def get_attachment(account: str, folder: str, uid: int, index: int, inline: int = 0, _: dict = _ADMIN):
    try:
        got = _ok(service.attachment(account, folder, uid, index))
    except service.ServiceError as e:
        raise _bad(e) from e
    show_inline = bool(inline) and bool(got["previewable"])
    headers = {
        "Content-Disposition": _content_disposition("inline" if show_inline else "attachment", got["filename"]),
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox; default-src 'none'; img-src data:; style-src 'unsafe-inline'",
        "Cache-Control": "private, no-store",
    }
    media_type = got["content_type"] if show_inline else "application/octet-stream"
    return Response(content=got["data"], media_type=media_type, headers=headers)


@naver_mailbox_router.post("/flags")
def set_flags(body: FlagBody, _: dict = _ADMIN):
    try:
        return _ok(service.mark_seen(body.account, body.folder, body.ids(), body.seen))
    except service.ServiceError as e:
        raise _bad(e) from e


@naver_mailbox_router.post("/trash")
def move_to_trash(body: MessageRef, _: dict = _ADMIN):
    try:
        return _ok(service.trash(body.account, body.folder, body.ids()))
    except service.ServiceError as e:
        raise _bad(e) from e


@naver_mailbox_router.post("/move")
def move_messages(body: MoveBody, _: dict = _ADMIN):
    try:
        return _ok(service.move(body.account, body.folder, body.ids(), body.dest))
    except service.ServiceError as e:
        raise _bad(e) from e


@naver_mailbox_router.post("/purge")
def purge_messages(body: MessageRef, _: dict = _ADMIN):
    """영구 삭제 — 휴지통·스팸에서만. 화면이 확인 창을 거친 뒤에 호출한다."""
    try:
        return _ok(service.purge(body.account, body.folder, body.ids()))
    except service.ServiceError as e:
        raise _bad(e) from e


@naver_mailbox_router.post("/empty")
def empty_folder(body: FolderRef, _: dict = _ADMIN):
    try:
        return _ok(service.empty(body.account, body.folder))
    except service.ServiceError as e:
        raise _bad(e) from e


def _read_uploads(files: list[UploadFile]) -> list[service.Upload]:
    out = []
    for f in files:
        data = f.file.read(service.MAX_UPLOAD_FILE_BYTES + 1)  # 상한을 넘으면 거기서 멈추고 검증에서 거부
        out.append(service.Upload(f.filename or "", f.content_type or "", data))
    return out


@naver_mailbox_router.post("/send/prepare")
def prepare_send(  # noqa: PLR0913 - 쓰기 창의 입력 항목 그대로
    account: str = Form(...),
    to: str = Form(...),
    subject: str = Form(...),
    body: str = Form(""),  # 서식 편집기를 쓰면 비워 두어도 된다(서버가 HTML 에서 텍스트를 만든다)
    html: str = Form(""),
    cc: str = Form(""),
    bcc: str = Form(""),
    in_reply_to: str = Form(""),
    references: str = Form(""),
    forward: str = Form(""),  # JSON: {"folder": ..., "uid": ..., "indices": [0, 1]} — 원본 첨부 전달
    files: list[UploadFile] = File(default_factory=list),
    _: dict = _ADMIN,
):
    try:
        forward_ref = json.loads(forward) if forward else None
    except ValueError as e:
        raise HTTPException(status_code=400, detail="forward 형식이 올바르지 않습니다") from e
    try:
        return service.prepare_send(
            account,
            to=to,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
            uploads=_read_uploads(files),
            in_reply_to=in_reply_to,
            references=references,
            forward=forward_ref,
            html=html,
        )
    except service.ServiceError as e:
        raise _bad(e) from e


@naver_mailbox_router.post("/send/confirm")
def confirm_send(body: TokenBody, _: dict = _ADMIN):
    try:
        result = service.confirm_send(body.token)
    except service.ServiceError as e:
        raise _bad(e) from e
    return _ok(result)


@naver_mailbox_router.post("/send/cancel")
def cancel_send(body: TokenBody, _: dict = _ADMIN):
    return {"ok": True, "cancelled": service.cancel_send(body.token)}


# ── AI 업무 창: 새 메일·가벼운 상세·초안·업무 지침 ───────────────────────────

_DRAFT_ID = PathParam(..., pattern="^[0-9a-f]{32}$")


class DraftBody(BaseModel):
    account: str
    to: str | list[str]
    subject: str
    body: str = ""
    html: str = ""
    cc: str | list[str] = ""
    bcc: str | list[str] = ""
    attachment_paths: list[str] = []
    forward: dict | None = None  # {"folder", "uid", "indices": [0, 1]} — 원본 첨부 전달
    in_reply_to: str = ""
    references: str = ""
    source: str = "ai"  # 감사 기록용(ai | user)


class InstructionsBody(BaseModel):
    account: str
    text: str


@naver_mailbox_router.get("/new")
def new_mail(account: str, limit: int = 20, advance: bool = False, _: dict = _ADMIN):
    """기준점 이후 도착한 새 메일. `advance=true` 로 호출하면 이번에 본 마지막 메일까지 확인한 것으로 기준점을 옮긴다."""
    try:
        return _ok(drafts.new_mail(account, limit, advance))
    except service.ServiceError as e:
        raise _bad(e) from e


@naver_mailbox_router.get("/inbox-watch")
def inbox_watch(account: str, prev_uidnext: int | None = None, prev_uidvalidity: int | None = None, _: dict = _ADMIN):
    """화면의 새 메일 알림용 — 받은편지함 UIDNEXT·안 읽음 수만(AI 기준점·읽음 표시 불변)."""
    try:
        return _ok(service.inbox_watch(account, prev_uidnext, prev_uidvalidity))
    except service.ServiceError as e:
        raise _bad(e) from e


@naver_mailbox_router.get("/message/compact")
def get_message_compact(account: str, folder: str, uid: int, _: dict = _ADMIN):
    try:
        return _ok(drafts.compact_message(account, folder, uid))
    except service.ServiceError as e:
        raise _bad(e) from e


@naver_mailbox_router.post("/drafts")
def create_draft(body: DraftBody, _: dict = _ADMIN):
    """승인 대기 초안을 만든다. **전송하지 않는다.** 보내기는 사람이 `/drafts/{id}/send` 로만 한다."""
    try:
        return drafts.create_draft(
            body.account,
            to=body.to,
            subject=body.subject,
            body=body.body,
            html=body.html,
            cc=body.cc,
            bcc=body.bcc,
            attachment_paths=body.attachment_paths,
            forward=body.forward,
            in_reply_to=body.in_reply_to,
            references=body.references,
            created_by=body.source,
        )
    except service.ServiceError as e:
        raise _bad(e) from e


@naver_mailbox_router.get("/drafts")
def list_drafts(account: str, all: bool = False, _: dict = _ADMIN):
    try:
        return {"drafts": drafts.list_drafts(account, only_open=not all)}
    except service.ServiceError as e:
        raise _bad(e) from e


@naver_mailbox_router.get("/drafts/{draft_id}")
def get_draft(draft_id: str = _DRAFT_ID, _: dict = _ADMIN):
    try:
        return drafts.get_draft(draft_id)
    except service.ServiceError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@naver_mailbox_router.post("/drafts/{draft_id}/send")
def send_draft(draft_id: str = _DRAFT_ID, user: dict = _ADMIN):
    """사람이 카드의 '승인하고 보내기'를 눌렀을 때만 호출한다. AI 허용 목록에 없다."""
    try:
        return drafts.send_draft(draft_id, actor=str(user.get("actor", "owner")))
    except service.ServiceError as e:
        raise _bad(e) from e


@naver_mailbox_router.post("/drafts/{draft_id}/cancel")
def cancel_draft(draft_id: str = _DRAFT_ID, _: dict = _ADMIN):
    try:
        return drafts.cancel_draft(draft_id)
    except service.ServiceError as e:
        raise _bad(e) from e


@naver_mailbox_router.get("/instructions")
def get_instructions(account: str, _: dict = _ADMIN):
    try:
        return {"account": account, "text": drafts.get_instructions(account)}
    except service.ServiceError as e:
        raise _bad(e) from e


@naver_mailbox_router.post("/instructions")
def set_instructions(body: InstructionsBody, _: dict = _ADMIN):
    try:
        return {"account": body.account, "text": drafts.set_instructions(body.account, body.text)}
    except service.ServiceError as e:
        raise _bad(e) from e
