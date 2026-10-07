"""사용자 자연어 의도 토큰 (Intent Token).

목적
====
사용자가 자연어로 1회 요청한 의도를 등록 → 그 범위 내 액션은 자동 진행.
범위 밖 (다른 origin, 다른 scope, 만료, 액션 한도 초과) → 차단/알림.

원칙
====
1. 1 의도 = 1 토큰 = 그 범위 안에서 자유로운 자동 작업.
2. 만료(기본 1시간) 또는 액션 한도(기본 50회) 초과 → 자동 invalidate.
3. allowed_origins 외 이동은 NOTIFY (자동 진행하되 한 줄 보고).
4. 모든 토큰 발급/소진/만료 이력은 감사 로그 기록.
5. 비밀번호/카드/주민번호 등 민감정보는 토큰에 절대 저장 안 함.

사용 예
======
    intent = create_intent(
        natural_language="한컴 개발자 센터에서 한글 SDK 가격 확인",
        allowed_origins=("developer.hancom.com", "www.hancom.com"),
        scope=SCOPE_INTERACTION,
    )
    ...
    if validate_intent(intent)["ok"]:
        intent = increment_action(intent)
"""

from __future__ import annotations

import json
import secrets
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from ai_orchestrator.paths import repo_root

# Scope 정의
SCOPE_READ_ONLY = "read_only"  # navigate/read/screenshot만
SCOPE_INTERACTION = "interaction"  # +click/type/scroll/download (commit 액션은 별도 승인)

_VALID_SCOPES = (SCOPE_READ_ONLY, SCOPE_INTERACTION)

# 검증 결과 코드
INTENT_OK = "ok"
INTENT_EXPIRED = "expired"
INTENT_EXCEEDED = "actions_exceeded"
INTENT_INVALID = "invalid"

DEFAULT_TTL_SECONDS = 3600  # 1시간
DEFAULT_MAX_ACTIONS = 50

# 이동해도 값이 안 바뀌게 __file__ 상대 계산 대신 repo_root() 기준으로 고정(T4 C1).
# 지금 값과 완전히 동일(ai_orchestrator/data/intents).
_INTENT_DIR = repo_root() / "ai_orchestrator" / "data" / "intents"


@dataclass(frozen=True)
class IntentToken:
    intent_id: str
    natural_language: str
    allowed_origins: tuple[str, ...]
    scope: str
    max_actions: int
    created_at: str  # ISO8601 UTC
    expires_at: str  # ISO8601 UTC
    actions_used: int = 0
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _normalize_origin(origin_or_url: str) -> str:
    """URL이면 host 추출, 이미 host면 그대로 (소문자)."""
    if not origin_or_url:
        return ""
    s = origin_or_url.strip().lower()
    if s.startswith("http://") or s.startswith("https://"):
        return urlparse(s).netloc
    # 'http://' 없는 host
    return s.split("/")[0]


def _generate_intent_id() -> str:
    ts = _now_utc().strftime("%Y%m%d_%H%M%S")
    return f"intent_{ts}_{secrets.token_hex(4)}"


def create_intent(
    *,
    natural_language: str,
    allowed_origins: tuple[str, ...] | list[str],
    scope: str = SCOPE_INTERACTION,
    max_actions: int = DEFAULT_MAX_ACTIONS,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    notes: str = "",
) -> IntentToken:
    """새 intent token 생성. 민감정보 검증 포함."""
    if not natural_language or not natural_language.strip():
        raise ValueError("natural_language는 비어있을 수 없습니다")
    if scope not in _VALID_SCOPES:
        raise ValueError(f"scope는 {_VALID_SCOPES} 중 하나")
    if max_actions <= 0 or max_actions > 1000:
        raise ValueError("max_actions는 1~1000 범위")
    if ttl_seconds <= 0 or ttl_seconds > 86400:
        raise ValueError("ttl_seconds는 1~86400(24h) 범위")

    origins = tuple(_normalize_origin(o) for o in allowed_origins if o)
    origins = tuple(o for o in origins if o)
    if not origins:
        raise ValueError("allowed_origins 최소 1개 필요")

    # 자연어에 명백한 민감정보가 있으면 거절
    nl_lower = natural_language.lower()
    forbidden = ("password=", "비밀번호:", "주민번호", "카드번호", "cvv", "cvc")
    for f in forbidden:
        if f in nl_lower:
            raise ValueError(f"natural_language에 민감 키워드 포함 금지: {f}")

    now = _now_utc()
    expires = now + timedelta(seconds=ttl_seconds)

    return IntentToken(
        intent_id=_generate_intent_id(),
        natural_language=natural_language.strip()[:500],
        allowed_origins=origins,
        scope=scope,
        max_actions=max_actions,
        created_at=_iso(now),
        expires_at=_iso(expires),
        actions_used=0,
        notes=notes[:200],
    )


