"""OpenAI(GPT) 호출 차단 게이트 — 2026-08-19 사업자 결정.

배경: 블로그·상품설명 등 글 작성을 GPT API로 처리해 왔는데, 사업자가
"GPT를 쓰지 않고 Claude Code를 쓴다"고 결정했다. 비용도 비용이지만,
GPT는 학습 데이터만으로 쓰다 보니 없는 수치("2022년 건설산업기본법",
"최저임금 10,000원")를 지어내는 문제가 실제로 발생했다. Claude Code는
웹 검색으로 근거를 확인하고 쓸 수 있어 품질이 다르다.

차단 방식:
  1) .env 의 OPENAI_API_KEY 주석 처리 + OPENAI_DISABLED=true
  2) 이 모듈의 assert_openai_allowed() 를 호출 지점에 삽입 (← 이 파일)

⚠️ .env 만으로는 못 막는다. Windows 시스템 환경변수에 키가 등록돼 있어
   .env 를 지워도 os.environ 으로 살아 들어온다(2026-08-19 실측).
   그래서 코드 레벨 가드가 필요하다.

다시 켜려면: .env 의 OPENAI_DISABLED=false (사업자 승인 후에만)
"""

from __future__ import annotations

import os


class OpenAIDisabledError(RuntimeError):
    """OpenAI 호출이 정책으로 차단된 상태에서 호출을 시도한 경우."""


_MESSAGE = (
    "OpenAI(GPT) 호출이 차단되어 있습니다 (2026-08-19 사업자 결정).\n"
    "  · 글 작성은 Claude Code가 직접 수행합니다 — GPT 대신 사람이 검토한 원고를 발행하세요.\n"
    "  · 블로그 발행: scripts/naver/blog/cli 의 blog_publish_manual 모듈 사용\n"
    "  · 정말 필요하면 .env 의 OPENAI_DISABLED=false 로 바꾸되, 사업자 승인이 먼저입니다."
)


def openai_disabled() -> bool:
    """차단 상태 여부. 기본값은 '차단'이다(플래그가 없어도 막는다)."""
    return os.getenv("OPENAI_DISABLED", "true").strip().lower() not in ("false", "0", "no")


def assert_openai_allowed(caller: str = "") -> None:
    """OpenAI 호출 직전에 부른다. 차단 상태면 예외를 던진다."""
    if openai_disabled():
        where = f" [{caller}]" if caller else ""
        raise OpenAIDisabledError(f"{_MESSAGE}{where}")
