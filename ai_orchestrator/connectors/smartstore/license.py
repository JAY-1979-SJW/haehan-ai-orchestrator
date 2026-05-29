"""라이선스 관리 — 발급·검증·만료·사용량 추적."""
from __future__ import annotations

import json
import secrets
import datetime
from pathlib import Path
from typing import Optional

ROOT      = Path(__file__).resolve().parents[3]
LICENSE_DB = ROOT / "data" / "licenses.json"


# ── DB 헬퍼 ──────────────────────────────────────────────────────────────────

def _load() -> dict:
    if not LICENSE_DB.exists():
        return {}
    try:
        return json.loads(LICENSE_DB.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(db: dict) -> None:
    LICENSE_DB.parent.mkdir(parents=True, exist_ok=True)
    LICENSE_DB.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 라이선스 CRUD ─────────────────────────────────────────────────────────────

def issue(name: str, email: str, plan: str = "basic",
          expire_days: int = 365) -> dict:
    """새 라이선스 발급."""
    db  = _load()
    key = secrets.token_urlsafe(24)
    exp = (datetime.datetime.now() + datetime.timedelta(days=expire_days)).isoformat(timespec="seconds")
    db[key] = {
        "key":        key,
        "name":       name,
        "email":      email,
        "plan":       plan,
        "issued_at":  datetime.datetime.now().isoformat(timespec="seconds"),
        "expires_at": exp,
        "active":     True,
        "call_count": 0,
        "last_seen":  None,
        "agent_id":   None,   # 연결된 로컬 에이전트 ID
    }
    _save(db)
    return db[key]


def verify(key: str) -> tuple[bool, Optional[dict], str]:
    """라이선스 검증. (ok, record, reason)"""
    db = _load()
    rec = db.get(key)
    if not rec:
        return False, None, "invalid_key"
    if not rec.get("active"):
        return False, rec, "revoked"
    exp = rec.get("expires_at")
    if exp and datetime.datetime.fromisoformat(exp) < datetime.datetime.now():
        return False, rec, "expired"
    return True, rec, "ok"


def touch(key: str, agent_id: str | None = None) -> None:
    """마지막 접속 시각 + 사용 횟수 업데이트."""
    db = _load()
    if key not in db:
        return
    db[key]["last_seen"]  = datetime.datetime.now().isoformat(timespec="seconds")
    db[key]["call_count"] = db[key].get("call_count", 0) + 1
    if agent_id:
        db[key]["agent_id"] = agent_id
    _save(db)


def revoke(key: str) -> bool:
    db = _load()
    if key not in db:
        return False
    db[key]["active"] = False
    _save(db)
    return True


def list_all() -> list[dict]:
    return list(_load().values())
