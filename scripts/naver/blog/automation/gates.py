"""블로그 자동 작성 실행 전·후 검사 — 전부 순수 함수(입력은 인자로 받고, 시각도 `now` 로 받는다).

기준서: docs/specs/2026-09-30_blog_auto_writing_automation.md (v2, §4 실행 흐름)

하는 일: 지금 실행할 차례인가 / 실행해도 되는가 / 발행까지 가도 되는가 / 이 주제를 써도 되는가 /
글이 기준을 통과했는가 / 중복 발행은 아닌가. 한도·승인·계정 제한은 여기서 코드로 강제한다
(Claude 지시문에 의존하지 않는다).

실행 기록(history) 한 줄의 모양:
    {"rule_id": str, "slot": "YYYY-MM-DD HH:MM", "at": ISO 시각, "status": str, "title": str(선택)}
    status = pending(발행 시도 전 예약) / published / draft_saved / failed / skipped
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from scripts.naver.blog.automation.rules import AUTO_PUBLISH_BLOG_IDS, Rule, is_approval_valid

# content.py / topics.py 의 값과 같아야 한다(어긋나면 테스트가 잡는다).
MIN_BODY_CHARS = 2500
MIN_TAG_COUNT = 15
MIN_SEARCH_VOLUME = 500
RESEARCH_MAX_AGE_DAYS = 30

SLOT_WINDOW_MINUTES = 10  # 예정 시각 뒤 이 시간 안에서만 "차례". 지나면 따라잡지 않는다.
MAX_CONSECUTIVE_FAILURES = 3
STALE_PENDING_MINUTES = 60

COUNTED_STATUSES = frozenset({"pending", "published", "draft_saved"})
DEDUP_STATUSES = frozenset({"pending", "published"})  # failed 는 발행이 안 된 것이라 재시도 허용

AUTO_PUBLISH_BLOCKERS = {
    "mode_draft_only": "규칙이 draft_only 이거나 승인이 없음/무효(규칙이 승인 뒤 수정됨)",
    "account_not_auto_publish": "이 계정은 자동 발행 대상이 아님(사람 검수 필요)",
    "research_not_fresh": "리서치가 없거나 30일을 넘어 주제를 검증할 수 없음",
    "local_draft_run": "네이버에 접근하지 않는 로컬 초안 실행(발행 불가)",
}


# ── 시각·한도 ────────────────────────────────────────────────────────────


def _at(entry: dict[str, Any]) -> datetime | None:
    try:
        return datetime.fromisoformat(entry["at"])
    except (KeyError, TypeError, ValueError):
        return None


def _mine(history: Iterable[dict[str, Any]], rule_id: str) -> list[dict[str, Any]]:
    return [h for h in history if h.get("rule_id") == rule_id]


def due_slot(rule: Rule, now: datetime, history: Iterable[dict[str, Any]]) -> str | None:
    """지금이 예정 시각 창 안이고 그 회차를 아직 안 돌렸으면 회차 키("YYYY-MM-DD HH:MM"), 아니면 None."""
    if now.weekday() not in rule.days:
        return None
    done = {h.get("slot") for h in _mine(history, rule.id)}
    window = timedelta(minutes=SLOT_WINDOW_MINUTES)
    for hhmm in rule.times:
        hour, minute = int(hhmm[:2]), int(hhmm[3:])
        start = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        slot = start.strftime("%Y-%m-%d %H:%M")
        if start <= now < start + window and slot not in done:
            return slot
    return None


def count_posts(history: Iterable[dict[str, Any]], rule_id: str, now: datetime, *, days: int) -> int:
    """오늘을 포함한 최근 days 일 동안 글을 만든(예약·발행·초안 저장) 회차 수."""
    first_day = (now - timedelta(days=days - 1)).date()
    total = 0
    for entry in _mine(history, rule_id):
        at = _at(entry)
        if at and entry.get("status") in COUNTED_STATUSES and first_day <= at.date() <= now.date():
            total += 1
    return total


def consecutive_failures(history: Iterable[dict[str, Any]], rule_id: str) -> int:
    """가장 최근 기록부터 거꾸로 세어 이어진 failed 횟수. skipped 는 건너뛰고, 그 밖의 상태에서 멈춘다."""
    dated = [(at, h) for h in _mine(history, rule_id) if (at := _at(h))]
    count = 0
    for _at_time, entry in sorted(dated, key=lambda pair: pair[0], reverse=True):
        status = entry.get("status")
        if status == "skipped":
            continue
        if status != "failed":
            break
        count += 1
    return count


def gap_remaining_seconds(rule: Rule, now: datetime, history: Iterable[dict[str, Any]]) -> float:
    """마지막 회차로부터 gap_seconds 가 지나려면 더 기다려야 하는 초(0 이면 통과)."""
    times = [at for h in _mine(history, rule.id) if h.get("status") in COUNTED_STATUSES and (at := _at(h))]
    if not times:
        return 0.0
    return max(0.0, rule.gap_seconds - (now - max(times)).total_seconds())


# ── 실행 판정 ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RunContext:
    now: datetime
    login_state: str  # "in" / "out" / "unknown" (요소 기준 로그인 판정 결과)
    blog_alias_matches: bool | None  # 화면의 블로그 공개 주소 == 대상 계정 (None = 확인 불가)
    claude_available: bool
    research_age_days: float | None  # None = 리서치 파일 없음
    history: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class RunDecision:
    run: bool
    publish: bool
    slot: str | None
    blockers: tuple[str, ...]  # run 을 막는 이유
    publish_blockers: tuple[str, ...]  # run 은 되지만 발행은 막는 이유


def _naver_blockers(ctx: RunContext) -> list[str]:
    """네이버에 접근하는 실행의 사전 조건 — 로그인이 확인돼야 하고 대상 계정과 일치해야 한다."""
    blockers: list[str] = []
    if ctx.login_state != "in":
        blockers.append(f"login_{ctx.login_state}")
    if ctx.blog_alias_matches is not True:
        blockers.append("blog_account_mismatch" if ctx.blog_alias_matches is False else "blog_account_unknown")
    return blockers


def _run_blockers(rule: Rule, ctx: RunContext, slot: str | None, *, scheduled: bool, uses_naver: bool) -> list[str]:
    blockers: list[str] = []
    if rule.paused:
        blockers.append("paused")
    if consecutive_failures(ctx.history, rule.id) >= MAX_CONSECUTIVE_FAILURES:
        blockers.append("auto_paused_failures")
    if scheduled and slot is None:
        blockers.append("not_due")
    if uses_naver:
        blockers += _naver_blockers(ctx)
    if not ctx.claude_available:
        blockers.append("claude_unavailable")
    if rule.use_research and not _research_fresh(ctx):
        blockers.append("research_stale")
    return blockers


def _limit_blockers(rule: Rule, ctx: RunContext) -> list[str]:
    blockers: list[str] = []
    if count_posts(ctx.history, rule.id, ctx.now, days=1) >= rule.per_day:
        blockers.append("daily_limit")
    if count_posts(ctx.history, rule.id, ctx.now, days=7) >= rule.per_week:
        blockers.append("weekly_limit")
    if gap_remaining_seconds(rule, ctx.now, ctx.history) > 0:
        blockers.append("gap_wait")
    return blockers


def _research_fresh(ctx: RunContext) -> bool:
    return ctx.research_age_days is not None and ctx.research_age_days <= RESEARCH_MAX_AGE_DAYS


def _publish_blockers(rule: Rule, ctx: RunContext, auto_publish_blog_ids: frozenset[str]) -> list[str]:
    blockers: list[str] = []
    if rule.mode != "auto_publish" or not is_approval_valid(rule):
        blockers.append("mode_draft_only")
    if rule.blog_id not in auto_publish_blog_ids:
        blockers.append("account_not_auto_publish")
    if not _research_fresh(ctx):
        blockers.append("research_not_fresh")
    return blockers


def evaluate_run(
    rule: Rule,
    ctx: RunContext,
    *,
    auto_publish_blog_ids: frozenset[str] = AUTO_PUBLISH_BLOG_IDS,
    scheduled: bool = True,
    uses_naver: bool = True,
) -> RunDecision:
    """이 규칙을 지금 실행해도 되는지, 실행하면 발행까지 가도 되는지 판정한다.

    scheduled=False: 사용자가 "지금 실행"을 눌렀을 때 — 예정 시각을 보지 않는다.
    uses_naver=False: 네이버에 접근하지 않는 실행(로컬 초안 생성) — 로그인 조건을 보지 않고, 발행은 항상 막는다.
    한도·간격·일시정지·연속 실패·Claude·리서치 조건은 어느 경우에도 그대로 적용한다.
    """
    slot = due_slot(rule, ctx.now, ctx.history)
    blockers = [
        *_run_blockers(rule, ctx, slot, scheduled=scheduled, uses_naver=uses_naver),
        *_limit_blockers(rule, ctx),
    ]
    publish_blockers = _publish_blockers(rule, ctx, auto_publish_blog_ids)
    if not uses_naver:
        publish_blockers.append("local_draft_run")
    run = not blockers
    return RunDecision(
        run=run,
        publish=run and not publish_blockers,
        slot=slot,
        blockers=tuple(blockers),
        publish_blockers=tuple(publish_blockers),
    )


# ── 주제 ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TopicVerdict:
    verified: bool
    reasons: tuple[str, ...]


def verify_topic(
    topic: dict[str, Any], research: dict[str, Any] | None, *, min_volume: int = MIN_SEARCH_VOLUME
) -> TopicVerdict:
    """사용자가 입력한 주제를 리서치 지표로 검증한다: 키워드 중 하나가 월 검색량 min_volume 이상이고
    그 키워드로 지식iN 실제 질문이 있어야 통과. 리서치가 없으면 검증 불가(미검증)."""
    if not research:
        return TopicVerdict(False, ("no_research",))
    volumes = {
        row.get("keyword"): row.get("total_search", 0) for row in research.get("keywords", []) if isinstance(row, dict)
    }
    asked = {
        row.get("keyword") for row in research.get("topics", []) if isinstance(row, dict) and row.get("question_title")
    }
    keywords = [k for k in topic.get("keywords", []) if isinstance(k, str)]
    with_volume = [k for k in keywords if isinstance(volumes.get(k), int | float) and volumes[k] >= min_volume]
    if not with_volume:
        return TopicVerdict(False, ("volume_below_min",))
    if not any(k in asked for k in with_volume):
        return TopicVerdict(False, ("no_real_question",))
    return TopicVerdict(True, ())


@dataclass(frozen=True)
class Candidate:
    topic: dict[str, Any]
    source: str  # "user" / "research"
    verified: bool  # 검증되지 않은 주제는 초안까지만(자동 발행 제외)


def rank_candidates(
    rule: Rule,
    research: dict[str, Any] | None,
    research_topics: Iterable[dict[str, Any]],
    is_duplicate: Callable[[str], bool],
) -> list[Candidate]:
    """사용자 입력 주제 → 리서치 주제 순으로, 중복이 아닌 것만. AI 가 새로 지어낸 주제는 받지 않는다.

    research_topics 는 기존 로더(topics.get_researched_topics 등)가 만든 topic_info — 리서치 결과 자체라
    검증된 것으로 본다. 사용자 주제는 verify_topic 으로 검증한다.
    """
    out: list[Candidate] = []
    for topic in rule.user_topics:
        if not is_duplicate(topic["topic"]):
            out.append(Candidate(dict(topic), "user", verify_topic(topic, research).verified))
    if rule.use_research:
        for topic in research_topics:
            if topic.get("topic") and not is_duplicate(topic["topic"]):
                out.append(Candidate(dict(topic), "research", True))
    return out


# ── 글 검사 ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class QualityVerdict:
    ok: bool
    reasons: tuple[str, ...]


def check_quality(
    post: dict[str, Any],
    seo: dict[str, Any],
    rule: Rule,
    *,
    min_body_chars: int = MIN_BODY_CHARS,
    min_tags: int = MIN_TAG_COUNT,
) -> QualityVerdict:
    """생성된 글이 자동 발행 기준을 통과했는지. seo 는 content.seo_check 의 반환값 그대로 받는다.

    seo_check 는 경고만 낼 뿐 막지 않으므로 여기서 "경고가 하나라도 있으면 통과 못 함"으로 강제한다
    (검증 필요 수치·결론 문단 없음·마크다운 잔존 등 모두 포함).
    """
    reasons = [f"seo:{w}" for w in seo.get("warnings", [])]
    title, body = str(post.get("title", "")), str(post.get("body", ""))
    if len(body) < min_body_chars:
        reasons.append(f"body_too_short:{len(body)}")
    if len(post.get("tags", [])) < min_tags:
        reasons.append(f"too_few_tags:{len(post.get('tags', []))}")
    haystack = f"{title}\n{body}".lower()
    reasons += [f"forbidden_word:{w}" for w in rule.forbidden_words if w.lower() in haystack]
    return QualityVerdict(not reasons, tuple(reasons))


def pick_cta(product_related: bool) -> str:
    """제품 관련 주제만 표준 CTA(검증된 실측치). 그 밖은 정직한 포지셔닝 문구를 주제마다 새로 쓴다(기준서 §4)."""
    return "standard" if product_related else "positioning"


# ── 중복 발행 ────────────────────────────────────────────────────────────


def is_duplicate_or_pending(title: str, entries: Iterable[dict[str, Any]], key_fn: Callable[[str], str]) -> bool:
    """이미 발행됐거나 발행 시도 중(pending)인 제목인가. failed 는 발행이 안 된 것이라 재시도 허용.

    key_fn 은 기존 topics.topic_key 를 그대로 넘긴다(중복 판정 방식을 바꾸지 않는다).
    """
    key, lowered = key_fn(title), title.strip().lower()
    for entry in entries:
        if entry.get("status") not in DEDUP_STATUSES:
            continue
        if entry.get("key") == key or str(entry.get("title", "")).strip().lower() == lowered:
            return True
    return False


def is_topic_used(topic: str, history: Iterable[dict[str, Any]]) -> bool:
    """이 주제(원문 문자열)로 이미 글을 만들었는가 — 초안 저장·발행 시도·발행 모두 포함.

    초안만 만들고 발행하지 않은 주제를 다음 회차가 또 고르면 같은 주제 초안이 쌓이므로,
    사용자가 초안을 버리거나 발행하기 전까지는 그 주제를 다시 쓰지 않는다. 실패(failed)는 재시도 허용.
    """
    wanted = topic.strip().lower()
    used = DEDUP_STATUSES | {"draft_saved"}
    return any(e.get("status") in used and str(e.get("topic", "")).strip().lower() == wanted for e in history)


def stale_pending(
    entries: Iterable[dict[str, Any]], now: datetime, *, max_minutes: int = STALE_PENDING_MINUTES
) -> list[dict[str, Any]]:
    """오래 pending 인 기록 — 발행됐는지 알 수 없어 사람이 확인해야 한다(2026-08-17 이중 발행 사고 유형)."""
    limit = timedelta(minutes=max_minutes)
    return [e for e in entries if e.get("status") == "pending" and (at := _at(e)) and now - at > limit]
