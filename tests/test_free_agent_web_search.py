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

from scripts.browser_agent import free_agent as FA

# in-process 직접 호출 대상 커넥터 — 이걸 모킹하면 HTTP/포트/인증 없이 동작 검증.
NEWS_MOD = "ai_orchestrator.connectors.naver_news_router"


# ── 1) web_search 정상 포맷 (커넥터 직접 호출) ───────────────────


def test_web_search_formats_items(monkeypatch):
    items = [
        {
            "title": "공모전 A 개최",
            "summary": "대우건설 스타트업 공모전 안내",
            "url": "https://x/1",
            "datetime": "Mon, 01 Jun 2026",
        },
        {"title": "공모전 B", "summary": "요약B", "url": "https://x/2", "datetime": "Tue, 02 Jun 2026"},
    ]
    captured = {}

    def _fake_news(query, page=1):
        captured["query"] = query
        captured["page"] = page
        return items

    monkeypatch.setattr(NEWS_MOD + "._naver_openapi_news", _fake_news)
    out = FA._web_search({"query": "대우건설 공모전"})

    # HTTP 가 아니라 커넥터 함수를 직접 호출하는지(쿼리 전달 확인)
    assert captured["query"] == "대우건설 공모전"
    # 결과 포맷에 제목·요약·URL 이 포함
    assert "공모전 A 개최" in out
    assert "https://x/1" in out
    assert "2건" in out


# ── 2) 빈 검색어 방어 (커넥터 미호출) ────────────────────────────


def test_web_search_empty_query_no_call(monkeypatch):
    called = {"n": 0}

    def _fake_news(query, page=1):  # 호출되면 안 됨
        called["n"] += 1
        return []

    monkeypatch.setattr(NEWS_MOD + "._naver_openapi_news", _fake_news)
    out = FA._web_search({"query": "   "})
    assert "검색어" in out
    assert called["n"] == 0  # 빈 입력은 커넥터 호출 없이 즉시 반환


# ── 3) 무결과 — 떠넘기지 않고 재시도 가이드 ──────────────────────


def test_web_search_no_items_guides_retry(monkeypatch):
    monkeypatch.setattr(NEWS_MOD + "._naver_openapi_news", lambda query, page=1: [])
    out = FA._web_search({"query": "존재하지않는검색어zzz"})
    assert "결과가 없습니다" in out
    # 무결과여도 "직접 검색하세요" 식 떠넘기기 문구는 없어야 한다
    assert "직접 검색" not in out


# ── 4) 커넥터 예외(키 미설정·네트워크) 도 죽지 않고 사유 보고 ────


def test_web_search_handles_connector_error(monkeypatch):
    def _boom(query, page=1):
        raise RuntimeError("NAVER_OPENAPI_CLIENT_ID / SECRET 환경변수 미설정")

    monkeypatch.setattr(NEWS_MOD + "._naver_openapi_news", _boom)
    out = FA._web_search({"query": "x"})
    assert "오류" in out  # 예외 없이 사유 문자열 반환
    assert "직접 검색" not in out  # 떠넘기지 않음


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
