"""자동 작성 1회 실행기(B단계) — 네이버에 쓰지 않고 로컬 초안만 만든다. 외부 의존은 전부 가짜를 주입한다."""

from __future__ import annotations

import ast
import json
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from scripts.naver.blog.automation import rules as R
from scripts.naver.blog.automation import runner as N
from scripts.naver.blog.automation import store as S
from scripts.naver.blog.automation.gates import MIN_BODY_CHARS, MIN_TAG_COUNT

NOW = datetime(2026, 10, 5, 9, 3)  # 월요일 — 수동 실행은 요일·시각을 보지 않는다
RESEARCH = {
    "generated_at": "2026-10-04T10:00:00",
    "keywords": [{"keyword": "하도급지킴이", "total_search": 44880}],
    "topics": [{"keyword": "하도급지킴이", "question_title": "지킴이 등록?"}],
}
CONTACT = ("https://home.example", "010-0000-0000")


def good_post(title="생성된 제목", **over):
    post = {
        "title": title,
        "body": "본" * (MIN_BODY_CHARS + 10),
        "tags": [f"t{i}" for i in range(MIN_TAG_COUNT)],
        "body_segments": ["a", "b"],
        "seo": {"ok": True, "warnings": []},
    }
    post.update(over)
    return post


def make_rule(**over):
    data = {
        "id": "r1",
        "name": "규칙",
        "blog_id": "skyjwsin",
        "user_topics": [{"topic": "직접입력 주제", "keywords": ["하도급지킴이"], "angle": "각도"}],
        "use_research": False,
        "days": [1],
        "times": ["23:00"],
        "per_day": 3,
        "per_week": 9,
        "gap_seconds": 60,
        "forbidden_words": [],
        "visibility": "public",
        "mode": "draft_only",
    }
    data.update(over)
    rule, errors = R.parse_rule(data)
    assert not errors
    return rule


class Fakes:
    """generate_post 호출 기록과 순서대로 돌려줄 결과."""

    def __init__(self, posts):
        self.posts = list(posts)
        self.calls = []

    def generate_post(self, topic, llm=None, cta_block=None, blog_id=None):
        self.calls.append({"topic": topic, "llm": llm, "cta_block": cta_block, "blog_id": blog_id})
        result = self.posts.pop(0) if self.posts else good_post()
        if isinstance(result, Exception):
            raise result
        return result


def make_deps(tmp_path, **options):
    """options: posts, research, research_topics, published, product, claude, now — 안 주면 기본값."""
    opt = {
        "posts": (),
        "research": RESEARCH,
        "research_topics": (),
        "published": (),
        "product": False,
        "claude": True,
        "now": NOW,
        **options,
    }
    fakes = Fakes(opt["posts"])
    deps = N.RunnerDeps(
        store=S.Store(tmp_path / "ba"),
        llm=lambda *a, **k: {"ok": True, "text": "x"},
        now=lambda: opt["now"],
        load_research=lambda blog_id: opt["research"],
        research_topics=lambda blog_id: list(opt["research_topics"]),
        published_entries=lambda blog_id: list(opt["published"]),
        topic_key=lambda title: "k:" + title.strip().lower(),
        product_related=lambda record: opt["product"],
        generate_post=fakes.generate_post,
        claude_available=lambda: opt["claude"],
        contact=CONTACT,
    )
    return deps, fakes


# ── 정상 경로 ────────────────────────────────────────────────────────────


def test_happy_path_saves_local_draft_and_history(tmp_path):
    deps, fakes = make_deps(tmp_path)
    result = N.run_once(make_rule(), deps)
    assert result["status"] == "draft_saved" and result["ok"]
    assert result["quality_ok"] and result["verified"] and result["publishable"]
    payload = json.loads((deps.store.drafts_dir / result["draft"]).read_text(encoding="utf-8"))
    assert payload["post"]["title"] == "생성된 제목" and payload["source"] == "user"
    (entry,) = deps.store.load_history()
    assert (entry["status"], entry["topic"], entry["title"], entry["key"]) == (
        "draft_saved",
        "직접입력 주제",
        "생성된 제목",
        "k:생성된 제목",
    )
    assert len(fakes.calls) == 1


def test_llm_and_blog_id_are_passed_to_generate_post(tmp_path):
    deps, fakes = make_deps(tmp_path)
    N.run_once(make_rule(), deps)
    assert fakes.calls[0]["llm"] is deps.llm
    assert fakes.calls[0]["blog_id"] == "skyjwsin"


def test_second_run_moves_on_to_the_next_topic(tmp_path):
    deps, fakes = make_deps(tmp_path)
    rule = make_rule(user_topics=[{"topic": "A", "keywords": ["k"]}, {"topic": "B", "keywords": ["k"]}])
    N.run_once(rule, deps)
    later = replace_now(deps, NOW + timedelta(minutes=5))
    N.run_once(rule, later)
    assert [c["topic"]["topic"] for c in fakes.calls] == ["A", "B"]


