"""L6 — 네이버 메일 AI 초안 업무 흐름: 초안 생성(AI/사람) → 목록·조회 → **사람이 카드 버튼으로 보내기** → 결과 기록.

기준서: docs/specs/2026-10-02_mailbox_ai_window.md
- AI(에이전트)는 `create_draft`·조회만 호출할 수 있다(허용 API 목록이 코드로 고정). 보내기(`send_draft`)는 사람 전용이다.
- 보내기 직전에 첨부 파일을 다시 읽어 **승인 때 본 파일과 같은지(sha256)** 확인한다. 달라졌으면 보내지 않는다.
- 전송 요청이 나간 뒤 결과가 불확실하면 `unknown` 으로 멈추고 **자동 재시도하지 않는다**(중복 발송 방지).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from ai_orchestrator.paths import repo_root
from scripts.naver.mail.imap import attachments as att
from scripts.naver.mail.imap import html_sanitize as hs
from scripts.naver.mail.imap import imap_mailbox as mailbox
from scripts.naver.mail.imap import reader, sender

from ai_orchestrator.connectors.naver_mail import draft_policy as policy
from ai_orchestrator.connectors.naver_mail import draft_store as store
from ai_orchestrator.connectors.naver_mail.mailbox_flow import ServiceError, require_account

ROOT = repo_root()
COMPACT_TEXT_LIMIT = 12000
_DEFINITE_FAILURES = ("send_failed", "auth_failed", "connect_failed", "no_password")


# ── 읽기 보조 (AI 가 쓰는 가벼운 응답) ───────────────────────────────────


def compact_message(account: str, folder: str, uid: int) -> dict[str, Any]:
    """AI 용 메일 상세 — 본문은 텍스트만(최대 12,000자), HTML·내장 이미지는 뺀다. 열어도 읽음 표시는 바뀌지 않는다."""
    got = mailbox.get_message(require_account(account), folder, uid)
    if not got.get("ok"):
        return got
    text = got["text"] or hs.html_to_text(got["html"])
    return {
        "ok": True,
        "uid": got["uid"],
        "folder": got["folder"],
        "subject": got["subject"],
        "from": got["from"],
        "to": got["to"],
        "cc": got["cc"],
        "date": got["date"],
        "message_id": got["message_id"],
        "references": got["references"],
        "seen": got["seen"],
        "text": text[:COMPACT_TEXT_LIMIT],
        "truncated": len(text) > COMPACT_TEXT_LIMIT,
        "attachments": [{k: a[k] for k in ("index", "filename", "size", "content_type")} for a in got["attachments"]],
    }


def new_mail(account: str, limit: int = 20, advance: bool = False) -> dict[str, Any]:
    """기준점 이후 도착한 새 메일의 헤더(오래된 것부터). 처음 호출이면 기준점만 잡고 빈 목록을 돌려준다."""
    return reader.list_new(require_account(account), limit=limit, advance=advance)


# ── 첨부 ────────────────────────────────────────────────────────────────


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _path_attachment(raw: str) -> tuple[dict[str, Any], att.Upload]:
    try:
        real = policy.validate_attachment_path(raw, allowed_dirs=policy.allowed_attachment_dirs(), deny_roots=[ROOT])
    except policy.PathRejected as e:
        raise ServiceError(str(e)) from e
    data = real.read_bytes()
    name = att.safe_filename(real.name)
    meta = {"kind": "path", "path": str(real), "name": name, "size": len(data), "sha256": _sha256(data)}
    return meta, att.Upload(name, "", data)


def _forward_attachments(account: str, forward: dict[str, Any] | None) -> list[tuple[dict[str, Any], att.Upload]]:
    if not forward:
        return []
    folder, uid = str(forward.get("folder", "")), int(forward.get("uid", 0))
    out = []
    for index in forward.get("indices") or []:
        got = mailbox.get_attachment(account, folder, uid, int(index))
        if not got.get("ok"):
            raise ServiceError("원본 첨부를 가져오지 못했습니다: " + str(got.get("message", "")))
        meta = {
            "kind": "forward",
            "folder": folder,
            "uid": uid,
            "index": int(index),
            "name": got["filename"],
            "size": len(got["data"]),
            "sha256": _sha256(got["data"]),
        }
        out.append((meta, att.Upload(got["filename"], got["content_type"], got["data"])))
    return out


def _rebuild_uploads(account: str, metas: list[dict[str, Any]]) -> list[att.Upload]:
    """저장된 첨부 정보로 파일을 다시 읽고, 승인 때 본 내용과 같은지 확인한다."""
    uploads = []
    for meta in metas:
        if meta["kind"] == "path":
            _, upload = _path_attachment(meta["path"])
        else:
            got = mailbox.get_attachment(account, meta["folder"], meta["uid"], meta["index"])
            if not got.get("ok"):
                raise ServiceError("원본 첨부를 다시 가져오지 못했습니다: " + str(got.get("message", "")))
            upload = att.Upload(got["filename"], got["content_type"], got["data"])
        if _sha256(upload.data) != meta["sha256"]:
            raise ServiceError(f"첨부 '{meta['name']}' 이(가) 초안을 만든 뒤 바뀌었습니다. 새 초안을 만드세요")
        uploads.append(upload)
    return uploads


# ── 초안 ────────────────────────────────────────────────────────────────


def public_view(d: dict[str, Any]) -> dict[str, Any]:
    """화면·AI 에 돌려주는 초안 정보 — 첨부 실제 경로·해시는 빼고 이름·크기만."""
    return {
        "id": d["id"],
        "account": d["account"],
        "status": d["status"],
        "to": d["to"],
        "cc": d["cc"],
        "bcc": d["bcc"],
        "subject": d["subject"],
        "body_preview": d["body_text"][:2000],
        "rich": bool(d["body_html"]),
        "attachments": [{"name": a["name"], "size": a["size"], "kind": a["kind"]} for a in d["attachments"]],
        "in_reply_to": d["in_reply_to"],
        "created_by": d["created_by"],
        "created_at": d["created_at"],
        "expires_at": d["expires_at"],
        "sent_at": d["sent_at"],
        "approved_by": d["approved_by"],
        "result": d["result"],
    }


def create_draft(  # noqa: PLR0913 - 초안 한 통의 입력(받는 사람·참조·숨은참조·제목·본문·첨부·답장 정보)
    account: str,
    *,
    to: str | list[str],
    subject: str,
    body: str = "",
    html: str = "",
    cc: str | list[str] = "",
    bcc: str | list[str] = "",
    attachment_paths: list[str] | None = None,
    forward: dict[str, Any] | None = None,
    in_reply_to: str = "",
    references: str = "",
    created_by: str = "ai",
) -> dict[str, Any]:
    """검증을 마친 승인 대기 초안을 만든다. **전송하지 않는다.** 문제가 있으면 ServiceError(사유 문구)."""
    require_account(account)
    pairs = [_path_attachment(p) for p in attachment_paths or []] + _forward_attachments(account, forward)
    try:
        built = sender.make_draft(
            account,
            to,
            subject,
            body,
            cc=cc,
            bcc=bcc,
            uploads=[u for _, u in pairs],
            in_reply_to=in_reply_to,
            references=references,
            html=html,
        )
    except ValueError as e:
        raise ServiceError(str(e)) from e
    decision = policy.check_create(
        pending_count=store.count_pending(account),
        recipient_count=len(built.all_recipients),
        attachment_count=len(pairs),
    )
    if not decision.allowed:
        raise ServiceError(decision.reason)
    saved = store.create_draft(
        account,
        to=built.to,
        cc=built.cc,
        bcc=built.bcc,
        subject=built.subject,
        body_text=built.body,
        body_html=hs.sanitize_html(html)
        if html.strip()
        else "",  # 내장 이미지는 data: 로 둔다(보낼 때 다시 cid 로 바꿈)
        attachments=[m for m, _ in pairs],
        in_reply_to=built.in_reply_to,
        references=built.references,
        created_by=created_by if created_by in ("ai", "user") else "ai",
    )
    return public_view(saved)


def list_drafts(account: str, *, only_open: bool = True) -> list[dict[str, Any]]:
    require_account(account)
    store.expire_old()
    statuses = policy.OPEN_STATUSES if only_open else None
    return [public_view(d) for d in store.list_drafts(account, statuses)]


def get_draft(draft_id: str) -> dict[str, Any]:
    d = store.get_draft(draft_id)
    if d is None:
        raise ServiceError("초안을 찾을 수 없습니다")
    return public_view(d)


def cancel_draft(draft_id: str) -> dict[str, Any]:
    if not store.transition(draft_id, policy.CANCELLED, only_from=policy.OPEN_STATUSES):
        raise ServiceError("취소할 수 없는 초안입니다(이미 보냈거나 취소·만료됨)")
    return get_draft(draft_id)


def _stored_draft(d: dict[str, Any], account: str) -> sender.Draft:
    try:
        return sender.make_draft(
            account, d["to"], d["subject"], d["body_text"],
            cc=d["cc"], bcc=d["bcc"], uploads=_rebuild_uploads(account, d["attachments"]),
            in_reply_to=d["in_reply_to"], references=d["references"], html=d["body_html"],
        )  # fmt: skip
    except ValueError as e:
        raise ServiceError(str(e)) from e


def send_draft(draft_id: str, *, actor: str) -> dict[str, Any]:
    """**사람이 카드의 '승인하고 보내기'를 눌렀을 때만** 호출된다(AI 허용 API 에 없음).

    순서: 상태·한도 확인 → 첨부 재확인 → 원자적으로 `sending` 으로 전이(동시에 두 번 눌러도 한 번만) → 전송 → 결과 기록.
    """
    d = store.get_draft(draft_id)
    if d is None:
        raise ServiceError("초안을 찾을 수 없습니다")
    account = d["account"]
    decision = policy.check_send(status=d["status"], expired=store.is_expired(d), sent_today=store.sent_today(account))
    if not decision.allowed:
        raise ServiceError(decision.reason)
    built = _stored_draft(d, account)  # 파일이 바뀌었으면 여기서 막힌다(상태는 그대로 pending)
    approved_at = datetime.now(UTC).isoformat(timespec="seconds")
    if not store.transition(
        draft_id, policy.SENDING, only_from=policy.OPEN_STATUSES, approved_by=actor, approved_at=approved_at
    ):
        raise ServiceError("이미 전송 중이거나 처리된 초안입니다")
    try:
        result = sender.send_draft(built)
    except Exception as e:  # noqa: BLE001 - 어떤 예외든 '결과 불확실'로 멈춘다(재시도하면 중복 발송 위험)
        store.transition(
            draft_id,
            policy.UNKNOWN,
            only_from=(policy.SENDING,),
            result={"ok": False, "error": "exception", "message": type(e).__name__},
        )
        return get_draft(draft_id)
    if result.get("ok"):
        store.add_sent(account, 1)
        store.transition(
            draft_id,
            policy.SENT,
            only_from=(policy.SENDING,),
            sent_at=datetime.now(UTC).isoformat(timespec="seconds"),
            result=_safe_result(result),
        )
    elif result.get("error") in _DEFINITE_FAILURES:
        store.transition(draft_id, policy.FAILED, only_from=(policy.SENDING,), result=_safe_result(result))
    else:
        store.transition(draft_id, policy.UNKNOWN, only_from=(policy.SENDING,), result=_safe_result(result))
    return get_draft(draft_id)


def _safe_result(result: dict[str, Any]) -> dict[str, Any]:
    """결과에서 받는 사람 주소·본문은 빼고 건수·오류 종류만 남긴다."""
    return {
        "ok": bool(result.get("ok")),
        "error": result.get("error", ""),
        "message": result.get("message", ""),
        "recipient_count": len(result.get("recipients", [])),
        "refused_count": len(result.get("refused", [])),
    }


# ── 업무 지침 ───────────────────────────────────────────────────────────


def get_instructions(account: str) -> str:
    return store.get_instructions(require_account(account))


def set_instructions(account: str, text: str) -> str:
    cleaned = text.strip()
    if len(cleaned) > policy.INSTRUCTIONS_MAX_CHARS:
        raise ServiceError(f"업무 지침은 {policy.INSTRUCTIONS_MAX_CHARS}자 이하여야 합니다")
    store.set_instructions(require_account(account), cleaned)
    return cleaned


# 대량 발송 실행기가 쓰는 공개 이름(같은 L6) — 첨부 경로 안전 검사와 sha256 재확인을 그대로 재사용한다
path_attachment = _path_attachment
rebuild_uploads = _rebuild_uploads
