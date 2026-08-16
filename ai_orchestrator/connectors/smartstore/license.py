"""라이선스 관리 — 발급·검증·만료·사용량 추적."""

from __future__ import annotations

import datetime
import json
import os
import secrets
from pathlib import Path


def _data_root() -> Path:
    """번들(exe) 환경과 개발 환경 모두에서 data/ 경로를 정확히 반환."""
    env_dir = os.environ.get("HAEHAN_DATA_DIR")
    if env_dir:
        return Path(env_dir)
    return Path(__file__).resolve().parents[3] / "data"


ROOT = Path(__file__).resolve().parents[3]
LICENSE_DB = _data_root() / "licenses.json"


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
    tmp = LICENSE_DB.with_suffix(LICENSE_DB.suffix + ".tmp")
    tmp.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, LICENSE_DB)


# ── 라이선스 CRUD ─────────────────────────────────────────────────────────────


def issue(name: str, email: str, plan: str = "basic", expire_days: int = 365) -> dict:
    """새 라이선스 발급."""
    db = _load()
    key = secrets.token_urlsafe(24)
    exp = (datetime.datetime.now() + datetime.timedelta(days=expire_days)).isoformat(timespec="seconds")
    db[key] = {
        "key": key,
        "name": name,
        "email": email,
        "plan": plan,
        "issued_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "expires_at": exp,
        "active": True,
        "call_count": 0,
        "last_seen": None,
        "agent_id": None,  # 연결된 로컬 에이전트 ID
    }
    _save(db)
    return db[key]


def verify(key: str) -> tuple[bool, dict | None, str]:
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
    db[key]["last_seen"] = datetime.datetime.now().isoformat(timespec="seconds")
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
