"""AI 본문/제목 생성 + 발행 전 SEO 점검.

작성 원칙(요청 스펙):
  - 친절하고 정확한 어조, 확실하지 않은 정보는 단정하지 않음
  - 실제 지식iN 질문(topics.py의 source_description)을 인용해 근거로 삼음
  - 분량 A4 3장(약 3,300자) 내외
  - 이미지는 A4 1장당 1장(구간 3개로 분할 - images.py/publish.py에서 처리)
"""

from __future__ import annotations

import re

from scripts.common.logger import get_logger
from scripts.naver.automation.integration.ai_responder import AIResponder

_log = get_logger(__name__)

# 분량 기준 (2026-08-23 재상향 — 실제 상위노출 경쟁 글 실측 근거)
#
# 2026-08-19엔 "분량보다 밀도"로 최소치를 1,200자까지 낮췄었다. 그런데
# 2026-08-23 실제 검색 1~2위 경쟁 글(하도급대금 직접지급 주제)을 직접
# 열어보니 각각 5,409자·3,061자였다 — 우리 초안(1,805자)의 2~3배.
# "짧아도 답만 있으면 된다"는 원칙 자체는 유지하되, 실제 이기고 있는
# 글들이 이 정도 분량으로 체크리스트·배경설명·사례까지 채운다는 사실을
# 무시할 수 없다. 최소 기준을 다시 올린다.
TARGET_BODY_CHARS = 3500
MIN_BODY_CHARS = 2500

# 태그 개수 (2026-08-23 재확정 — 실제 상위노출 경쟁 글 실측 근거)
#
# "30개 채우기가 유리하다는 근거를 못 찾았다"고 판단했었는데, 같은 주제로
# 검색 1위 글이 정확히 30개, 2위 글이 18개 태그를 쓰고 있는 걸 실측으로
# 확인했다(2026-08-23). 웹 서치보다 실제 순위가 더 강한 증거다 — 태그를
# 아끼지 않는다. 주제 관련어(법령명·기관명·핵심 개념·업종명 등)를
# 최대한 뽑아 15~30개 범위로 채운다.
MIN_TAG_COUNT = 15
TARGET_TAG_COUNT = 25

# 도입 문의 CTA — 홈페이지 주소를 크게 노출 (2026-08-17 추가)
HOMEPAGE_URL = "https://haehan-ai.kr"
# 광고가 아니라 "증명"으로 끝내기 위한 실물 자료(2026-08-20).
# 블로그 목적은 AI 적산·자동화 프로그램 영업이므로, 실무 답변으로 신뢰를 얻은 뒤
# 그 문제를 실제로 푸는 결과물을 보여준다.
PROPOSAL_URL = "https://haehan-ai.kr/quantity-proposal.html"
# 전화번호 노출 정책 변경(2026-08-22, 2026-08-23 재확인) — 기존 "미노출"(2026-08-17)을
# 뒤집음. 요지는 번호 자체가 아니라 "왜 우리에게 연락해야 하는가"이므로, 증명(실측
# 수치) 다음에만 번호를 배치한다. 브랜드 표기는 "해한 AI"로 고정(2026-08-23).
CONTACT_PHONE = "010-7387-6635"
_CTA_BLOCK = f"""

[이거 매번 계산하기 번거로우시죠]

해한 AI는 도면에서 물량을 자동으로 뽑는 프로그램을 만듭니다. 실제 검증한 결과입니다.

· 구조 일람표 14종 전부 인식 — 기존 CAD 파싱 방식은 4종만 읽혔습니다
· 철근비 42.5% 과다계상을 잡아낸 사례 (오류 메시지 없이 통과되던 값입니다)
· 소방 5,830호표 · 전기 2,674호표 품셈 엔진으로 근거까지 함께 산출

이 프로그램을 우리 회사에 도입하고 싶으시거나, 직접 다뤄보고 싶어서
개인 교습을 받아보고 싶으시면 편하게 연락 주세요.

👉 물량산출 제안서 {PROPOSAL_URL}
👉 도입 문의 · 개인 교습 문의 {HOMEPAGE_URL} · {CONTACT_PHONE}"""