def replace_now(deps, when):
    return replace(deps, now=lambda: when)


# ── CTA ──────────────────────────────────────────────────────────────────


def test_non_product_topic_gets_honest_positioning_cta(tmp_path):
    deps, fakes = make_deps(tmp_path, product=False)
    result = N.run_once(make_rule(), deps)
    cta = fakes.calls[0]["cta_block"]
    assert result["cta_kind"] == "positioning"
    assert "해한 AI" in cta and CONTACT[0] in cta and CONTACT[1] in cta
    assert "이미 만들어져 있다는 뜻은 아닙니다" in cta  # 없는 기능을 있다고 하지 않는다


def test_product_topic_uses_standard_cta(tmp_path):
    deps, fakes = make_deps(tmp_path, product=True)
    result = N.run_once(make_rule(), deps)
    assert result["cta_kind"] == "standard" and fakes.calls[0]["cta_block"] is None


def test_product_check_receives_the_shape_the_existing_function_reads(tmp_path):
    seen = []
    deps, _ = make_deps(tmp_path)
    deps = replace(deps, product_related=lambda record: seen.append(record) or False)
    N.run_once(make_rule(), deps)
    assert seen == [{"keyword": "하도급지킴이", "question_title": "직접입력 주제"}]


def test_positioning_cta_truncates_long_topic():
    cta = N.positioning_cta("가" * 100, CONTACT)
    assert "가" * 40 in cta and "가" * 41 not in cta


# ── 막힘 ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("kwargs", "rule_over", "blocker"),
    [
        ({}, {"paused": True}, "paused"),
        ({"claude": False}, {}, "claude_unavailable"),
        ({"research": None}, {"use_research": True}, "research_stale"),
        ({"research": {**RESEARCH, "generated_at": "2026-08-01T00:00:00"}}, {"use_research": True}, "research_stale"),
    ],
)
def test_blocked_runs_do_nothing(tmp_path, kwargs, rule_over, blocker):
    deps, fakes = make_deps(tmp_path, **kwargs)
    result = N.run_once(make_rule(**rule_over), deps)
    assert result["status"] == "blocked" and blocker in result["blockers"]
    assert fakes.calls == [] and deps.store.load_history() == []


def test_daily_limit_blocks_manual_run_too(tmp_path):
    deps, _ = make_deps(tmp_path)
    rule = make_rule(per_day=1, per_week=3)
    assert N.run_once(rule, deps)["status"] == "draft_saved"
    result = N.run_once(rule, replace_now(deps, NOW + timedelta(minutes=10)))
    assert "daily_limit" in result["blockers"]


def test_gap_blocks_back_to_back_runs(tmp_path):
    deps, _ = make_deps(tmp_path)
    rule = make_rule(gap_seconds=600)
    N.run_once(rule, deps)
    assert "gap_wait" in N.run_once(rule, replace_now(deps, NOW + timedelta(seconds=30)))["blockers"]


# ── 주제·중복 ────────────────────────────────────────────────────────────


def test_no_topic_when_everything_is_used(tmp_path):
    deps, fakes = make_deps(tmp_path)
    deps.store.upsert_history(
        {
            "rule_id": "other",
            "slot": "s",
            "at": "2026-10-01T09:00:00",
            "status": "draft_saved",
            "topic": "직접입력 주제",
        }
    )
    result = N.run_once(make_rule(), deps)
    assert result == {"ok": False, "status": "no_topic", "blockers": []}
    assert fakes.calls == []


def test_topic_already_published_in_legacy_cache_is_skipped(tmp_path):
    published = [{"title": "직접입력 주제", "key": "k:직접입력 주제"}]
    deps, fakes = make_deps(tmp_path, published=published)
    assert N.run_once(make_rule(), deps)["status"] == "no_topic"
    assert fakes.calls == []


def test_failed_topic_can_be_retried(tmp_path):
    deps, fakes = make_deps(tmp_path, posts=[None, good_post()])
    rule = make_rule()
    assert N.run_once(rule, deps)["status"] == "failed"
    result = N.run_once(rule, replace_now(deps, NOW + timedelta(minutes=5)))
    assert result["status"] == "draft_saved" and len(fakes.calls) == 2


def test_research_topics_are_used_only_when_enabled(tmp_path):
    research_topics = [{"topic": "지식iN 질문", "keywords": ["하도급지킴이"]}]
    deps, fakes = make_deps(tmp_path, research_topics=research_topics)
    N.run_once(make_rule(user_topics=[], use_research=True), deps)
    assert fakes.calls[0]["topic"]["topic"] == "지식iN 질문"
    deps2, fakes2 = make_deps(tmp_path / "x", research_topics=research_topics)
    N.run_once(make_rule(use_research=False), deps2)
    assert fakes2.calls[0]["topic"]["topic"] == "직접입력 주제"


def test_unverified_user_topic_is_drafted_but_not_publishable(tmp_path):
    deps, _ = make_deps(tmp_path, research=None)
    result = N.run_once(make_rule(), deps)
    assert result["status"] == "draft_saved" and result["verified"] is False and result["publishable"] is False


