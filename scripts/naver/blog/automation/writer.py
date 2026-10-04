"""글 작성 — 기준서의 최신 프롬프트를 재사용해 `claude -p` 로 초안 1편을 만든다.

기준서: docs/specs/2026-09-30_blog_auto_writing_automation.md (v2 §4 단계 3)

새로 쓰지 않고 `marketing/gpt_writer.py` 의 것을 그대로 쓴다: 계정별 프롬프트 템플릿(기준서를 옮긴 것),
`parse_draft`(JSON 응답 파싱), `review_draft`(발행 전 자동 점검). 바뀌는 것은 전송 수단(ChatGPT 웹 → claude -p)뿐이다.
옛 경로 `content.generate_post` 는 OpenAI API 차단·앱 런타임 AI 스텁이라 쓰지 않는다.

- 웹 검색을 못 하는 실행이면 템플릿의 "웹 검색으로 근거를 찾으세요" 절을 정직한 문구로 바꾼다
  (검색을 못 하는데 출처를 확인한 것처럼 쓰게 만들지 않기 위해).
- 경쟁 글 조사(competitor_block)는 CDP 브라우저가 필요해 이 단계에서는 하지 않는다.
- CTA 는 Claude 가 쓰지 않는다(기준서: 제품 실측치를 지어낼 위험). 호출자가 넘긴 CTA 를 본문 끝에 붙인다.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from scripts.naver.blog.accounts import DEFAULT_ACCOUNT
from scripts.naver.blog.marketing import content, gpt_writer

SYSTEM_PROMPT = "당신은 한국 실무 블로그 작가입니다. 요청받은 JSON 형식으로만 답하고 다른 설명은 붙이지 않습니다."

_EVIDENCE_SECTION = re.compile(r"## 먼저 할 일 — 근거 조사.*?(?=\{competitor_block\})", re.S)
_NO_WEB_SECTION = (
    "## 근거 — 이번 작성에서는 웹 검색을 쓸 수 없습니다\n"
    "아는 범위에서만 쓰세요. 확실하지 않은 수치·조항 번호·요율·연도·금액은 **쓰지 말고**\n"
    '"어디서 확인하는지(기관·문서명)"를 안내하세요. 출처를 확인한 것처럼 쓰지 마세요.\n\n'
)
# review_draft 의 problems 중 seo_check 가 못 보는 것만 경고로 합친다(분량·태그는 check_quality 가 따로 본다).
_REVIEW_PROBLEMS_TO_KEEP = ("마크다운 기호", "[핵심 답변]")


def build_prompt(topic_info: dict[str, Any], blog_id: str, *, web: bool = False) -> str:
    """계정별 템플릿에 주제를 채운 프롬프트. web=False 면 근거 조사 절을 웹 검색 불가 문구로 바꾼다."""
    template = gpt_writer._PROMPT_TEMPLATES.get(blog_id)
    if template is None:
        raise ValueError(f"프롬프트 템플릿이 없는 계정: {blog_id}")
    if not web:
        template, replaced = _EVIDENCE_SECTION.subn(lambda _m: _NO_WEB_SECTION, template, count=1)
        if not replaced:
            raise RuntimeError("gpt_writer 프롬프트의 '근거 조사' 절 모양이 바뀜 — writer.py 를 함께 고칠 것")
    note = str(topic_info.get("revision_note") or "").strip()
    revision_block = f"## 수정 지시 (이전 초안의 검사 결과)\n{note}\n" if note else ""
    return template.format(
        topic=topic_info.get("topic", ""),
        source=topic_info.get("source_description") or topic_info.get("source") or "(없음)",
        keywords=", ".join(topic_info.get("keywords", [])),
        competitor_block=revision_block,
        min_chars=content.MIN_BODY_CHARS,
        target_chars=content.TARGET_BODY_CHARS,
        min_tags=content.MIN_TAG_COUNT,
        target_tags=content.TARGET_TAG_COUNT,
    )


def _clean_tags(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    tags = (str(t).strip().lstrip("#").strip() for t in raw)
    return list(dict.fromkeys(t for t in tags if t))


def _review_warnings(draft: dict[str, Any]) -> list[str]:
    problems = gpt_writer.review_draft(draft).get("problems", [])
    return [p for p in problems if any(key in p for key in _REVIEW_PROBLEMS_TO_KEEP)]


def draft_post(
    topic_info: dict[str, Any],
    *,
    llm: Callable[..., dict[str, Any]],
    cta_block: str | None = None,
    blog_id: str = DEFAULT_ACCOUNT,
    web: bool = False,
) -> dict[str, Any] | None:
    """주제 → {title, body(CTA 포함), body_segments, tags, seo, cost_usd?}. 생성·파싱에 실패하면 None.

    초안 텍스트만 만든다. 네이버에 쓰는 `core.writer.write_post` 와 이름·역할이 다르다.
    """
    result = llm(SYSTEM_PROMPT, build_prompt(topic_info, blog_id, web=web), 8000)
    if not result.get("ok"):
        return None
    draft = gpt_writer.parse_draft(result.get("text", ""))
    if draft is None:
        return None
    title, body = str(draft["title"]).strip(), str(draft["body"]).strip()
    tags = _clean_tags(draft.get("tags"))
    main_keyword = (topic_info.get("keywords") or [None])[0]
    if main_keyword:  # 핵심 키워드는 항상 첫 태그 — 검사(seo_check)의 태그 수와 실제 발행 태그를 일치시킨다
        tags = [main_keyword, *[t for t in tags if t != main_keyword]]
    seo = content.seo_check(title=title, body=body, keywords=tags)
    seo = {**seo, "warnings": [*seo["warnings"], *_review_warnings({"body": body, "tags": tags})]}
    seo["ok"] = not seo["warnings"]
    cta = content._CTA_BLOCK if cta_block is None else cta_block
    post: dict[str, Any] = {
        "title": title,
        "body": body + cta,
        "body_segments": [*content.split_body(body, parts=3), cta.strip()],
        "tags": tags,
        "seo": seo,
    }
    if isinstance(result.get("cost_usd"), int | float):
        post["cost_usd"] = float(result["cost_usd"])
    return post