def generate_post(topic_info: dict, dry_run: bool = False) -> dict | None:
    topic = topic_info["topic"]
    keywords = topic_info.get("keywords", [])
    angle = topic_info.get("angle", "실용 가이드")
    source = topic_info.get("source_description", "")

    if dry_run:
        title = f"{topic} — 실무자를 위한 완전정리"
        body = f"""실제로 많은 분들이 이런 질문을 합니다: "{topic}"

## 무엇이 문제인가

{source or (angle + " 관점에서 자주 발생하는 상황입니다.")}

## 정확히 확인해야 할 것

키워드: {", ".join(keywords)}

관련 규정과 실무 절차를 순서대로 정리합니다.

## 단계별 정리

1. 우선 확인할 사항
2. 실제 처리 절차
3. 흔히 하는 실수와 주의사항

## 마무리

이 글이 실제로 도움이 되셨길 바랍니다. 정확한 판단이 필요한 사안은 관할 기관·전문가 확인을 권장드립니다.

#{keywords[0] if keywords else "건설실무"}"""
        return {"title": title, "body": body, "tags": keywords[:7]}

    ai = AIResponder()

    # 제목 — 검색어 우선. "AI 필수" 규칙은 2026-08-23 폐기됐다.
    #
    # 2026-08-17엔 블로그 정체성을 드러내려 제목에 "AI"를 강제하고, 없으면
    # "(AI 자동화 활용법)"을 코드로 덧붙였다. 폐기 이유:
    #  · 08-19에 "실무 답변이 본체"로 방향을 바꿨을 때 같이 폐기됐어야 할
    #    규칙인데 남아 있었다(정체성은 CTA·본문에서 드러내면 된다).
    #  · 제목 30~50자는 유한 자원이라 "AI" 2자만큼 실제 검색어가 밀린다.
    #    검색자는 "AI"가 아니라 "하도급대금 직접지급 지급보증"으로 찾는다.
    #  · 같은 주제 검색 1위 경쟁 글도 제목에 AI가 없다(2026-08-23 실측).
    # 참고: 조회수 비교에선 AI 유무 차이가 시기 보정 후 사라졌다(8월 기준
    # 8.4회 vs 8.0회). 즉 "AI가 해롭다"는 증거는 아니고, 강제할 근거가
    # 없다는 뜻이다 — 내용상 자연스러우면 넣어도 된다.
    title_r = ai._call(
        "한국 건설업 실무 블로그 SEO 전문가. 클릭률 높은 제목 1개만 출력.",
        f"주제(실제 지식iN 질문): {topic}\n각도: {angle}\n키워드: {', '.join(keywords)}\n"
        f"조건: 30~50자, 질문 원문 어투를 살리되 자연스러운 블로그 제목으로 다듬기\n"
        f"조건: 검색자가 실제로 입력할 키워드({', '.join(keywords[:2])})를 제목 앞쪽에 배치\n제목:",
        max_tokens=80,
    )
    if not title_r.get("ok"):
        return None
    title = title_r["text"].split("\n")[0].strip().strip('"').strip("'")

    # 본문 — A4 3장(약 3,300자) 분량, 실제 질문(source)을 인용해 근거로 삼는다.
    source_block = (
        f"\n[실제 사용자 질문/상황 — 이 내용을 그대로 인용·요약해 도입부 근거로 사용]\n{source}\n" if source else ""
    )
    body_prompt = f"""주제: {topic}
각도: {angle}
키워드: {", ".join(keywords)}
대상: 한국 건설업 실무자(공무·경리·현장관리)
블로그 정체성: "AI업무자동화" — AI로 건설 실무(적산·물량산출·내역서·행정신고)를
분석하고 자동화 프로그램으로 만드는 걸 전문으로 하는 블로그
{source_block}
이 글은 "설명하는 글"이 아니라 **"문제를 해결해주는 글"**입니다.
검색해서 들어온 사람은 답을 원하지, 개념 설명을 원하지 않습니다.

⚠️ 지금까지 가장 큰 문제였던 것 (2026-08-19 진단):
질문을 인용해놓고 정작 그 질문에 답을 안 했습니다. "노무비란 무엇인가"를
설명만 하고 "그래서 어떻게 하라는 건지" 결론이 없었습니다. 백과사전 같은 글은
검색자가 바로 나갑니다. **반드시 기승전결이 있어야 합니다.**

[기] 문제 특정 — 이 사람이 진짜 막힌 지점이 무엇인지 한 문장으로 짚기
  예: "총액을 맞춰야 하는데 어느 항목을 조정해야 할지 모르는 상황이죠."
  ※ 질문을 그대로 반복하지 말고, 실무에서 이게 왜 어려운지로 바꿔 쓸 것

[승] 왜 헷갈리는가 — 쟁점이 무엇인지, 어디서 갈리는지
  예: "요율이 고정인 항목과 협의 가능한 항목이 섞여 있어서 그렇습니다."

[전] **해결 — 이 글의 본체 (전체의 50~60%)**
  "그래서 이렇게 하시면 됩니다"를 구체적으로:
  - 순서대로 (1단계 → 2단계 → 3단계, 어느 사이트 어느 메뉴까지)
  - 필요한 서식·서류 이름을 정확히
  - 판단 기준을 명확히 ("○○면 A, △△면 B")
  - 막히는 지점과 우회법 (경험자 어투)

[결] 결론 — "정리하면 이렇습니다"로 명확히 답을 못박기
  독자가 이 문단만 봐도 뭘 해야 할지 알 수 있어야 합니다.

그 다음 덧붙이는 것 (전체의 20~25%만):
- AI로 자동화한다면: 이 업무의 반복 부분(마감일 계산, 대상자 판정, 서식
  채우기)을 AI가 어떻게 처리하는지 3~5단계로 간결하게.

전체 {TARGET_BODY_CHARS}자 내외, 최소 {MIN_BODY_CHARS}자 이상.

작성 원칙:
- **결론을 반드시 낼 것.** "확인이 필요합니다"로 끝내면 실패한 글입니다.
  모르는 수치는 빼되, 판단 기준과 절차는 끝까지 답해야 합니다.
- **수치·법령을 지어내지 마세요.** 요율(%)·금액·법령 조항·시행규칙 연도는
  확실히 아는 것만. 모르면 "조달청 고시 제비율표에서 해당 연도 기준 확인"처럼
  어디서 확인하는지를 알려주세요. 틀린 수치 한 줄이 글 전체 신뢰를 무너뜨립니다.
- 일반론 금지: "복잡할 수 있습니다", "중요합니다", "정확한 이해가 필요합니다"
  같은 문장은 쓰지 마세요. 정보가 0인 문장입니다.
- 실무자가 쓴 것처럼. AI가 쓴 티 나는 문장 금지.
- **소제목은 마크다운(##) 대신 [ ] 대괄호.** 네이버는 마크다운을 렌더링하지
  않아 ##이 독자 화면에 그대로 보입니다.
  예: [이런 상황이시죠], [왜 헷갈리나], [이렇게 하시면 됩니다], [정리하면],
      [AI로 자동화한다면]

본문만 출력 (제목 제외):"""

    body_r = ai._call(
        "한국 건설업 실무 블로그 전문 작가. 친절하고 정확한 정보 전달이 최우선. "
        f"분량 지시(최소 {MIN_BODY_CHARS}자)를 반드시 지킨다 — 짧게 끝내지 않는다.",
        body_prompt,
        max_tokens=5000,
    )
    if not body_r.get("ok"):
        return None

    body = body_r["text"].strip()
    tags = keywords[:7] if keywords else ["건설실무", "건설업"]

    seo = seo_check(title=title, body=body, keywords=keywords)
    if seo["warnings"]:
        _log.warning("[SEO] %s — %s", title[:30], "; ".join(seo["warnings"]))

    segments = split_body(body, parts=3)
    body_with_cta = body + _CTA_BLOCK
    segments_with_cta = [*segments, _CTA_BLOCK.strip()]

    return {
        "title": title,
        "body": body_with_cta,
        "body_segments": segments_with_cta,
        "tags": tags,
        "seo": seo,
    }