# ── 실패·재시도 ──────────────────────────────────────────────────────────


def test_generation_failure_is_recorded_and_counts_toward_auto_pause(tmp_path):
    deps, _ = make_deps(tmp_path, posts=[None, None, None])
    rule = make_rule(user_topics=[{"topic": f"T{i}", "keywords": ["k"]} for i in range(5)], per_day=5, per_week=15)
    for i in range(3):
        assert N.run_once(rule, replace_now(deps, NOW + timedelta(minutes=5 * i)))["status"] == "failed"
    blocked = N.run_once(rule, replace_now(deps, NOW + timedelta(minutes=30)))
    assert "auto_paused_failures" in blocked["blockers"]


def test_exception_in_generation_becomes_failed_result_not_crash(tmp_path):
    deps, _ = make_deps(tmp_path, posts=[RuntimeError("boom")])
    result = N.run_once(make_rule(), deps)
    assert result == {"ok": False, "status": "failed", "reason": "exception:RuntimeError"}
    assert deps.store.load_history()[0]["status"] == "failed"


def test_seo_warning_triggers_one_retry_with_the_warning_fed_back(tmp_path):
    bad = good_post(title="나쁨", seo={"ok": False, "warnings": ["핵심 키워드 본문 출현 1회"]})
    deps, fakes = make_deps(tmp_path, posts=[bad, good_post(title="좋음")])
    result = N.run_once(make_rule(), deps)
    assert result["title"] == "좋음" and result["quality_ok"]
    assert len(fakes.calls) == 2
    assert "핵심 키워드 본문 출현 1회" in fakes.calls[1]["topic"]["revision_note"]
    assert "revision_note" not in fakes.calls[0]["topic"]  # 첫 시도에는 수정 지시가 없다


def test_retry_result_is_ignored_when_it_is_worse(tmp_path):
    first = good_post(title="첫째", seo={"ok": False, "warnings": ["경고 하나"]})
    worse = good_post(title="둘째", seo={"ok": False, "warnings": ["경고 하나", "경고 둘"]})
    deps, _ = make_deps(tmp_path, posts=[first, worse])
    assert N.run_once(make_rule(), deps)["title"] == "첫째"


def test_no_retry_when_quality_is_already_ok_or_failure_is_not_seo(tmp_path):
    deps, fakes = make_deps(tmp_path)
    N.run_once(make_rule(), deps)
    assert len(fakes.calls) == 1
    forbidden, fakes2 = make_deps(tmp_path / "f", posts=[good_post(title="최고의 글")])
    result = N.run_once(make_rule(forbidden_words=["최고의"]), forbidden)
    assert len(fakes2.calls) == 1
    assert result["status"] == "draft_saved" and not result["quality_ok"] and not result["publishable"]
    assert "forbidden_word:최고의" in result["quality_reasons"]


def test_retry_failure_keeps_the_first_draft(tmp_path):
    first = good_post(seo={"ok": False, "warnings": ["경고"]})
    deps, _ = make_deps(tmp_path, posts=[first, None])
    result = N.run_once(make_rule(), deps)
    assert result["status"] == "draft_saved" and not result["quality_ok"]


# ── 안전 경계 ────────────────────────────────────────────────────────────


def test_runner_never_imports_anything_that_writes_to_naver():
    """B단계 약속: 네이버에 쓰는 코드(에디터·발행)를 import 하지 않는다."""
    tree = ast.parse(Path("scripts/naver/blog/automation/runner.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(f"{node.module}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    forbidden = ("scripts.naver.blog.core", "scripts.naver.blog.marketing.publish", "playwright")
    assert imported, "imported 이(가) 비어 있음 — 비교대상 0건이면 아래 assert 는 공허하게 통과한다"
    assert not [name for name in imported if any(name.startswith(f) for f in forbidden)]


# ── 보조 함수 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("research", "expected"),
    [
        ({"generated_at": "2026-10-04T09:03:00"}, 1.0),
        ({"generated_at": "2026-10-05T09:03:00"}, 0.0),
        ({"generated_at": "2026-12-01T00:00:00"}, 0.0),  # 미래 시각은 0 으로
        ({}, None),
        (None, None),
        ({"generated_at": "어제"}, None),
    ],
)
def test_research_age_days(research, expected):
    assert N.research_age_days(research, NOW) == expected


def test_default_deps_wiring_matches_existing_modules(tmp_path):
    from scripts.naver.blog.marketing import content, topics

    deps = N.default_deps(S.Store(tmp_path))
    assert deps.contact == (content.HOMEPAGE_URL, content.CONTACT_PHONE)
    assert deps.topic_key is topics.topic_key
    assert deps.research_topics("skyjwshin") == []  # 조명 계정 리서치 주제 로더는 아직 없다
    assert deps.load_research("skyjwsin") is None or "generated_at" in deps.load_research("skyjwsin")
