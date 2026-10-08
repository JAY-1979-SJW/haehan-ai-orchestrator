"""네이버 메일 수신(IMAP) — 목록·본문 읽기. 읽음 표시를 바꾸지 않는다(`BODY.PEEK`, 폴더는 읽기 전용으로 연다).

기준서: docs/specs/2026-10-01_naver_mail_imap_smtp.md 8절. 비밀번호는 이 모듈이 기록·출력하지 않는다.
"""

from __future__ import annotations

import contextlib
import email
import imaplib
import json
import socket
from collections.abc import Callable
from datetime import date
from email.header import decode_header, make_header
from email.message import Message
from pathlib import Path
from typing import Any

from scripts.naver.mail.imap.protocol import (
    AUTH_HINT,
    IMAP_HOST,
    IMAP_PORT,
    TIMEOUT_SEC,
    _fail,
    load_password,
    password_env_name,
)

MAX_LIST = 50
MAX_SCAN = 500  # 한 번의 조회에서 헤더를 훑는 최대 통수(키워드 걸러내기 포함)
MAX_READ_MANY = 20
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
CHECKPOINT_NAME = "checkpoint.json"
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
    assert conn is not None
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
    assert conn is not None
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


def _imap_date(d: date) -> str:
    return f"{d.day:02d}-{_MONTHS[d.month - 1]}-{d.year}"  # 로케일과 무관하게 IMAP 형식(01-Oct-2026)


def _search_criteria(since: date | None, before: date | None, unseen_only: bool) -> list[str]:
    criteria = []
    if unseen_only:
        criteria.append("UNSEEN")
    if since:
        criteria.append(f"SINCE {_imap_date(since)}")
    if before:
        criteria.append(f"BEFORE {_imap_date(before)}")
    return criteria or ["ALL"]


