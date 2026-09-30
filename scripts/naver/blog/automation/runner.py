"""1회 실행 — 주제 선정 → 글 생성 → 검사 → 로컬 초안 저장.

기준서: docs/specs/2026-09-30_blog_auto_writing_automation.md (v2 §4, B단계)

**B단계는 네이버에 아무것도 쓰지 않는다.** 결과는 `data/blog_automation/drafts/` 의 로컬 초안과 실행 기록뿐이다.
외부 의존(Claude·리서치 파일·발행 캐시·글 생성 함수)은 전부 `RunnerDeps` 로 주입받아 테스트에서 가짜로 바꾼다.
실제 부품 연결은 `default_deps()` 한 곳에만 있다.
"""

from __future__ import annotations

import contextlib
import io
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.naver.blog.automation import gates as G
from scripts.naver.blog.automation.rules import Rule
from scripts.naver.blog.automation.store import ROOT, Store

_MAX_RESEARCH_TOPICS = 100


@dataclass(frozen=True)
class RunnerDeps:
    store: Store
    llm: Callable[..., dict[str, Any]]
    now: Callable[[], datetime]
    load_research: Callable[[str], dict[str, Any] | None]  # blog_id → 리서치 결과(없으면 None)
    research_topics: Callable[[str], list[dict[str, Any]]]  # blog_id → topic_info 목록(AI 보충 없이)
    published_entries: Callable[[str], list[dict[str, Any]]]  # blog_id → 기존 발행 이력(title/key)
    topic_key: Callable[[str], str]
    product_related: Callable[[dict[str, Any]], bool]
    generate_post: Callable[..., dict[str, Any] | None]
    claude_available: Callable[[], bool]
    contact: tuple[str, str]  # (홈페이지, 전화번호)


def research_age_days(research: dict[str, Any] | None, now: datetime) -> float | None:
    """리서치 파일이 만들어진 지 며칠 됐는가. 없거나 시각을 못 읽으면 None."""
    try:
        made = datetime.fromisoformat(str((research or {})["generated_at"]))
    except (KeyError, ValueError):
        return None
    return max(0.0, (now - made).total_seconds() / 86400)


def positioning_cta(topic: str, contact: tuple[str, str]) -> str:
    """검증된 구체 기능이 없는 주제용 CTA — 기준서 §4 의 정직한 포지셔닝.

    "이미 이 기능이 있다"고 하지 않는다. 적산·물량산출은 검증 사례가 있다는 사실만 근거로 대고,
    오늘 글의 문제는 자동화가 가능한지 검토해 준다고만 말한다.
    """
    homepage, phone = contact
    short = topic.strip()[:40]
    return (
        f"\n\n📌 {short}, 매번 손으로 하기 번거로우시죠\n\n"
        "해한 AI는 건설 실무의 반복 업무를 AI로 자동화하는 회사입니다.\n"
        "적산·물량산출은 이미 검증된 사례가 있고, 오늘 글에서 다룬 것처럼 반복되는 업무도 "
        "AI로 자동화할 수 있는지 함께 검토해 드립니다. (이 주제의 기능이 이미 만들어져 있다는 뜻은 아닙니다.)\n\n"
        "도입하고 싶으시거나, 직접 다뤄보고 싶어서 개인 교습을 받아보고 싶으시면 편하게 연락 주세요.\n\n"
        f"👉 도입 문의 · 개인 교습 문의 {homepage} · {phone}"
    )


def _as_research_record(topic: dict[str, Any]) -> dict[str, Any]:
    """topic_info(topic·keywords) → 기존 `is_product_related` 가 읽는 모양(keyword·question_title)."""
    keywords = topic.get("keywords") or [""]
    return {"keyword": keywords[0], "question_title": topic.get("topic", "")}


def _duplicate_checker(rule: Rule, deps: RunnerDeps, history: tuple[dict[str, Any], ...]) -> Callable[[str], bool]:
    legacy = [{**e, "status": "published"} for e in deps.published_entries(rule.blog_id)]
    entries = [*legacy, *history]

    def is_duplicate(title: str) -> bool:
        return G.is_topic_used(title, history) or G.is_duplicate_or_pending(title, entries, deps.topic_key)

    return is_duplicate


def _generate_checked(
    rule: Rule, topic: dict[str, Any], cta_block: str | None, deps: RunnerDeps
) -> tuple[dict[str, Any] | None, G.QualityVerdict | None]:
    """글 생성 + 검사. seo 경고가 있으면 경고 문구를 되먹여 1회 다시 쓰고, 더 나은 쪽을 고른다."""
    post = deps.generate_post(topic, llm=deps.llm, cta_block=cta_block, blog_id=rule.blog_id)
    if post is None:
        return None, None
    quality = G.check_quality(post, post.get("seo") or {}, rule)
    seo_reasons = [r[len("seo:") :] for r in quality.reasons if r.startswith("seo:")]
    if quality.ok or not seo_reasons:
        return post, quality
    hint = f"검사에서 걸린 문제: {'; '.join(seo_reasons)}. 이 문제를 고쳐서 처음부터 다시 쓰세요."
    second = deps.generate_post(
        {**topic, "revision_note": hint}, llm=deps.llm, cta_block=cta_block, blog_id=rule.blog_id
    )
    if second is None:
        return post, quality
    second_quality = G.check_quality(second, second.get("seo") or {}, rule)
    return (second, second_quality) if len(second_quality.reasons) <= len(quality.reasons) else (post, quality)


def _record(deps: RunnerDeps, rule: Rule, slot: str, now: datetime, status: str, **extra: Any) -> None:
    deps.store.upsert_history(
        {"rule_id": rule.id, "slot": slot, "at": now.isoformat(timespec="seconds"), "status": status, **extra}
    )


