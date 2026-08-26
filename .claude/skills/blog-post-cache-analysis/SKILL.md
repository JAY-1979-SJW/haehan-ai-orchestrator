---
name: blog-post-cache-analysis
description: skyjwsin 블로그에 발행된 전체 글(자동 발행분 + 사용자 직접 발행분)을 CDP로 긁어 로컬 캐시에 저장하고 기준서 준수 여부를 분석. "발행글 캐시해", "블로그 글 분석해", "중복 발행 확인해" 같은 요청에 사용. 반복 스크래핑·코드 작성은 서브에이전트(Agent 도구)에 위임하고 결과만 검증하는 패턴. 2026-08-23 기준서 작성, 구현은 미착수.
---

# 발행글 캐시·분석 (skyjwsin 블로그)

## 왜 필요한가 (2026-08-23 발견)

`data/blog_topic_cache.json`은 **AI가 자동 발행한 글만** 기록한다
(`scripts/naver/blog/marketing/publish.py::record_success()`가 호출될
때만 쌓임). 그런데 실제로는:

- 사용자가 **직접** chatgpt.com/네이버 에디터로 쓴 글도 있다(2026-08-23,
  "하도급대금 직접지급" 글 등) — 이건 캐시에 안 잡힌다.
- 전체 103편 중 몇 편이 실제로 기준서(`naver_blog_content_standard.md`)
  기준(분량 2,500자+, 태그 15개+, `[핵심 답변]` 구조, CTA 정직성 등)을
  지키는지 아무도 모른다.
- `topics.py::is_duplicate()`가 이 캐시만 보고 중복 판정을 하므로,
  사용자가 직접 쓴 글과 같은 주제를 AI가 다시 발행할 위험이 있다.

## 이 스킬이 하는 일 (설계 — 2026-08-23, 구현 미착수)

1. **수집**: `blog.naver.com/PostList.naver?blogId=skyjwsin&categoryNo=0`
   목록을 페이지네이션 순회해 전체 글의 logNo·제목·카테고리·작성일을
   먼저 뽑는다.
2. **본문 추출**: 각 logNo 글을 열어(`blog.naver.com/skyjwsin/{logNo}`)
   본문 텍스트·태그를 innerText로 긁는다 — 최상위 문서에 콘텐츠가
   있을 때도, iframe(`#mainFrame`) 안에 있을 때도 있으니 **둘 다
   확인**한다(2026-08-23 실측: `PostList.naver`는 top document,
   구버전 에디터 글은 iframe인 경우가 있었음 — 매 글마다 실제로 확인).
3. **저장**: `data/blog_posts_cache.json`에 증분 저장(이미 있는 logNo는
   재수집 안 함) — `{"posts": [{"logNo", "title", "category", "tags",
   "body", "posted_at", "char_count"}]}`
4. **분석**: 각 글에 `content.py::seo_check()`를 그대로 적용해 태그 수·
   분량·결론 유무·마크다운 잔존 등을 일괄 리포트.
5. **연동**: `topics.py::is_duplicate()`가 `blog_topic_cache.json`뿐
   아니라 이 캐시의 제목도 같이 대조하도록 수정.

## 실행 절차 — 드라이런 먼저

1. **5편만** 먼저 긁어서 추출 정확도(제목/본문/태그가 실제로 맞게
   뽑히는지) 확인한다. 이 단계에서 iframe vs top-document 문제,
   페이지네이션 구조를 확정한다.
2. 사람 확인 후 **전체 103편** 진행.
3. 완료 후 분석 리포트로 "기준서 위반 글 목록"(예: 태그 5개 미만,
   결론 없음, 행정신고 주제인데 안 지워짐 등)을 뽑아 보고한다 — 실제
   삭제·비공개 전환은 사용자가 직접 하거나 별도 승인 후 진행
   (외부 공개 콘텐츠 변경 = 매번 재확인 원칙, CLAUDE.md).

## 작업 위임 패턴 (2026-08-23 확정)

103편 스크래핑 + `post_cache.py` 코드 작성처럼 **반복적이고 명세가
명확한 작업**은 `Agent` 도구로 서브에이전트에 위임한다. 위임하는 쪽은:

- 무엇을 스크래핑할지(URL 패턴, 추출 필드), 어디에 저장할지(파일 경로),
  드라이런 범위(5편)를 **구체적으로 지시**한다.
- 서브에이전트 결과를 받으면 **직접 검증**한다 — layer audit, quality
  gate, 그리고 실제로 5편 샘플이 정확히 뽑혔는지 눈으로 확인.
- 게이트 통과·검증 끝난 뒤에만 커밋한다.

## 관련 파일

- `scripts/naver/blog/marketing/topics.py::is_duplicate()` — 이 캐시와
  연동될 함수
- `scripts/naver/blog/marketing/content.py::seo_check()` — 분석에
  재사용할 검증 로직
- `scripts/naver/blog/management/analytics.py` — 방문자 통계(다른 역할,
  이 스킬과 헷갈리지 말 것 — 저건 트래픽, 이건 콘텐츠)
- [[naver-blog-publish]] — 발행 파이프라인 본체