def list_existing(  # noqa: PLR0913 - 검색 조건이 전부 키워드 전용 선택 인자(날짜·읽음·보낸 사람·제목·이어보기·개수)
    account: str,
    *,
    since: date | None = None,
    before: date | None = None,
    unseen_only: bool = False,
    from_contains: str = "",
    subject_contains: str = "",
    before_uid: int | None = None,
    limit: int = 50,
    password: str | None = None,
    factory: Callable[..., Any] = imaplib.IMAP4_SSL,
) -> dict[str, Any]:
    """이미 쌓여 있는 메일을 조건으로 좁혀 최신순 헤더 목록으로. 읽음 표시는 바뀌지 않는다.

    - `since`(포함)·`before`(미포함) 날짜, `unseen_only`는 서버가 거르고, 보낸 사람·제목 키워드는 한글 때문에 헤더를 받은 뒤 걸러낸다.
    - 한 번에 최대 `MAX_SCAN`통을 훑는다. 더 있으면 `next_before_uid` 를 `before_uid` 로 넘겨 이어서 본다.
    """
    limit = max(1, min(int(limit), MAX_LIST))
    conn, err = _open(account, load_password(account) if password is None else password, factory)
    if err:
        return err
    assert conn is not None
    needle_from, needle_subject = from_contains.strip().lower(), subject_contains.strip().lower()
    try:
        _, data = conn.uid("SEARCH", None, *_search_criteria(since, before, unseen_only))
        uids = [int(u) for u in (data[0] or b"").decode().split()]
        if before_uid is not None:
            uids = [u for u in uids if u < int(before_uid)]
        candidates = uids[::-1]  # 최신(번호가 큰 것)부터
        rows, scanned = [], 0
        for uid in candidates[:MAX_SCAN]:
            scanned += 1
            _, parts = conn.uid("FETCH", str(uid), "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            row = _header_row(str(uid), _fetched_bytes(parts))
            if needle_from and needle_from not in row["from"].lower():
                continue
            if needle_subject and needle_subject not in row["subject"].lower():
                continue
            rows.append(row)
            if len(rows) >= limit:
                break
        more = scanned < len(candidates)
        return {
            "ok": True,
            "matched_in_scan": len(rows),
            "scanned": scanned,
            "total_candidates": len(candidates),
            "next_before_uid": candidates[scanned - 1] if more else None,
            "messages": rows,
        }
    finally:
        _quiet_logout(conn)


def read_messages(
    account: str,
    uids: list[str],
    *,
    password: str | None = None,
    factory: Callable[..., Any] = imaplib.IMAP4_SSL,
) -> dict[str, Any]:
    """고른 메일 여러 통(최대 20)의 본문을 연결 1번으로 읽는다. 개별 실패는 그 메일 항목에만 표시한다."""
    picked = [str(u) for u in uids][:MAX_READ_MANY]
    if not picked or not all(u.isdigit() for u in picked):
        return _fail("bad_uid", "uid 는 숫자 1~20개여야 합니다")
    conn, err = _open(account, load_password(account) if password is None else password, factory)
    if err:
        return err
    assert conn is not None
    try:
        out = []
        for uid in picked:
            _, parts = conn.uid("FETCH", uid, "(BODY.PEEK[])")
            raw = _fetched_bytes(parts)
            if not raw:
                out.append({"ok": False, "uid": uid, "error": "not_found"})
                continue
            msg = email.message_from_bytes(raw)
            body = _text_body(msg)
            out.append(
                {
                    "ok": True,
                    **_header_row(uid, raw),
                    "body": body[:BODY_LIMIT],
                    "truncated": len(body) > BODY_LIMIT,
                    "attachments": _attachments(msg),
                }
            )
        return {"ok": True, "messages": out}
    finally:
        _quiet_logout(conn)


def _checkpoint_path() -> Path:
    from scripts.common.data_paths import get_app_dir

    return get_app_dir("mail", "naver_imap") / CHECKPOINT_NAME


def _load_checkpoint(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def commit_checkpoint(account: str, last_uid: int, uidvalidity: int, *, path: Path | None = None) -> None:
    """`last_uid` 까지 확인했다고 기록한다(이후 `list_new` 는 그보다 큰 번호만 새 메일로 본다)."""
    target = path or _checkpoint_path()
    state = _load_checkpoint(target)
    state[account] = {"uidvalidity": int(uidvalidity), "last_uid": int(last_uid)}
    target.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def _uidvalidity(conn: Any) -> int:
    _, data = conn.response("UIDVALIDITY")
    return int(data[0]) if data and data[0] else 0


def list_new(
    account: str,
    *,
    limit: int = 20,
    advance: bool = False,
    password: str | None = None,
    factory: Callable[..., Any] = imaplib.IMAP4_SSL,
    checkpoint_path: Path | None = None,
) -> dict[str, Any]:
    """기준점 이후에 도착한 **새 메일**의 헤더만(오래된 것부터). 쌓여 있던 메일은 대상이 아니다.

    - 처음 호출(기준점 없음) 또는 서버 UID 체계가 바뀐 경우(UIDVALIDITY 변경, 또는 기준점이 현재 최대 번호보다 큰 경우): 현재 가장 큰 번호를 기준점으로 저장하고 빈 목록을 돌려준다.
    - `advance=False`(기본): 기준점을 옮기지 않아 같은 새 메일이 다시 보인다. 확인을 마친 뒤 `commit_checkpoint` 또는 `advance=True`.
    """
    limit = max(1, min(int(limit), MAX_LIST))
    path = checkpoint_path or _checkpoint_path()
    conn, err = _open(account, load_password(account) if password is None else password, factory)
    if err:
        return err
    assert conn is not None
    try:
        validity = _uidvalidity(conn)
        _, data = conn.uid("SEARCH", None, "ALL")
        all_uids = [int(u) for u in (data[0] or b"").decode().split()]
        newest = max(all_uids, default=0)
        saved = _load_checkpoint(path).get(account)
        if not saved or saved.get("uidvalidity") != validity or int(saved["last_uid"]) > newest:  # 번호가 줄었으면 서버가 UID 를 새로 매긴 것
            commit_checkpoint(account, newest, validity, path=path)
            return {"ok": True, "baseline_set": True, "uidvalidity": validity, "last_uid": newest, "total_new": 0, "messages": []}
        fresh = [u for u in all_uids if u > int(saved["last_uid"])]
        rows = []
        for uid in fresh[:limit]:
            _, parts = conn.uid("FETCH", str(uid), "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            rows.append(_header_row(str(uid), _fetched_bytes(parts)))
        last_seen = int(rows[-1]["uid"]) if rows else int(saved["last_uid"])
        if advance and rows:
            commit_checkpoint(account, last_seen, validity, path=path)
        return {
            "ok": True,
            "baseline_set": False,
            "uidvalidity": validity,
            "last_uid": last_seen,
            "total_new": len(fresh),
            "messages": rows,
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
