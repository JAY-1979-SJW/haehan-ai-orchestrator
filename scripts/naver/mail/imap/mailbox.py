"""네이버 메일함 화면용 IMAP 어댑터 — 폴더 목록·페이지 목록·메일 상세·첨부 받기·읽음 표시·휴지통 이동.

기준서: docs/specs/2026-10-01_naver_mailbox_tab.md
- 메일을 읽을 때는 항상 `BODY.PEEK`/읽기 전용 select 라서 **열어도 읽음 표시가 바뀌지 않는다**(사용자 결정).
- 읽음 표시 변경·휴지통 이동만 쓰기 모드로 연다. 영구 삭제는 구현하지 않는다.
- 요청마다 연결을 열고 닫는다. 비밀번호는 `.env` 에서만 읽고 결과에 넣지 않는다.
"""

from __future__ import annotations

import base64
import contextlib
import email
import email.policy
import imaplib
import re
import socket
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from email.message import EmailMessage
from email.utils import getaddresses, parsedate_to_datetime
from typing import Any, cast

from scripts.naver.mail.imap import attachments as att
from scripts.naver.mail.imap import folders as fld
from scripts.naver.mail.imap import html_sanitize as hs
from scripts.naver.mail.imap.protocol import (
    AUTH_HINT,
    IMAP_HOST,
    IMAP_PORT,
    TIMEOUT_SEC,
    _fail,
    _inbox_counts,
    load_password,
    password_env_name,
)
from scripts.naver.mail.imap.reader import _imap_date

PER_PAGE_DEFAULT = 30
PER_PAGE_MAX = 100
MAX_SCAN = 500  # 검색어·첨부 필터처럼 서버가 못 거르는 조건에서 훑는 최대 통수
FETCH_BATCH = 100
HTML_LIMIT = 1_500_000
INLINE_IMAGE_LIMIT = 2 * 1024 * 1024
FILTERS = ("all", "unseen", "attach")
_HEADER_FIELDS = "FROM TO CC SUBJECT DATE CONTENT-TYPE"
_FETCH_HEADERS = f"(UID FLAGS RFC822.SIZE BODYSTRUCTURE BODY.PEEK[HEADER.FIELDS ({_HEADER_FIELDS})])"


