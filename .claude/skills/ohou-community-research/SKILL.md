---
name: ohou-community-research
description: 오늘의집(ohou.se) 커뮤니티에서 실제 사용자 질문·게시글을 검색해 블로그 주제 리서치 신호로 쓴다. "오늘의집 조사해", "조명 커뮤니티 리서치", "실제 사람들이 뭘 궁금해하는지 오늘의집에서 찾아줘" 같은 요청에 사용. skyjwshin(조명) 블로그처럼 카페 데이터가 없는 도메인의 주제 리서치에 특히 유용.
---

# 오늘의집 커뮤니티 리서치

## 이 스킬이 하는 일

두 레이어로 나뉜다.

1. **스크래퍼** — `scripts/community/sites/ohou.py::search_community(query)`.
   오늘의집 커뮤니티(집들이·집사진·질문 게시판 등)를 검색해 **실제
   사용자가 쓴 질문·경험담**을 가져온다.
2. **파이프라인** — `scripts/naver/blog/cli/research_blog_topics_lighting.py`.
   ①을 시드 14개(조명 8개+인테리어 6개)로 돌려 게시글을 모으고
   → 키워드 빈도 추출(불용어 필터) → 검색광고 실검색량 조회 → 지식iN
   실질문 조회까지 이어지는 **완결된 3중 검증 실행 파일**. 카페 크롤링과
   같은 역할(실수요 콘텐츠 각도 확보)을 카페 없이 대체한다 —
   [[naver-blog-publish]] 파이프라인의 3중 검증(카페 빈도+검색광고+지식iN)
   중 "카페 빈도" 자리를 오늘의집으로 채운 것. 출력은
   `data/blog_topic_research_lighting_latest.json`.

**"오늘의집 조사해줘" 요청이면 대부분 ②(파이프라인)를 바로 실행하면 된다.**
①(스크래퍼 단독)은 다른 사이트 조사나 임시 확인이 필요할 때만 쓴다.

## 실행

파이프라인 (권장 — 검색량·실질문까지 완결):
```bash
python -m scripts.naver.blog.cli.research_blog_topics_lighting
```

스크래퍼만 단독으로:
```bash
python -m scripts.community.sites.ohou "조명"
python -m scripts.community.sites.ohou "거실등"
```

Python에서 직접:
```python
from scripts.community.sites.ohou import search_community
result = search_community("스탠드 조명")
# {"query": "스탠드 조명", "posts": [{"title", "snippet", "url", "board", "posted_at"}, ...]}
```

## 왜 이 방식인가 (2026-08-24 실측 — 다시 조사하지 말 것)

### 1. requests/curl은 403 — CDP 필수
`ohou.se`는 서버 단 봇 차단이 있어 일반 HTTP 요청(정상 UA 포함)은
**무조건 403**이 난다. `scripts.browser.cdp.cdp_force_start`로 띄운 실제 브라우저로
직접 URL 이동하면 로그인 없이 정상 로딩된다. **requests/BeautifulSoup만
으로 재시도하지 말 것** — 이미 확인된 막다른 길이다.

### 2. 검색 URL을 클릭 시뮬레이션 없이 바로 쓴다
```
https://ohou.se/search/community?query={URL인코딩 검색어}&search_affect_type=Typing
```
이 URL은 React SPA 클릭 흐름(검색창 클릭 → 타이핑 → Enter)을 실제로
재현해서 도달한 최종 URL을 확인해 알아낸 것이다. **이제는 이 URL에
`cdp.navigate()`만 하면 되고, 클릭 재현은 필요 없다.**

다른 오늘의집 하위 검색(쇼핑/이미지/콘텐츠 등)이 필요해지면 같은 방식
(`query=` 파라미터, tab 이름만 다름: `/search/index`(통합),
`/search/community`(커뮤니티))으로 유추 가능하지만, **확인 없이 다른
tab URL을 추측해서 쓰지 말고 한 번은 직접 클릭 재현으로 검증**한다 —
연관검색어 칩은 `/search/community`가 아니라 `/search/index`에만 있는
식으로 탭마다 화면 구성이 다르다(2026-08-24 확인, 아래 "알려진 함정"
참조).

### 3. 좌표 실수 — 반드시 피할 것
React 클릭을 CDP로 재현할 때 **스크린샷 픽셀 좌표와 CSS 뷰포트 좌표를
혼동하면 클릭이 계속 빗나간다.** `cdp.shot()`이 주는 이미지는
`devicePixelRatio`(보통 1.5)가 곱해진 픽셀이고, `Input.dispatchMouseEvent`
가 받는 좌표는 CSS 픽셀(`getBoundingClientRect()`가 주는 값)이다. 클릭할
요소는 스크린샷에서 눈대중으로 좌표를 잡지 말고, 반드시 JS로
`getBoundingClientRect()`를 먼저 조회해 그 값을 그대로 쓴다.

### 4. React input에 타이핑할 때 이벤트 중복 주의
`Input.dispatchKeyEvent`에 `type:'keyDown'`과 `type:'char'`를 **둘 다**
텍스트와 함께 보내면 글자가 두 번 찍힌다(`조명`→`조조명명`). **`type:'char'`
만 문자별로 보낸다.** 필드를 비울 때도 `el.value=''` 직접 대입이 아니라
React가 감지하도록 네이티브 setter를 써야 한다:
```js
var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
setter.call(el, '');
el.dispatchEvent(new Event('input', {bubbles:true}));
```