def _basic_seo_warnings(title: str, body: str, keywords: list[str]) -> list[str]:
    """제목·본문 길이·키워드·태그·소제목 구조 점검."""
    warnings = []
    if not (20 <= len(title) <= 60):
        warnings.append(f"제목 길이 {len(title)}자 (권장 20~60자)")
    if len(body) < MIN_BODY_CHARS:
        warnings.append(f"본문 {len(body)}자 (최소 {MIN_BODY_CHARS}자 미달 — 답이 덜 담겼을 수 있음)")
    main_kw = keywords[0] if keywords else ""
    if main_kw and main_kw not in title:
        warnings.append(f"핵심 키워드 '{main_kw}'가 제목에 없음")
    if main_kw and body.count(main_kw) < 2:
        warnings.append(f"핵심 키워드 '{main_kw}' 본문 출현 {body.count(main_kw)}회 (권장 2회 이상)")
    if len(keywords) < MIN_TAG_COUNT:
        warnings.append(
            f"태그 {len(keywords)}개 (최소 {MIN_TAG_COUNT}개, 목표 {TARGET_TAG_COUNT}개 — "
            "상위노출 경쟁 글 실측 기준, 관련어를 최대한 뽑아 채울 것)"
        )
    if "##" in body:
        warnings.append("마크다운 소제목(##) 잔존 — 네이버는 렌더링하지 않음")
    if "[" not in body:
        warnings.append("소제목([ ]) 구조 없음")
    return warnings


