"""네이버 검색 OpenAPI 수집 — 비로그인 공개 검색 테스트."""
from __future__ import annotations

import json
import logging

import pytest

from ai_orchestrator.connectors.naver_search import (
    naver_public_page_reader,
)
from scripts.naver.shopping import naver_blog_collectors
from scripts.naver.shopping import naver_search_jobs
from scripts.naver.shopping import (
    naver_openapi_config as cfg_mod,
    naver_search_client,
    naver_search_utils,
    naver_shopping_collectors,
)


# ── helpers ─────────────────────────────────────────────────────
def _clear_env(monkeypatch):
    for k in (
        cfg_mod.ENV_BASE_URL, cfg_mod.ENV_CLIENT_ID,
        cfg_mod.ENV_CLIENT_SECRET, cfg_mod.ENV_DRY_RUN,
    ):
        monkeypatch.delenv(k, raising=False)


# ────────────────────────────────────────────────────────────────
# 1) live + env 누락 시 명확한 에러 (키 이름만, 값은 미노출)
# ────────────────────────────────────────────────────────────────
def test_require_live_lists_missing_keys_only(monkeypatch):
    _clear_env(monkeypatch)
    cfg = cfg_mod.load_config()
    with pytest.raises(cfg_mod.NaverOpenApiConfigError) as e:
        cfg_mod.require_live(cfg)
    msg = str(e.value)
    assert cfg_mod.ENV_CLIENT_ID in msg
    assert cfg_mod.ENV_CLIENT_SECRET in msg


