"""앱 런타임 LLM 단일 출처 — 앱에 연결된 모든 기능은 GPT(OpenAI)를 사용한다.

아키텍처 경계(중요):
  • 앱(단독앱·FastAPI 서버·웹·데스크톱 런타임)의 모든 AI 기능 = **GPT(OpenAI) 전용**.
  • 터미널 Claude Code 연동(MCP 서버·git 훅 AI 리뷰·OpenAI 부재 시 CLI 폴백)은
    **별개 경계** — 이 모듈을 쓰지 않으며, 거기서만 Claude 가 허용된다.
  • 앱 기능은 모델명을 하드코딩하지 말고 반드시 여기서 import 한다.
  • 경계 강제: ``tests/test_app_llm_boundary.py`` 가 경계 밖의 Anthropic 직접호출을 차단한다.

레이어: L1 공유 계약 — 순수 상수, 외부 의존 0.
"""

from __future__ import annotations

# 앱 LLM 공급자 — 앱 기능은 GPT(OpenAI) 외 사용 금지.
APP_LLM_PROVIDER = "openai"

# 기본 모델(빠름·저렴) — 대부분의 채팅/생성 도구가 사용.
APP_LLM_MODEL = "gpt-4o-mini"

# 고품질 모델(추론·이미지 vision) — 자율 에이전트·고품질 상세설명 등.
APP_LLM_QUALITY_MODEL = "gpt-4o"

__all__ = (
    "APP_LLM_MODEL",
    "APP_LLM_PROVIDER",
    "APP_LLM_QUALITY_MODEL",
)
