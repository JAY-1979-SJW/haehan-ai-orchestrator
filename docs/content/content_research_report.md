# 콘텐츠 조사 리포트 (F-4S-4)

## 목적

키워드 기반으로 네이버 검색 결과(블로그/뉴스/카페/쇼핑/웹문서)와
유튜브 검색 결과(read-only) 를 한 번에 수집해, 다음 작업의 입력으로 쓸
**통합 조사 리포트(JSON / CSV / Markdown)** 를 생성한다.

본 리포트는 다음을 위한 입력이다:
- LTX 등 영상 제작 큐의 소재 후보 추출
- 동일 키워드의 노출 채널/플랫폼 분포 파악
- 상위 콘텐츠의 제목 패턴/조회수/반응 비교

## 지원 데이터 소스

| 플랫폼 | 모듈 | 호출 종류 | 자격증명 |
| --- | --- | --- | --- |
| Naver Search Open API | `ai_orchestrator.connectors.naver_search_api_client` | `blog`, `news`, `cafearticle`, `shop`, `webkr` (GET 전용) | `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` |
| YouTube Data API v3 | `ai_orchestrator.connectors.youtube_data_api_client` | `search.list`, `videos.list` (GET 전용) | `YOUTUBE_DATA_API_KEY` (server key, 비OAuth) |

두 소스 모두 read-only 이며, **로그인/카페가입/댓글/업로드/수정/삭제 흐름은 절대 추가하지 않는다.**

## API 키 필요 여부

- 키 미설정 시 각 클라이언트는 `mode=mock_or_disabled` 로 응답하고, 경고가 누적된다.
- 한쪽 키만 있어도 다른 쪽 실패가 전체 실행을 중단시키지 않는다.
- API 키/시크릿은 **환경변수에서만** 읽으며, 코드/문서/리포트/로그 어디에도 원문을 기록하지 않는다.

`.env.example` 참고:
```
NAVER_CLIENT_ID=
NAVER_CLIENT_SECRET=
YOUTUBE_DATA_API_KEY=
```

## live / dry-run 차이

| 모드 | 트리거 | 네트워크 호출 | 결과 |
| --- | --- | --- | --- |
| dry-run (기본) | `--live` 미지정 | 없음 | 모든 호출이 `mock_or_disabled`. 리포트 구조만 생성. |
| live | `--live` 지정 + 키 존재 | 해당 플랫폼만 실호출 | 가능한 플랫폼만 실데이터 수집. |
| live (키 없음) | `--live` 지정, 키 없음 | 없음 | 해당 플랫폼은 `mock_or_disabled`, 경고 추가. |

## 실행 예시

```bash
# 단일 키워드 dry-run (키 없어도 동작, 리포트 구조만 생성)
python scripts/research_content.py --keyword "소방공사" \
    --naver-types blog,news,cafearticle \
    --youtube-with-details

# 다중 키워드 + JSON 요약 출력
python scripts/research_content.py \
    --keyword "소방공사" --keyword "스마트팩토리" \
    --youtube-with-details --json

# 키워드 파일 + live 호출 (.env 키 필요)
python scripts/research_content.py \
    --keywords-file ./kw.txt \
    --naver-display 10 \
    --youtube-max-results 10 \
    --youtube-with-details \
    --live
```

## 결과 파일

`--out-dir` (기본 `runs/content/`) 아래에 동일 timestamp 로 3개 파일이 생성된다:

```
runs/content/content_research_YYYYMMDD_HHMMSS.json
runs/content/content_research_YYYYMMDD_HHMMSS.csv
runs/content/content_research_YYYYMMDD_HHMMSS.md
```

### JSON 구조 (요약 발췌)

```json
{
  "generated_at": "2026-04-26T12:00:00Z",
  "mode": "dry_run",
  "keywords": ["소방공사"],
  "platforms_attempted": ["naver", "youtube"],
  "platforms_live": [],
  "summary": {
    "keywords_count": 1,
    "total_items": 0,
    "naver_items": 0,
    "youtube_items": 0,
    "platforms_attempted": ["naver", "youtube"],
    "platforms_live": [],
    "warnings_count": 5,
    "mode": "dry_run"
  },
  "items": [],
  "title_terms": [],
  "content_ideas": [],
  "warnings": ["..."]
}
```

