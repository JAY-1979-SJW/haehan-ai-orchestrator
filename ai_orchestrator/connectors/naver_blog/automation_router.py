"""블로그 자동 작성 API — 규칙 관리·승인·1회 실행·기록 조회. HTTP 처리만 한다(업무 로직은 scripts/naver/blog/automation).

기준서: docs/specs/2026-09-30_blog_auto_writing_automation.md (v2, B단계)

**B단계는 네이버에 아무것도 쓰지 않는다.** run-now 는 로컬 초안(data/blog_automation/drafts)까지만 만든다.
- 규칙 저장 시 클라이언트가 보낸 `approval` 은 무시한다(승인 위조 방지). 승인은 approve 엔드포인트로만, `owner` 만 가능.
- 규칙 내용이 바뀌면 rule_hash 가 달라져 기존 승인이 자동으로 무효가 된다(응답의 approval_valid 로 확인).
- 엔드포인트는 `def` 다 — FastAPI 가 스레드풀에서 실행하므로 수 분 걸리는 run-now 도 서버를 막지 않는다.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from scripts.common.realtime_audit import emit_event
from scripts.naver.blog import accounts
from scripts.naver.blog.automation import gates, rules
from scripts.naver.blog.automation import runner as automation_runner
from scripts.naver.blog.automation.llm import claude_available
from scripts.naver.blog.automation.store import ROOT, Store, StoreError
from tools.gates.auth import require_role

blog_automation_router = APIRouter(prefix="/naver/blog/automation", tags=["naver-blog-automation"])

_store = Store()
_RUNNING: set[str] = set()
_RUNNING_LOCK = threading.Lock()
_DRAFT_FILE_RE = re.compile(r"^[A-Za-z0-9_.-]+\.json$")
_DEFAULT_RESEARCH_FILE = "data/blog_topic_research_latest.json"

DepsFactory = Callable[[Store, bool], automation_runner.RunnerDeps]


def get_store() -> Store:
    return _store


def get_deps_factory() -> DepsFactory:
    return lambda store, web: automation_runner.default_deps(store, web_research=web)


def _known_blog_ids() -> frozenset[str]:
    return frozenset(accounts.BLOG_ACCOUNTS)


def _audit(action: str, rule_id: str, user: dict, *, risk: str = "low", **meta: Any) -> None:
    emit_event(
        "NAVER_BLOG_AUTO_RULE",
        site="naver_blog",
        workflow="blog_automation",
        status=action,
        risk=risk,
        actor=str(user.get("actor", "unknown")),
        metadata={"rule_id": rule_id, **meta},
    )


def _view(rule: rules.Rule) -> dict[str, Any]:
    """저장용 사전 + 화면이 바로 쓸 계산값."""
    return {
        **rules.rule_to_dict(rule),
        "rule_hash": rules.rule_hash(rule),
        "approval_valid": rules.is_approval_valid(rule),
        "effective_mode": rules.effective_mode(rule),
    }


def _valid_id_or_400(rule_id: str) -> str:
    if not rules.is_valid_rule_id(rule_id):
        raise HTTPException(status_code=400, detail="규칙 id 는 영문·숫자·_·- 1~64자")
    return rule_id


def _load_or_404(store: Store, rule_id: str) -> rules.Rule:
    try:
        rule = store.load_rule(_valid_id_or_400(rule_id), known_blog_ids=_known_blog_ids())
    except StoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if rule is None:
        raise HTTPException(status_code=404, detail="규칙을 찾을 수 없음")
    return rule


def _research_age(blog_id: str, now: datetime) -> float | None:
    raw = accounts.get_account(blog_id).get("topic_research_file") or _DEFAULT_RESEARCH_FILE
    path = Path(raw) if Path(raw).is_absolute() else ROOT / raw
    try:
        return automation_runner.research_age_days(json.loads(path.read_text(encoding="utf-8")), now)
    except (OSError, ValueError):
        return None


# ── 상태 ─────────────────────────────────────────────────────────────────


@blog_automation_router.get("/status")
def automation_status(user: dict = Depends(require_role("admin", "owner"))) -> dict[str, Any]:
    """화면 상단에 보여 줄 실행 환경: Claude 사용 가능 여부, 계정별 리서치 신선도, 자동 발행 허용 계정."""
    now = datetime.now()
    research = {}
    for blog_id in sorted(accounts.BLOG_ACCOUNTS):
        age = _research_age(blog_id, now)
        research[blog_id] = {
            "age_days": None if age is None else round(age, 1),
            "fresh": age is not None and age <= gates.RESEARCH_MAX_AGE_DAYS,
        }
    return {
        "claude_available": claude_available(),
        "research": research,
        "research_max_age_days": gates.RESEARCH_MAX_AGE_DAYS,
        "auto_publish_blog_ids": sorted(rules.AUTO_PUBLISH_BLOG_IDS),
        "blog_ids": sorted(accounts.BLOG_ACCOUNTS),
        "publishes_to_naver": False,  # B단계: 로컬 초안까지만
    }


# ── 규칙 ─────────────────────────────────────────────────────────────────


@blog_automation_router.get("/rules")
def list_rules(
    user: dict = Depends(require_role("admin", "owner")),
    store: Store = Depends(get_store),
) -> dict[str, Any]:
    found, broken = store.list_rules(known_blog_ids=_known_blog_ids())
    return {"rules": [_view(r) for r in found], "broken": broken}


@blog_automation_router.put("/rules/{rule_id}")
def save_rule(
    rule_id: str,
    body: dict[str, Any],
    user: dict = Depends(require_role("admin", "owner")),
    store: Store = Depends(get_store),
) -> dict[str, Any]:
    """규칙 저장(생성·수정). body 의 approval 은 무시하고, 저장돼 있던 승인 기록을 그대로 유지한다
    (내용이 바뀌었으면 해시가 달라져 approval_valid 가 false 가 된다)."""
    _valid_id_or_400(rule_id)
    if body.get("id", rule_id) != rule_id:
        raise HTTPException(status_code=400, detail="본문의 id 와 주소의 id 가 다름")
    try:
        existing = store.load_rule(rule_id, known_blog_ids=_known_blog_ids())
    except StoreError:
        existing = None  # 손상된 파일은 새 내용으로 덮어쓴다
    data = {**body, "id": rule_id, "approval": existing.approval if existing else None}
    if existing is not None and "paused" not in body:
        data["paused"] = existing.paused
    rule, errors = rules.parse_rule(data, known_blog_ids=_known_blog_ids())
    if rule is None:
        raise HTTPException(status_code=422, detail=errors)
    store.save_rule(rule)
    _audit("saved", rule_id, user, mode=rule.mode, blog_id=rule.blog_id)
    return _view(rule)


@blog_automation_router.delete("/rules/{rule_id}")
def delete_rule(
    rule_id: str,
    user: dict = Depends(require_role("admin", "owner")),
    store: Store = Depends(get_store),
) -> dict[str, Any]:
    if not store.delete_rule(_valid_id_or_400(rule_id)):
        raise HTTPException(status_code=404, detail="규칙을 찾을 수 없음")
    _audit("deleted", rule_id, user)
    return {"ok": True}


@blog_automation_router.post("/rules/{rule_id}/approve")
def approve_rule(
    rule_id: str,
    user: dict = Depends(require_role("owner")),
    store: Store = Depends(get_store),
) -> dict[str, Any]:
    """지금 저장된 내용 그대로를 승인한다(owner 만). 이후 규칙을 수정하면 승인은 무효가 된다."""
    rule = _load_or_404(store, rule_id)
    if rule.mode != "auto_publish":
        raise HTTPException(status_code=409, detail="mode 가 auto_publish 인 규칙만 승인할 수 있음")
    approved = rules.approve(rule, str(user.get("actor", "")), datetime.now())
    store.save_rule(approved)
    _audit("approved", rule_id, user, risk="high", rule_hash=rules.rule_hash(approved))
    return {**_view(approved), "summary": rules.approval_summary(approved)}


def _set_paused(rule_id: str, paused: bool, user: dict, store: Store) -> dict[str, Any]:
    rule = replace(_load_or_404(store, rule_id), paused=paused)
    store.save_rule(rule)
    _audit("paused" if paused else "resumed", rule_id, user)
    return _view(rule)


@blog_automation_router.post("/rules/{rule_id}/pause")
def pause_rule(
    rule_id: str, user: dict = Depends(require_role("admin", "owner")), store: Store = Depends(get_store)
) -> dict[str, Any]:
    return _set_paused(rule_id, True, user, store)


@blog_automation_router.post("/rules/{rule_id}/resume")
def resume_rule(
    rule_id: str, user: dict = Depends(require_role("admin", "owner")), store: Store = Depends(get_store)
) -> dict[str, Any]:
    return _set_paused(rule_id, False, user, store)


# ── 실행 ─────────────────────────────────────────────────────────────────


@blog_automation_router.post("/rules/{rule_id}/run-now")
def run_now(
    rule_id: str,
    web_research: bool = False,
    user: dict = Depends(require_role("admin", "owner")),
    store: Store = Depends(get_store),
    factory: DepsFactory = Depends(get_deps_factory),
) -> dict[str, Any]:
    """규칙 1회 실행(로컬 초안 생성). 수 분 걸릴 수 있다. 같은 규칙이 실행 중이면 409.

    web_research=true 면 Claude 에게 읽기 전용 웹 도구만 허용한다(시간·비용 증가). 네이버에는 쓰지 않는다.
    """
    rule = _load_or_404(store, rule_id)
    with _RUNNING_LOCK:
        if rule_id in _RUNNING:
            raise HTTPException(status_code=409, detail="이미 실행 중")
        _RUNNING.add(rule_id)
    try:
        result = automation_runner.run_once(rule, factory(store, web_research), manual=True)
    finally:
        with _RUNNING_LOCK:
            _RUNNING.discard(rule_id)
    emit_event(
        "NAVER_BLOG_AUTO_RUN",
        site="naver_blog",
        workflow="blog_automation",
        status=str(result.get("status")),
        risk="low",
        actor=str(user.get("actor", "unknown")),
        metadata={"rule_id": rule_id, "web_research": web_research, "blockers": result.get("blockers", [])},
    )
    return result


# ── 기록·초안 ────────────────────────────────────────────────────────────


@blog_automation_router.get("/history")
def history(
    rule_id: str | None = None,
    limit: int = 50,
    user: dict = Depends(require_role("admin", "owner")),
    store: Store = Depends(get_store),
) -> dict[str, Any]:
    if rule_id is not None:
        _valid_id_or_400(rule_id)
    entries = [e for e in store.load_history() if rule_id is None or e.get("rule_id") == rule_id]
    return {"history": list(reversed(entries))[: max(1, min(limit, 500))]}


@blog_automation_router.get("/drafts")
def drafts(
    rule_id: str | None = None,
    limit: int = 30,
    user: dict = Depends(require_role("admin", "owner")),
    store: Store = Depends(get_store),
) -> dict[str, Any]:
    try:
        return {"drafts": store.list_drafts(rule_id, limit=max(1, min(limit, 200)))}
    except StoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@blog_automation_router.get("/drafts/{file}")
def draft_detail(
    file: str,
    user: dict = Depends(require_role("admin", "owner")),
    store: Store = Depends(get_store),
) -> dict[str, Any]:
    """초안 1건 전체(본문 포함). 파일 이름은 영문·숫자·_·.- 와 .json 만 허용하고 초안 폴더 밖은 읽지 않는다."""
    if not _DRAFT_FILE_RE.match(file) or ".." in file:
        raise HTTPException(status_code=400, detail="잘못된 초안 파일 이름")
    path = (store.drafts_dir / file).resolve()
    if store.drafts_dir.resolve() not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="초안을 찾을 수 없음")
    return json.loads(path.read_text(encoding="utf-8"))