def validate_intent(intent: IntentToken, *, now: datetime | None = None) -> dict:
    """intent 유효성 검증. 결과 dict 반환 (예외 없음)."""
    if not isinstance(intent, IntentToken):
        return {"ok": False, "code": INTENT_INVALID, "reason": "IntentToken 인스턴스 아님"}
    now = now or _now_utc()
    try:
        expires = _parse_iso(intent.expires_at)
    except (ValueError, TypeError):
        return {"ok": False, "code": INTENT_INVALID, "reason": "expires_at 파싱 실패"}
    if now >= expires:
        return {"ok": False, "code": INTENT_EXPIRED, "reason": f"만료됨 (expired_at={intent.expires_at})"}
    if intent.actions_used >= intent.max_actions:
        return {
            "ok": False,
            "code": INTENT_EXCEEDED,
            "reason": f"max_actions 초과 ({intent.actions_used}/{intent.max_actions})",
        }
    return {
        "ok": True,
        "code": INTENT_OK,
        "remaining_actions": intent.max_actions - intent.actions_used,
        "remaining_seconds": int((expires - now).total_seconds()),
    }


def is_origin_allowed(intent: IntentToken, url_or_origin: str) -> bool:
    """주어진 URL/origin이 intent의 allowed_origins에 포함되는지."""
    target = _normalize_origin(url_or_origin)
    if not target:
        return False
    return target in intent.allowed_origins


def increment_action(intent: IntentToken) -> IntentToken:
    """actions_used + 1 새 토큰 반환 (frozen이라 replace)."""
    return replace(intent, actions_used=intent.actions_used + 1)


def add_origin(intent: IntentToken, new_origin: str) -> IntentToken:
    """allowed_origins에 origin 추가 (사용자 명시 승인 시 사용)."""
    norm = _normalize_origin(new_origin)
    if not norm:
        return intent
    if norm in intent.allowed_origins:
        return intent
    return replace(intent, allowed_origins=intent.allowed_origins + (norm,))  # noqa: RUF005


def save_intent(intent: IntentToken, *, intent_dir: Path | None = None) -> Path:
    """intent을 파일로 저장 (data/intents/active/<id>.json)."""
    base = intent_dir or _INTENT_DIR
    active = base / "active"
    active.mkdir(parents=True, exist_ok=True)
    path = active / f"{intent.intent_id}.json"
    path.write_text(
        json.dumps(intent.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_intent(intent_id: str, *, intent_dir: Path | None = None) -> IntentToken | None:
    """저장된 intent 로드. 없으면 None."""
    base = intent_dir or _INTENT_DIR
    path = base / "active" / f"{intent_id}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    data["allowed_origins"] = tuple(data.get("allowed_origins", []))
    return IntentToken(**data)


def expire_intent(intent: IntentToken, *, intent_dir: Path | None = None) -> Path | None:
    """active → expired 디렉터리로 이동."""
    base = intent_dir or _INTENT_DIR
    active = base / "active" / f"{intent.intent_id}.json"
    if not active.exists():
        return None
    expired = base / "expired"
    expired.mkdir(parents=True, exist_ok=True)
    target = expired / f"{intent.intent_id}.json"
    active.rename(target)
    return target


def list_active_intents(intent_dir: Path | None = None) -> list[str]:
    """현재 active intent_id 목록."""
    base = intent_dir or _INTENT_DIR
    active = base / "active"
    if not active.exists():
        return []
    return sorted(p.stem for p in active.glob("intent_*.json"))
