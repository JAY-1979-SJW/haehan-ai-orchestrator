"""원본 1개 주제 → 채널별 콘텐츠 패키지 생성 (마케팅 운영실 v1).

blog/marketing 파이프라인(topics.py/content.py)이 만드는 블로그 글을
"원본"으로 삼고, 같은 주제를 유튜브 대본·쇼츠 대본·인스타 캡션·커뮤니티
답변 초안으로 재가공한다. 실제 게시는 하지 않음 — 전부 초안 생성까지만
(기준서 원칙: 미리보기 → 사람 승인 → 게시).

사용:
    from scripts.naver.blog.marketing.multichannel import generate_content_package
    pkg = generate_content_package("벽등 하나 달았는데 왜 집이 호텔처럼 보일까?")
"""

from __future__ import annotations

from scripts.common.logger import get_logger
from scripts.naver.automation.integration.ai_responder import AIResponder

_log = get_logger(__name__)


def _draft(key: str, system: str, prompt: str, max_tokens: int) -> dict:
    """AIResponder 로 초안 1개 생성 — 실패면 {"ok": False}, 성공이면 {"ok": True, key: 앞뒤 공백 뺀 본문}.

    채널별 generate_* 4개가 같은 호출·결과 포장을 복사해 쓰던 본문을 한 곳으로 모았다(문구·키는 각자 넘김).
    """
    ai = AIResponder()
    r = ai._call(system, prompt, max_tokens=max_tokens)
    if not r.get("ok"):
        return {"ok": False}
    return {"ok": True, key: r["text"].strip()}


def generate_youtube_script(topic: str, angle: str = "") -> dict:
    return _draft(
        "script",
        "조명·인테리어 전문 유튜브 채널 작가. 실제 시공 경험을 근거로 친절하고 "
        "신뢰감 있게 설명하되 광고 문구는 쓰지 않는다.",
        f"""주제: {topic}
{f"각도: {angle}" if angle else ""}
5~8분 분량 유튜브 영상 대본을 작성하세요. 다음 형식으로:

[제목 후보 5개]
1~5.

[썸네일 문구]
(짧고 임팩트 있게, 10자 내외 1~2개)

[장면 구성]
장면1: (설명) — 필요한 자료: (제품사진/Before-After/AI생성컷 등 명시)
장면2: ...
(장면마다 이렇게 5~8개)

[대본]
(각 장면에 대응하는 실제 나레이션 텍스트, 친근한 구어체)

실제 시공 사진/영상이 있다면 그걸 우선 쓰라고 장면 구성에 명시하고,
AI 생성 이미지는 보조 자료로만 쓰라고 표시하세요.""",
        max_tokens=3000,
    )


def generate_shorts_scripts(topic: str, count: int = 3) -> dict:
    return _draft(
        "scripts",
        "조명·인테리어 숏폼 콘텐츠 작가. 15~30초 안에 훅-정보-마무리가 끝나야 한다.",
        f"""주제: {topic}
이 주제에서 파생되는 서로 다른 앵글의 쇼츠(15~30초) {count}개를 기획하세요.
각각:

[쇼츠 N: 제목]
- 훅(첫 3초 문구):
- 내용 흐름(시간대별):
- 자막 텍스트:
- CTA(마지막 문구):
""",
        max_tokens=1500,
    )


def generate_instagram_caption(topic: str, cta_url: str = "https://haehan-ai.kr") -> dict:
    return _draft(
        "caption",
        "인테리어 브랜드 인스타그램 운영자. 감성적이되 과장 광고 문구는 피한다.",
        f"""주제: {topic}
릴스(15~30초, Before/After 구성)용 캡션을 작성하세요.
- 첫 줄: 스크롤을 멈추게 할 한 줄
- 본문: 2~4문장, 실제 후기/경험 톤
- 해시태그: 8~12개 (인테리어·조명 관련, 스팸성 태그 도배 금지)
- 마지막 줄: 자연스러운 CTA (문의는 {cta_url})""",
        max_tokens=600,
    )


def generate_community_answer(question: str, question_context: str = "") -> dict:
    """실제 커뮤니티 질문에 대한 답변 초안 — 광고 문구 없이 정보 위주.

    자동 게시 금지(기준서 원칙) — 사람이 검토 후 직접 답한다.
    """
    return _draft(
        "answer",
        "조명·인테리어 실무 경험자. 커뮤니티에서 진짜 도움이 되는 답변을 쓴다. "
        "절대 홍보·광고 문구를 넣지 않는다 — 정보 제공이 유일한 목적.",
        f"""질문: {question}
{f"맥락: {question_context}" if question_context else ""}
이 질문에 대한 답변 초안을 작성하세요. 실제 경험/사례 기반으로 구체적으로,
2~4문단. 마지막에 광고 문구("저희 업체 이용하세요" 등)는 절대 넣지 마세요.""",
        max_tokens=800,
    )


def generate_content_package(topic: str, angle: str = "") -> dict:
    """원본 주제 하나 → 블로그 제외 전 채널 콘텐츠 패키지."""
    return {
        "topic": topic,
        "youtube": generate_youtube_script(topic, angle),
        "shorts": generate_shorts_scripts(topic),
        "instagram": generate_instagram_caption(topic),
    }
