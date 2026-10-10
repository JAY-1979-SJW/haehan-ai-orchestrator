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
    from scripts.browser.cdp.cdp_helper import CDP
    from scripts.naver.blog.marketing.gpt_writer import generate_draft

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

from scripts.browser.cdp.cdp_helper import CDP
from scripts.common.logger import get_logger
from scripts.naver.blog.accounts import DEFAULT_ACCOUNT
from scripts.naver.blog.marketing.chatgpt_prompt import send_chatgpt_prompt
from scripts.naver.blog.marketing.competitor import research_competitors, summarize_for_prompt
from scripts.naver.blog.marketing.content import (
    MIN_BODY_CHARS,
    MIN_TAG_COUNT,
    TARGET_BODY_CHARS,
    TARGET_TAG_COUNT,
    _risky_claims,
)

_log = get_logger(__name__)

# ── 상시 고정 프로젝트 (계정별, 2026-08-24 확장) ────────────────────────────
# 블로그 초안은 **항상 계정 전용 ChatGPT 프로젝트 안에서** 생성한다. 프로젝트에
# 도메인 커스텀 지시가 걸려 있어 빈 대화창보다 맥락이 좋기 때문이다.
#
# ⚠️ 그냥 URL로 이동만 하면 **실패해도 조용히 빈 대화창에서 생성**되어
# 품질이 떨어진 걸 눈치채기 어렵다. 그래서 `ensure_project()`로 실제로
# 프로젝트 안에 있는지 확인하고, 아니면 **에러를 내고 멈춘다.**
#
# 프로젝트 안에서 새 대화를 시작하면 URL이 `/g/{PROJECT_ID}/c/{대화ID}` 가
# 되므로, PROJECT_ID 포함 여부로 프로젝트 소속을 판정할 수 있다.
PROJECT_IDS = {
    "skyjwsin": "g-p-6a8b0a1b7ef881919d1b00bb5f6b481c-geonseoljeonmun-ai",  # 건설전문 ai
    "skyjwshin": "g-p-6a8910f9c8088191b3f3f8098f0c6959-bandisbul-jeonpasa",  # 반딧불 전파사 (2026-08-24 추가)
}

# 하위호환 — blog_id 인자 없이 부르는 기존 호출부는 skyjwsin(건설) 프로젝트.
PROJECT_ID = PROJECT_IDS["skyjwsin"]
PROJECT_URL = f"https://chatgpt.com/g/{PROJECT_ID}/project"
CHATGPT_URL = PROJECT_URL  # 하위호환용 별칭


def project_url(blog_id: str | None = None) -> str:
    pid = PROJECT_IDS.get(blog_id or DEFAULT_ACCOUNT, PROJECT_ID)
    return f"https://chatgpt.com/g/{pid}/project"


def in_project(cdp: CDP, blog_id: str | None = None) -> bool:
    """현재 열린 탭이 해당 계정 전용 프로젝트(또는 그 안의 대화)인지."""
    pid = PROJECT_IDS.get(blog_id or DEFAULT_ACCOUNT, PROJECT_ID)
    return pid in (cdp.js("location.href") or "")


def ensure_project(cdp: CDP, wait: float = 3.5, retries: int = 2, blog_id: str | None = None) -> bool:
    """프로젝트 안으로 이동시키고, 실제로 들어갔는지 확인한다."""
    url = project_url(blog_id)
    for attempt in range(retries + 1):
        if in_project(cdp, blog_id):
            return True
        cdp.js(f"location.href = '{url}';")
        time.sleep(wait)
        if in_project(cdp, blog_id):
            return True
        _log.warning("[gpt-writer] 프로젝트 진입 재시도 %d/%d", attempt + 1, retries)
    return False


# 기준서(docs/specs/naver_blog_content_standard.md)를 프롬프트로 옮긴 것.
# 기준서가 바뀌면 여기도 같이 고친다.
_PROMPT_TEMPLATE = """당신은 한국 건설 실무 블로그 작가입니다. 아래 규칙을 정확히 지켜 글 1편을 써주세요.

[주제] {topic}
[검색자의 실제 질문] {source}
[핵심 키워드] {keywords}

## 먼저 할 일 — 근거 조사 (건너뛰지 마세요)
글을 쓰기 전에 **웹 검색으로 실제 근거를 찾으세요.** 관련 법령·계약예규·
고시·발주기관 공고 원문을 확인하고, 본문에서 **출처를 문장 안에 밝히세요**
(예: "재정경제부 계약예규 「공사계약일반조건」 제20조는 ~하도록 정하고 있습니다").
검색해도 확인이 안 되는 수치는 **쓰지 말고** "어디서 확인하는지"를 안내하세요.
추측으로 조항 번호·요율·연도를 만들어내면 안 됩니다.

{competitor_block}

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

# skyjwshin(조명·인테리어) 전용 프롬프트 (2026-08-24 추가). 건설과 달리
# 법령·계약예규 근거가 아니라 **실제 시공 경험/제품 스펙**이 신뢰의 근거다.
# 지어내면 안 되는 대상도 다르다 — "법 조항"이 아니라 "구체적 규격·전압·
# 가격대" 같은 확인 안 된 수치.
_LIGHTING_PROMPT_TEMPLATE = """당신은 한국 조명·인테리어 실무 블로그 작가입니다. 아래 규칙을 정확히 지켜 글 1편을 써주세요.

