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
