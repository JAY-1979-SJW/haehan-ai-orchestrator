"""네이버 메일 수신(IMAP) — 목록·본문 읽기. 읽음 표시를 바꾸지 않는다(`BODY.PEEK`, 폴더는 읽기 전용으로 연다).

기준서: docs/specs/2026-10-01_naver_mail_imap_smtp.md 8절. 비밀번호는 이 모듈이 기록·출력하지 않는다.
"""

from __future__ import annotations

import contextlib
import email
import imaplib
import socket
from collections.abc import Callable
from email.header import decode_header, make_header
from email.message import Message
from typing import Any

from scripts.naver.mail_imap.protocol import (
    AUTH_HINT,
    IMAP_HOST,
    IMAP_PORT,
    TIMEOUT_SEC,
    _fail,
    load_password,
    password_env_name,
)

MAX_LIST = 50
BODY_LIMIT = 20000


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:  # noqa: BLE001 - 깨진 헤더는 원문 그대로 보여 준다
        return value


def _text_body(msg: Message) -> str:
    """text/plain 우선, 없으면 text/html 을 그대로(태그 포함) 돌려준다. 첨부는 제외."""
    html_part = ""
    for part in msg.walk():
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes):
            continue
        text = payload.decode(part.get_content_charset() or "utf-8", "replace")
        if part.get_content_type() == "text/plain":
            return text
        if part.get_content_type() == "text/html" and not html_part:
            html_part = text
    return html_part


def _attachments(msg: Message) -> list[dict[str, Any]]:
    out = []
    for part in msg.walk():
        if part.get_content_disposition() == "attachment":
            payload = part.get_payload(decode=True)
            out.append(
                {"filename": _decode(part.get_filename()), "size": len(payload) if isinstance(payload, bytes) else 0}
            )
    return out


def _quiet_logout(conn: Any) -> None:
    with contextlib.suppress(Exception):  # 종료 정리 실패는 결과에 영향 없음
        conn.logout()


def _open(account: str, password: str, factory: Callable[..., Any]) -> tuple[Any | None, dict[str, Any] | None]:
    """로그인하고 받은편지함을 읽기 전용으로 연다. (연결, None) 또는 (None, 실패 결과)."""
    if not password:
        return None, _fail("no_password", f".env 에 {password_env_name(account)} 가 없습니다")
    try:
        socket.setdefaulttimeout(TIMEOUT_SEC)
        conn = factory(IMAP_HOST, IMAP_PORT)
    except Exception as e:  # noqa: BLE001 - 접속 실패를 결과로 돌려준다
        return None, _fail("connect_failed", f"IMAP 서버에 접속하지 못했습니다 ({type(e).__name__})")
    try:
        conn.login(account, password)
        code, _ = conn.select("INBOX", readonly=True)
    except imaplib.IMAP4.error:
        _quiet_logout(conn)
        return None, _fail("auth_failed", "IMAP 로그인이 거부되었습니다. " + AUTH_HINT)
    if code != "OK":
        _quiet_logout(conn)
        return None, _fail("select_failed", "받은편지함을 열지 못했습니다")
    return conn, None


def _header_row(uid: str, raw: bytes) -> dict[str, Any]:
    msg = email.message_from_bytes(raw)
    return {
        "uid": uid,
        "from": _decode(msg.get("From")),
        "subject": _decode(msg.get("Subject")),
        "date": msg.get("Date", ""),
    }


def _fetched_bytes(parts: list[Any]) -> bytes:
    return next((p[1] for p in parts if isinstance(p, tuple)), b"")


def list_messages(
    account: str,
    *,
    unseen_only: bool = True,
    limit: int = 20,
    password: str | None = None,
    factory: Callable[..., Any] = imaplib.IMAP4_SSL,
) -> dict[str, Any]:
    """받은편지함의 최근 메일 헤더(보낸 사람·제목·날짜). 가장 최근 것부터 `limit`개(최대 50)."""
    limit = max(1, min(int(limit), MAX_LIST))
    conn, err = _open(account, load_password(account) if password is None else password, factory)
    if err:
        return err
    try:
        _, data = conn.uid("SEARCH", None, "UNSEEN" if unseen_only else "ALL")
        uids = (data[0] or b"").decode().split()
        rows = []
        for uid in uids[-limit:][::-1]:
            _, parts = conn.uid("FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            rows.append(_header_row(uid, _fetched_bytes(parts)))
        return {"ok": True, "total_matched": len(uids), "messages": rows}
    finally:
        _quiet_logout(conn)


def read_message(
    account: str,
    uid: str,
    *,
    password: str | None = None,
    factory: Callable[..., Any] = imaplib.IMAP4_SSL,
) -> dict[str, Any]:
    """메일 1통의 본문(최대 20,000자)과 첨부 목록(이름·크기만). 읽음 표시는 바뀌지 않는다."""
    if not str(uid).isdigit():
        return _fail("bad_uid", "uid 는 숫자여야 합니다")
    conn, err = _open(account, load_password(account) if password is None else password, factory)
    if err:
        return err
    try:
        _, parts = conn.uid("FETCH", str(uid), "(BODY.PEEK[])")
        raw = _fetched_bytes(parts)
        if not raw:
            return _fail("not_found", "해당 메일이 없습니다")
        msg = email.message_from_bytes(raw)
        body = _text_body(msg)
        return {
            "ok": True,
            **_header_row(str(uid), raw),
            "body": body[:BODY_LIMIT],
            "truncated": len(body) > BODY_LIMIT,
            "attachments": _attachments(msg),
        }
    finally:
        _quiet_logout(conn)


def describe(result: dict[str, Any]) -> str:
    """예약 작업 결과용 요약(본문은 넣지 않는다)."""
    if not result["ok"]:
        return str(result["message"])
    rows = result["messages"]
    head = f"조건에 맞는 메일 {result['total_matched']}통 중 최근 {len(rows)}통"
    return "\n".join([head] + [f"- {r['date']} | {r['from']} | {r['subject']}" for r in rows])