### CSV 컬럼

`platform, source_type, keyword, title, url, summary, published_at, channel_or_author, view_count, like_count, comment_count, risk_flags`

### Markdown 섹션

```
# 콘텐츠 조사 리포트
## 요약
## 플랫폼별 결과
## 상위 노출/반응 후보
## 제목 키워드 빈도
## 영상 소재 후보
## LTX 영상 제작 아이디어
## 경고 및 제한
## 다음 조치
```

## 통합 item 필드

```python
UnifiedItem(
    platform: "naver" | "youtube",
    source_type: "blog" | "news" | "cafearticle" | "shop" | "webkr" | "youtube_video",
    keyword: str,
    title: str,                      # HTML 태그 제거 후 저장
    url: str,                        # 네이버 link 또는 https://www.youtube.com/watch?v=<id>
    summary: str,                    # description 발췌(최대 300자)
    published_at: str | None,
    channel_or_author: str | None,
    metrics: {
        "view_count": int | None,
        "like_count": int | None,
        "comment_count": int | None,
    },
    raw_rank: int,                   # 해당 source 결과 내 순위
    risk_flags: list[str],           # 예: missing_url, missing_title, missing_video_id
)
```

## 금지 작업 (절대 추가하지 말 것)

- 댓글 작성, 카페 가입, 글쓰기, 업로드, 수정, 삭제
- 네이버/유튜브 로그인 자동화, 쿠키/세션/storage 접근
- 브라우저 자동화 (Playwright / Selenium 등) 활용
- OAuth 2.0 / 사용자 토큰 발급
- API key / client secret 의 코드/문서/리포트/로그 출력
- `.env` 파일 커밋
- requests 등 신규 외부 의존성 추가

## 향후 확장

- 키워드 자동 추천: 기존 리포트의 `title_terms` 와 외부 트렌드 신호 결합
- 인기 영상 패턴 분석: `views` / `likes` / `published_at` 기반 시즌성/길이/포맷 패턴 산출
- 자동 대본/자막 생성: 본 리포트 결과 → 별도 LLM 파이프라인 (read-only 보장)
- LTX 영상 제작 큐 연결: `content_ideas` 항목을 외부 영상 제작 작업으로 푸시 (write 작업은 별도 승인 게이트 적용)


## F-4S-5 분석 고도화

### 분석 점수 기준

`score_content_items(items, keywords)` 가 각 item 에 대해 다음 컴포넌트로 점수를 산출한다.

공통:
- `title_match` — 제목 내 키워드 일치 수
- `summary_match` — 요약/description 내 키워드 일치 수
- `recency` — `published_at` 기준 0..1 (1년 이내 1.0, 3년 초과 0.0 선형감쇠)
- `rank_penalty` — `1 / (1 + raw_rank)` (해당 source 결과 내 노출 순위 보정)

YouTube:
- `view_log = log10(view_count + 1)`, weight 1.0
- `like_log = log10(like_count + 1)`, weight 0.6
- `comment_log = log10(comment_count + 1)`, weight 0.4
- `relevance = title_match * 1.2 + summary_match * 0.4`
- `score = view_log + 0.6*like_log + 0.4*comment_log + relevance + recency*1.0 + rank_penalty*0.3`

Naver:
- `score = title_match*1.5 + summary_match*0.5 + recency*0.8 + rank_penalty*1.2`
- 실제 view/like/comment 가 없는 source 가 다수이므로 키워드/순위/시점 비중을 높임

### 콘텐츠 패턴 분류

`detect_content_patterns(items)` 가 다음 라벨을 부여한다 (제목/요약 전체에서 매칭).

| 라벨 | 트리거 |
| --- | --- |
| `question` | 제목에 `?` 또는 의문사 (왜/어떻게/어떤/무엇/언제/어디/누가, how/why/what/which/when/where) |
| `numbered` | 제목에 숫자 포함 (예: "5가지", "3개 사례") |
| `comparison` | "vs", "비교", "차이", "versus" 등 |
| `problem_solution` | "문제", "해결", "원인", "대처", "fix", "solve" 등 |
| `review_case` | "후기", "리뷰", "사례", "경험", "review", "case" 등 |
| `law_standard` | "법", "법령", "기준", "규정", "표준" 등 |
| `cost_estimate` | "비용", "가격", "견적", "예산", "원", "만원" 등 |
| `checklist` | "체크리스트", "리스트", "checklist", "준비물" 등 |