class MailboxError(Exception):
    """호출부가 그대로 결과 dict 로 바꿀 수 있는 오류."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind, self.message = kind, message


def failure(e: MailboxError) -> dict[str, Any]:
    return _fail(e.kind, e.message)


def quote(name: str) -> str:
    """IMAP 폴더 이름 인자 — 공백·한글(UTF-7 로 변환된 이름)을 안전하게 감싼다."""
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


# ── 연결 풀 ─────────────────────────────────────────────────────────────
# 요청마다 TLS 연결+로그인을 새로 하면 클릭 한 번에 0.4초가 로그인에 쓰인다. 메일 클라이언트의 일반적인 방식대로 계정당
# 인증된 연결 몇 개를 잠깐 보관했다가 재사용한다(꺼내 쓸 때 NOOP 으로 살아 있는지 확인, 오래 놀린 연결은 버림).
# 서버의 동시 접속 제한을 고려해 보관 수는 계정당 3개로 낮게 둔다. 테스트처럼 factory 를 직접 주면 풀을 쓰지 않는다.
POOL_IDLE_SEC = 45
POOL_MAX_IDLE = 3
_POOL: dict[str, list[tuple[Any, float]]] = {}
_pool_lock = threading.Lock()


def _close(conn: Any) -> None:
    with contextlib.suppress(Exception):  # 종료 정리 실패는 결과에 영향 없음
        conn.logout()


def clear_pool() -> None:
    """보관 중인 연결을 모두 닫는다(테스트·종료용)."""
    with _pool_lock:
        idle = [conn for items in _POOL.values() for conn, _ in items]
        _POOL.clear()
    for conn in idle:
        _close(conn)


def _connect(account: str, pw: str, factory: Callable[..., Any]) -> Any:
    try:
        socket.setdefaulttimeout(TIMEOUT_SEC)
        conn = factory(IMAP_HOST, IMAP_PORT)
    except Exception as e:  # 접속 실패를 결과로 돌려준다
        raise MailboxError("connect_failed", f"IMAP 서버에 접속하지 못했습니다 ({type(e).__name__})") from e
    try:
        conn.login(account, pw)
    except imaplib.IMAP4.error as e:
        _close(conn)
        raise MailboxError("auth_failed", "IMAP 로그인이 거부되었습니다. " + AUTH_HINT) from e
    return conn


def _checkout(account: str, pw: str) -> Any:
    while True:
        with _pool_lock:
            idle = _POOL.get(account)
            item = idle.pop() if idle else None
        if item is None:
            return _connect(account, pw, imaplib.IMAP4_SSL)
        conn, since = item
        if time.monotonic() - since > POOL_IDLE_SEC:
            _close(conn)
            continue
        try:
            conn.noop()
            return conn
        except (imaplib.IMAP4.error, OSError):
            _close(conn)


def _checkin(account: str, conn: Any) -> None:
    with _pool_lock:
        idle = _POOL.setdefault(account, [])
        if len(idle) < POOL_MAX_IDLE:
            idle.append((conn, time.monotonic()))
            return
    _close(conn)


@contextmanager
def session(
    account: str,
    folder: str | None = "INBOX",
    *,
    readonly: bool = True,
    password: str | None = None,
    factory: Callable[..., Any] | None = None,
) -> Iterator[Any]:
    """로그인(+폴더 선택)한 연결을 빌려준다. 정상 종료하면 풀에 돌려놓고, 오류가 나면 닫는다. 실패는 MailboxError."""
    pw = load_password(account) if password is None else password
    if not pw:
        raise MailboxError("no_password", f".env 에 {password_env_name(account)} 가 없습니다")
    pooled = factory is None
    conn = _checkout(account, pw) if factory is None else _connect(account, pw, factory)
    healthy = False
    try:
        if folder is None:
            with contextlib.suppress(Exception):  # STATUS 가 선택된 폴더의 낡은 값을 주지 않도록 선택을 푼다
                conn.unselect()
        else:
            try:
                code, _ = conn.select(quote(folder), readonly=readonly)
            except imaplib.IMAP4.error as e:
                raise MailboxError("folder_not_found", "폴더를 열지 못했습니다") from e
            if code != "OK":
                raise MailboxError("folder_not_found", "폴더를 열지 못했습니다")
        yield conn
        healthy = True
    finally:
        if pooled and healthy:
            _checkin(account, conn)
        else:
            _close(conn)


# ── 헤더 해석 ───────────────────────────────────────────────────────────


def _addr(value: str | None) -> dict[str, str]:
    name, address = (getaddresses([value or ""]) or [("", "")])[0]
    return {"name": name, "address": address}


def _addrs(value: str | None) -> list[dict[str, str]]:
    return [{"name": n, "address": a} for n, a in getaddresses([value or ""]) if a or n]


def _iso(value: str | None) -> str:
    try:
        return parsedate_to_datetime(value or "").isoformat()
    except (TypeError, ValueError):
        return ""


def _parse_fetch_meta(meta: bytes) -> dict[str, Any]:
    text = meta.decode("ascii", "replace")
    uid = re.search(r"UID (\d+)", text)
    flags = re.search(r"FLAGS \(([^)]*)\)", text)
    size = re.search(r"RFC822\.SIZE (\d+)", text)
    return {
        "uid": int(uid.group(1)) if uid else 0,
        "flags": [f.lower() for f in (flags.group(1).split() if flags else [])],
        "size": int(size.group(1)) if size else 0,
    }


def _has_attachment(structure: str, content_type: str) -> bool:
    """BODYSTRUCTURE 에 첨부(disposition=attachment)가 있으면 True. 구조를 못 받았을 때만 Content-Type 으로 추정."""
    if structure:
        return bool(re.search(r'"attachment"', structure, re.IGNORECASE))
    return "multipart/mixed" in content_type or "multipart/signed" in content_type


def _row(meta: dict[str, Any], raw: bytes) -> dict[str, Any]:
    h = parse_message(raw)
    ctype = str(h.get("Content-Type", "")).lower()
    return {
        "uid": meta["uid"],
        "from": _addr(str(h.get("From", ""))),
        "to": _addrs(str(h.get("To", ""))),
        "subject": str(h.get("Subject", "")),
        "date": str(h.get("Date", "")),
        "date_iso": _iso(str(h.get("Date", ""))),
        "size": meta["size"],
        "seen": "\\seen" in meta["flags"],
        "flagged": "\\flagged" in meta["flags"],
        "has_attachment": _has_attachment(meta.get("structure", ""), ctype),
    }


# 메일 헤더는 번호(UID)가 같으면 바뀌지 않으므로 서버 메모리에 보관한다. 서버가 메일 내용을 읽는 요청은 100통에 약 4초지만
# 플래그·크기만 읽는 요청은 0.03초라서, 읽음 상태만 매번 새로 받고 나머지는 캐시에서 쓴다.
_ROW_CACHE: dict[tuple[str, str, int, int], dict[str, Any]] = {}
_ROW_CACHE_MAX = 20000
_cache_lock = threading.Lock()


def clear_row_cache() -> None:
    with _cache_lock:
        _ROW_CACHE.clear()


def _fast_meta(conn: Any, uids: list[int]) -> dict[int, dict[str, Any]]:
    """(UID FLAGS RFC822.SIZE) — 메일 내용을 읽지 않는 빠른 조회."""
    out: dict[int, dict[str, Any]] = {}
    for i in range(0, len(uids), 500):
        _, data = conn.uid("FETCH", ",".join(str(u) for u in uids[i : i + 500]), "(UID FLAGS RFC822.SIZE)")
        for item in data or []:
            raw = item[0] if isinstance(item, tuple) else item
            if isinstance(raw, bytes) and b"UID" in raw:
                meta = _parse_fetch_meta(raw)
                out[meta["uid"]] = meta
    return out


def _fetch_static(conn: Any, uids: list[int], metas: dict[int, dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """캐시에 없는 메일의 헤더·첨부 구조를 한 번에 받아 정적 필드로 만든다."""
    # 응답은 [(앞부분, 헤더 리터럴), 뒷부분, ...] 순서 — BODYSTRUCTURE 는 앞/뒷부분 어디에든 있을 수 있어 이어 붙여 본다
    records: list[dict[str, Any]] = []
    for i in range(0, len(uids), FETCH_BATCH):
        _, data = conn.uid("FETCH", ",".join(str(u) for u in uids[i : i + FETCH_BATCH]), _FETCH_HEADERS)
        for item in data or []:
            if isinstance(item, tuple):
                meta = _parse_fetch_meta(item[0])
                meta["raw"], meta["text"] = item[1], item[0].decode("ascii", "replace")
                records.append(meta)
            elif isinstance(item, bytes) and records:
                records[-1]["text"] += item.decode("ascii", "replace")
    out: dict[int, dict[str, Any]] = {}
    for meta in records:
        structure = re.search(r"BODYSTRUCTURE (\(.*\))", meta["text"], re.DOTALL)
        meta["structure"] = structure.group(1) if structure else ""
        out[meta["uid"]] = _row({**meta, "flags": metas.get(meta["uid"], meta)["flags"]}, meta["raw"])
    return out


def _fetch_rows(conn: Any, uids: list[int], key: tuple[str, str]) -> list[dict[str, Any]]:
    """uid 목록(주어진 순서 유지)의 목록용 행. `key` = (계정, 폴더)."""
    if not uids:
        return []
    metas = _fast_meta(conn, uids)
    with _cache_lock:
        cached = {u: _ROW_CACHE.get((*key, u, metas[u]["size"])) for u in uids if u in metas}
    missing = [u for u in uids if u in metas and cached[u] is None]
    fresh = _fetch_static(conn, missing, metas) if missing else {}
    if fresh:
        with _cache_lock:
            if len(_ROW_CACHE) + len(fresh) > _ROW_CACHE_MAX:
                _ROW_CACHE.clear()
            for u, row in fresh.items():
                _ROW_CACHE[(*key, u, metas[u]["size"])] = row
    rows = []
    for u in uids:
        if u not in metas:
            continue
        base = cached[u] or fresh.get(u)
        if base is None:
            continue
        flags = metas[u]["flags"]
        rows.append({**base, "seen": r"\seen" in flags, "flagged": r"\flagged" in flags})
    return rows


# ── 폴더 ────────────────────────────────────────────────────────────────


def list_folders(
    account: str, *, password: str | None = None, factory: Callable[..., Any] | None = None
) -> dict[str, Any]:
    """목차: 시스템 폴더(받은편지함·보낸메일함·임시보관함·스팸·휴지통) 다음에 사용자 폴더, 각 폴더의 전체/안 읽음 수."""
    try:
        with session(account, None, password=password, factory=factory) as conn:
            _, lines = conn.list()
            folders = fld.build_folder_list(list(lines or []))
            for f in folders:
                f["total"], f["unseen"] = 0, 0
                if f["selectable"]:
                    _, status = conn.status(quote(f["id"]), "(MESSAGES UNSEEN)")
                    counts = _inbox_counts(status[0].decode("utf-8", "replace") if status and status[0] else "")
                    f["total"], f["unseen"] = counts.get("MESSAGES", 0), counts.get("UNSEEN", 0)
            return {"ok": True, "folders": folders}
    except MailboxError as e:
        return failure(e)


def inbox_status(
    account: str, *, password: str | None = None, factory: Callable[..., Any] | None = None
) -> dict[str, Any]:
    """새 메일 알림용 — 받은편지함을 선택하지 않고 STATUS 한 줄만 보낸다(읽음 표시·캐시 불변)."""
    try:
        with session(account, None, password=password, factory=factory) as conn:
            _, status = conn.status("INBOX", "(UIDNEXT UIDVALIDITY UNSEEN)")
            line = status[0].decode("utf-8", "replace") if status and status[0] else ""
            words = line.split("(")[-1].rstrip(") ").split()
            nums = {words[i]: int(words[i + 1]) for i in range(0, len(words) - 1, 2) if words[i + 1].isdigit()}
            if "UIDNEXT" not in nums or "UIDVALIDITY" not in nums:
                return {"ok": False, "error": "bad_status", "message": "받은편지함 상태를 해석하지 못했습니다"}
            return {"ok": True, "uidnext": nums["UIDNEXT"], "uidvalidity": nums["UIDVALIDITY"], "unseen": nums.get("UNSEEN", 0)}
    except MailboxError as e:
        return failure(e)
    except (imaplib.IMAP4.error, OSError):
        return {"ok": False, "error": "connect_failed", "message": "받은편지함 상태를 확인하지 못했습니다"}


# ── 목록 ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ListQuery:
    folder: str = "INBOX"
    page: int = 1
    per_page: int = PER_PAGE_DEFAULT
    filter: str = "all"  # all | unseen | attach
    query: str = ""  # 제목·보낸 사람·받는 사람에 포함된 글자
    since: date | None = None
    before: date | None = None


def _criteria(q: ListQuery) -> list[str]:
    out = []
    if q.filter == "unseen":
        out.append("UNSEEN")
    if q.since:
        out.append(f"SINCE {_imap_date(q.since)}")
    if q.before:
        out.append(f"BEFORE {_imap_date(q.before)}")
    return out or ["ALL"]


def _matches(row: dict[str, Any], q: ListQuery) -> bool:
    if q.filter == "attach" and not row["has_attachment"]:
        return False
    needle = q.query.strip().lower()
    if not needle:
        return True
    hay = " ".join(
        [
            row["subject"],
            row["from"]["name"],
            row["from"]["address"],
            *(f"{t['name']} {t['address']}" for t in row["to"]),
        ]
    )
    return needle in hay.lower()


_warming: set[tuple[str, str, int]] = set()


def _warm_async(account: str, folder: str, uids: list[int]) -> None:
    """다음 페이지의 헤더를 뒤에서 미리 받아 캐시에 넣는다 — 다음 쪽 넘김이 즉시 열린다. 실패해도 영향 없다."""
    if not uids:
        return
    key = (account, folder, uids[0])
    with _cache_lock:
        if key in _warming:
            return
        _warming.add(key)

    def _run() -> None:
        try:
            # 미리 불러오기는 실패해도 화면에 영향이 없다 — 오류는 삼키고 다음 요청이 직접 받는다
            with contextlib.suppress(Exception), session(account, folder) as conn:
                _fetch_rows(conn, uids, (account, folder))
        finally:
            with _cache_lock:
                _warming.discard(key)

    threading.Thread(target=_run, daemon=True, name="mailbox-warm").start()


def list_messages(
    account: str,
    q: ListQuery,
    *,
    password: str | None = None,
    factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """폴더의 메일 한 페이지(최신순). 읽음 표시는 바뀌지 않는다."""
    if q.filter not in FILTERS:
        return _fail("bad_filter", f"filter 는 {FILTERS} 중 하나여야 합니다")
    page, per_page = max(1, int(q.page)), max(1, min(int(q.per_page), PER_PAGE_MAX))
    try:
        with session(account, q.folder, password=password, factory=factory) as conn:
            _, data = conn.uid("SEARCH", None, *_criteria(q))
            uids = sorted((int(u) for u in (data[0] or b"").decode().split()), reverse=True)
            start = (page - 1) * per_page
            if not q.query.strip() and q.filter != "attach":
                rows = _fetch_rows(conn, uids[start : start + per_page], (account, q.folder))
                if factory is None:
                    _warm_async(account, q.folder, uids[start + per_page : start + 2 * per_page])
                return {
                    "ok": True,
                    "page": page,
                    "per_page": per_page,
                    "total": len(uids),
                    "truncated": False,
                    "messages": rows,
                }
            matched: list[dict[str, Any]] = []
            scan = uids[:MAX_SCAN]
            for i in range(0, len(scan), FETCH_BATCH):
                matched += [
                    r for r in _fetch_rows(conn, scan[i : i + FETCH_BATCH], (account, q.folder)) if _matches(r, q)
                ]
                if len(matched) >= start + per_page:
                    break
            return {
                "ok": True,
                "page": page,
                "per_page": per_page,
                "total": len(matched),
                "truncated": len(uids) > MAX_SCAN,
                "messages": matched[start : start + per_page],
            }
    except MailboxError as e:
        return failure(e)


# ── 상세 ────────────────────────────────────────────────────────────────


def _safe_text(part: Any) -> str:
    try:
        return str(part.get_content())
    except (LookupError, ValueError):
        payload = part.get_payload(decode=True)
        return payload.decode("utf-8", "replace") if isinstance(payload, bytes) else ""


def _is_attachment(part: EmailMessage) -> bool:
    if part.is_multipart():
        return False
    if part.get_content_disposition() == "attachment":
        return True
    # 본문이 아니고 이름이 있는 파트(인라인 이미지는 Content-ID 가 있으면 본문에서 쓰는 것이라 제외)
    return bool(part.get_filename()) and not (part.get("Content-ID") and part.get_content_maintype() == "image")


def _walk_attachments(msg: EmailMessage) -> list[EmailMessage]:
    return [p for p in msg.walk() if isinstance(p, EmailMessage) and _is_attachment(p)]


def _inline_images(msg: EmailMessage) -> dict[str, str]:
    """Content-ID → data: URI (본문 속 cid: 이미지를 서버 호출 없이 보여 주기 위해). 2MB 초과는 제외."""
    out: dict[str, str] = {}
    for part in msg.walk():
        cid = str(part.get("Content-ID", "")).strip("<> ")
        if not cid or part.get_content_maintype() != "image":
            continue
        payload = part.get_payload(decode=True)
        if (
            isinstance(payload, bytes)
            and len(payload) <= INLINE_IMAGE_LIMIT
            and att.is_previewable(part.get_content_type())
        ):
            out[cid] = f"data:{part.get_content_type()};base64,{base64.b64encode(payload).decode('ascii')}"
    return out


def _body(msg: EmailMessage) -> tuple[str, str]:
    html_part = msg.get_body(preferencelist=("html",))
    text_part = msg.get_body(preferencelist=("plain",))
    html = _safe_text(html_part)[:HTML_LIMIT] if html_part is not None else ""
    for cid, uri in _inline_images(msg).items():
        html = html.replace(f"cid:{cid}", uri)
    return (_safe_text(text_part) if text_part is not None else ""), html


def parse_message(raw: bytes) -> EmailMessage:
    return cast(
        EmailMessage, email.message_from_bytes(raw, policy=email.policy.default)
    )  # policy.default 는 항상 EmailMessage


def _attachment_info(index: int, part: EmailMessage) -> dict[str, Any]:
    payload = part.get_payload(decode=True)
    ctype = part.get_content_type()
    return {
        "index": index,
        "filename": att.safe_filename(part.get_filename(), f"첨부{index + 1}"),
        "size": len(payload) if isinstance(payload, bytes) else 0,
        "content_type": ctype,
        "previewable": att.is_previewable(ctype),
    }


# 열어 본 메일 원문 캐시 — 같은 번호(UID)·같은 크기의 메일은 바뀌지 않으므로 다시 열 때·첨부를 받을 때 서버에서 또 받지 않는다.
# 읽음 표시(플래그)는 캐시와 무관하게 매번 새로 받는다. 메모리 상한: 60통·40MB.
_RAW_CACHE: OrderedDict[tuple[str, str, int, int], bytes] = OrderedDict()
_RAW_CACHE_MAX_ITEMS = 60
_RAW_CACHE_MAX_BYTES = 40 * 1024 * 1024
_raw_lock = threading.Lock()


def _raw_get(key: tuple[str, str, int, int]) -> bytes | None:
    with _raw_lock:
        raw = _RAW_CACHE.get(key)
        if raw is not None:
            _RAW_CACHE.move_to_end(key)
        return raw


def _raw_put(key: tuple[str, str, int, int], raw: bytes) -> None:
    if len(raw) > _RAW_CACHE_MAX_BYTES // 2:
        return
    with _raw_lock:
        _RAW_CACHE[key] = raw
        _RAW_CACHE.move_to_end(key)
        while len(_RAW_CACHE) > _RAW_CACHE_MAX_ITEMS or sum(len(v) for v in _RAW_CACHE.values()) > _RAW_CACHE_MAX_BYTES:
            _RAW_CACHE.popitem(last=False)


def clear_raw_cache() -> None:
    with _raw_lock:
        _RAW_CACHE.clear()


def _fetch_raw(conn: Any, uid: int, scope: tuple[str, str]) -> tuple[bytes, list[str]]:
    """메일 원문과 플래그. `scope` = (계정, 폴더) — 캐시 키."""
    _, meta = conn.uid("FETCH", str(uid), "(FLAGS RFC822.SIZE)")
    info = _parse_fetch_meta(meta[0] if meta and isinstance(meta[0], bytes) else b"")
    if info["size"] > att.MAX_MESSAGE_BYTES:
        raise MailboxError("too_large", "메일이 너무 커서 열 수 없습니다(60MB 초과)")
    key = (*scope, uid, info["size"])
    raw = _raw_get(key)
    if raw is None:
        _, parts = conn.uid("FETCH", str(uid), "(BODY.PEEK[])")
        raw = next((p[1] for p in parts or [] if isinstance(p, tuple)), b"")
        if not raw:
            raise MailboxError("not_found", "해당 메일이 없습니다")
        _raw_put(key, raw)
    return raw, info["flags"]


def get_message(
    account: str,
    folder: str,
    uid: int,
    *,
    password: str | None = None,
    factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """메일 1통: 헤더·본문(텍스트/HTML)·첨부 목록. 열어도 읽음 표시는 바뀌지 않는다(PEEK)."""
    try:
        with session(account, folder, password=password, factory=factory) as conn:
            raw, flags = _fetch_raw(conn, int(uid), (account, folder))
    except MailboxError as e:
        return failure(e)
    msg = parse_message(raw)
    text, html = _body(msg)
    return {
        "ok": True,
        "uid": int(uid),
        "folder": folder,
        "subject": str(msg.get("Subject", "")),
        "from": _addr(str(msg.get("From", ""))),
        "to": _addrs(str(msg.get("To", ""))),
        "cc": _addrs(str(msg.get("Cc", ""))),
        "date": str(msg.get("Date", "")),
        "date_iso": _iso(str(msg.get("Date", ""))),
        "message_id": str(msg.get("Message-ID", "")),
        "references": str(msg.get("References", "")),
        "seen": "\\seen" in flags,
        "text": text,
        "html": html,
        # 답장/전달 때 편집기에 넣는 인용문 — 반드시 정제한 HTML 만 쓴다(원문 html 은 격리 iframe 으로만 보여 준다)
        "quote_html": hs.sanitize_html(html, max_data_image_bytes=300_000) if html else hs.text_to_html(text),
        "attachments": [_attachment_info(i, p) for i, p in enumerate(_walk_attachments(msg))],
    }


def get_attachment(
    account: str,
    folder: str,
    uid: int,
    index: int,
    *,
    password: str | None = None,
    factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """첨부 1개의 내용. 25MB 초과는 거부한다."""
    try:
        with session(account, folder, password=password, factory=factory) as conn:
            raw, _ = _fetch_raw(conn, int(uid), (account, folder))
    except MailboxError as e:
        return failure(e)
    parts = _walk_attachments(parse_message(raw))
    if not 0 <= int(index) < len(parts):
        return _fail("not_found", "해당 첨부가 없습니다")
    part = parts[int(index)]
    data = part.get_payload(decode=True)
    data = data if isinstance(data, bytes) else b""
    if len(data) > att.MAX_DOWNLOAD_BYTES:
        return _fail("too_large", "첨부가 너무 큽니다(25MB 초과)")
    info = _attachment_info(int(index), part)
    return {
        "ok": True,
        "filename": info["filename"],
        "content_type": info["content_type"],
        "previewable": info["previewable"],
        "data": data,
    }


# ── 상태 변경(읽음 표시·이동·삭제) ──────────────────────────────────────

MAX_BULK = 100
PURGEABLE_KINDS = ("trash", "junk")  # 영구 삭제는 휴지통·스팸에서만


def _uid_set(uids: int | list[int]) -> str:
    """UID 목록 → IMAP uid-set. 숫자만, 1~MAX_BULK 개."""
    items = [uids] if isinstance(uids, int) else list(uids)
    if (
        not items
        or len(items) > MAX_BULK
        or not all(isinstance(u, int) and not isinstance(u, bool) and u > 0 for u in items)
    ):
        raise MailboxError("bad_uid", f"uid 는 양의 정수 1~{MAX_BULK}개여야 합니다")
    return ",".join(str(u) for u in dict.fromkeys(items))


def _folder_table(conn: Any) -> list[dict[str, Any]]:
    _, lines = conn.list()
    return fld.build_folder_list(list(lines or []))


def _kind_of(table: list[dict[str, Any]], folder_id: str) -> str | None:
    return next((f["kind"] for f in table if f["id"] == folder_id), None)


def set_seen(
    account: str,
    folder: str,
    uids: int | list[int],
    seen: bool,
    *,
    password: str | None = None,
    factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """읽음/안 읽음 표시 바꾸기(쓰기 모드). 여러 통도 연결 1번으로."""
    try:
        uid_set = _uid_set(uids)
        with session(account, folder, readonly=False, password=password, factory=factory) as conn:
            code, _ = conn.uid("STORE", uid_set, "+FLAGS.SILENT" if seen else "-FLAGS.SILENT", r"(\Seen)")
            return (
                {"ok": True, "seen": bool(seen)} if code == "OK" else _fail("store_failed", "표시를 바꾸지 못했습니다")
            )
    except MailboxError as e:
        return failure(e)


def move_messages(
    account: str,
    folder: str,
    uids: int | list[int],
    dest: str,
    *,
    password: str | None = None,
    factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """다른 폴더로 이동(MOVE). 대상은 실제 존재하는 선택 가능한 폴더여야 하고 같은 폴더로는 옮기지 않는다."""
    try:
        uid_set = _uid_set(uids)
        with session(account, folder, readonly=False, password=password, factory=factory) as conn:
            table = _folder_table(conn)
            target = next((f for f in table if f["id"] == dest), None)
            if target is None or not target["selectable"]:
                return _fail("folder_not_found", "옮길 폴더를 찾지 못했습니다")
            if dest == folder:
                return _fail("same_folder", "같은 폴더로는 옮길 수 없습니다")
            code, _ = conn.uid("MOVE", uid_set, quote(dest))
            return (
                {"ok": True, "moved_to": dest, "count": len(uid_set.split(","))}
                if code == "OK"
                else _fail("move_failed", "폴더를 옮기지 못했습니다")
            )
    except MailboxError as e:
        return failure(e)


def move_to_trash(
    account: str,
    folder: str,
    uids: int | list[int],
    *,
    password: str | None = None,
    factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """휴지통으로 이동(MOVE). 이미 휴지통이면 거부 — 영구 삭제는 `purge` 로 따로 한다."""
    try:
        uid_set = _uid_set(uids)
        with session(account, folder, readonly=False, password=password, factory=factory) as conn:
            trash = fld.pick_by_kind(_folder_table(conn), "trash")
            if not trash:
                return _fail("no_trash", "휴지통 폴더를 찾지 못했습니다")
            if folder == trash:
                return _fail("already_in_trash", "이미 휴지통에 있는 메일입니다(영구 삭제를 사용하세요)")
            code, _ = conn.uid("MOVE", uid_set, quote(trash))
            return (
                {"ok": True, "moved_to": trash, "count": len(uid_set.split(","))}
                if code == "OK"
                else _fail("move_failed", "휴지통으로 옮기지 못했습니다")
            )
    except MailboxError as e:
        return failure(e)


def _expunge(conn: Any, uid_set: str) -> bool:
    """지정한 UID 만 삭제 표시 후 즉시 제거(UIDPLUS 의 UID EXPUNGE — 다른 메일의 삭제 표시를 건드리지 않는다)."""
    code, _ = conn.uid("STORE", uid_set, "+FLAGS.SILENT", r"(\Deleted)")
    if code != "OK":
        return False
    code, _ = conn.uid("EXPUNGE", uid_set)
    return code == "OK"


def purge(
    account: str,
    folder: str,
    uids: int | list[int],
    *,
    password: str | None = None,
    factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """**영구 삭제** — 휴지통·스팸 폴더의 메일만. 되돌릴 수 없으므로 호출 전에 화면에서 확인을 받는다."""
    try:
        uid_set = _uid_set(uids)
        with session(account, folder, readonly=False, password=password, factory=factory) as conn:
            if _kind_of(_folder_table(conn), folder) not in PURGEABLE_KINDS:
                return _fail("not_purgeable", "영구 삭제는 휴지통·스팸메일함에서만 할 수 있습니다")
            if not _expunge(conn, uid_set):
                return _fail("purge_failed", "삭제하지 못했습니다")
            return {"ok": True, "count": len(uid_set.split(","))}
    except MailboxError as e:
        return failure(e)


def empty_folder(
    account: str,
    folder: str,
    *,
    password: str | None = None,
    factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """휴지통/스팸 비우기(영구 삭제). 다른 폴더에는 쓸 수 없다."""
    try:
        with session(account, folder, readonly=False, password=password, factory=factory) as conn:
            if _kind_of(_folder_table(conn), folder) not in PURGEABLE_KINDS:
                return _fail("not_purgeable", "비우기는 휴지통·스팸메일함에서만 할 수 있습니다")
            _, data = conn.uid("SEARCH", None, "ALL")
            uids = [int(u) for u in (data[0] or b"").decode().split()]
            for i in range(0, len(uids), 500):
                if not _expunge(conn, ",".join(str(u) for u in uids[i : i + 500])):
                    return _fail("purge_failed", "일부를 삭제하지 못했습니다")
            return {"ok": True, "count": len(uids)}
    except MailboxError as e:
        return failure(e)
