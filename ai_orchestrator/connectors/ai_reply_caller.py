"""AI 기반 문의 답변 생성 커넥터 (L3) — 카카오 챗봇 / 인스타 댓글·DM 공용.

정책:
  - 벤더 미정(2026-09-12, 사용자가 "나중에 결정") — 이 모듈은 ANTHROPIC_API_KEY가
    설정된 경우에만 실제로 호출한다. 키가 없으면 즉시 None을 반환해 호출부가
    기존 규칙기반(message_classifier) 응답으로 자연스럽게 폴백하게 만든다.
    즉 이 파일이 존재해도 키를 넣기 전까지는 유료 API 호출이 전혀 발생하지 않는다.
  - 짧은 타임아웃(기본 3.5초)으로 호출한다 — 카카오 스킬의 5초 응답 제한 안에
    폴백 판단까지 끝내기 위함. 실패/타임아웃 시 예외를 삼키고 None 반환.
  - 시스템 프롬프트에 "회사 정보 밖 확답 금지" 제약을 강제한다 — 확인 안 된 가격/일정을
    확답하면 안 되고, 담당자 확인이 필요하다는 안내로 마무리하게 한다.
"""

from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

# API 키 패턴이 예외 메시지에 실려 로그로 유출되는 걸 막는다(2026-09-12,
# 보안 재검토 계기 — SDK/urllib 예외가 헤더까지 str(e)에 포함하는지 100%
# 보장 못 하므로 로깅 직전에 항상 마스킹).
_SECRET_PATTERN = re.compile(r"(sk-ant-[a-zA-Z0-9_-]{10,}|sk-[a-zA-Z0-9_-]{10,}|Bearer\s+[a-zA-Z0-9._-]{10,})")


def _redact(text: str) -> str:
    return _SECRET_PATTERN.sub("[REDACTED]", text)


_DEFAULT_TIMEOUT = 3.5
_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM_PROMPT = (
    "당신은 회사 고객 문의에 1차 응대하는 상담 보조입니다. "
    "가격, 재고, 일정처럼 확인되지 않은 사실은 절대 확답하지 말고, "
    "담당자가 확인 후 안내드리겠다는 취지로 정중하고 짧게(2~3문장 이내) 답하세요. "
    "전화번호나 개인정보는 답변에 포함하지 마세요."
)


def is_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def generate_reply(inquiry_text: str, category: str = "general", timeout: float = _DEFAULT_TIMEOUT) -> str | None:
    """문의 텍스트에 대한 AI 답변 생성. 키 미설정/실패/타임아웃 시 None."""
    if not is_configured():
        return None

    try:
        import anthropic
    except ImportError:
        logger.warning("ai_reply_caller: anthropic 패키지 미설치 — 폴백")
        return None

    try:
        client = anthropic.Anthropic(timeout=timeout)
        resp = client.messages.create(
            model=_MODEL,
            max_tokens=200,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"[카테고리: {category}] 고객 문의: {inquiry_text}"}],
        )
        text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text").strip()
        return text or None
    except Exception as e:  # 타임아웃 포함 모든 실패는 폴백으로 처리
        logger.warning("ai_reply_caller: 호출 실패(%s) — 폴백", _redact(str(e)))
        return None
