"""네이버 메일 발송(SMTP 465/SSL). 실제 전송은 호출부(예약 작업 `mail_send`)의 회차 승인 뒤에만 일어난다.

기준서: docs/specs/2026-10-01_naver_mail_imap_smtp.md 8절. 비밀번호는 기록·출력하지 않는다.
"""

from __future__ import annotations

import contextlib
import re
import smtplib
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Any

from scripts.naver.mail.imap import attachments as att
from scripts.naver.mail.imap import html_sanitize as hs
from scripts.naver.mail.imap.protocol import (
    AUTH_HINT,
    SMTP_HOST,
    SMTP_PORT,
    TIMEOUT_SEC,
    load_password,
    password_env_name,
)

MAX_RECIPIENTS = 10
# 서버가 응답 코드로 분명히 거부한 오류들(그 외 연결 끊김·시간 초과는 '결과 불확실')
_DEFINITE_REJECTIONS = (smtplib.SMTPResponseException, smtplib.SMTPRecipientsRefused)
MAX_RECIPIENTS_FULL = 20  # 받는 사람·참조·숨은참조 합계(메일함 화면)
MAX_SUBJECT = 200
MAX_BODY = 20000
_ADDR = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def parse_recipients(raw: str | list[str]) -> list[str]:
    """쉼표·세미콜론·줄바꿈으로 구분한 수신자를 검증해 목록으로. 잘못된 주소가 하나라도 있으면 ValueError."""
    pieces = re.split(r"[,;\n]", raw) if isinstance(raw, str) else raw
    items = [str(s).strip() for s in pieces if str(s).strip()]
    if not items or len(items) > MAX_RECIPIENTS:
        raise ValueError(f"수신자는 1~{MAX_RECIPIENTS}명이어야 합니다")
    bad = [a for a in items if not _ADDR.match(a)]
    if bad:
        raise ValueError(f"올바르지 않은 메일 주소: {bad}")
    return items


def validate_content(subject: str, body: str) -> tuple[str, str]:
    subject, body = subject.strip(), body.strip()
    if not subject or len(subject) > MAX_SUBJECT or "\n" in subject or "\r" in subject:
        raise ValueError(f"제목은 한 줄, 1~{MAX_SUBJECT}자여야 합니다")
    if not body or len(body) > MAX_BODY:
        raise ValueError(f"본문은 1~{MAX_BODY}자여야 합니다")
    return subject, body


def build_message(account: str, to: list[str], subject: str, body: str) -> EmailMessage:
    subject, body = validate_content(subject, body)
    msg = EmailMessage()
    msg["From"] = f"{account}@naver.com"
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


def send_mail(
    account: str,
    to: str | list[str],
    subject: str,
    body: str,
    *,
    password: str | None = None,
    factory: Callable[..., Any] = smtplib.SMTP_SSL,
) -> dict[str, Any]:
    """메일 1통을 보낸다. 결과에 비밀번호·본문은 넣지 않는다."""
    recipients = parse_recipients(to)
    msg = build_message(account, recipients, subject, body)
    pw = load_password(account) if password is None else password
    if not pw:
        return {"ok": False, "error": "no_password", "message": f".env 에 {password_env_name(account)} 가 없습니다"}
    try:
        socket.setdefaulttimeout(TIMEOUT_SEC)
        conn = factory(SMTP_HOST, SMTP_PORT)
    except Exception as e:  # noqa: BLE001 - 접속 실패를 결과로 돌려준다
        return {
            "ok": False,
            "error": "connect_failed",
            "message": f"SMTP 서버에 접속하지 못했습니다 ({type(e).__name__})",
        }
    try:
        try:
            conn.login(account, pw)
        except smtplib.SMTPAuthenticationError:
            return {"ok": False, "error": "auth_failed", "message": "SMTP 로그인이 거부되었습니다. " + AUTH_HINT}
        try:
            refused = conn.send_message(msg)
        except smtplib.SMTPException as e:
            return {"ok": False, "error": "send_failed", "message": f"전송에 실패했습니다 ({type(e).__name__})"}
        return {"ok": True, "recipients": recipients, "refused": sorted(refused)}
    finally:
        with contextlib.suppress(Exception):  # 종료 정리 실패는 결과에 영향 없음
            conn.quit()


# ── 메일함 화면용: 참조·숨은참조·첨부·답장 헤더 ─────────────────────────────


@dataclass(frozen=True)
class Draft:
    """보낼 메일 한 통(검증을 마친 값)."""

    account: str
    to: list[str]
    subject: str
    body: str
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    uploads: list[att.Upload] = field(default_factory=list)
    in_reply_to: str = ""
    references: str = ""
    html: str = ""  # 정제를 마친 HTML(본문 속 이미지는 cid 로 바뀐 상태). 비어 있으면 텍스트만 보낸다
    inline_images: list[hs.InlineImage] = field(default_factory=list)

    @property
    def all_recipients(self) -> list[str]:
        return [*self.to, *self.cc, *self.bcc]


