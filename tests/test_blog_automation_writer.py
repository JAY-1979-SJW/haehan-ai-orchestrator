"""글 작성 — gpt_writer 의 최신 프롬프트·파서 재사용, 웹 검색 불가 문구 교체, CTA·seo 조립. claude 는 부르지 않는다."""

from __future__ import annotations

import json

import pytest

from scripts.naver.blog.automation import writer as W
from scripts.naver.blog.marketing import content, gpt_writer

TOPIC = {
    "topic": "고용산재보험 가입했는데 원천세는?",
    "keywords": ["고용산재", "건설실무"],
    "source_description": "지식iN 질문 원문입니다",
}
BODY = (
    "[핵심 답변]\n고용산재 답입니다.\n\n[이런 상황이시죠]\n상황.\n\n[이렇게 하시면 됩니다]\n고용산재 방법.\n\n[정리하면]\n결론입니다.\n"
    + "본" * 2600
)
TAGS = [f"태그{i}" for i in range(20)]


def reply(**over):
    data = {"title": "고용산재 원천세 납부, 이렇게 하시면 됩니다", "tags": ["고용산재", *TAGS], "body": BODY}
    data.update(over)
    return {"ok": True, "text": "```json\n" + json.dumps(data, ensure_ascii=False) + "\n```", "cost_usd": 0.11}


class FakeLlm:
    def __init__(self, response):
        self.response, self.calls = response, []

    def __call__(self, system, user, max_tokens=0):
        self.calls.append({"system": system, "user": user, "max_tokens": max_tokens})
        return self.response


# ── 프롬프트 ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("blog_id", ["skyjwsin", "skyjwshin"])
def test_prompt_is_filled_for_every_account(blog_id):
    prompt = W.build_prompt(TOPIC, blog_id, web=True)
    for placeholder in ("{topic}", "{source}", "{keywords}", "{competitor_block}", "{min_chars}", "{min_tags}"):
        assert placeholder not in prompt
    assert TOPIC["topic"] in prompt and "지식iN 질문 원문입니다" in prompt and "고용산재, 건설실무" in prompt
    assert str(content.MIN_BODY_CHARS) in prompt and str(content.MIN_TAG_COUNT) in prompt
    assert '{"title"' in prompt  # JSON 출력 형식 예시의 중괄호가 살아 있다


def test_web_off_replaces_the_search_instruction_with_an_honest_one():
    prompt = W.build_prompt(TOPIC, "skyjwsin", web=False)
    assert "웹 검색을 쓸 수 없습니다" in prompt
    assert "웹 검색으로 실제 근거를 찾으세요" not in prompt
    assert "확인한 것처럼 쓰지 마세요" in prompt


def test_web_on_keeps_the_original_research_section():
    prompt = W.build_prompt(TOPIC, "skyjwsin", web=True)
    assert "웹 검색으로 실제 근거를 찾으세요" in prompt and "웹 검색을 쓸 수 없습니다" not in prompt


def test_upstream_template_shape_is_watched():
    """gpt_writer 템플릿의 '근거 조사' 절 모양이 바뀌면 조용히 틀어지지 않고 여기서 실패한다."""
    for template in gpt_writer._PROMPT_TEMPLATES.values():
        assert W._EVIDENCE_SECTION.search(template)
        assert template.count("{competitor_block}") == 1


def test_unknown_account_has_no_template():
    with pytest.raises(ValueError):
        W.build_prompt(TOPIC, "ghost")


def test_revision_note_goes_into_the_competitor_slot():
    prompt = W.build_prompt({**TOPIC, "revision_note": "태그 3개 문제"}, "skyjwsin", web=True)
    assert "## 수정 지시" in prompt and "태그 3개 문제" in prompt
    assert "## 수정 지시" not in W.build_prompt(TOPIC, "skyjwsin", web=True)


def test_source_falls_back_in_order():
    assert "원문 A" in W.build_prompt({**TOPIC, "source_description": "", "source": "원문 A"}, "skyjwsin")
    assert "[검색자의 실제 질문] (없음)" in W.build_prompt({"topic": "t", "keywords": []}, "skyjwsin")


# ── 초안 조립 ────────────────────────────────────────────────────────────


