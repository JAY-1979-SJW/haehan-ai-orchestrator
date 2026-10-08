"""블로그 Unsplash 이미지 해석 — 캐시 폴백·실시간 검색·재노출. 네트워크를 쓰지 않는다(가짜 requests).

층간 위반 정리(2026-10-01): CLI(L6)가 라우터(L8)를 import 하지 않도록 헬퍼를 services 로 옮겼다.
이 테스트는 이동 전 동작(캐시 경로)을 고정하고, 이동 후에도 라우터의 옛 이름이 그대로 동작함을 확인한다.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import scripts.naver.blog.unsplash_images as images

ROOT = Path(__file__).resolve().parents[2]
CLI_FILES = [
    "scripts/naver/blog/cli/apply_cta_to_batches.py",
    "scripts/naver/blog/cli/publish_ep_batch.py",
    "scripts/naver/blog/cli/publish_ep_batch_gov2.py",
]


class FakeResponse:
    def __init__(self, payload=None, content=b"IMG"):
        self._payload, self.content = payload or {}, content

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    """업로드 폴더·캐시 파일을 임시 경로로, requests.get 을 가짜로, 이벤트 기록을 수집으로 바꾼다."""
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr(images, "UPLOADS_DIR", uploads)
    monkeypatch.setattr(images, "_UNSPLASH_CACHE", tmp_path / "unsplash_images.json")
    monkeypatch.delenv("UNSPLASH_ACCESS_KEY", raising=False)
    events: list[tuple] = []
    monkeypatch.setattr(images, "emit_event", lambda *a, **k: events.append((a, k)))
    calls: list[str] = []

    def fake_get(url, **kwargs):
        calls.append(url)
        return FakeResponse(content=b"IMG-" + url.encode()[-8:])

    monkeypatch.setattr("requests.get", fake_get)
    return {"uploads": uploads, "cache": tmp_path / "unsplash_images.json", "events": events, "calls": calls}


def write_cache(sb, items):
    sb["cache"].write_text(json.dumps({"images": items}, ensure_ascii=False), encoding="utf-8")


def test_media_that_already_exists_is_returned_untouched(sandbox):
    assert images.resolve_unsplash_images("조명", ["a.jpg", "b.jpg"]) == ["a.jpg", "b.jpg"]
    assert sandbox["calls"] == [] and sandbox["events"] == []


def test_without_api_key_it_falls_back_to_the_local_cache_and_downloads(sandbox):
    write_cache(
        sandbox,
        [
            {
                "url": "https://img.test/lamp.jpg",
                "query": "mood lamp",
                "desc": "무드등",
                "download_location": "https://api.test/dl/1",
            },
            {"url": "https://img.test/sofa.jpg", "query": "furniture", "desc": "sofa"},
        ],
    )
    names = images.resolve_unsplash_images("무드등 조명", [], count=1)
    assert len(names) == 1 and names[0].startswith("unsplash_") and names[0].endswith(".jpg")
    assert (sandbox["uploads"] / names[0]).read_bytes().startswith(b"IMG-")
    assert "https://img.test/lamp.jpg" in sandbox["calls"]  # 키워드가 맞는 항목을 골랐다
    assert "https://api.test/dl/1" in sandbox["calls"]  # Unsplash 정책: download_location 통지
    assert sandbox["events"] and sandbox["events"][0][0][0] == "NAVER_BLOG_UNSPLASH"


def test_cache_selection_cycles_when_more_images_are_requested_than_cached(sandbox):
    write_cache(sandbox, [{"url": "https://img.test/only.jpg", "query": "x", "desc": "y"}])
    names = images.resolve_unsplash_images("전혀 다른 주제", [], count=3)
    assert len(names) == 3 and len(set(names)) == 1  # 매칭이 없어도 전체를 순환해 사용


def test_missing_cache_returns_empty_instead_of_failing(sandbox):
    assert images.resolve_unsplash_images("조명", [], count=2) == []


def test_download_failure_returns_empty_list(sandbox, monkeypatch):
    write_cache(sandbox, [{"url": "https://img.test/a.jpg", "query": "x", "desc": "y"}])

    def boom(url, **kwargs):
        raise OSError("network down")

    monkeypatch.setattr("requests.get", boom)
    assert images.resolve_unsplash_images("조명", [], count=1) == []


def test_live_search_is_used_first_when_a_key_is_set(sandbox, monkeypatch):
    monkeypatch.setenv("UNSPLASH_ACCESS_KEY", "key-for-test")

    def fake_get(url, **kwargs):
        sandbox["calls"].append(url)
        if url.endswith("/search/photos"):
            return FakeResponse({"results": [{"id": "p1", "urls": {"regular": "https://img.test/live.jpg"}}]})
        return FakeResponse(content=b"LIVE")

    monkeypatch.setattr("requests.get", fake_get)
    names = images.resolve_unsplash_images("인테리어", [], count=1)
    assert len(names) == 1 and (sandbox["uploads"] / names[0]).read_bytes() == b"LIVE"
    assert sandbox["calls"][0].endswith("/search/photos") and any(
        c.endswith("/photos/p1/download") for c in sandbox["calls"]
    )


def test_topic_keywords_map_to_english_queries():
    assert images._unsplash_english_query("무드등 추천") == "mood lamp"
    assert images._unsplash_english_query("아무 말") == "interior design"


def test_paths_still_point_at_the_repo_data_folder():
    """파일 위치가 바뀌어도(parents 단계 수) 업로드 폴더·캐시가 저장소 루트의 data/ 아래여야 한다."""
    assert images.UPLOADS_DIR == ROOT / "data" / "blog_uploads"
    assert images._UNSPLASH_CACHE == ROOT / "data" / "unsplash_images.json"


def test_router_keeps_its_old_names_as_re_exports():
    from ai_orchestrator.connectors.naver_blog import naver_blog_router as router

    assert router._resolve_unsplash_images is images.resolve_unsplash_images
    assert router.UPLOADS_DIR is images.UPLOADS_DIR


@pytest.mark.parametrize("rel", CLI_FILES)
def test_cli_scripts_no_longer_import_the_router(rel):
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    modules = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert not any("naver_blog_router" in m for m in modules), modules
    assert any(m == "scripts.naver.blog.unsplash_images" for m in modules), modules