분포 결과는 리포트 `analysis.patterns.distribution` 에 `count`/`ratio`/`examples` 형태로 저장된다.

### 플랫폼별 권장 전략

`build_platform_strategy(summary, ranked_items, patterns)` 가 다음 구조를 산출:

```json
{
  "youtube": {
    "item_count": 5,
    "focus_recommendations": ["질문형 제목 활용 — Shorts hook 으로 적합", "..."],
    "recommended_formats": ["short", "long_form"]
  },
  "naver": {
    "item_count": 7,
    "by_source_type": {"blog": 3, "news": 2, "cafearticle": 2},
    "focus_recommendations": ["..."],
    "recommended_formats": ["blog_long", "cafe_qna"]
  },
  "cross_platform": {
    "shared_patterns": ["question", "numbered", "review_case"],
    "note": "동일 키워드를 네이버/유튜브 양쪽에서 변형 재사용해 노출면을 넓힐 것"
  }
}
```

### LTX 영상 brief

`build_ltx_video_briefs(items, keywords, max_count=5)` 는 score 상위 item 기준 brief 를 생성:

```json
{
  "title": "소방공사 견적 비교 — 견적서에서 꼭 봐야 할 7가지",
  "hook": "왜 지금 '소방공사 견적 비교' 인가?",
  "scene_ideas": ["오프닝 — ... hook", "핵심 포인트 3가지 자막 강조", "..."],
  "subtitle_points": ["핵심 메시지: ...", "보조 요약: ...", "키워드 강조: 소방공사"],
  "source_basis": [
    {"platform": "youtube", "source_type": "youtube_video", "url": "...", "title": "..."}
  ],
  "target_platform": "youtube_long",
  "risk_notes": [
    "read-only 분석 결과 기반. 댓글/업로드/가입 흐름 절대 추가 금지",
    "원본 영상/포스트 캡처 직접 사용 시 저작권/초상권 별도 검토"
  ]
}
```

`target_platform` 은 다음 규칙으로 추정:
- `youtube` 이고 제목에 `#shorts`/`쇼츠`/`30초`/`1분` 포함 → `youtube_short`
- `youtube` 이고 위 조건 외 → `youtube_long`
- `naver` 이고 `source_type=cafearticle` → `cafe_post`
- 그 외 → `naver_blog`

### Fixture 기반 분석 방법

라이브 키 없이 동작 검증:

```bash
python scripts/research_content.py \
  --fixture samples/content_research_fixture.json \
  --analysis-only \
  --json
```

동작:
- `samples/content_research_fixture.json` 의 `items[]` 만 사용. **API 호출 없음.**
- 키워드는 fixture 의 `keywords` → CLI `--keyword` 우선순위로 결정.
- 결과는 동일하게 `runs/content/content_research_<ts>.{json,csv,md}` 로 출력.
- summary mode 는 `fixture` 로 표기.

### Live key 등록 후 검증 방법

1. `.env` 에 `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, `YOUTUBE_DATA_API_KEY` 입력 (커밋 금지).
2. dry-run 으로 구조 검증:
   ```bash
   python scripts/research_content.py --keyword "소방공사" --json
   ```
3. live 호출:
   ```bash
   python scripts/research_content.py --keyword "소방공사" --live --json
   ```
4. 결과 확인:
   - `runs/content/content_research_*.json` 의 `mode == "live"`
   - `analysis.ranked_youtube[*].score` > 0 인 항목 존재
   - `ltx_video_briefs[*].source_basis[0].url` 가 실제 youtube/naver URL 인지 확인
5. JSON/CSV/MD 어디에도 API 키 원문이 노출되지 않는지 grep 으로 확인:
   ```bash
   grep -F "$NAVER_CLIENT_SECRET" runs/content/*.json    # 결과 없음 기대
   ```

### Markdown 추가 섹션

`render_markdown_report` 에 다음 섹션이 추가됨:
- `## YouTube 후보 랭킹`
- `## Naver 후보 랭킹 (source_type 별)`
- `## 콘텐츠 패턴 분포`
- `## 플랫폼별 권장 전략`
- `## LTX 영상 brief`