def seo_check(*, title: str, body: str, keywords: list[str]) -> dict:
    """발행 전 최소 SEO 점검. 차단하지 않고 경고만 남긴다(사람이 최종 확인)."""
    warnings = _basic_seo_warnings(title, body, keywords)

    weak = _weak_writing(body)
    if weak:
        warnings.append(f"내용 없는 표현 {len(weak)}건: {', '.join(weak[:3])}")
    if not re.search(r"\[정리하면|\[결론|정리하면 이", body):
        warnings.append("결론 문단 없음 — 설명만 하고 답을 안 낸 글일 수 있음")

    risky = _risky_claims(body)
    if risky:
        warnings.append(f"검증 필요 수치 {len(risky)}건: {', '.join(risky[:3])}")

    ai_ratio = _ai_section_ratio(body)
    if ai_ratio > 0.35:
        warnings.append(f"AI 섹션 비중 {ai_ratio:.0%} (권장 20~25%, 실무 답변이 본체여야 함)")
    return {"ok": not warnings, "warnings": warnings, "ai_ratio": ai_ratio}


def _weak_writing(body: str) -> list[str]:
    """정보가 0인 일반론 표현을 찾는다.

    2026-08-19 진단: 글이 질문을 인용해놓고 정작 답을 안 하고 "복잡할 수
    있습니다", "정확한 이해가 필요합니다" 같은 문장으로 분량만 채우고 있었다.
    검색자는 답을 원하지 개념 설명을 원하지 않는다(네이버 D.I.A. 로직).
    """
    phrases = [
        "복잡할 수 있습니다",
        "중요합니다",
        "필요합니다만",
        "정확한 이해가 필요",
        "주의가 필요합니다",
        "다양한 요소",
        "여러 가지가 있습니다",
        "말씀드리겠습니다",
    ]
    return [ph for ph in phrases if ph in body]


def _risky_claims(body: str) -> list[str]:
    """AI가 지어내기 쉬운 단정적 수치·법령 표현을 찾아 경고 목록으로 돌려준다.

    2026-08-19 실측: 프롬프트로 "지어내지 말라"고 해도 "2022년 시행규칙",
    "총 공사비의 20~30%", "최저임금 10,000원" 같은 미검증 수치가 섞여 나왔다.
    틀린 수치는 마크다운 노출보다 신뢰 손상이 크므로 발행 전 사람이 확인한다.
    """
    pats = [
        (r"\d{4}년\s*[가-힣]*법", "법령 연도"),
        (r"제?\s*\d+조", "법 조항"),
        (r"\d+(\.\d+)?\s*%", "요율"),
        (r"\d{1,3},\d{3}\s*원", "금액"),
    ]
    hits: list[str] = []
    for pat, label in pats:
        for m in re.finditer(pat, body):
            frag = m.group(0)
            # 상식 수준으로 고정된 값은 오탐이므로 제외(부가세 10% 등)
            if label == "요율" and frag.strip().replace(" ", "") in {"100%", "0%", "10%", "50%"}:
                continue
            hits.append(f"{label}({frag})")
    return list(dict.fromkeys(hits))


def _ai_section_ratio(body: str) -> float:
    """'AI' 소제목 아래 섹션이 전체 본문에서 차지하는 비중.

    소제목 표기는 대괄호([핵심 답변])를 쓴다 — 네이버는 마크다운을 렌더링하지
    않아 '##'가 독자 화면에 그대로 보이기 때문이다(2026-08-19 실측·정정).
    과거 마크다운으로 쓰던 글도 있으므로 '## ' 형식도 함께 인식한다.

    이 값은 이제 "최소 60%"가 아니라 "최대 35%" 기준으로 쓴다. 검색자가 원하는
    실무 답변이 본체여야 체류시간이 유지되기 때문이다.
    """
    lines = body.split("\n")
    h2_idx = [
        i
        for i, ln in enumerate(lines)
        if re.match(r"^##\s", ln.strip()) or re.match(r"^\[[^\]]{2,30}\]\s*$", ln.strip())
    ]
    ai_headings = [i for i in h2_idx if "AI" in lines[i]]
    if not ai_headings or len(body) == 0:
        return 0.0
    start = ai_headings[0]
    later = [i for i in h2_idx if i > start]
    end = later[0] if later else len(lines)
    section_text = "\n".join(lines[start:end])
    return len(section_text) / len(body)


def split_body(body: str, parts: int = 3) -> list[str]:
    """본문을 단락(빈 줄) 기준으로 parts 등분.

    이미지를 글 중간에 끼우기 위해 사용.
    단락이 부족하면 글자 수 기준으로 균등 분할.
    """
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    if len(paragraphs) < parts:
        chunk = max(1, len(body) // parts)
        return [body[i * chunk : (i + 1) * chunk].strip() for i in range(parts)]

    per = len(paragraphs) // parts
    segments = []
    for i in range(parts):
        start = i * per
        end = (i + 1) * per if i < parts - 1 else len(paragraphs)
        segments.append("\n\n".join(paragraphs[start:end]))
    return segments