def test_live_without_env_returns_unconfigured(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv(cfg_mod.ENV_DRY_RUN, "false")

    def transport(**_):
        raise AssertionError("transport must not be called")

    client = naver_search_client.NaverSearchClient(transport=transport)
    r = client.search_blog("python")
    assert r.status == "unconfigured"
    assert r.error_code == "MISSING_CREDENTIALS"


# ────────────────────────────────────────────────────────────────
# 2) dry_run 기본 동작 — 네트워크 미사용, mock 반환
# ────────────────────────────────────────────────────────────────
def test_dry_run_default_does_not_call_transport(monkeypatch):
    _clear_env(monkeypatch)  # dry_run default true

    def transport(**_):
        raise AssertionError("transport must not be called in dry_run")

    client = naver_search_client.NaverSearchClient(transport=transport)
    r1 = client.search_blog("python")
    r2 = client.search_shop("keyboard")
    assert r1.status == "dry_run"
    assert r2.status == "dry_run"
    assert r1.item_count >= 1
    assert r2.item_count >= 1
    # 헤더 키만 노출되고 값은 어디에도 없음
    flat = repr({"r1": r1.to_dict(), "r2": r2.to_dict()})
    assert "X-Naver-Client-Secret" in r1.request_summary["header_keys"]
    assert cfg_mod.DEFAULT_BASE_URL in flat or "openapi.naver.com" in flat


# ────────────────────────────────────────────────────────────────
# 3) GET 외 메서드 차단
# ────────────────────────────────────────────────────────────────
def test_non_get_method_blocked(monkeypatch):
    _clear_env(monkeypatch)
    client = naver_search_client.NaverSearchClient()
    r = client._request(
        source="naver_blog", path="/v1/search/blog.json",
        params={"query": "x", "display": 1, "start": 1, "sort": "sim"},
        method="POST",
    )
    assert r.status == "error"
    assert r.error_code == "METHOD_NOT_ALLOWED"


# ────────────────────────────────────────────────────────────────
# 4) 블로그 응답 정규화 스키마 일관성
# ────────────────────────────────────────────────────────────────
def test_blog_normalization_schema(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv(cfg_mod.ENV_CLIENT_ID, "cid")
    monkeypatch.setenv(cfg_mod.ENV_CLIENT_SECRET, "cs")
    monkeypatch.setenv(cfg_mod.ENV_DRY_RUN, "false")

    def transport(method, url, headers, params):
        body = {
            "lastBuildDate": "Thu, 23 Apr 2026 00:00:00 +0900",
            "total": 1, "start": 1, "display": 1,
            "items": [
                {
                    "title": "안녕 <b>파이썬</b> &amp; 코드",
                    "link": "https://blog.example.invalid/abc",
                    "description": "요약 <b>line</b>",
                    "bloggername": "닉네임",
                    "bloggerlink": "https://blog.example.invalid/me",
                    "postdate": "20260423",
                }
            ],
        }
        return 200, body

    client = naver_search_client.NaverSearchClient(transport=transport)
    r = naver_blog_collectors.collect_blog_search("파이썬", client=client)
    assert r.status == "ok"
    assert r.item_count == 1
    item = r.items[0]
    expected_keys = {"title", "link", "blogger_name", "blogger_link",
                     "description", "post_date", "source"}
    assert expected_keys.issubset(set(item.keys()))
    assert item["title"] == "안녕 파이썬 & 코드"
    assert item["description"] == "요약 line"
    assert item["post_date"] == "2026-04-23"
    assert item["source"] == "naver_blog"


# ────────────────────────────────────────────────────────────────
# 5) 쇼핑 응답 정규화 스키마 일관성
# ────────────────────────────────────────────────────────────────
def test_shop_normalization_schema(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv(cfg_mod.ENV_CLIENT_ID, "cid")
    monkeypatch.setenv(cfg_mod.ENV_CLIENT_SECRET, "cs")
    monkeypatch.setenv(cfg_mod.ENV_DRY_RUN, "false")

    def transport(method, url, headers, params):
        body = {
            "items": [
                {
                    "title": "<b>Logitech</b> 키보드",
                    "link": "https://shop.example.invalid/p/1",
                    "image": "https://shop.example.invalid/p/1.jpg",
                    "lprice": "29,800",
                    "hprice": "",
                    "mallName": "쇼핑몰A",
                    "productId": "PID-1",
                    "productType": "1",
                    "brand": "Logitech",
                    "maker": "Logitech Inc.",
                    "category1": "디지털",
                    "category2": "주변기기",
                    "category3": "키보드",
                    "category4": "기계식",
                }
            ],
        }
        return 200, body

    client = naver_search_client.NaverSearchClient(transport=transport)
    r = naver_shopping_collectors.collect_shopping_search("키보드", client=client)
    assert r.status == "ok"
    item = r.items[0]
    expected = {"title", "link", "image", "lprice", "hprice", "mall_name",
                "product_id", "product_type", "brand", "maker",
                "category1", "category2", "category3", "category4", "source"}
    assert expected.issubset(set(item.keys()))
    assert item["title"] == "Logitech 키보드"
    assert item["lprice"] == 29800
    assert item["hprice"] is None
    assert item["source"] == "naver_shop"


# ────────────────────────────────────────────────────────────────
# 6) HTML 태그 제거 정상
# ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("raw,expected", [
    ("<b>hi</b>", "hi"),
    ("a &amp; b", "a & b"),
    ("  multi   space  ", "multi space"),
    ("<a href='x'>link</a> tail", "link tail"),
    (None, ""),
    ("", ""),
])
def test_strip_html(raw, expected):
    assert naver_search_utils.strip_html(raw) == expected


# ────────────────────────────────────────────────────────────────
# 7) 가격 문자열 정규화 정상
# ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("raw,expected", [
    ("29800", 29800),
    ("29,800", 29800),
    ("  10000원  ", 10000),
    ("", None),
    (None, None),
    ("foo", None),
    ("0", 0),
])
def test_to_int_price(raw, expected):
    assert naver_search_utils.to_int_price(raw) == expected


# ────────────────────────────────────────────────────────────────
# 8) 민감정보(client secret/header raw) 로그 미노출
# ────────────────────────────────────────────────────────────────
def test_logs_do_not_leak_client_secret(monkeypatch, caplog):
    _clear_env(monkeypatch)
    monkeypatch.setenv(cfg_mod.ENV_CLIENT_ID, "id-supersecret-XYZ")
    monkeypatch.setenv(cfg_mod.ENV_CLIENT_SECRET, "secret-supersecret-ABC")
    # dry_run 으로 두면 transport 안 타지만 헤더는 빌드된다.
    client = naver_search_client.NaverSearchClient()

    with caplog.at_level(logging.DEBUG):
        client.search_blog("rust")
        client.search_shop("rust")

    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "id-supersecret-XYZ" not in text
    assert "secret-supersecret-ABC" not in text
    # cfg redacted 도 길이만 노출
    red = client.config.redacted()
    assert "id-supersecret-XYZ" not in repr(red)
    assert "len=" in red["client_secret"]


