"""블로그 자동 작성 규칙 모델 — 검증·승인 해시·유효 모드. 기준서 v2 §3, §4."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pytest

from scripts.naver.blog.automation import rules as R

NOW = datetime(2026, 10, 5, 9, 0)


def base(**over):
    data = {
        "id": "r1",
        "name": "건설 주 3회",
        "blog_id": "skyjwsin",
        "user_topics": [{"topic": "하도급대금 직접지급 방법", "keywords": ["하도급지킴이", "건설실무"]}],
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
    return data


def make(**over):
    rule, errors = R.parse_rule(base(**over))
    assert errors == []
    assert rule is not None
    return rule


# ── 검증 ─────────────────────────────────────────────────────────────────


def test_parse_ok_and_defaults():
    rule = make()
    assert (rule.blog_id, rule.mode, rule.visibility, rule.paused) == ("skyjwsin", "auto_publish", "public", False)
    minimal = {
        k: v for k, v in base().items() if k not in ("mode", "visibility", "blog_id", "forbidden_words", "gap_seconds")
    }
    parsed, errors = R.parse_rule(minimal)
    assert errors == [] and parsed is not None
    assert (parsed.mode, parsed.visibility, parsed.blog_id, parsed.gap_seconds) == (
        "draft_only",
        "public",
        "skyjwsin",
        90,
    )


@pytest.mark.parametrize(
    "over",
    [
        {"id": "../evil"},  # 경로 문자 — 파일 이름으로 쓰이므로 거부
        {"id": ""},
        {"id": "a" * 65},
        {"name": "  "},
        {"days": []},
        {"days": [7]},
        {"days": [1, 1]},
        {"days": [True]},
        {"times": []},
        {"times": ["9:00"]},
        {"times": ["24:00"]},
        {"times": ["09:60"]},
        {"times": ["09:00", "09:00"]},
        {"times": [f"0{h}:00" for h in range(7)]},
        {"per_day": 0},
        {"per_day": R.MAX_PER_DAY + 1},
        {"per_day": True},
        {"per_day": "1"},  # 문자열을 숫자로 보정하지 않는다
        {"per_week": R.MAX_PER_WEEK + 1},
        {"per_day": 3, "per_week": 2},
        {"gap_seconds": R.MIN_GAP_SECONDS - 1},
        {"user_topics": [], "use_research": False},
        {"user_topics": [{"topic": "x"}]},  # keywords 없음
        {"user_topics": [{"topic": "", "keywords": ["k"]}]},
        {"user_topics": ["문자열"]},
        {"use_research": "yes"},
        {"visibility": "everyone"},
        {"mode": "auto"},
        {"forbidden_words": "최고의"},
        {"forbidden_words": [""]},
        {"approval": {"approved_by": "a"}},
        {"approval": {"approved_by": "a", "approved_at": "x", "rule_hash": "zz"}},
        {"paused": "no"},
    ],
)
def test_invalid_rules_are_rejected_with_reason(over):
    rule, errors = R.parse_rule(base(**over))
    assert rule is None
    assert errors


def test_non_dict_rejected():
    assert R.parse_rule([1, 2]) == (None, ["규칙은 객체여야 함"])


def test_unknown_blog_id_rejected_only_when_registry_given():
    assert R.parse_rule(base(blog_id="ghost"))[0] is not None
    rule, errors = R.parse_rule(base(blog_id="ghost"), known_blog_ids=frozenset({"skyjwsin"}))
    assert rule is None and any("ghost" in e for e in errors)


def test_roundtrip_is_lossless():
    rule = R.approve(make(), "owner", NOW)
    again, errors = R.parse_rule(R.rule_to_dict(rule))
    assert errors == [] and again == rule


def test_days_and_times_are_normalized_by_sorting():
    rule = make(days=[4, 0, 2], times=["18:00", "09:00"])
    assert rule.days == (0, 2, 4) and rule.times == ("09:00", "18:00")


# ── 승인 해시 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "over",
    [
        {"blog_id": "skyjwshin"},
        {"user_topics": [{"topic": "다른 주제", "keywords": ["k"]}]},
        {"use_research": False},
        {"days": [1]},
        {"times": ["10:00"]},
        {"per_day": 2},
        {"per_week": 4},
        {"gap_seconds": 120},
        {"forbidden_words": []},
        {"visibility": "private"},
        {"mode": "draft_only"},
    ],
)
def test_hash_changes_when_behavior_changes(over):
    assert R.rule_hash(make()) != R.rule_hash(make(**over))


def test_hash_ignores_name_pause_and_approval():
    rule = make()
    assert R.rule_hash(rule) == R.rule_hash(replace(rule, name="새 이름"))
    assert R.rule_hash(rule) == R.rule_hash(replace(rule, paused=True))
    assert R.rule_hash(rule) == R.rule_hash(R.approve(rule, "owner", NOW))


def test_hash_is_deterministic_hex():
    digest = R.rule_hash(make())
    assert digest == R.rule_hash(make()) and len(digest) == 64


# ── 승인·유효 모드 ───────────────────────────────────────────────────────


def test_approve_records_who_when_and_hash():
    rule = R.approve(make(), " owner ", NOW)
    assert rule.approval == {
        "approved_by": "owner",
        "approved_at": "2026-10-05T09:00:00",
        "rule_hash": R.rule_hash(rule),
    }
    assert R.is_approval_valid(rule)


@pytest.mark.parametrize("who", ["", "   "])
def test_approve_requires_approver(who):
    with pytest.raises(ValueError):
        R.approve(make(), who, NOW)


def test_unapproved_rule_is_not_valid():
    assert not R.is_approval_valid(make())


def test_editing_after_approval_voids_it():
    approved = R.approve(make(), "owner", NOW)
    edited = replace(approved, per_day=2, per_week=5)
    assert not R.is_approval_valid(edited)
    assert R.effective_mode(edited) == "draft_only"


def test_effective_mode_auto_publish_only_when_all_conditions_hold():
    assert R.effective_mode(R.approve(make(), "owner", NOW)) == "auto_publish"


def test_effective_mode_draft_cases():
    assert R.effective_mode(make()) == "draft_only"  # 승인 없음
    assert R.effective_mode(R.approve(make(mode="draft_only"), "owner", NOW)) == "draft_only"  # 규칙이 초안 전용


def test_lighting_account_never_auto_publishes_even_if_approved():
    """조명 계정은 README 상 발행 전 사람 검수가 필요 — 승인이 있어도 초안까지만."""
    rule = R.approve(make(blog_id="skyjwshin"), "owner", NOW)
    assert R.is_approval_valid(rule)
    assert R.effective_mode(rule) == "draft_only"


def test_auto_publish_account_whitelist_is_locked():
    assert R.AUTO_PUBLISH_BLOG_IDS == frozenset({"skyjwsin"})


def test_approval_summary_lists_scope():
    text = "\n".join(R.approval_summary(R.approve(make(), "owner", NOW)))
    for expected in ("skyjwsin", "월수금", "09:00", "하루 1편", "금칙어 1개", "초안으로 남깁니다"):
        assert expected in text
