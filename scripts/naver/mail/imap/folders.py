"""IMAP 폴더 이름·목록 해석 — 수정 UTF-7(RFC 3501) 변환과 네이버 시스템 폴더 한글 이름/정렬.

기준서: docs/specs/2026-10-01_naver_mailbox_tab.md. 네트워크를 쓰지 않는 순수 함수만 둔다.
"""

from __future__ import annotations

import base64
import re
from typing import Any

# 특수 용도 속성 → (표시 이름, 정렬 순서)
SPECIAL_USE: dict[str, tuple[str, int]] = {
    "\\inbox": ("받은편지함", 0),
    "\\sent": ("보낸메일함", 1),
    "\\drafts": ("임시보관함", 2),
    "\\junk": ("스팸메일함", 3),
    "\\trash": ("휴지통", 4),
}
USER_FOLDER_ORDER = 10

_LIST_LINE = re.compile(r'^\((?P<flags>[^)]*)\)\s+(?P<delim>"[^"]*"|NIL)\s+(?P<name>.+)$')


def utf7_decode(name: str) -> str:
    """수정 UTF-7 → 문자열. `&-` 는 `&`."""

    def _chunk(match: re.Match[str]) -> str:
        body = match.group(1)
        if not body:
            return "&"
        raw = body.replace(",", "/")
        raw += "=" * (-len(raw) % 4)
        return base64.b64decode(raw).decode("utf-16-be")

    return re.sub(r"&([^-]*)-", _chunk, name)


def utf7_encode(name: str) -> str:
    """문자열 → 수정 UTF-7 (폴더 이름을 서버에 보낼 때)."""
    out: list[str] = []
    pending: list[str] = []

    def _flush() -> None:
        if pending:
            raw = base64.b64encode("".join(pending).encode("utf-16-be")).decode("ascii").rstrip("=")
            out.append("&" + raw.replace("/", ",") + "-")
            pending.clear()

    for ch in name:
        if 0x20 <= ord(ch) <= 0x7E:
            _flush()
            out.append("&-" if ch == "&" else ch)
        else:
            pending.append(ch)
    _flush()
    return "".join(out)


def parse_list_line(line: bytes | str) -> dict[str, Any] | None:
    """`(\\HasNoChildren \\Sent) "/" "Sent Messages"` 한 줄을 해석한다. 해석 못 하면 None."""
    text = line.decode("utf-8", "replace") if isinstance(line, bytes) else line
    match = _LIST_LINE.match(text.strip())
    if not match:
        return None
    flags = [f.lower() for f in match.group("flags").split()]
    delim = match.group("delim").strip('"') if match.group("delim") != "NIL" else ""
    raw = match.group("name").strip()
    if raw.startswith('"') and raw.endswith('"'):
        raw = raw[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return {"raw": raw, "flags": flags, "delimiter": delim}


def describe_folder(entry: dict[str, Any]) -> dict[str, Any]:
    """표시 이름·종류·정렬 키·깊이를 붙인다."""
    flags = entry["flags"]
    raw: str = entry["raw"]
    kind, label, order = "user", None, USER_FOLDER_ORDER
    if raw.upper() == "INBOX":
        kind, (label, order) = "inbox", SPECIAL_USE["\\inbox"]
    else:
        for flag, (name, rank) in SPECIAL_USE.items():
            if flag in flags:
                kind, label, order = flag.lstrip("\\"), name, rank
                break
    delim = entry["delimiter"]
    parts = utf7_decode(raw).split(delim) if delim else [utf7_decode(raw)]
    return {
        "id": raw,
        "name": label or parts[-1],
        "path": utf7_decode(raw),
        "kind": kind,
        "depth": 0 if label else len(parts) - 1,
        "sort": (order, utf7_decode(raw)),
        "has_children": "\\haschildren" in flags,
        "selectable": "\\noselect" not in flags,
    }


def build_folder_list(lines: list[Any]) -> list[dict[str, Any]]:
    """LIST 응답 전체 → 시스템 폴더(고정 순서) 다음에 사용자 폴더(이름순, 하위 폴더는 부모 아래)."""
    folders = [describe_folder(e) for e in (parse_list_line(line) for line in lines if line) if e]
    folders.sort(key=lambda f: f["sort"])
    for f in folders:
        del f["sort"]
    return folders


def pick_by_kind(folders: list[dict[str, Any]], kind: str) -> str | None:
    """특수 용도 폴더의 서버 이름(예: kind='trash' → 'Deleted Messages')."""
    return next((f["id"] for f in folders if f["kind"] == kind), None)
