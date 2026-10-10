"""Instagram 댓글->키워드->비공개DM 자동화 API (L8).

Webhook 엔드포인트는 Meta signature(HMAC)로만 인증한다 — JWT 인증 미들웨어 대상이 아니다.
나머지 관리용 엔드포인트(rules/logs/dashboard/oauth)는 이 데스크톱형 서버 구조상
AUTH_ENABLED=false 기본값을 그대로 따른다(다른 커넥터 라우터와 동일 컨벤션).
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import time

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from ai_orchestrator.connectors.instagram import instagram_dm_db as db
from ai_orchestrator.connectors.instagram import instagram_dm_rule_engine as rule_engine
from ai_orchestrator.connectors.instagram import instagram_dm_token_store as token_store
from ai_orchestrator.connectors.instagram.instagram_dm_service import process_comment_event
from ai_orchestrator.connectors.instagram.instagram_graph_client import InstagramApiError, build_authorize_url, exchange_code_for_short_lived_token, exchange_for_long_lived_token
from ai_orchestrator.connectors.instagram.instagram_graph_client import verify_token as graph_verify_token
from ai_orchestrator.connectors.instagram.instagram_webhook_parser import parse_comment_events

logger = logging.getLogger(__name__)

instagram_dm_router = APIRouter(prefix="/instagram-dm", tags=["instagram-dm"])

db.init_db()

_TOKEN_REF_MARKER = "keyring"  # noqa: S105 — 참조 마커일 뿐 토큰 값이 아님, 실제 토큰은 token_store(keyring)에만 저장

_OAUTH_SCOPES = ["instagram_business_basic", "instagram_business_manage_comments", "instagram_business_manage_messages"]
_oauth_states: dict[str, float] = {}  # state -> 생성 시각. 단일 프로세스 CSRF state — 데스크톱형 단일사용자 전제(§19)
_OAUTH_STATE_TTL_SEC = 600.0  # 10분 초과 state 는 거부·청소
_OAUTH_STATE_MAX = 1000  # 초과 시 가장 오래된 state 제거


def _oauth_state_add(state: str) -> None:
    now = time.time()
    for k in [k for k, t in _oauth_states.items() if now - t > _OAUTH_STATE_TTL_SEC]:
        _oauth_states.pop(k, None)
    _oauth_states[state] = now
    while len(_oauth_states) > _OAUTH_STATE_MAX:
        _oauth_states.pop(next(iter(_oauth_states)), None)  # dict 삽입순 = 가장 오래된 것


def _app_id() -> str:
    # Instagram Login OAuth(인가 URL·코드 교환)는 Meta 앱 ID가 아니라
    # Instagram 전용 앱 ID로 발급된 code만 받아들인다 — 두 값이 다르면
    # 코드 교환 시 "Invalid platform app"으로 실패한다(2026-09-11 확인).
    return os.environ.get("IG_APP_ID", os.environ.get("META_APP_ID", "")).strip()


def _app_secret() -> str:
    return os.environ.get("META_APP_SECRET", "").strip()


def _redirect_uri() -> str:
    return os.environ.get("INSTAGRAM_REDIRECT_URI", "").strip()


def _verify_token_env() -> str:
    return os.environ.get("META_WEBHOOK_VERIFY_TOKEN", "").strip()


# ── Webhook ──────────────────────────────────────────────────────


def _ingest_comment_events(payload: dict, background_tasks: BackgroundTasks) -> None:
    """동기 sqlite 조회·적재를 모아 스레드에서 실행한다(이벤트 루프 비차단). 계정 조회는 id별 1회만."""
    accounts: dict = {}
    for parsed in parse_comment_events(payload):
        uid = parsed.instagram_user_id
        if uid not in accounts:
            accounts[uid] = db.get_account_by_ig_user_id(uid)
        account = accounts[uid]
        if account is None:
            logger.warning("instagram_dm: webhook에 미등록 계정 id=%s", uid)
            continue
        normalized = rule_engine.normalize_text(parsed.comment_text or "")
        event_id, is_new = db.insert_comment_event_if_new(
            instagram_account_id=account["id"],
            comment_id=parsed.comment_id,
            media_id=parsed.media_id,
            media_product_type=parsed.media_product_type,
            commenter_ig_scoped_id=parsed.commenter_ig_scoped_id,
            commenter_username=parsed.commenter_username,
            comment_text=parsed.comment_text,
            normalized_text=normalized,
            comment_created_at=parsed.comment_created_at,
            raw_payload=payload,
        )
        if is_new and event_id:
            background_tasks.add_task(process_comment_event, event_id, instagram_account_id=account["id"])


@instagram_dm_router.get("/webhooks/instagram")
async def webhook_verify(request: Request):
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge", "")
    expected = _verify_token_env()
    if mode == "subscribe" and expected and token == expected:
        return PlainTextResponse(challenge, status_code=200)
    raise HTTPException(status_code=403, detail="verify_token 불일치")


@instagram_dm_router.post("/webhooks/instagram")
async def webhook_receive(request: Request, background_tasks: BackgroundTasks):
    raw_body = await request.body()
    signature_header = request.headers.get("X-Hub-Signature-256", "")
    app_secret = _app_secret()

    signature_valid = False
    expected_sig = ""
    if app_secret and signature_header.startswith("sha256="):
        expected_sig = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        signature_valid = hmac.compare_digest(expected_sig, signature_header[len("sha256=") :])

    payload_hash = hashlib.sha256(raw_body).hexdigest()

    if not signature_valid:
        # 진단용: 해시값만 로깅(비밀키 자체는 노출 안 됨) — 원인 파악 후 제거 예정
        logger.warning(
            "instagram_dm webhook 서명 불일치 | app_secret_set=%s received_header=%r "
            "expected_sig=%s received_sig=%s body_len=%d",
            bool(app_secret),
            signature_header[:15] + "..." if signature_header else "(없음)",
            expected_sig,
            signature_header[len("sha256=") :] if signature_header.startswith("sha256=") else signature_header,
            len(raw_body),
        )
        try:
            payload = json.loads(raw_body or b"{}")
        except json.JSONDecodeError:
            payload = {}
        await asyncio.to_thread(
            db.log_webhook_event,
            event_type=payload.get("object"),
            external_account_id=None,
            external_object_id=None,
            signature_valid=False,
            payload_hash=payload_hash,
            payload=payload,
            status="REJECTED",
            error_message="HMAC signature 검증 실패",
        )
        raise HTTPException(status_code=401, detail="signature 검증 실패")

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as e:
        await asyncio.to_thread(
            db.log_webhook_event,
            event_type=None,
            external_account_id=None,
            external_object_id=None,
            signature_valid=True,
            payload_hash=payload_hash,
            payload={},
            status="MALFORMED",
            error_message=str(e),
        )
        raise HTTPException(status_code=400, detail="malformed payload") from e

    await asyncio.to_thread(
        db.log_webhook_event,
        event_type=payload.get("object"),
        external_account_id=None,
        external_object_id=None,
        signature_valid=True,
        payload_hash=payload_hash,
        payload=payload,
        status="RECEIVED",
    )

    await asyncio.to_thread(_ingest_comment_events, payload, background_tasks)

    # Meta 재전송 대비: 빠르게 200 (idempotent — comment_id UNIQUE로 중복 방지됨)
    return {"status": "ok"}


# ── OAuth ────────────────────────────────────────────────────────


@instagram_dm_router.post("/oauth/start")
async def oauth_start():
    if not _app_id() or not _redirect_uri():
        raise HTTPException(status_code=400, detail="META_APP_ID / INSTAGRAM_REDIRECT_URI 미설정")
    state = secrets.token_urlsafe(24)
    _oauth_state_add(state)
    url = build_authorize_url(app_id=_app_id(), redirect_uri=_redirect_uri(), state=state, scopes=_OAUTH_SCOPES)
    return {"auth_url": url, "state": state}


@instagram_dm_router.get("/oauth/callback")
def oauth_callback(code: str = "", state: str = "", error: str = ""):
    if error:
        raise HTTPException(status_code=400, detail=f"Instagram 인가 거부: {error}")
    created = _oauth_states.pop(state, None) if state else None
    if created is None or time.time() - created > _OAUTH_STATE_TTL_SEC:
        raise HTTPException(status_code=400, detail="state 검증 실패(CSRF)")
    if not code:
        raise HTTPException(status_code=400, detail="code 없음")

    try:
        short = exchange_code_for_short_lived_token(
            app_id=_app_id(), app_secret=_app_secret(), redirect_uri=_redirect_uri(), code=code
        )
        short_token = short.get("access_token")
        if not short_token:
            raise HTTPException(status_code=502, detail="Meta OAuth 실패: 단기 토큰 없음")
        ig_user_id = str(short.get("user_id") or "")
        if not ig_user_id:
            # fail-closed: 사용자 식별 없이는 검증·토큰 저장·계정 등록 어느 것도 진행하지 않는다
            raise HTTPException(status_code=502, detail="Meta OAuth 실패: 사용자 ID 없음")
        long_ = exchange_for_long_lived_token(app_secret=_app_secret(), short_lived_token=short_token)
        long_token = long_.get("access_token")
        if not long_token:
            # fail-closed: 장기 토큰 교환 응답에 토큰이 없으면 단기 토큰으로 대체 저장하지 않는다
            raise HTTPException(status_code=502, detail="Meta OAuth 실패: 장기 토큰 없음")
        profile = graph_verify_token(ig_user_id, long_token)
    except InstagramApiError as e:
        raise HTTPException(status_code=502, detail=f"Meta OAuth 실패: {e.error_message or str(e)}") from e

    token_store.save_token(ig_user_id, long_token)
    account_id = db.upsert_account(
        instagram_user_id=ig_user_id,
        username=profile.get("username"),
        account_type=profile.get("account_type"),
        encrypted_access_token=_TOKEN_REF_MARKER,
        scopes=",".join(_OAUTH_SCOPES),
    )
    return {"account_id": account_id, "username": profile.get("username"), "status": "connected"}


# ── Accounts ─────────────────────────────────────────────────────


@instagram_dm_router.get("/accounts")
def list_accounts():
    return [{k: v for k, v in dict(a).items() if k != "encrypted_access_token"} for a in db.list_accounts()]


@instagram_dm_router.post("/accounts/{account_id}/verify")
def verify_account(account_id: str):
    account = db.get_account(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="계정 없음")
    token = token_store.load_token(account["instagram_user_id"])
    if not token:
        raise HTTPException(status_code=400, detail="저장된 토큰 없음 — 재연결 필요")
    try:
        profile = graph_verify_token(account["instagram_user_id"], token)
    except InstagramApiError as e:
        db.set_account_status(account_id, "token_expired" if e.http_status == 401 else "error")
        raise HTTPException(status_code=502, detail=e.error_message or str(e)) from e
    db.set_account_status(account_id, "connected")
    return {"status": "connected", "username": profile.get("username")}


@instagram_dm_router.post("/accounts/{account_id}/disconnect")
def disconnect_account(account_id: str):
    account = db.get_account(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="계정 없음")
    db.set_account_status(account_id, "disconnected")
    return {"status": "disconnected"}


class AutomationToggle(BaseModel):
    enabled: bool


@instagram_dm_router.post("/accounts/{account_id}/automation")
def toggle_account_automation(account_id: str, body: AutomationToggle):
    if db.get_account(account_id) is None:
        raise HTTPException(status_code=404, detail="계정 없음")
    db.set_account_automation_enabled(account_id, body.enabled)
    return {"automation_enabled": body.enabled}


# ── Rules ────────────────────────────────────────────────────────


class RuleCreate(BaseModel):
    instagram_account_id: str
    name: str
    scope_type: str = "ALL_MEDIA"
    media_id: str | None = None
    reply_message: str
    keywords: list[str]
    exclusion_keywords: list[str] = []
    priority: int = 100
    enabled: bool = True


@instagram_dm_router.get("/rules")
def list_rules(instagram_account_id: str):
    return db.list_rules(instagram_account_id)


@instagram_dm_router.post("/rules")
def create_rule(body: RuleCreate):
    if body.scope_type not in {"ALL_MEDIA", "SPECIFIC_MEDIA"}:
        raise HTTPException(status_code=400, detail="scope_type은 ALL_MEDIA|SPECIFIC_MEDIA만 허용")
    if body.scope_type == "SPECIFIC_MEDIA" and not body.media_id:
        raise HTTPException(status_code=400, detail="SPECIFIC_MEDIA는 media_id 필수")
    if not body.keywords:
        raise HTTPException(status_code=400, detail="keywords 최소 1개 필요")
    rule_id = db.create_rule(
        instagram_account_id=body.instagram_account_id,
        name=body.name,
        scope_type=body.scope_type,
        media_id=body.media_id,
        reply_message=body.reply_message,
        keywords=body.keywords,
        exclusion_keywords=body.exclusion_keywords,
        priority=body.priority,
        enabled=body.enabled,
    )
    return {"id": rule_id}


@instagram_dm_router.patch("/rules/{rule_id}")
def update_rule_enabled(rule_id: str, body: AutomationToggle):
    if db.get_rule(rule_id) is None:
        raise HTTPException(status_code=404, detail="rule 없음")
    db.set_rule_enabled(rule_id, body.enabled)
    return {"enabled": body.enabled}


@instagram_dm_router.delete("/rules/{rule_id}")
def remove_rule(rule_id: str):
    if db.get_rule(rule_id) is None:
        raise HTTPException(status_code=404, detail="rule 없음")
    db.delete_rule(rule_id)
    return {"status": "deleted"}


class SimulateRequest(BaseModel):
    instagram_account_id: str
    comment_text: str
    media_id: str | None = None


@instagram_dm_router.post("/rules/simulate")
def simulate(body: SimulateRequest):
    """실제 DM을 보내지 않는다 — rule engine 결과만 반환."""
    account = db.get_account(body.instagram_account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="계정 없음")
    rules = db.list_rules(body.instagram_account_id)
    result = rule_engine.evaluate(
        account_automation_enabled=True,  # simulate는 account on/off와 무관하게 매칭 결과를 보여준다
        comment_text=body.comment_text,
        media_id=body.media_id,
        rules=rules,
    )
    preview_message = None
    if result.matched and result.rule is not None:
        preview_message = rule_engine.render_template(
            result.rule["reply_message"], username="테스트유저", keyword=result.matched_keyword
        )
    return {
        "matched": result.matched,
        "reason": result.reason,
        "matched_rule": {"id": result.rule["id"], "name": result.rule["name"]} if result.rule else None,
        "matched_keyword": result.matched_keyword,
        "preview_dm": preview_message,
    }


# ── Logs / Dashboard ─────────────────────────────────────────────


@instagram_dm_router.get("/comments")
def get_comment_logs(instagram_account_id: str, limit: int = 100):
    return [dict(r) for r in db.list_comment_events(instagram_account_id, limit=limit)]


@instagram_dm_router.get("/private-replies")
def get_reply_logs(instagram_account_id: str, limit: int = 100):
    return [dict(r) for r in db.list_reply_logs(instagram_account_id, limit=limit)]


@instagram_dm_router.get("/dashboard")
def dashboard(instagram_account_id: str):
    return db.dashboard_stats(instagram_account_id)


@instagram_dm_router.get("/health")
def health():
    return {
        "global_enabled": os.environ.get("INSTAGRAM_DM_ENABLED", "false").strip().lower() == "true",
        "dry_run": os.environ.get("INSTAGRAM_DM_DRY_RUN", "true").strip().lower() != "false",
        "connected_accounts": len([a for a in db.list_accounts() if a["status"] == "connected"]),
    }
