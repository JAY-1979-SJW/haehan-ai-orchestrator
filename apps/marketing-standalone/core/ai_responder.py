"""AI 기반 블로그 글 초안 생성 — 독립 앱 전용 사본.

원본: scripts/naver/automation/integration/ai_responder.py (AIResponder).
차이점:
  - ai_orchestrator.llm.openai_guard.assert_openai_allowed 의존 제거.
    원본은 "회사 소유 API 키로 회사 서비스가 호출"하는 내부 자동화라 승인 게이트가
    필요했지만, 이 독립 앱은 **고객이 자기 OpenAI API 키로 직접 호출**하므로
    회사 승인 정책과 무관하다(고객 본인 비용/책임).
  - 블로그 글 초안 생성(draft_blog_post)만 남김 — 리뷰 답변/상품설명 등
    스마트스토어 전용 기능은 이 제품 범위 밖이라 제외.

요구: .env 의 OPENAI_API_KEY (setup_gui.py 로 저장됨)
"""

from __future__ import annotations

import json
import os
import re
import urllib.request

_DEFAULT_MODEL = "gpt-4o-mini"

# 예외 메시지에 API 키가 실려 화면(고객 콘솔)에 출력되는 걸 막는다(2026-09-12 보안 재검토).
_SECRET_PATTERN = re.compile(r"(sk-[a-zA-Z0-9_-]{10,}|Bearer\s+[a-zA-Z0-9._-]{10,})")


def _redact(text: str) -> str:
    return _SECRET_PATTERN.sub("[REDACTED]", text)


class AIResponder:
    def __init__(self, model: str | None = None):
        self.api_key = os.environ.get("OPENAI_API_KEY")
        self.model = model or _DEFAULT_MODEL
        self.endpoint = "https://api.openai.com/v1/chat/completions"

    def _call(self, system: str, user: str, max_tokens: int = 500) -> dict:
        if not self.api_key:
            return {"ok": False, "error": "no_api_key", "hint": "설정 화면에서 OpenAI API 키를 입력해주세요."}

        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        try:
            req = urllib.request.Request(  # noqa: S310 (고정된 OpenAI 공식 엔드포인트)
                self.endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                data = json.loads(resp.read())
            text = data["choices"][0]["message"]["content"]
            return {"ok": True, "text": text.strip(), "model": self.model}
        except Exception as e:  # noqa: BLE001 - AI 응답 생성 API 호출 실패 - ok:False + _redact()로 민감정보 제거된 에러 메시지만 반환, 이미 안전 처리된 에러 경로
            return {"ok": False, "error": _redact(str(e))[:200]}

    def draft_blog_post(self, topic: str, keywords: list[str] | None = None, length: str = "medium") -> dict:
        length_map = {"short": 500, "medium": 1500, "long": 3000}
        max_tok = length_map.get(length, 1500)
        kw_str = ", ".join(keywords or [])
        system = "한국어 블로그 작가입니다. SEO를 고려한 자연스러운 글을 작성하세요."
        user = f"주제: {topic}\n키워드: {kw_str}\n길이: {length}\n\n블로그 글을 작성해 주세요."
        return self._call(system, user, max_tokens=max_tok)
