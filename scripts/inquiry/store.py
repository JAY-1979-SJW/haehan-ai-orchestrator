"""문의 저장소 — data/inquiries/inquiries.jsonl (append, 저용량 CRUD).

상태: new(접수) → read(읽음) → done(답변완료)
"""

from __future__ import annotations

import json
import re
import secrets
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_orchestrator.paths.runtime import data_dir

ROOT = Path(__file__).resolve().parents[2]
_FILE = data_dir() / "inquiries" / "inquiries.jsonl"
_LOCK = threading.Lock()  # 동시 append/재기록 직렬화(업데이트 유실 방지)

_MAXLEN = {"name": 60, "contact": 120, "company": 80, "subject": 120, "message": 4000}
_VALID_STATUS = {"new", "read", "done"}


def _clip(v: Any, key: str) -> str:
    s = str(v or "").strip()
    return s[: _MAXLEN.get(key, 200)]


def add_inquiry(data: dict) -> dict:
    """문의 1건 저장. 필수: name, message. 반환: 저장된 레코드(연락처 마스킹 없음 — 내부용)."""
    name = _clip(data.get("name"), "name")
    message = _clip(data.get("message"), "message")
    if not name or not message:
        raise ValueError("이름과 문의 내용을 입력하세요")
    rec = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S") + secrets.token_hex(3),
        "name": name,
        "contact": _clip(data.get("contact"), "contact"),
        "company": _clip(data.get("company"), "company"),
        "subject": _clip(data.get("subject"), "subject") or "(제목 없음)",
        "message": message,
        "status": "new",
        "memo": "",
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    with _LOCK:
        _FILE.parent.mkdir(parents=True, exist_ok=True)
        with _FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def list_inquiries(limit: int = 200) -> list[dict]:
    """전체 문의(최근 우선)."""
    if not _FILE.exists():
        return []
    out = []
    for line in _FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001 - 문의 저장소 JSONL 파일 읽기 - 손상된 줄은 skip하고 나머지만 반환(읽기전용 파싱)
            continue
    out.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return out[:limit]


def update_inquiry(inquiry_id: str, status: str | None = None, memo: str | None = None) -> bool:
    """상태/메모 갱신 → 전체 재기록. 락으로 read-modify-write 직렬화(유실 방지)."""
    with _LOCK:
        items = list_inquiries(limit=100000)
        found = False
        for r in items:
            if r.get("id") == inquiry_id:
                if status and status in _VALID_STATUS:
                    r["status"] = status
                if memo is not None:
                    r["memo"] = str(memo)[:2000]
                found = True
                break
        if not found:
            return False
        # 시간순(오래된→최신)으로 원자적 재기록(temp → replace)
        items.sort(key=lambda r: r.get("created_at", ""))
        _FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _FILE.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for r in items:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp.replace(_FILE)
    return True


def counts() -> dict:
    items = list_inquiries(limit=100000)
    return {
        "total": len(items),
        "new": sum(1 for r in items if r.get("status") == "new"),
        "done": sum(1 for r in items if r.get("status") == "done"),
    }


_VALID_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def looks_like_contact(contact: str) -> bool:
    c = (contact or "").strip()
    return bool(c) and (bool(_VALID_EMAIL.match(c)) or bool(re.match(r"^[\d\-+\s()]{7,}$", c)))
