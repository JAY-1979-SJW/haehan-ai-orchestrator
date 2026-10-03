"""자동 작성 저장소 — 규칙·초안·실행 기록 파일 I/O. 경로 탈출 차단·원자적 쓰기·손상 처리."""

from __future__ import annotations

import pytest

from scripts.naver.blog.automation import rules as R
from scripts.naver.blog.automation import store as S


def make_rule(rule_id="r1", **over):
    data = {
        "id": rule_id,
        "name": "규칙",
        "blog_id": "skyjwsin",
        "user_topics": [{"topic": "주제", "keywords": ["키워드"]}],
        "use_research": False,
        "days": [0],
        "times": ["09:00"],
        "per_day": 1,
        "per_week": 3,
    }
    data.update(over)
    rule, errors = R.parse_rule(data)
    assert not errors
    return rule


@pytest.fixture
def store(tmp_path):
    return S.Store(tmp_path / "blog_automation")


# ── 규칙 ─────────────────────────────────────────────────────────────────


def test_rule_roundtrip_and_no_tmp_left(store):
    rule = make_rule()
    path = store.save_rule(rule)
    assert path.name == "r1.json"
    assert store.load_rule("r1") == rule
    assert list(store.rules_dir.glob("*.tmp")) == []


def test_load_missing_rule_is_none(store):
    assert store.load_rule("nope") is None


@pytest.mark.parametrize("bad", ["../evil", "a/b", "..", "", "a\\b", "x" * 65, "a b"])
def test_path_traversal_ids_rejected_everywhere(store, bad):
    with pytest.raises(S.StoreError):
        store.load_rule(bad)
    with pytest.raises(S.StoreError):
        store.delete_rule(bad)
    with pytest.raises(S.StoreError):
        store.save_draft(bad, {}, stamp="1")
    with pytest.raises(S.StoreError):
        store.list_drafts(bad)


def test_corrupt_rule_file_raises_but_does_not_break_listing(store):
    store.save_rule(make_rule("good"))
    (store.rules_dir / "bad.json").write_text("{not json", encoding="utf-8")
    (store.rules_dir / "wrong.json").write_text('{"id": "other"}', encoding="utf-8")
    with pytest.raises(S.StoreError):
        store.load_rule("bad")
    rules, broken = store.list_rules()
    assert [r.id for r in rules] == ["good"]
    assert set(broken) == {"bad", "wrong"}


def test_rule_file_with_mismatched_id_is_reported(store):
    rule = make_rule("real")
    (store.rules_dir).mkdir(parents=True)
    import json

    (store.rules_dir / "alias.json").write_text(json.dumps(R.rule_to_dict(rule)), encoding="utf-8")
    rules, broken = store.list_rules()
    assert rules == [] and broken == {"alias": ["파일 이름과 규칙 id 가 다름"]}


def test_list_rules_without_directory(store):
    assert store.list_rules() == ([], {})


def test_delete_rule(store):
    store.save_rule(make_rule())
    assert store.delete_rule("r1") is True
    assert store.delete_rule("r1") is False
    assert store.load_rule("r1") is None


# ── 실행 기록 ────────────────────────────────────────────────────────────


def test_history_upsert_replaces_same_slot_and_appends_others(store):
    store.upsert_history({"rule_id": "r1", "slot": "s1", "status": "pending"})
    store.upsert_history({"rule_id": "r1", "slot": "s2", "status": "pending"})
    store.upsert_history({"rule_id": "r1", "slot": "s1", "status": "published"})
    store.upsert_history({"rule_id": "r2", "slot": "s1", "status": "failed"})
    history = store.load_history()
    assert [(h["rule_id"], h["slot"], h["status"]) for h in history] == [
        ("r1", "s1", "published"),
        ("r1", "s2", "pending"),
        ("r2", "s1", "failed"),
    ]


def test_history_is_trimmed_to_the_most_recent(store, monkeypatch):
    monkeypatch.setattr(S, "HISTORY_MAX", 3)
    for i in range(6):
        store.upsert_history({"rule_id": "r1", "slot": f"s{i}", "status": "draft_saved"})
    assert [h["slot"] for h in store.load_history()] == ["s3", "s4", "s5"]


def test_load_history_when_missing_or_not_a_list(store):
    assert store.load_history() == []
    store.base.mkdir(parents=True)
    store.history_path.write_text('{"a": 1}', encoding="utf-8")
    assert store.load_history() == []


# ── 초안 ─────────────────────────────────────────────────────────────────


def test_drafts_never_overwrite_each_other(store):
    first = store.save_draft("r1", {"rule_id": "r1", "n": 1}, stamp="20261005090300")
    second = store.save_draft("r1", {"rule_id": "r1", "n": 2}, stamp="20261005090300")
    assert first != second and first.exists() and second.exists()


def test_draft_stamp_is_sanitized(store):
    path = store.save_draft("r1", {"rule_id": "r1"}, stamp="../../evil 2026")
    assert path.parent == store.drafts_dir
    assert path.name == "r1_2026.json"


def test_list_drafts_filters_by_stored_rule_id_not_file_prefix(store):
    """규칙 id `a` 와 `a_b` — 파일 이름 접두어로 거르면 `a` 목록에 `a_b` 초안이 섞인다."""
    store.save_draft("a", {"rule_id": "a", "topic": {"topic": "A"}, "post": {"title": "A글", "body": "x"}}, stamp="1")
    store.save_draft(
        "a_b", {"rule_id": "a_b", "topic": {"topic": "B"}, "post": {"title": "B글", "body": "y"}}, stamp="2"
    )
    assert [d["title"] for d in store.list_drafts("a")] == ["A글"]
    assert sorted(d["title"] for d in store.list_drafts()) == ["A글", "B글"]


def test_list_drafts_summary_has_no_full_body_and_respects_limit(store):
    for i in range(4):
        store.save_draft(
            "r1", {"rule_id": "r1", "post": {"title": f"t{i}", "body": "본" * 100}, "publishable": False}, stamp=str(i)
        )
    out = store.list_drafts("r1", limit=2)
    assert len(out) == 2
    assert out[0]["body_chars"] == 100 and "body" not in out[0]