def make_draft(  # noqa: PLR0913 - 메일 한 통을 이루는 필드(받는 사람·참조·숨은참조·제목·본문·첨부·답장 헤더)
    account: str,
    to: str | list[str],
    subject: str,
    body: str,
    *,
    cc: str | list[str] = "",
    bcc: str | list[str] = "",
    uploads: list[att.Upload] | None = None,
    in_reply_to: str = "",
    references: str = "",
    html: str = "",
) -> Draft:
    """입력을 검증해 Draft 로. 문제가 있으면 ValueError(사용자에게 보일 문구).

    `html` 이 있으면(서식 편집기) 서버가 다시 정제하고, `body` 가 비어 있으면 HTML 에서 텍스트 대체본을 만든다.
    """
    to_list = parse_recipients(to)
    cc_list = parse_recipients(cc) if _has_text(cc) else []
    bcc_list = parse_recipients(bcc) if _has_text(bcc) else []
    if len(to_list) + len(cc_list) + len(bcc_list) > MAX_RECIPIENTS_FULL:
        raise ValueError(f"받는 사람은 참조·숨은참조를 합쳐 {MAX_RECIPIENTS_FULL}명 이하여야 합니다")
    clean_html = ""
    images: list[hs.InlineImage] = []
    if html.strip():
        sanitized = hs.sanitize_html(html)
        clean_html, images = hs.split_inline_images(sanitized)
        body = body.strip() or hs.html_to_text(sanitized) or ("[이미지]" if images else "")
    clean_subject, clean_body = validate_content(subject, body)
    for header in (in_reply_to, references):
        if "\n" in header or "\r" in header:
            raise ValueError("답장 헤더에 줄바꿈이 있습니다")
    return Draft(
        account,
        to_list,
        clean_subject,
        clean_body,
        cc_list,
        bcc_list,
        att.validate_uploads(uploads or []),
        in_reply_to.strip(),
        references.strip(),
        clean_html,
        images,
    )


def _has_text(value: str | list[str]) -> bool:
    return bool(value if isinstance(value, list) else value.strip())


def build_full_message(d: Draft) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = f"{d.account}@naver.com"
    msg["To"] = ", ".join(d.to)
    if d.cc:
        msg["Cc"] = ", ".join(d.cc)
    if d.bcc:
        msg["Bcc"] = ", ".join(d.bcc)  # smtplib.send_message 가 전송 시 이 헤더를 지운다
    msg["Subject"] = d.subject
    if d.in_reply_to:
        msg["In-Reply-To"] = d.in_reply_to
    if d.references:
        msg["References"] = d.references
    msg.set_content(d.body)
    if d.html:
        msg.add_alternative(d.html, subtype="html")
        html_part = msg.get_payload(1)
        assert isinstance(html_part, EmailMessage)
        for img in d.inline_images:
            html_part.add_related(img.data, maintype="image", subtype=img.subtype, cid=f"<{img.cid}>")
    for u in d.uploads:
        main, sub = att.guess_type(u.filename, u.content_type)
        msg.add_attachment(u.data, maintype=main, subtype=sub, filename=u.filename)
    return msg


def send_draft(
    d: Draft,
    *,
    password: str | None = None,
    factory: Callable[..., Any] = smtplib.SMTP_SSL,
) -> dict[str, Any]:
    """Draft 를 보낸다. 결과에 본문·비밀번호는 넣지 않는다. 호출 전에 사용자 확인을 마쳐야 한다."""
    pw = load_password(d.account) if password is None else password
    if not pw:
        return {"ok": False, "error": "no_password", "message": f".env 에 {password_env_name(d.account)} 가 없습니다"}
    msg = build_full_message(d)
    try:
        socket.setdefaulttimeout(TIMEOUT_SEC)
        conn = factory(SMTP_HOST, SMTP_PORT)
    except Exception as e:  # noqa: BLE001 - 접속 실패를 결과로 돌려준다
        return {"ok": False, "error": "connect_failed", "message": f"SMTP 서버에 접속하지 못했습니다 ({type(e).__name__})"}
    try:
        try:
            conn.login(d.account, pw)
        except smtplib.SMTPAuthenticationError:
            return {"ok": False, "error": "auth_failed", "message": "SMTP 로그인이 거부되었습니다. " + AUTH_HINT}
        try:
            refused = conn.send_message(msg)
        except _DEFINITE_REJECTIONS as e:
            # 서버가 응답 코드로 거부한 경우 — 메일은 나가지 않았다(다시 시도해도 중복이 아니다)
            return {"ok": False, "error": "send_failed", "message": f"전송에 실패했습니다 ({type(e).__name__})"}
        except (smtplib.SMTPException, OSError) as e:
            # 연결이 끊기거나 시간이 초과된 경우 — 서버가 메일을 받았는지 알 수 없다. 자동 재시도 금지(중복 발송 방지)
            return {"ok": False, "error": "send_unknown", "message": f"전송 결과를 확인하지 못했습니다 ({type(e).__name__}). 보낸메일함을 확인하세요"}
        return {"ok": True, "recipients": d.all_recipients, "refused": sorted(refused), "attachments": [u.filename for u in d.uploads]}
    finally:
        with contextlib.suppress(Exception):  # 종료 정리 실패는 결과에 영향 없음
            conn.quit()
