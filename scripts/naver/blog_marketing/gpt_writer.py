"""ChatGPT(웹)로 블로그 본문 초안을 받아오는 모듈 (raw CDP 기반, L5).

## 이 모듈의 위치
```
주제 선정(topics.py) → [이 모듈] GPT 초안 → Claude 검증 → 발행(blog_publish_manual.py)
```
GPT는 **초안 작성자**, Claude는 **팩트체커·편집자**다. GPT가 쓴 걸 그대로
발행하지 않는다 — `seo_check()` + 미검증 수치 출처 확인을 반드시 거친다.

## 왜 API가 아니라 웹인가
`content.py::generate_post()`는 OpenAI API를 호출하는데 2026-08-19 사업자
결정으로 차단돼 있다(`OpenAIDisabledError`). 차단 사유는 "GPT가 없는 수치·
법령을 지어낸다"였는데, 그건 **학습 데이터만으로 쓰던 API** 얘기다.
ChatGPT 웹은 검색 기능이 있고, 무엇보다 **출력물을 Claude가 검증**하는
구조라 위험이 통제된다. 비용도 API 과금이 아니라 사용자의 Plus 구독이다.
→ 2026-08-23 사용자 승인 하에 이 경로를 신설했다. **API 차단은 그대로 유지.**

## 설계상 의도적으로 GPT에게 안 시키는 것
- **CTA**: 우리 제품 실측 수치(호표 수·인식률 등)가 들어가야 하는데 GPT가
  지어낼 위험이 크다. 기준서의 "CTA 정직성 원칙" 위반이 되므로 Claude가 직접 붙인다.
- **주제 선정**: `topics.py`의 3중 검증 결과를 쓴다. GPT가 지어내지 않는다.

## 실측 확인 (2026-08-23)
- 응답 추출: `[data-message-author-role="assistant"]`의 마지막 요소 innerText
- 완료 감지: 버튼 셀렉터는 불안정 → **텍스트 길이가 N회 연속 안 변하면 완료**로 판정
- 입력: `#prompt-textarea` focus 후 `Input.insertText`,
  전송은 `button[data-testid="send-button"]` 클릭

사용:
    from scripts.cdp_helper import CDP
    from scripts.naver.blog_marketing.gpt_writer import generate_draft

    cdp = CDP(port=9222)
    draft = generate_draft(cdp, {
        "topic": "건설공사 설계변경시 공사기간 증가에 따른 제비율 변경",
        "keywords": ["제비율", "설계변경"],
        "source": "(지식iN 원문 질문)",
    }, out_path="data/blog_drafts/draft_03.json")
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from scripts.cdp_helper import CDP
from scripts.logger import get_logger
from scripts.naver.blog_marketing.content import (
    MIN_BODY_CHARS,
    MIN_TAG_COUNT,
    TARGET_BODY_CHARS,
    TARGET_TAG_COUNT,
    _risky_claims,
)

_log = get_logger(__name__)

CHATGPT_URL = "https://chatgpt.com/"

# 기준서(docs/specs/naver_blog_content_standard.md)를 프롬프트로 옮긴 것.
# 기준서가 바뀌면 여기도 같이 고친다.
_PROMPT_TEMPLATE = """당신은 한국 건설 실무 블로그 작가입니다. 아래 규칙을 정확히 지켜 글 1편을 써주세요.

[주제] {topic}
[검색자의 실제 질문] {source}
[핵심 키워드] {keywords}

## 필수 구조 — 대괄호 소제목을 그대로 쓰세요
[핵심 답변]
2~3문장으로 결론부터. 스크롤하지 않아도 답이 보여야 합니다.

[이런 상황이시죠]
검색자가 막힌 지점을 구체적으로 짚습니다. 질문을 그대로 반복하지 마세요.

[왜 헷갈리나]
쟁점이 무엇인지, 어디서 판단이 갈리는지.

[이렇게 하시면 됩니다]
이 글의 본체입니다(전체 분량의 50~60%). 순서·서식·판단기준을 번호를 매겨
구체적으로 씁니다. 체크리스트가 있으면 · 로 나열하세요.

[정리하면]
결론을 다시 못박습니다. 이 문단만 읽어도 뭘 해야 할지 알 수 있어야 합니다.