# ────────────────────────────────────────────────────────────────
# 9) public page reader — 인증 필요 호스트 / non-html 차단
# ────────────────────────────────────────────────────────────────
def test_reader_blocks_login_required_hosts():
    r = naver_public_page_reader.fetch_public_page_summary(
        "https://nid.naver.com/foo/bar",
    )
    assert r.status == "blocked"
    assert r.error_code == "LOGIN_REQUIRED_HOST"

    r2 = naver_public_page_reader.fetch_public_page_summary(
        "https://cafe.naver.com/some_cafe/articles/1",
    )
    assert r2.status == "blocked"


def test_reader_unsupported_when_no_transport():
    r = naver_public_page_reader.fetch_public_page_summary(
        "https://blog.example.invalid/a"
    )
    assert r.status == "unsupported"
    assert r.error_code == "TRANSPORT_NOT_WIRED"


def test_reader_blocks_on_401_and_unsupported_on_non_html():
    def t401(method, url, headers):
        return 401, {"Content-Type": "text/html"}, ""

    r = naver_public_page_reader.fetch_public_page_summary(
        "https://blog.example.invalid/a", transport=t401,
    )
    assert r.status == "blocked"
    assert r.error_code == "HTTP_401"

    def tjson(method, url, headers):
        return 200, {"Content-Type": "application/json"}, "{}"

    r2 = naver_public_page_reader.fetch_public_page_summary(
        "https://blog.example.invalid/a", transport=tjson,
    )
    assert r2.status == "unsupported"
    assert r2.error_code == "NON_HTML_CONTENT"


def test_reader_extracts_title_meta_canonical():
    html = """
    <html><head>
      <title>내 글 제목</title>
      <meta name="description" content="요약 입니다">
      <meta property="og:title" content="OG 제목">
      <link rel="canonical" href="https://blog.example.invalid/canonical">
    </head><body>본문 생략</body></html>
    """

    def tok(method, url, headers):
        return 200, {"Content-Type": "text/html; charset=utf-8"}, html

    r = naver_public_page_reader.fetch_public_page_summary(
        "https://blog.example.invalid/abc", transport=tok,
    )
    assert r.status == "ok"
    assert r.title == "내 글 제목"
    assert r.meta_description == "요약 입니다"
    assert r.canonical_url == "https://blog.example.invalid/canonical"


# ────────────────────────────────────────────────────────────────
# 10) Job 결과 저장 파일 구조 정상
# ────────────────────────────────────────────────────────────────
def test_blog_job_saves_record(tmp_path, monkeypatch):
    _clear_env(monkeypatch)  # dry_run 기본 — 외부 호출 없음
    store = tmp_path / "data" / "naver_blog_search.json"
    out = naver_search_jobs.run_naver_blog_search_job(
        "파이썬", store_path=store,
    )
    assert out.status == "dry_run"
    assert out.saved_path == str(store)
    assert store.exists()
    data = json.loads(store.read_text(encoding="utf-8"))
    assert data["source"] == "naver_blog"
    assert data["query"] == "파이썬"
    assert "collected_at" in data
    assert isinstance(data["items"], list) and len(data["items"]) >= 1
    # 정규화 키 존재
    assert "blogger_name" in data["items"][0]


def test_shopping_job_saves_record(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    store = tmp_path / "data" / "naver_shopping_search.json"
    out = naver_search_jobs.run_naver_shopping_search_job(
        "키보드", store_path=store,
    )
    assert out.status == "dry_run"
    assert out.saved_path == str(store)
    data = json.loads(store.read_text(encoding="utf-8"))
    assert data["source"] == "naver_shop"
    assert data["query"] == "키보드"
    assert "mall_name" in data["items"][0]


def test_unconfigured_job_does_not_save(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv(cfg_mod.ENV_DRY_RUN, "false")
    store = tmp_path / "data" / "naver_blog_search.json"
    out = naver_search_jobs.run_naver_blog_search_job(
        "파이썬", store_path=store,
    )
    assert out.status == "unconfigured"
    assert out.saved_path is None
    assert not store.exists()
