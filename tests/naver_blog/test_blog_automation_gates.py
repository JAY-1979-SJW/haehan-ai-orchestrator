"""블로그 자동 작성 실행 전·후 검사 — 실행 판정·한도·주제 검증·글 검사·중복 예약. 기준서 v2 §4."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from scripts.naver.blog.automation import gates as G
from scripts.naver.blog.automation import rules as R

MONDAY_9_03 = datetime(2026, 10, 5, 9, 3)  # 월요일
assert MONDAY_9_03.weekday() == 0


def rule(**over):
    data = {
        "id": "r1",
        "name": "건설 주 3회",
        "blog_id": "skyjwsin",
        "user_topics": [{"topic": "직접입력 주제", "keywords": ["하도급지킴이"]}],
        "use_research": True,
        "days": [0, 2, 4],
        "times": ["09:00"],
        "per_day": 1,
        "per_week": 3,
        "gap_seconds": 90,
        "forbidden_words": ["최고의"],
        "visibility": "public",
        "mode": "auto_publish",
    }
    data.update(over)
    parsed, errors = R.parse_rule(data)
    assert not errors
    return parsed


def approved(**over):
    return R.approve(rule(**over), "owner", MONDAY_9_03)


def entry(status, at, *, slot="x", rule_id="r1", **extra):
    return {"rule_id": rule_id, "slot": slot, "at": at.isoformat(), "status": status, **extra}


def ctx(**over):
    base = {
        "now": MONDAY_9_03,
        "login_state": "in",
        "blog_alias_matches": True,
        "claude_available": True,
        "research_age_days": 3.0,
        "history": (),
    }
    base.update(over)
    return G.RunContext(**base)


# ── 회차 ─────────────────────────────────────────────────────────────────


def test_due_slot_inside_window():
    assert G.due_slot(rule(), MONDAY_9_03, []) == "2026-10-05 09:00"


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 10, 5, 8, 59),  # 예정 전
        datetime(2026, 10, 5, 9, G.SLOT_WINDOW_MINUTES),  # 창이 막 끝남 — 따라잡지 않는다
        datetime(2026, 10, 6, 9, 3),  # 화요일(규칙은 월·수·금)
    ],
)
def test_not_due_outside_window_or_day(now):
    assert G.due_slot(rule(), now, []) is None


def test_slot_already_run_is_not_due_again():
    done = [entry("published", MONDAY_9_03, slot="2026-10-05 09:00")]
    assert G.due_slot(rule(), MONDAY_9_03, done) is None


def test_other_rules_history_does_not_block_slot():
    other = [entry("published", MONDAY_9_03, slot="2026-10-05 09:00", rule_id="other")]
    assert G.due_slot(rule(), MONDAY_9_03, other) == "2026-10-05 09:00"


def test_second_time_of_day_is_due_independently():
    r = rule(times=["09:00", "18:00"])
    done = [entry("published", MONDAY_9_03, slot="2026-10-05 09:00")]
    assert G.due_slot(r, datetime(2026, 10, 5, 18, 2), done) == "2026-10-05 18:00"


# ── 한도·연속 실패·간격 ──────────────────────────────────────────────────


def test_count_posts_counts_only_post_producing_statuses():
    history = [
        entry("pending", MONDAY_9_03),
        entry("published", MONDAY_9_03),
        entry("draft_saved", MONDAY_9_03),
        entry("failed", MONDAY_9_03),
        entry("skipped", MONDAY_9_03),
    ]
    assert G.count_posts(history, "r1", MONDAY_9_03, days=1) == 3


def test_count_posts_windows_and_rule_scope():
    yesterday = MONDAY_9_03 - timedelta(days=1)
    week_ago = MONDAY_9_03 - timedelta(days=7)
    history = [
        entry("published", MONDAY_9_03),
        entry("published", yesterday),
        entry("published", week_ago),  # 7일 창 밖
        entry("published", MONDAY_9_03, rule_id="other"),
    ]
    assert G.count_posts(history, "r1", MONDAY_9_03, days=1) == 1
    assert G.count_posts(history, "r1", MONDAY_9_03, days=7) == 2


def test_consecutive_failures_stops_at_success_and_ignores_skipped():
    t = MONDAY_9_03
    history = [
        entry("failed", t - timedelta(days=3)),
        entry("published", t - timedelta(days=2)),
        entry("failed", t - timedelta(days=1)),
        entry("skipped", t - timedelta(hours=5)),
        entry("failed", t - timedelta(hours=1)),
    ]
    assert G.consecutive_failures(history, "r1") == 2


def test_consecutive_failures_orders_by_time_not_list_position():
    t = MONDAY_9_03
    history = [entry("failed", t), entry("published", t - timedelta(days=1)), entry("failed", t - timedelta(days=2))]
    assert G.consecutive_failures(history, "r1") == 1


def test_gap_remaining():
    r = rule()
    assert G.gap_remaining_seconds(r, MONDAY_9_03, []) == 0
    recent = [entry("published", MONDAY_9_03 - timedelta(seconds=30))]
    assert G.gap_remaining_seconds(r, MONDAY_9_03, recent) == pytest.approx(60)
    assert G.gap_remaining_seconds(r, MONDAY_9_03, [entry("failed", MONDAY_9_03 - timedelta(seconds=1))]) == 0


# ── 실행 판정 ────────────────────────────────────────────────────────────


def test_all_conditions_met_runs_and_publishes():
    decision = G.evaluate_run(approved(), ctx())
    assert (decision.run, decision.publish, decision.blockers, decision.publish_blockers) == (True, True, (), ())
    assert decision.slot == "2026-10-05 09:00"


@pytest.mark.parametrize(
    ("override", "blocker"),
    [
        ({"login_state": "out"}, "login_out"),
        ({"login_state": "unknown"}, "login_unknown"),
        ({"blog_alias_matches": False}, "blog_account_mismatch"),
        ({"blog_alias_matches": None}, "blog_account_unknown"),
        ({"claude_available": False}, "claude_unavailable"),
        ({"research_age_days": G.RESEARCH_MAX_AGE_DAYS + 1}, "research_stale"),
        ({"research_age_days": None}, "research_stale"),
        ({"now": datetime(2026, 10, 5, 12, 0)}, "not_due"),
    ],
)
def test_run_blockers(override, blocker):
    decision = G.evaluate_run(approved(), ctx(**override))
    assert not decision.run and not decision.publish
    assert blocker in decision.blockers


def test_paused_rule_does_not_run():
    decision = G.evaluate_run(replace(approved(), paused=True), ctx())
    assert not decision.run and "paused" in decision.blockers


def test_three_consecutive_failures_auto_pause():
    t = MONDAY_9_03
    history = tuple(entry("failed", t - timedelta(days=d), slot=f"s{d}") for d in (1, 2, 3))
    decision = G.evaluate_run(approved(), ctx(history=history))
    assert "auto_paused_failures" in decision.blockers and not decision.run


def test_limits_block_run():
    t = MONDAY_9_03
    day = tuple([entry("published", t - timedelta(hours=1), slot="a")])
    assert "daily_limit" in G.evaluate_run(approved(), ctx(history=day)).blockers
    week = tuple(entry("published", t - timedelta(days=d), slot=f"s{d}") for d in (1, 2, 3))
    blockers = G.evaluate_run(approved(), ctx(history=week)).blockers
    assert "weekly_limit" in blockers


def test_gap_blocks_run():
    r = approved(per_day=3, per_week=9)
    recent = (entry("draft_saved", MONDAY_9_03 - timedelta(seconds=10), slot="a"),)
    assert "gap_wait" in G.evaluate_run(r, ctx(history=recent)).blockers


def test_draft_only_rule_runs_but_never_publishes():
    decision = G.evaluate_run(rule(mode="draft_only"), ctx())
    assert decision.run and not decision.publish
    assert "mode_draft_only" in decision.publish_blockers


def test_unapproved_auto_publish_rule_runs_as_draft():
    decision = G.evaluate_run(rule(), ctx())
    assert decision.run and not decision.publish and "mode_draft_only" in decision.publish_blockers


def test_rule_edited_after_approval_cannot_publish():
    edited = replace(approved(), per_day=2, per_week=5)
    decision = G.evaluate_run(edited, ctx())
    assert decision.run and not decision.publish and "mode_draft_only" in decision.publish_blockers


def test_lighting_account_runs_but_never_publishes():
    decision = G.evaluate_run(approved(blog_id="skyjwshin"), ctx())
    assert decision.run and not decision.publish
    assert "account_not_auto_publish" in decision.publish_blockers


def test_user_only_rule_with_stale_research_drafts_but_does_not_publish():
    """리서치를 안 쓰는 규칙은 낡은 리서치로 막히지 않지만, 주제를 검증할 수 없으니 발행은 못 한다."""
    decision = G.evaluate_run(approved(use_research=False), ctx(research_age_days=99))
    assert decision.run and not decision.publish
    assert "research_not_fresh" in decision.publish_blockers


def test_manual_local_draft_run_ignores_schedule_and_login_but_never_publishes():
    """ "지금 실행"(로컬 초안): 예정 시각·로그인을 보지 않고, 발행은 항상 막는다."""
    off_schedule = ctx(now=datetime(2026, 10, 6, 15, 0), login_state="out", blog_alias_matches=None)
    decision = G.evaluate_run(approved(), off_schedule, scheduled=False, uses_naver=False)
    assert decision.run and not decision.publish
    assert decision.publish_blockers[-1] == "local_draft_run"


def test_manual_run_still_honors_pause_limits_claude_and_research():
    r = approved()
    assert "paused" in G.evaluate_run(replace(r, paused=True), ctx(), scheduled=False, uses_naver=False).blockers
    assert (
        "claude_unavailable"
        in G.evaluate_run(r, ctx(claude_available=False), scheduled=False, uses_naver=False).blockers
    )
    assert "research_stale" in G.evaluate_run(r, ctx(research_age_days=99), scheduled=False, uses_naver=False).blockers
    today = (entry("draft_saved", MONDAY_9_03 - timedelta(hours=1), slot="a"),)
    assert "daily_limit" in G.evaluate_run(r, ctx(history=today), scheduled=False, uses_naver=False).blockers


def test_scheduled_run_with_naver_default_is_unchanged():
    decision = G.evaluate_run(approved(), ctx(login_state="out"))
    assert "login_out" in decision.blockers


# ── 주제 검증·선정 ───────────────────────────────────────────────────────

RESEARCH = {
    "keywords": [
        {"keyword": "하도급지킴이", "total_search": 44880},
        {"keyword": "희귀어", "total_search": 100},
        {"keyword": "질문없음", "total_search": 9000},
    ],
    "topics": [
        {"keyword": "하도급지킴이", "question_title": "지킴이 등록 방법?", "question_description": "설명"},
        {"keyword": "희귀어", "question_title": "희귀 질문"},
    ],
}


def test_verify_topic_passes_with_volume_and_real_question():
    assert G.verify_topic({"keywords": ["하도급지킴이"]}, RESEARCH).verified


@pytest.mark.parametrize(
    ("topic", "research", "reason"),
    [
        ({"keywords": ["희귀어"]}, RESEARCH, "volume_below_min"),
        ({"keywords": ["질문없음"]}, RESEARCH, "no_real_question"),
        ({"keywords": ["없는키워드"]}, RESEARCH, "volume_below_min"),
        ({"keywords": ["하도급지킴이"]}, None, "no_research"),
        ({"keywords": ["하도급지킴이"]}, {}, "no_research"),
    ],
)
def test_verify_topic_rejections(topic, research, reason):
    verdict = G.verify_topic(topic, research)
    assert not verdict.verified and verdict.reasons == (reason,)


def test_verify_topic_needs_volume_and_question_on_the_same_keyword():
    """검색량은 A 키워드, 질문은 B 키워드에만 있으면 검증 통과가 아니다."""
    research = {
        "keywords": [{"keyword": "A", "total_search": 9999}, {"keyword": "B", "total_search": 10}],
        "topics": [{"keyword": "B", "question_title": "q"}],
    }
    assert not G.verify_topic({"keywords": ["A", "B"]}, research).verified


def test_rank_candidates_order_source_and_verification():
    r = rule()
    research_topics = [{"topic": "지식iN 질문 1", "keywords": ["k"]}, {"topic": "지식iN 질문 2", "keywords": ["k"]}]
    out = G.rank_candidates(r, RESEARCH, research_topics, lambda title: False)
    assert [c.source for c in out] == ["user", "research", "research"]
    assert [c.verified for c in out] == [True, True, True]
    unverified = G.rank_candidates(r, None, [], lambda title: False)
    assert [(c.source, c.verified) for c in unverified] == [("user", False)]


def test_rank_candidates_skips_duplicates_and_respects_use_research():
    r = rule(use_research=False)
    out = G.rank_candidates(r, RESEARCH, [{"topic": "리서치 주제", "keywords": ["k"]}], lambda t: False)
    assert [c.source for c in out] == ["user"]  # use_research 꺼짐 → 리서치 주제 무시
    assert G.rank_candidates(rule(), RESEARCH, [], lambda t: t == "직접입력 주제") == []
    seen = []
    G.rank_candidates(rule(), RESEARCH, [{"topic": "T", "keywords": ["k"]}], lambda t: seen.append(t) or False)
    assert seen == ["직접입력 주제", "T"]


# ── 글 검사 ──────────────────────────────────────────────────────────────

GOOD_POST = {"title": "제목", "body": "본" * G.MIN_BODY_CHARS, "tags": [f"t{i}" for i in range(G.MIN_TAG_COUNT)]}
CLEAN_SEO = {"ok": True, "warnings": []}


def test_quality_ok():
    verdict = G.check_quality(GOOD_POST, CLEAN_SEO, rule())
    assert verdict.ok and verdict.reasons == ()


def test_quality_any_seo_warning_fails():
    """seo_check 는 경고만 낼 뿐 막지 않는다 — 자동 발행에서는 경고 하나도 통과시키지 않는다."""
    verdict = G.check_quality(GOOD_POST, {"ok": False, "warnings": ["검증 필요 수치 1건: 요율(3%)"]}, rule())
    assert not verdict.ok and verdict.reasons == ("seo:검증 필요 수치 1건: 요율(3%)",)


def test_quality_length_and_tag_floors():
    short = {**GOOD_POST, "body": "짧다", "tags": ["a"]}
    reasons = G.check_quality(short, CLEAN_SEO, rule()).reasons
    assert "body_too_short:2" in reasons and "too_few_tags:1" in reasons


def test_quality_forbidden_words_case_insensitive_in_title_and_body():
    r = rule(forbidden_words=["최고의", "Guarantee"])
    post = {**GOOD_POST, "title": "최고의 방법", "body": GOOD_POST["body"] + " we GUARANTEE it"}
    reasons = G.check_quality(post, CLEAN_SEO, r).reasons
    assert "forbidden_word:최고의" in reasons and "forbidden_word:Guarantee" in reasons


def test_pick_cta():
    assert G.pick_cta(True) == "standard"
    assert G.pick_cta(False) == "positioning"


# ── 중복 발행 ────────────────────────────────────────────────────────────


def key_fn(title):
    return "k:" + title.strip().lower()


def test_duplicate_counts_published_and_pending_but_not_failed():
    entries = [
        {"status": "published", "title": "게시됨", "key": key_fn("게시됨")},
        {"status": "pending", "title": "시도중", "key": key_fn("시도중")},
        {"status": "failed", "title": "실패", "key": key_fn("실패")},
    ]
    assert G.is_duplicate_or_pending("게시됨", entries, key_fn)
    assert G.is_duplicate_or_pending("시도중", entries, key_fn)  # 발행 여부를 모르는 시도는 중복으로 본다
    assert not G.is_duplicate_or_pending("실패", entries, key_fn)  # 발행이 안 됐으니 재시도 허용
    assert not G.is_duplicate_or_pending("새 글", entries, key_fn)


def test_duplicate_matches_by_title_case_insensitive_even_without_key():
    assert G.is_duplicate_or_pending(" Hello ", [{"status": "published", "title": "hello"}], key_fn)


def test_topic_used_after_draft_publish_or_attempt_but_not_after_failure():
    history = [
        entry("draft_saved", MONDAY_9_03, slot="a", topic="초안 주제"),
        entry("pending", MONDAY_9_03, slot="b", topic="시도 주제"),
        entry("published", MONDAY_9_03, slot="c", topic="발행 주제"),
        entry("failed", MONDAY_9_03, slot="d", topic="실패 주제"),
        entry("skipped", MONDAY_9_03, slot="e", topic="건너뜀 주제"),
    ]
    for used in ("초안 주제", "시도 주제", "발행 주제", "  발행 주제 "):
        assert G.is_topic_used(used, history)
    for free in ("실패 주제", "건너뜀 주제", "없는 주제"):
        assert not G.is_topic_used(free, history)


def test_stale_pending_flags_only_old_pending():
    now = MONDAY_9_03
    entries = [
        entry("pending", now - timedelta(minutes=G.STALE_PENDING_MINUTES + 1), title="오래됨"),
        entry("pending", now - timedelta(minutes=5), title="방금"),
        entry("published", now - timedelta(days=1), title="완료"),
    ]
    assert [e["title"] for e in G.stale_pending(entries, now)] == ["오래됨"]


# ── 기존 코드와의 값 일치·분리 경계 ──────────────────────────────────────


def test_thresholds_match_the_existing_pipeline():
    from scripts.naver.blog.marketing import content

    assert G.MIN_BODY_CHARS == content.MIN_BODY_CHARS
    assert G.MIN_TAG_COUNT == content.MIN_TAG_COUNT
    research_src = Path("scripts/naver/blog/cli/research_blog_topics.py").read_text(encoding="utf-8")
    match = re.search(r"^_MIN_SEARCH_VOLUME\s*=\s*(\d+)", research_src, re.MULTILINE)
    assert match and int(match.group(1)) == G.MIN_SEARCH_VOLUME
    topics_src = Path("scripts/naver/blog/marketing/topics.py").read_text(encoding="utf-8")
    age = re.search(r"^_RESEARCH_MAX_AGE_DAYS\s*=\s*(\d+)", topics_src, re.MULTILINE)
    assert age and int(age.group(1)) == G.RESEARCH_MAX_AGE_DAYS


def test_lighting_account_is_not_in_auto_publish_list_of_accounts_module():
    accounts_src = Path("scripts/naver/blog/accounts.py").read_text(encoding="utf-8")
    assert "skyjwshin" in accounts_src  # 계정이 실제로 존재한다는 전제
    assert "skyjwshin" not in R.AUTO_PUBLISH_BLOG_IDS


def test_package_respects_blog_separation_boundary():
    """분리 경계(기준서 §0): 타 업무 도메인·앱 본체를 import 하지 않는다."""
    forbidden = re.compile(
        r"^\s*(?:from|import)\s+(scripts\.(?:eum|g2b|hiworks|kakaowork)|scripts\.naver\.smartstore|ai_orchestrator)",
        re.M,
    )
    for path in Path("scripts/naver/blog/automation").glob("*.py"):
        assert not forbidden.search(path.read_text(encoding="utf-8")), path
