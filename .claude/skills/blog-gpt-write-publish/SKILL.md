---
name: blog-gpt-write-publish
description: GPT가 블로그 본문 초안을 쓰고 Claude가 팩트체크·CTA 부착 후 네이버에 발행하는 전체 파이프라인. "블로그 글 써서 올려줘", "GPT로 블로그 써줘", "블로그 N편 발행해" 같은 요청에 사용. 2026-08-23 실전 발행 검증 완료(4,171자·태그24개). 탐색 없이 정해진 5단계만 실행하면 되므로 토큰이 적게 든다.
---

# GPT 초안 → Claude 검증 → 네이버 발행

**이 스킬의 목적은 토큰 절약이다.** 2026-08-23에 이 파이프라인을 만드느라
탐색·시행착오로 많은 토큰을 썼다. 그 결과가 코드에 다 들어갔으므로,
이제는 **아래 5단계를 그대로 실행만** 하면 된다. 화면을 뒤지거나 셀렉터를
찾지 말 것 — 이미 다 해결돼 있다.

## 실행 5단계 (이대로만)

### 1. 주제 고르기
```python
from scripts.naver.blog.marketing.topics import get_researched_topics
topics = get_researched_topics()          # 3중 검증 결과(제품 관련만 필터됨)
```
`data/blog_posts_cache.json`(전체 발행분 103편)과 대조해 **이미 쓴 주제는
제외**한다. 주제를 지어내지 않는다.

### 2. GPT 초안 요청
```python
from scripts.browser.cdp.cdp_helper import CDP
from scripts.naver.blog.marketing.gpt_writer import generate_draft

cdp = CDP(port=9222)
r = generate_draft(cdp, {
    "topic": "...", "keywords": ["...", "..."], "source": "(지식iN 원문)",
}, out_path="data/blog_drafts/draft_NN_주제.json")
cdp.close()
```
- 1편당 **2~5분** 걸린다(GPT가 웹검색까지 함). 타임아웃 400초 이상 줄 것.
- 기준서(분량·태그·구조·금지사항)는 `gpt_writer.py`의 프롬프트에 이미 들어있다.

### 3. 팩트체크 ← **여기가 Claude의 핵심 역할**
`r["review"]["must_verify"]`에 잡힌 수치(법 조항·연도·요율·금액)를
**WebSearch로 실제 출처를 확인**한다.
- 확인되면 그대로 둔다.
- 확인 안 되면 **그 문장의 숫자를 빼고** "어디서 확인하는지"로 바꾼다.
- GPT가 웹검색을 하면 정확도가 높지만, **검증 없이 발행하지 않는다.**

### 4. CTA 붙이기 ← **GPT에게 시키지 않는다**
제품 실측 수치가 들어가야 해서 GPT가 지어낼 위험이 크다. 주제에 맞춰
Claude가 직접 쓴다(표준 문구 복붙 금지 — [[naver-blog-publish]] CTA 정직성 원칙).

| 주제 | 연결 |
|---|---|
| 일위대가·제비율·원가계산·물량산출 | 적산 엔진 (소방 5,830호표·전기 2,674호표) |
| 계약·행정 등 검증된 기능 없음 | "AI로 자동화하는 회사"로 정직하게, 과장 금지 |

끝은 항상 `👉 도입 문의 · 개인 교습 문의 https://haehan-ai.kr · 010-7387-6635`

### 5. 점검 → 발행
```bash
python -m scripts.naver.blog.cli.blog_publish_manual "data/blog_drafts/draft_NN.json" --check
# 이미지 3장이 자동 확보돼 원고에 저장됨 → 사용자 승인 → 아래 실행
python -m scripts.naver.blog.cli.blog_publish_manual "data/blog_drafts/draft_NN.json" --publish
```
**발행은 외부 공개라 매번 사용자 확인을 받는다**(CLAUDE.md).

## 알려진 정상 동작 (놀라지 말 것)

- `공개설정 실패: Locator.click Timeout` 경고가 뜬다 → **기본값이 전체공개라 무관**
- 점검에서 `법 조항(제20조)` 같은 경고가 남아도, 3단계에서 확인했으면 발행해도 된다
- GPT 응답에 출처 칩이 섞이는 문제·검색 중 완료 오판 문제는 `gpt_writer.py`가
  이미 처리한다(노드 복제 후 링크 제거 / min_len 하한)

## 토큰을 더 줄이려면

- **스크린샷을 찍지 않는다.** 위 5단계는 전부 CLI·함수 반환값으로 확인 가능하다.
  화면 확인이 필요한 건 발행 결과를 사용자가 눈으로 볼 때뿐이다.
- **여러 편을 쓸 땐 2~4단계를 편별로 반복**하고, 5단계 발행만 사용자 승인을
  한 번에 받는다(배치 승인 — CLAUDE.md "사용자 승인 후 자동 진행").
- 실패 원인 진단이 필요 없는 **반복 실행**은 하위 모델 서브에이전트에 위임
  가능하다. 단 **판단이 필요한 3·4단계는 위임하지 않는다**
  (2026-08-23 실측: 하위 모델은 실행은 정확했으나 원인 진단은 틀렸다).

## 실전 기록

- 2026-08-23 첫 발행: "제비율 설계변경 공사기간연장 시 당초 요율 그대로 적용할까"
  (`skyjwsin/224387854372`) — 4,171자·태그 24개·이미지 3장.
  GPT가 재정경제부 계약예규「공사계약일반조건」제20조를 인용했고, Claude가
  WebSearch로 실제 조항임을 확인한 뒤 발행.
