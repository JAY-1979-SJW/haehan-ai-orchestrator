"""FREE_AGENT_WEB_SEARCH — 자율 에이전트의 브라우저 불필요 웹검색 도구 단위 테스트.

배경: 앱 콘솔 에이전트가 공개정보 조회를 CDP 브라우저로만 시도하다 실패하면
"직접 검색하세요"로 떠넘기던 문제를 web_search 도구 추가로 해결. 본 테스트는
- web_search 가 기존 뉴스검색 API(naver_news_router, CDP 불필요)를 재사용하고
- 결과를 사람이 읽을 형태로 포맷하며
- 빈 입력/무결과를 안전하게 처리하고
- 도구가 _TOOLS·dispatch·시스템 프롬프트에 올바로 배선됐는지
네트워크/서버 없이(_call_local_api 모킹) 검증한다.
"""

from __future__ import annotations

import json

from scripts.browser_agent import free_agent as FA

# ── 1) web_search 정상 포맷 ──────────────────────────────────────


def test_web_search_formats_items(monkeypatch):
    fake = {
        "items": [
            {
                "title": "공모전 A 개최",
                "summary": "대우건설 스타트업 공모전 안내",
                "url": "https://x/1",
                "datetime": "Mon, 01 Jun 2026",
            },
            {"title": "공모전 B", "summary": "요약B", "url": "https://x/2", "datetime": "Tue, 02 Jun 2026"},
        ],
        "total": 2,
        "query": "대우건설 공모전",
    }
    captured = {}

    def _fake_call(args):
        captured.update(args)
        return json.dumps(fake, ensure_ascii=False)

    monkeypatch.setattr(FA, "_call_local_api", _fake_call)
    out = FA._web_search({"query": "대우건설 공모전"})

    # 기존 뉴스검색 API(CDP 불필요)를 재사용하는지
    assert captured["path"] == "/api/v1/external/naver/news-search"
    assert captured["method"] == "GET"
    assert captured["params"]["query"] == "대우건설 공모전"
    # 결과 포맷에 제목·요약·URL 이 포함
    assert "공모전 A 개최" in out
    assert "https://x/1" in out
    assert "2건" in out


# ── 2) 빈 검색어 방어 ────────────────────────────────────────────


def test_web_search_empty_query_no_network(monkeypatch):
    called = {"n": 0}

    def _fake_call(args):  # 호출되면 안 됨
        called["n"] += 1
        return "{}"

    monkeypatch.setattr(FA, "_call_local_api", _fake_call)
    out = FA._web_search({"query": "   "})
    assert "검색어" in out
    assert called["n"] == 0  # 빈 입력은 API 호출 없이 즉시 반환


# ── 3) 무결과 — 떠넘기지 않고 재시도 가이드 ──────────────────────


def test_web_search_no_items_guides_retry(monkeypatch):
    monkeypatch.setattr(FA, "_call_local_api", lambda args: json.dumps({"items": []}))
    out = FA._web_search({"query": "존재하지않는검색어zzz"})
    assert "결과가 없습니다" in out
    # 무결과여도 "직접 검색하세요" 식 떠넘기기 문구는 없어야 한다
    assert "직접 검색" not in out


# ── 4) API 가 비정상(JSON 아님) 일 때도 죽지 않음 ────────────────


def test_web_search_handles_nonjson(monkeypatch):
    monkeypatch.setattr(FA, "_call_local_api", lambda args: "HTTP 503: 뉴스 검색 오류")
    out = FA._web_search({"query": "x"})
    assert "503" in out or "검색 결과" in out  # 원문을 그대로 노출, 예외 없이 반환


# ── 5) 도구 배선 — _TOOLS / dispatch ─────────────────────────────


def test_web_search_registered_in_tools():
    names = {t["function"]["name"] for t in FA._TOOLS}
    assert "web_search" in names
    spec = next(t for t in FA._TOOLS if t["function"]["name"] == "web_search")
    assert "query" in spec["function"]["parameters"]["required"]


# ── 6) 시스템 프롬프트 — 떠넘기기 금지 계약 ──────────────────────


def test_system_prompt_forbids_deferring_to_user():
    sys = FA._SYSTEM
    assert "web_search" in sys
    # 핵심 행동 계약: 사용자에게 작업을 미루지 말 것
    assert "떠넘기" in sys
    assert "직접 검색하세요" in sys


# ── 7) 내부 API 포트 — 하드코딩 금지, APP_PORT 따름 ──────────────
# prod 컨테이너(8400) vs 로컬 dev(8401) 포트 차이로 call_local_api/web_search 가
# 연결거부되던 회귀를 방지. _LOCAL_PORT 는 import 시점 평가 → reload 로 검증.


def test_local_api_port_follows_app_port(monkeypatch):
    import importlib

    monkeypatch.setenv("APP_PORT", "8400")  # prod 컨테이너 포트
    mod = importlib.reload(FA)
    try:
        assert mod._LOCAL_PORT == "8400"
        assert mod._LOCAL_API == "http://127.0.0.1:8400"
        assert mod._SS_API == "http://127.0.0.1:8400/api/v1/smartstore"
        # 하드코딩 8401 흔적이 남아있지 않은지
        assert "8401" not in mod._LOCAL_API
    finally:
        monkeypatch.delenv("APP_PORT", raising=False)
        importlib.reload(mod)  # 모듈 상태 원복


def test_local_api_port_fallback_when_unset(monkeypatch):
    import importlib

    monkeypatch.delenv("APP_PORT", raising=False)  # 미설정 환경
    mod = importlib.reload(FA)
    assert mod._LOCAL_PORT == "8401"  # 로컬 dev 기본값
    assert mod._LOCAL_API == "http://127.0.0.1:8401"