[주제] {topic}
[검색자의 실제 질문] {source}
[핵심 키워드] {keywords}

## 먼저 할 일 — 근거 조사 (건너뛰지 마세요)
글을 쓰기 전에 **웹 검색으로 실제 근거를 찾으세요.** 제품 규격·전압·설치
방식·업계에서 통용되는 시공 방법을 확인하고, 확실하지 않은 가격대·정확한
규격 수치는 **쓰지 말고** "정확한 사양은 구매 전 확인하시라"고 안내하세요.
추측으로 가격·전력소비량·수명(시간)을 만들어내면 안 됩니다.

{competitor_block}

## 필수 구조 — 대괄호 소제목을 그대로 쓰세요
[핵심 답변]
2~3문장으로 결론부터. 스크롤하지 않아도 답이 보여야 합니다.

[이런 상황이시죠]
검색자가 막힌 지점을 구체적으로 짚습니다. 질문을 그대로 반복하지 마세요.

[왜 헷갈리나]
쟁점이 무엇인지, 어디서 판단이 갈리는지(예: 제품마다 규격이 달라서/직접
시공이 위험해서 등).

[이렇게 하시면 됩니다]
이 글의 본체입니다(전체 분량의 50~60%). 순서·판단기준을 번호를 매겨
구체적으로 씁니다. 체크리스트가 있으면 · 로 나열하세요. 전문 시공이
필요한 경우(누전 위험, 매입등 배선 작업 등)와 직접 해도 되는 경우를
분명히 구분해주세요.

[정리하면]
결론을 다시 못박습니다. 이 문단만 읽어도 뭘 해야 할지 알 수 있어야 합니다.

## 분량·문체
- 본문 {min_chars}자 이상(공백 포함), {target_chars}자 목표
- 문단은 2~3줄. 모바일에서 글자 벽처럼 보이면 안 됩니다
- 짧은 문장. 한 문장에 한 가지만. 만연체 금지
- "~합니다" 기본, 가끔 "~예요"로 힘 빼기. 딱딱한 문어체 금지
- 전문용어는 첫 등장에 풀어쓰기(예: "다운라이트(매입등)")