def run_once(rule: Rule, deps: RunnerDeps, *, manual: bool = True) -> dict[str, Any]:
    """규칙 1회 실행. 반환 status: blocked / no_topic / failed / draft_saved (네이버 접근 없음)."""
    now = deps.now()
    history = tuple(deps.store.load_history())
    research = deps.load_research(rule.blog_id)
    ctx = G.RunContext(
        now=now,
        login_state="unknown",
        blog_alias_matches=None,
        claude_available=deps.claude_available(),
        research_age_days=research_age_days(research, now),
        history=history,
    )
    decision = G.evaluate_run(rule, ctx, scheduled=not manual, uses_naver=False)
    if not decision.run:
        return {"ok": False, "status": "blocked", "blockers": list(decision.blockers)}

    slot = f"manual {now:%Y-%m-%d %H:%M:%S}" if manual else (decision.slot or "")
    research_topics = deps.research_topics(rule.blog_id) if rule.use_research else []
    candidates = G.rank_candidates(rule, research, research_topics, _duplicate_checker(rule, deps, history))
    if not candidates:
        return {"ok": False, "status": "no_topic", "blockers": []}

    chosen = candidates[0]
    topic = chosen.topic
    cta_kind = G.pick_cta(deps.product_related(_as_research_record(topic)))
    cta_block = None if cta_kind == "standard" else positioning_cta(topic["topic"], deps.contact)
    try:
        post, quality = _generate_checked(rule, topic, cta_block, deps)
    except Exception as exc:  # noqa: BLE001 - 외부 생성 호출의 어떤 실패도 "실패 회차"로 기록하고 다음 회차에 맡긴다(예외로 서버를 죽이지 않음)
        post, quality = None, None
        _record(deps, rule, slot, now, "failed", topic=topic["topic"], reason=f"exception:{type(exc).__name__}")
        return {"ok": False, "status": "failed", "reason": f"exception:{type(exc).__name__}"}
    if post is None or quality is None:
        _record(deps, rule, slot, now, "failed", topic=topic["topic"], reason="generation_failed")
        return {"ok": False, "status": "failed", "reason": "generation_failed"}

    publishable = quality.ok and chosen.verified
    payload = {
        "rule_id": rule.id,
        "generated_at": now.isoformat(timespec="seconds"),
        "topic": topic,
        "source": chosen.source,
        "verified": chosen.verified,
        "cta_kind": cta_kind,
        "post": post,
        "quality": {"ok": quality.ok, "reasons": list(quality.reasons)},
        "publishable": publishable,
    }
    path = deps.store.save_draft(rule.id, payload, stamp=now.strftime("%Y%m%d%H%M%S"))
    _record(
        deps,
        rule,
        slot,
        now,
        "draft_saved",
        topic=topic["topic"],
        title=post.get("title", ""),
        key=deps.topic_key(post.get("title", "")),
        quality_ok=quality.ok,
        publishable=publishable,
    )
    return {
        "ok": True,
        "status": "draft_saved",
        "draft": path.name,
        "title": post.get("title", ""),
        "source": chosen.source,
        "verified": chosen.verified,
        "cta_kind": cta_kind,
        "quality_ok": quality.ok,
        "quality_reasons": list(quality.reasons),
        "publishable": publishable,
    }


def default_deps(store: Store | None = None, *, model: str | None = None, web_research: bool = False) -> RunnerDeps:
    """실제 부품(기존 marketing 파이프라인·claude -p)을 연결한다. 테스트는 이 함수를 쓰지 않는다.

    web_research=True 면 Claude 에게 읽기 전용 웹 도구(WebSearch·WebFetch)만 허용한다(시간·비용이 늘어난다).
    """
    from scripts.naver.blog import accounts
    from scripts.naver.blog.automation.llm import READ_ONLY_WEB_TOOLS, claude_available, make_claude_llm
    from scripts.naver.blog.automation.writer import draft_post
    from scripts.naver.blog.marketing import content, topics

    def load_research(blog_id: str) -> dict[str, Any] | None:
        raw = accounts.get_account(blog_id).get("topic_research_file") or str(topics.RESEARCH_FILE)
        path = Path(raw) if Path(raw).is_absolute() else ROOT / raw
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def research_topics(blog_id: str) -> list[dict[str, Any]]:
        if blog_id != accounts.DEFAULT_ACCOUNT:
            return []  # 조명 계정용 리서치 주제 로더는 아직 없다(기존 로더는 건설 리서치 파일만 읽음)
        # generate_topics(dry_run=True) 는 리서치 결과만 쓰고 AI 보충 생성을 하지 않는다(안내 출력만 삼킨다).
        with contextlib.redirect_stdout(io.StringIO()):
            return topics.generate_topics(topics.load_cache(blog_id), _MAX_RESEARCH_TOPICS, dry_run=True)

    return RunnerDeps(
        store=store or Store(),
        llm=make_claude_llm(model=model, tools=tuple(sorted(READ_ONLY_WEB_TOOLS)) if web_research else ()),
        now=datetime.now,
        load_research=load_research,
        research_topics=research_topics,
        published_entries=lambda blog_id: topics.load_cache(blog_id).get("posted", []),
        topic_key=topics.topic_key,
        product_related=topics.is_product_related,
        generate_post=lambda topic, llm, cta_block, blog_id: draft_post(
            topic, llm=llm, cta_block=cta_block, blog_id=blog_id, web=web_research
        ),
        claude_available=claude_available,
        contact=(content.HOMEPAGE_URL, content.CONTACT_PHONE),
    )
