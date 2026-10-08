"""네이버 CDP 라우터의 playwright 스레드 안전성 검증.

배경: web_connector.get_page() 로 얻은 page 를 FastAPI 요청 스레드에서 직접 조작하면
playwright sync API 가 'Cannot switch to a different thread' 로 깨진다(로그인 감지 실패 등).
반드시 run_on_browser_thread 로 브라우저 전용 스레드에서 호출해야 한다.

이 테스트는 get_page() 를 쓰는 네이버 라우터가 run_on_browser_thread 도 함께 쓰는지
파일 단위로 검증해 회귀를 막는다.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# get_page() 로 CDP page 를 조작하는 라우터들 — 모두 run_on_browser_thread 필수
NAVER_CDP_ROUTERS = [
    "ai_orchestrator/connectors/naver_cafe/naver_cafe_router.py",
    "ai_orchestrator/connectors/naver_mail/naver_mail_router.py",
    "ai_orchestrator/connectors/naver_blog/naver_blog_router.py",
    "ai_orchestrator/connectors/community_router.py",
    "ai_orchestrator/connectors/eum/router.py",
    "ai_orchestrator/connectors/google/gmail_router.py",
    "ai_orchestrator/connectors/hiworks/mail_router.py",
]


def test_naver_routers_wrap_get_page_in_browser_thread():
    offenders = []
    for rel in NAVER_CDP_ROUTERS:
        text = (ROOT / rel).read_text(encoding="utf-8")
        if "get_page()" in text and "run_on_browser_thread" not in text:
            offenders.append(rel)
    assert not offenders, (
        "get_page() 를 쓰지만 run_on_browser_thread 가 없음 — playwright 스레드 버그 위험:\n" + "\n".join(offenders)
    )
