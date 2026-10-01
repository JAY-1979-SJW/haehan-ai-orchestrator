"""네이버 메일 발송(SMTP 465/SSL). 실제 전송은 호출부(예약 작업 `mail_send`)의 회차 승인 뒤에만 일어난다.

기준서: docs/specs/2026-10-01_naver_mail_imap_smtp.md 8절. 비밀번호는 기록·출력하지 않는다.
"""

from __future__ import annotations

import contextlib
import re
import smtplib
import socket
from collections.abc import Callable
from email.message import EmailMessage
from typing import Any

from scripts.naver.mail_imap.protocol import (
    AUTH_HINT,
    SMTP_HOST,
    SMTP_PORT,
    TIMEOUT_SEC,
    load_password,
    password_env_name,
)

MAX_RECIPIENTS = 10
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
