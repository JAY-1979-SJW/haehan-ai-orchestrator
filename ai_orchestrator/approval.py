import uuid
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Literal, Optional

from .models import TaskRequest, RiskAssessment

_STORE_PATH = Path(__file__).parent / "storage" / "approval_tokens.json"
_store: dict[str, dict] = {}


@dataclass
class ApprovalToken:
    token_id: str
    task_id: str
    issued_at: str
    expires_at: str
    issued_by: str
    approved_by: Optional[str]
    risk_level: str
    status: Literal["issued", "approved", "expired", "revoked"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_store():
    global _store
    if _STORE_PATH.exists():
        try:
            _store = json.loads(_STORE_PATH.read_text(encoding="utf-8"))
        except Exception:
            _store = {}


def _save_store():
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORE_PATH.write_text(json.dumps(_store, indent=2, ensure_ascii=False), encoding="utf-8")


def issue_token(req: TaskRequest, risk: RiskAssessment, ttl_minutes: int = 30) -> ApprovalToken:
    _load_store()
    now = _now()
    token = ApprovalToken(
        token_id=str(uuid.uuid4()),
        task_id=req.task_id,
        issued_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=ttl_minutes)).isoformat(),
        issued_by=req.requested_by,
        approved_by=None,
        risk_level=risk.risk_level,
        status="issued",
    )
    _store[token.token_id] = asdict(token)
    _save_store()
    return token


def approve_token(token_id: str, approved_by: str) -> ApprovalToken:
    _load_store()
    if token_id not in _store:
        raise KeyError(f"토큰 없음: {token_id}")
    entry = _store[token_id]
    expires = datetime.fromisoformat(entry["expires_at"])
    if _now() > expires:
        entry["status"] = "expired"
        _save_store()
        raise ValueError(f"토큰 만료: {token_id}")
    entry["approved_by"] = approved_by
    entry["status"] = "approved"
    _save_store()
    return ApprovalToken(**entry)


def validate_token(token_id: str, task_id: str) -> bool:
    _load_store()
    entry = _store.get(token_id)
    if not entry:
        return False
    if entry["task_id"] != task_id:
        return False
    if entry["status"] != "approved":
        return False
    expires = datetime.fromisoformat(entry["expires_at"])
    if _now() > expires:
        entry["status"] = "expired"
        _save_store()
        return False
    return True


def revoke_token(token_id: str) -> None:
    _load_store()
    if token_id in _store:
        _store[token_id]["status"] = "revoked"
        _save_store()


def get_token(token_id: str) -> Optional[ApprovalToken]:
    _load_store()
    entry = _store.get(token_id)
    return ApprovalToken(**entry) if entry else None