### 5. 게시글 카드 셀렉터 — css-xxxx 해시 클래스 쓰지 않는다
오늘의집은 CSS-in-JS라 클래스명(`css-1ip2hmn` 등)이 배포마다 바뀔 수
있다. `ohou.py`의 추출 JS는 구조 기반 셀렉터만 쓴다:
```
article a[href*="/community/posts/"]
  └ h3                    ← 제목
  └ h3 다음 형제 span        ← 본문 스니펫
  └ .css-60smz5 (구조상 첫/둘째) ← 게시판명 / 작성시각
```
`.css-60smz5`류 해시 클래스가 언젠가 안 먹으면(추출 결과 0건), 이 카드
구조 자체(`article > a[href*="/community/posts/"]`)부터 다시 확인한다.

## WebFetch로 사전 조사하지 말 것

이 사이트를 WebFetch로 먼저 "로그인 없이 검색되나?"라고 물어봤더니 **거짓
긍정**을 줬다 — 페이지에 게시글 목록이 있다는 것만 보고 "검색이 된다"고
답했지만, 실제로 curl+BeautifulSoup으로 정밀 검증하니 검색어와 무관한
일반 피드였다(클리앙·뽐뿌·82cook도 같은 방식으로 오판했었다). **커뮤니티
사이트의 검색 가능 여부는 WebFetch 요약이 아니라 실제 파싱(제목에 검색어가
포함되는지)으로 검증한다.**

## 6. 키워드 후보 추출 — 불용어는 "단어 나열"이 아니라 "어미 패턴"으로 거른다

`research_blog_topics_lighting.py::_top_keyword_candidates()`가 게시글
제목+본문에서 2글자 이상 한글 토큰을 뽑는데, 처음엔 노이즈 단어를 하나씩
`_GENERIC_WORDS`에 추가하는 식이었다. "오늘의집만 분리해서 분석해봐"로
검색광고 필터 없이 순수 빈도표를 뽑아보니 "있는(40회)","너무","제가",
"도와주세요" 같은 조사/부사/서술어가 상위권에 그대로 남는 걸 확인했다
(2026-08-24). **단어 나열은 다음 도메인에서 또 반복될 문제**라 구조를
바꿨다:

- `_PREDICATE_SUFFIX_RE` — "~습니다/해요/세요/까요/죠" 등 어미로 끝나는
  토큰은 자동으로 서술어 취급해 제외 (명사는 거의 이런 어미로 안 끝난다)
- `_EXISTENTIAL_VERB_FORMS` — "있는/있어/없는" 등 존재동사 활용형은
  어미가 짧고 다양해 정규식 하나로 못 잡아서 명시적 세트로 차단
- `_PRONOUN_ADVERB_WORDS` — "제가/너무/특히/직접" 같은 순수 기능어

다른 도메인(예: 이번 것 말고 또 새 블로그를 만들 때) 리서치 스크립트를
만들 때도 **이 3단 구조(어미 정규식+존재동사 세트+대명사 세트)를 그대로
복붙**하는 게 낫다 — 매번 노이즈 단어를 눈으로 보고 하나씩 추가하지 않아도
된다.

## 다음에 필요해질 수 있는 것 (미착수)

- 검색 결과가 6~20건 정도로 적다 — 페이지네이션/무한스크롤 대응 안 함
  (스크롤 트리거 후 재추출 필요, 아직 안 만듦)
- 통합검색 탭(`/search/index`)의 연관검색어 칩 추출 — 시도했다 실패해서
  뺐다(상단 네비게이션까지 잘못 잡음). 필요해지면 `/search/index` 페이지의
  실제 칩 컨테이너를 `dump_card.py`식으로 outerHTML 떠서 재조사할 것.
- 지식iN 질의에 항상 "조명 " 접두어를 붙이는 로직이라, "인테리어" 같은
  순수 인테리어 키워드로도 결국 조명 위주 질문만 나온다. 완전히 조명과
  무관한 인테리어 주제(가구배치 자체, 수납 노하우 등)까지 원하면 접두어
  로직을 키워드별로 분기해야 한다(2026-08-24 확인, 미해결).
- 오늘의집 데이터로 만든 68~71개 주제 후보는 **아직 사람이 검수한 적
  없다** — `accounts.py`의 skyjwshin.topic_research_ready=True 지만,
  자동 발행에 그대로 물리기 전에 한 번 훑어볼 것.

## 관련
- `scripts/community/sites/ohou.py` — 스크래퍼 실제 구현
- `scripts/naver/blog/cli/research_blog_topics_lighting.py` — 3중 검증 파이프라인
- `scripts/community/sites/iboss.py` — 같은 패턴(CDP 필수, 구조 기반 셀렉터)의 선례
- [[cdp-browser-automation]] — CDP 기본 사용법
- [[naver-blog-publish]] — 이 리서치 결과를 최종적으로 쓰는 곳