def test_draft_post_assembles_title_tags_cta_and_seo():
    llm = FakeLlm(reply())
    post = W.draft_post(TOPIC, llm=llm)
    assert post["title"].startswith("고용산재 원천세")
    assert post["tags"][0] == "고용산재" and len(post["tags"]) == 21
    assert post["body"].startswith(BODY) and post["body"].endswith(content._CTA_BLOCK)
    assert post["body_segments"][-1] == content._CTA_BLOCK.strip()
    assert post["seo"]["ok"] is True and post["seo"]["warnings"] == []
    assert post["cost_usd"] == 0.11
    assert llm.calls[0]["system"] == W.SYSTEM_PROMPT and TOPIC["topic"] in llm.calls[0]["user"]


def test_custom_cta_replaces_the_standard_one():
    post = W.draft_post(TOPIC, llm=FakeLlm(reply()), cta_block="\n\n맞춤 CTA")
    assert post["body"].endswith("\n\n맞춤 CTA") and content._CTA_BLOCK not in post["body"]
    assert post["body_segments"][-1] == "맞춤 CTA"


def test_tags_are_cleaned_and_deduplicated_with_main_keyword_first():
    post = W.draft_post(TOPIC, llm=FakeLlm(reply(tags=[" 원천세 ", "#고용산재", "고용산재", "", 7, "#"])))
    assert post["tags"] == ["고용산재", "원천세", "7"]


def test_bad_tags_field_becomes_empty_and_is_reported():
    post = W.draft_post(TOPIC, llm=FakeLlm(reply(tags="태그하나")))
    assert post["tags"] == ["고용산재"]  # 핵심 키워드만 남는다
    assert any("태그 1개" in w for w in post["seo"]["warnings"])


def test_markdown_and_missing_summary_are_added_as_warnings():
    bad_body = "## 소제목\n**강조** 본문\n" + "본" * 2600 + "\n[정리하면]\n끝"
    post = W.draft_post(TOPIC, llm=FakeLlm(reply(body=bad_body)))
    joined = " / ".join(post["seo"]["warnings"])
    assert "마크다운 기호" in joined and "[핵심 답변]" in joined
    assert post["seo"]["ok"] is False


def test_review_only_problem_flips_the_seo_ok_flag():
    """`**` 는 seo_check 가 못 보고 review_draft 만 잡는다 — 그 경고가 붙으면 ok 도 False 여야 한다."""
    clean = W.draft_post(TOPIC, llm=FakeLlm(reply()))
    assert clean["seo"]["ok"] is True
    bold = W.draft_post(TOPIC, llm=FakeLlm(reply(body=BODY + "\n**강조**")))
    assert any("마크다운 기호" in w for w in bold["seo"]["warnings"])
    assert bold["seo"]["ok"] is False


def test_length_problem_is_reported_once_not_twice():
    """분량 부족은 seo_check 가 이미 다룬다 — review_draft 의 같은 문구를 중복으로 얹지 않는다."""
    post = W.draft_post(TOPIC, llm=FakeLlm(reply(body="[핵심 답변]\n짧다\n[정리하면]\n끝")))
    assert sum(w.startswith("본문 ") for w in post["seo"]["warnings"]) == 1


@pytest.mark.parametrize(
    "response",
    [
        {"ok": False, "error": "timeout"},
        {"ok": True, "text": "JSON 아님"},
        {"ok": True, "text": json.dumps({"title": "", "body": "x"})},
        {"ok": True, "text": json.dumps({"title": "제목"})},
    ],
)
def test_generation_or_parse_failure_returns_none(response):
    assert W.draft_post(TOPIC, llm=FakeLlm(response)) is None


def test_main_keyword_is_first_for_the_seo_check():
    post = W.draft_post({**TOPIC, "keywords": ["원천세"]}, llm=FakeLlm(reply(tags=["기타"] * 1 + TAGS)))
    # 핵심 키워드 '원천세' 가 제목·본문에 없으면 seo_check 가 지적한다
    assert any("핵심 키워드 '원천세'" in w for w in post["seo"]["warnings"])


def test_web_flag_reaches_the_prompt():
    llm = FakeLlm(reply())
    W.draft_post(TOPIC, llm=llm, web=True)
    assert "웹 검색으로 실제 근거를 찾으세요" in llm.calls[0]["user"]
    llm2 = FakeLlm(reply())
    W.draft_post(TOPIC, llm=llm2, web=False)
    assert "웹 검색을 쓸 수 없습니다" in llm2.calls[0]["user"]