## 분량·문체
- 본문 {min_chars}자 이상(공백 포함), {target_chars}자 목표
- 문단은 2~3줄. 모바일에서 글자 벽처럼 보이면 안 됩니다
- 짧은 문장. 한 문장에 한 가지만. 만연체 금지
- "~합니다" 기본. 딱딱한 문어체("~함", "~할 것") 금지
- 전문용어는 첫 등장에 풀어쓰기(예: "제비율(간접공사비 요율)")

## 절대 금지
- 마크다운 기호(##, **, -) 사용 금지. 네이버는 렌더링하지 않아 그대로 노출됩니다
- **지어낸 수치·법령·조항 절대 금지.** 요율·금액·법 조항·시행연도를 쓰려면
  반드시 출처(기관명 + 문서명)를 문장 안에 함께 밝히세요.
  확실하지 않으면 숫자를 쓰지 말고 "어디서 확인하는지"를 안내하세요.
- 내용 없는 문장 금지: "복잡할 수 있습니다", "중요합니다", "주의가 필요합니다",
  "다양한 요소", "정확한 이해가 필요"
- 제품·서비스 홍보 문구를 넣지 마세요. 광고는 별도로 붙입니다

## 출력 형식
다른 설명 없이 아래 JSON만 출력하세요.
{{"title": "...", "tags": ["...", "..."], "body": "..."}}

- title: 30~50자. 검색자가 실제로 입력할 키워드를 앞쪽에 배치
- tags: {min_tags}~{target_tags}개. 법령명·기관명·핵심개념·업종명·유의어
- body: 위 구조대로 쓴 본문 전체. 줄바꿈은 \\n 으로
"""

# 응답 텍스트를 읽되 **인용 칩을 제거**하고 읽는다.
# ChatGPT가 웹검색을 하면 본문 중간에 출처 칩(`a[href^=http]`, 예: "법률정보
# 시스템 +1")이 인라인으로 박히는데, 이게 innerText에 섞여 JSON을 깨뜨린다
# (2026-08-23 실측: `{"title":"` 다음에 칩 텍스트가 쏟아져 파싱 실패).
# 노드를 복제해서 링크를 지운 뒤 읽으면 깨끗한 원문만 남는다.
_LAST_ASSISTANT_JS = """(function(){
  var nodes = document.querySelectorAll('[data-message-author-role="assistant"]');
  if (!nodes.length) return '';
  var clone = nodes[nodes.length - 1].cloneNode(true);
  clone.querySelectorAll('a[href^="http"]').forEach(function(a){ a.remove(); });
  return (clone.innerText || '');
})()"""


def _send_prompt(cdp: CDP, prompt: str) -> str:
    focus = cdp.js("""(function(){
      var ta = document.querySelector('#prompt-textarea');
      if (!ta) return 'textarea not found';
      ta.focus();
      return 'focused';
    })()""")
    if focus != "focused":
        return focus
    time.sleep(0.3)
    cdp.send("Input.insertText", {"text": prompt})
    time.sleep(0.8)
    return cdp.js("""(function(){
      var b = document.querySelector('button[data-testid="send-button"]');
      if (!b) return 'send button not found';
      b.click();
      return 'clicked';
    })()""")


def _wait_for_response(
    cdp: CDP,
    timeout: float = 300.0,
    poll: float = 3.0,
    stable_polls: int = 4,
    min_len: int = 800,
) -> str:
    """마지막 assistant 응답이 더 이상 길어지지 않을 때까지 대기 후 텍스트 반환.

    "생성 중" 버튼 셀렉터로 판정하려다 실패해서(2026-08-23) **텍스트 길이가
    연속 N회 그대로면 완료**로 본다.

    ⚠️ `min_len`이 핵심이다. GPT가 웹검색을 하면 **1분 넘게 텍스트가 안
    자라는 구간**이 생기는데(실측: "1m 6s 동안 처리함"), 길이만 보면 그때를
    완료로 오판한다. 실제로 `{"title":"`(102자)에서 멈춘 걸 완성으로 읽어
    파싱에 실패했다. 그래서 **min_len 미만이면 안정돼 보여도 계속 기다린다.**
    본문 {min_chars}자 이상을 요구하므로 정상 응답은 훨씬 길다.
    """
    prev_len, stable = -1, 0
    deadline = time.time() + timeout
    while time.time() < deadline:
        text = cdp.js(_LAST_ASSISTANT_JS) or ""
        cur = len(text)
        if cur >= min_len and cur == prev_len:
            stable += 1
            if stable >= stable_polls:
                return text
        else:
            stable = 0
        prev_len = cur
        time.sleep(poll)
    _log.warning("[gpt-writer] 응답 대기 타임아웃(%ds) — 받은 만큼 반환", int(timeout))
    return cdp.js(_LAST_ASSISTANT_JS) or ""


def parse_draft(raw: str) -> dict | None:
    """GPT 응답에서 JSON 원고를 뽑는다. ```json 코드펜스로 감싸 오는 경우 처리."""
    if not raw:
        return None
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            return None
        text = text[start : end + 1]
    try:
        data = json.loads(text)
    except Exception as e:
        _log.warning("[gpt-writer] JSON 파싱 실패: %s", e)
        return None
    if not data.get("title") or not data.get("body"):
        return None
    data.setdefault("tags", [])
    return data


def review_draft(draft: dict) -> dict:
    """발행 전 자동 점검. **Claude가 사람 눈으로 한 번 더 봐야 하는 항목**을 돌려준다."""
    body = draft.get("body", "")
    tags = draft.get("tags", [])
    problems, must_verify = [], []

    if len(body) < MIN_BODY_CHARS:
        problems.append(f"본문 {len(body)}자 (최소 {MIN_BODY_CHARS}자 미달)")
    if len(tags) < MIN_TAG_COUNT:
        problems.append(f"태그 {len(tags)}개 (최소 {MIN_TAG_COUNT}개 미달)")
    if "##" in body or "**" in body:
        problems.append("마크다운 기호 잔존 — 네이버는 렌더링하지 않음")
    if "[핵심 답변]" not in body:
        problems.append("[핵심 답변] 선요약 블록 없음")
    if not re.search(r"\[정리하면|\[결론", body):
        problems.append("결론 문단 없음")

    # 지어낸 수치 탐지 — 여기 걸린 건 Claude가 반드시 출처를 확인해야 한다.
    must_verify = _risky_claims(body)

    return {
        "ok": not problems,
        "problems": problems,
        "must_verify": must_verify,
        "char_count": len(body),
        "tag_count": len(tags),
    }


def generate_draft(
    cdp: CDP,
    topic_info: dict,
    out_path: str | None = None,
    new_chat: bool = True,
) -> dict:
    """GPT에게 초안을 요청해 받아오고 자동 점검까지 수행한다.

    반환: {"draft": {...} | None, "review": {...}, "raw": "..."}
    **이 결과를 그대로 발행하면 안 된다** — review["must_verify"]의 수치를
    Claude가 출처 확인한 뒤, CTA를 붙여서 발행한다.
    """
    prompt = _PROMPT_TEMPLATE.format(
        topic=topic_info.get("topic", ""),
        source=topic_info.get("source", "(없음)"),
        keywords=", ".join(topic_info.get("keywords", [])),
        min_chars=MIN_BODY_CHARS,
        target_chars=TARGET_BODY_CHARS,
        min_tags=MIN_TAG_COUNT,
        target_tags=TARGET_TAG_COUNT,
    )

    if new_chat:
        cdp.js(f"location.href = '{CHATGPT_URL}';")
        time.sleep(3)

    sent = _send_prompt(cdp, prompt)
    if sent != "clicked":
        return {"draft": None, "review": {"ok": False, "problems": [f"전송 실패: {sent}"]}, "raw": ""}

    raw = _wait_for_response(cdp)
    draft = parse_draft(raw)
    if not draft:
        return {"draft": None, "review": {"ok": False, "problems": ["응답 파싱 실패"]}, "raw": raw}

    draft["topic"] = topic_info.get("topic", "")
    draft.setdefault("images", [])
    review = review_draft(draft)

    if out_path:
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
        _log.info("[gpt-writer] 초안 저장: %s (%d자, 태그 %d개)", p, review["char_count"], review["tag_count"])

    return {"draft": draft, "review": review, "raw": raw}