## 절대 금지
- 마크다운 기호(##, **, -) 사용 금지. 네이버는 렌더링하지 않아 그대로 노출됩니다
- **지어낸 가격·전력소비량·제품 스펙 절대 금지.** 확실하지 않으면 숫자를
  쓰지 말고 "정확한 사양은 구매/시공 전 확인하시라"고 안내하세요.
- 내용 없는 문장 금지: "복잡할 수 있습니다", "중요합니다", "주의가 필요합니다"
- 제품·서비스 홍보 문구를 넣지 마세요. 광고는 별도로 붙입니다

## 출력 형식
다른 설명 없이 아래 JSON만 출력하세요.
{{"title": "...", "tags": ["...", "..."], "body": "..."}}

- title: 30~50자. 검색자가 실제로 입력할 키워드를 앞쪽에 배치
- tags: {min_tags}~{target_tags}개. 제품유형·공간유형·핵심개념·유의어
- body: 위 구조대로 쓴 본문 전체. 줄바꿈은 \\n 으로
"""

_PROMPT_TEMPLATES = {
    "skyjwsin": _PROMPT_TEMPLATE,
    "skyjwshin": _LIGHTING_PROMPT_TEMPLATE,
}

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
    return send_chatgpt_prompt(cdp, prompt, 0.8)


def _wait_for_response(
    cdp: CDP,
    timeout: float = 720.0,
    poll: float = 4.0,
    stable_polls: int = 4,
    min_len: int = 800,
) -> str:
    """마지막 assistant 응답이 더 이상 길어지지 않을 때까지 대기 후 텍스트 반환.

    "생성 중" 버튼 셀렉터로 판정하려다 실패해서(2026-08-23) **텍스트 길이가
    연속 N회 그대로면 완료**로 본다.

    ⚠️ `min_len`이 핵심이다. GPT가 웹검색을 하면 **수 분간 텍스트가 안
    자라는 구간**이 생기는데(실측: "1m 6s", "3m 39s 동안 처리함"), 길이만
    보면 그때를 완료로 오판한다. 그래서 min_len 미만이면 안정돼 보여도 계속
    기다린다.

    ⚠️ `timeout`도 넉넉해야 한다. 처음 300초로 뒀다가 GPT가 3분 39초를
    검색에 쓰는 바람에 14자(`{"title":"공사원가`)만 받고 타임아웃한 적이
    있다(2026-08-24). 웹검색을 시키면 **5~7분**까지 걸리므로 720초로 잡았다.
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
    except Exception as e:  # noqa: BLE001 - GPT 응답 JSON 파싱 실패시 None 반환, 경쟁사 조사 실패시 그 정보 없이 계속 진행 — 안전한 기능저하(degradation)일 뿐 발행 승인/여부에는 영향 없음
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
    research_competitors_first: bool = True,
    blog_id: str | None = None,
) -> dict:
    """GPT에게 초안을 요청해 받아오고 자동 점검까지 수행한다.

    `research_competitors_first=True`(기본)면 같은 주제로 이미 상위 노출된
    경쟁 글을 먼저 조사해 그 실측치를 프롬프트에 넣는다 — 주제마다 경쟁
    강도가 크게 다르기 때문이다(2026-08-23 실측: "하도급대금 직접지급"은
    1위가 5,409자/태그30개인데 "일위대가 작성 방법"은 평균 1,336자/태그4개).

    반환: {"draft": {...} | None, "review": {...}, "raw": "...", "competitors": {...}}
    **이 결과를 그대로 발행하면 안 된다** — review["must_verify"]의 수치를
    Claude가 출처 확인한 뒤, CTA를 붙여서 발행한다.
    """
    competitors = {}
    competitor_block = ""
    if research_competitors_first:
        try:
            query = topic_info.get("competitor_query") or topic_info.get("topic", "")
            competitors = research_competitors(cdp, query)
            competitor_block = summarize_for_prompt(competitors)
        except Exception as e:  # noqa: BLE001 - GPT 응답 JSON 파싱 실패시 None 반환, 경쟁사 조사 실패시 그 정보 없이 계속 진행 — 안전한 기능저하(degradation)일 뿐 발행 승인/여부에는 영향 없음
            _log.warning("[gpt-writer] 경쟁 글 조사 실패(무시하고 진행): %s", e)

    template = _PROMPT_TEMPLATES.get(blog_id or DEFAULT_ACCOUNT, _PROMPT_TEMPLATE)
    prompt = template.format(
        topic=topic_info.get("topic", ""),
        source=topic_info.get("source", "(없음)"),
        keywords=", ".join(topic_info.get("keywords", [])),
        competitor_block=competitor_block,
        min_chars=MIN_BODY_CHARS,
        target_chars=TARGET_BODY_CHARS,
        min_tags=MIN_TAG_COUNT,
        target_tags=TARGET_TAG_COUNT,
    )

    # 상시 고정: 반드시 계정 전용 프로젝트 안에서 생성한다.
    # 진입 실패 시 **조용히 빈 대화창에서 쓰지 않고 멈춘다** — 프로젝트 커스텀
    # 지시가 빠진 채 생성되면 품질이 떨어지는데 결과만 봐선 알기 어렵기 때문.
    if new_chat and not ensure_project(cdp, blog_id=blog_id):
        return {
            "draft": None,
            "review": {
                "ok": False,
                "problems": [f"프로젝트 진입 실패({blog_id}) — 현재 URL: {cdp.js('location.href')}"],
            },
            "raw": "",
            "competitors": competitors,
        }

    sent = _send_prompt(cdp, prompt)
    if sent != "clicked":
        return {
            "draft": None,
            "review": {"ok": False, "problems": [f"전송 실패: {sent}"]},
            "raw": "",
            "competitors": competitors,
        }

    raw = _wait_for_response(cdp)
    draft = parse_draft(raw)
    if not draft:
        return {
            "draft": None,
            "review": {"ok": False, "problems": ["응답 파싱 실패"]},
            "raw": raw,
            "competitors": competitors,
        }

    draft["topic"] = topic_info.get("topic", "")
    draft.setdefault("images", [])
    review = review_draft(draft)

    if out_path:
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
        _log.info("[gpt-writer] 초안 저장: %s (%d자, 태그 %d개)", p, review["char_count"], review["tag_count"])

    return {"draft": draft, "review": review, "raw": raw, "competitors": competitors}
