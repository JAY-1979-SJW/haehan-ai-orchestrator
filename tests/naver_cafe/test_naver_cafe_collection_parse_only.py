"""naver_cafe_collection — HTML 샘플 없는 순수 파싱/로직 검증. 실제 접속 없음."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_orchestrator.sites.adapters.naver_cafe_collection import (
    build_board_url,
    existing_ids,
    filter_new_posts,
    load_stored,
    merge_record,
    save_stored,
)


# ── build_board_url ──────────────────────────────────────────────
class TestBuildBoardUrl:
    def test_contains_club_and_menu(self) -> None:
        url = build_board_url("12345", "67890")
        assert "12345" in url
        assert "67890" in url

    def test_no_external_call(self) -> None:
        url = build_board_url("abc", "def", page=2)
        assert url.startswith("https://cafe.naver.com/")

    def test_empty_ids_raises(self) -> None:
        with pytest.raises(ValueError):
            build_board_url("", "menu1")

    def test_page_param_included(self) -> None:
        url = build_board_url("c1", "m1", page=3)
        assert "page=3" in url or "search.page=3" in url


# ── filter_new_posts ──────────────────────────────────────────────
class TestFilterNewPosts:
    def _item(self, pid: str, title: str = "t", author: str = "a", date: str = "2026-01-01") -> dict:
        return {
            "post_id": pid,
            "title": title,
            "author": author,
            "date": date,
            "url": f"https://cafe.naver.com/articles/{pid}",
        }

    def test_new_items_included(self) -> None:
        items = [self._item("1"), self._item("2")]
        new, skipped = filter_new_posts(items, existing=set())
        assert len(new) == 2
        assert skipped == 0

    def test_existing_ids_skipped(self) -> None:
        items = [self._item("1"), self._item("2")]
        new, skipped = filter_new_posts(items, existing={"1"})
        assert len(new) == 1
        assert new[0]["post_id"] == "2"
        assert skipped == 1

    def test_empty_post_id_skipped(self) -> None:
        items = [{"post_id": "", "title": "t", "author": "a", "date": "", "url": ""}]
        new, skipped = filter_new_posts(items, existing=set())
        assert len(new) == 0
        assert skipped == 1

    def test_duplicate_within_batch_deduplicated(self) -> None:
        items = [self._item("1"), self._item("1")]
        new, skipped = filter_new_posts(items, existing=set())
        assert len(new) == 1
        assert skipped == 1

    def test_normalized_fields(self) -> None:
        items = [self._item("99")]
        new, _ = filter_new_posts(items, existing=set())
        assert set(new[0].keys()) == {"post_id", "title", "author", "created_at", "url"}

    def test_no_extra_fields_like_body_comments_likes(self) -> None:
        items = [self._item("10")]
        new, _ = filter_new_posts(items, existing=set())
        for bad in ("body", "comment", "comments", "like", "likes", "view_count", "content", "html"):
            assert bad not in new[0], f"과수집 필드 발견: {bad}"


# ── load_stored / save_stored / merge_record (tmp_path 격리) ──────
class TestStoreOperations:
    def test_load_nonexistent_returns_empty(self, tmp_path: Path) -> None:
        p = tmp_path / "posts.json"
        data = load_stored(p)
        assert data["posts"] == []

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        p = tmp_path / "posts.json"
        record = {
            "site": "naver_cafe",
            "club_id": "c1",
            "menu_id": "m1",
            "posts": [
                {
                    "post_id": "1",
                    "title": "t1",
                    "author": "a1",
                    "created_at": "2026-01-01",
                    "url": "https://cafe.naver.com/articles/1",
                }
            ],
        }
        save_stored(p, record)
        loaded = load_stored(p)
        assert loaded["club_id"] == "c1"
        assert len(loaded["posts"]) == 1

    def test_save_path_under_tmp(self, tmp_path: Path) -> None:
        p = tmp_path / "sub" / "posts.json"
        save_stored(p, {"site": "naver_cafe", "club_id": "", "menu_id": "", "posts": []})
        assert p.exists()
        assert str(p).startswith(str(tmp_path))

    def test_no_sensitive_data_in_saved_file(self, tmp_path: Path) -> None:
        p = tmp_path / "posts.json"
        record = {"site": "naver_cafe", "club_id": "c1", "menu_id": "m1", "posts": []}
        save_stored(p, record)
        content = json.loads(p.read_text(encoding="utf-8"))
        for bad in ("password", "token", "cookie", "session", "secret"):
            assert bad not in content


# ── existing_ids ──────────────────────────────────────────────────
class TestExistingIds:
    def test_extracts_ids(self) -> None:
        record = {"posts": [{"post_id": "1"}, {"post_id": "2"}, {"post_id": ""}]}
        ids = existing_ids(record)
        assert ids == {"1", "2"}

    def test_empty_record(self) -> None:
        assert existing_ids({}) == set()


# ── merge_record ─────────────────────────────────────────────────
class TestMergeRecord:
    def test_new_posts_appended(self) -> None:
        record = {
            "site": "naver_cafe",
            "club_id": "c",
            "menu_id": "m",
            "posts": [{"post_id": "1", "title": "t1", "author": "a", "created_at": "2026-01-01", "url": "u1"}],
        }
        new = [{"post_id": "2", "title": "t2", "author": "b", "created_at": "2026-01-02", "url": "u2"}]
        merged = merge_record(record, new, club_id="c", menu_id="m")
        ids = {p["post_id"] for p in merged["posts"]}
        assert ids == {"1", "2"}

    def test_duplicate_id_last_wins(self) -> None:
        record = {
            "site": "naver_cafe",
            "club_id": "c",
            "menu_id": "m",
            "posts": [{"post_id": "1", "title": "old", "author": "a", "created_at": "2026-01-01", "url": "u1"}],
        }
        new = [{"post_id": "1", "title": "new", "author": "b", "created_at": "2026-01-02", "url": "u1"}]
        merged = merge_record(record, new, club_id="c", menu_id="m")
        assert len(merged["posts"]) == 1
        assert merged["posts"][0]["title"] == "new"
