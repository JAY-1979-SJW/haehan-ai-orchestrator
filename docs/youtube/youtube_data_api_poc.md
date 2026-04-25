# YouTube Data API v3 — read-only PoC (F-4S-3)

## 목적
공식 YouTube Data API v3 를 이용해 **브라우저 자동화 없이** 영상 검색과 영상
메타/통계 조회를 수행한다. YouTube Studio / 로그인 자동화 / OAuth 흐름은
이번 PoC 에서 사용하지 않는다.

## 공식 API 우선 원칙
- 외부 사이트와 통합할 때는 가능한 한 공식 API 를 우선 사용한다.
- 브라우저 자동화 / Studio UI 스크래핑 / 로그인 시뮬레이션은 차단/금지.
- API key 또는 OAuth 토큰은 환경변수에서만 로드하며, 절대 코드/문서/로그에
  원문을 남기지 않는다.

## 본 PoC 범위 (read-only)
| 기능 | 엔드포인트 | quota cost | 비고 |
| ---- | ---------- | ---------- | ---- |
| 영상 검색 | `GET /youtube/v3/search` (`type=video`) | 100 | snippet 만 |
| 영상 상세 | `GET /youtube/v3/videos` | 1 | snippet + statistics + contentDetails |

이번 단계에 **포함되지 않는 작업**:
- 업로드 / 수정 / 삭제 / 댓글 작성
- OAuth 인증
- YouTube Studio 자동화
- 채널/계정 관리

## 환경변수
`.env` 또는 OS 환경변수에 다음 값을 설정한다. `.env` 는 절대 git 에 커밋하지 않는다.

```
YOUTUBE_DATA_API_KEY=
YOUTUBE_DATA_API_BASE_URL=https://www.googleapis.com/youtube/v3
YOUTUBE_DATA_API_TIMEOUT_SECONDS=10.0
```

키는 Google Cloud Console > APIs & Services > Credentials 에서
"YouTube Data API v3" 활성화 후 server API key 로 발급한다.

## live / dry-run 차이
- 기본 동작은 **dry-run** 이며 실제 네트워크 호출이 일어나지 않는다.
- `--live` 옵션을 명시했고, 그리고 `YOUTUBE_DATA_API_KEY` 가 존재할 때만
  실제 API 가 호출된다.
- `--live` 가 있어도 키가 없으면 결과는 `mock_or_disabled` 모드로 반환되고
  WARN 메시지가 기록된다.

## quota 주의
- search.list 1 회 = **100 unit**.
- videos.list 1 회 = **1 unit** (id 가 50 개여도 1 unit, 부분(part) 추가도
  공식적으로는 동일 cost — 본 PoC 는 보수적으로 1 로만 기록).
- 일일 무료 quota 는 기본 10,000 unit 이므로 검색 호출은 100 회 이내로 관리.

## CLI 사용 예시

```bash
# dry-run: 실제 호출 없이 검증만
python scripts/search_youtube.py --query "소방공사" --max-results 3

# live 검색 + 상세 조회 (키 필요)
python scripts/search_youtube.py --query "소방공사" --max-results 3 \
    --with-details --live --json

# 정렬 + 게시일 필터
python scripts/search_youtube.py --query "건설현장 안전" \
    --order date --published-after 2026-01-01 --live
```

결과는 `runs/youtube/youtube_search_YYYYMMDD_HHMMSS.{json,md}` 로 저장된다.

## 금지 사항
- YouTube Studio 자동화 / 로그인 자동화 / 쿠키·storage_state 사용 금지.
- 업로드 / 수정 / 삭제 / 댓글 작성 / 좋아요 등 write action 금지.
- API key 를 코드/문서/테스트/로그에 출력 금지. 마스킹은 `key=***`.
- requests 등 신규 의존성 추가 금지 — stdlib `urllib` 사용.

## 다음 확장 (별도 단계)
- 키워드별 영상 소재 분석 (업종/지역별 트렌드 파악).
- 인기 영상 메타/조회수 추세 분석.
- 댓글 read-only 분석 (`commentThreads.list`) — write 가 아니므로 계속 read-only.
- YouTube Analytics / Studio 데이터 (OAuth 필요) — 별도 승인형 단계로 분리.
- 자체 채널 업로드 / 메타 수정 (OAuth + write) — 별도 승인형 단계, 본 단계와 분리.
