# Naver Search Open API PoC (F-4S-2)

본 문서는 **공식 검색 Open API**를 이용한 read-only 조회 PoC를 정리한다.
브라우저 자동화나 로그인 자동화는 본 PoC에 절대 포함되지 않는다.

## 1. 공식 API 우선 원칙

- 네이버 검색 결과를 얻을 때는 항상 공식 Open API를 우선 사용한다.
- 본 PoC는 **로그인 / OAuth 흐름 없음** — 공개 검색 엔드포인트만 호출한다.
- Playwright / Selenium / 사용자 쿠키·세션 사용 금지.
- requests 신규 의존성 없음 — Python stdlib `urllib` 사용.

## 2. 지원 범위

| search_type   | endpoint               | 정렬(sort) 허용값        |
| ------------- | ---------------------- | ------------------------- |
| `blog`        | `/blog.json`           | `sim`, `date`             |
| `news`        | `/news.json`           | `sim`, `date`             |
| `cafearticle` | `/cafearticle.json`    | `sim`, `date`             |
| `shop`        | `/shop.json`           | `sim`, `date`, `asc`, `dsc` |
| `webkr`       | `/webkr.json`          | (없음 / 사용하지 않음)    |

> `cafearticle`은 카페 **공개 게시글 검색**에 한정한다.
> 카페 가입, 글쓰기, 댓글 등의 자동화와 혼동하지 말 것.

## 3. 환경변수

- `NAVER_CLIENT_ID` (필수, live 호출 시)
- `NAVER_CLIENT_SECRET` (필수, live 호출 시)
- `NAVER_SEARCH_API_BASE_URL` (선택, 기본값 `https://openapi.naver.com/v1/search`)
- `NAVER_SEARCH_API_TIMEOUT_SECONDS` (선택, 기본값 `10.0`)

원칙:

- secret 은 환경변수 또는 `.env` 에서만 로드한다. **하드코딩 금지**.
- secret 은 stdout / 파일 / 로그 어디에도 원문이 노출되지 않는다.
  설정 노출은 항상 `redacted()` 형태(`*_present`, `*_length`, `base_url`, `timeout_seconds`)만 사용한다.
- `.env` 는 git ignore 유지 (`.gitignore` 규칙 그대로).

## 4. live / dry-run 모드

| 조건                                       | mode               | 실제 호출 |
| ------------------------------------------ | ------------------ | --------- |
| `--live` 미지정                            | `mock_or_disabled` | ❌        |
| `--live` 지정 + 키 없음                    | `mock_or_disabled` (WARN) | ❌ |
| `--live` 지정 + 키 있음                    | `live`             | ✅        |

`mock_or_disabled` 응답은 빈 items와 warnings 만 반환하므로,
키 미설정 환경에서도 dry-run 검증/테스트가 가능하다.

## 5. CLI 사용 예

```bash
# dry-run (실제 호출 없음)
python scripts/search_naver.py --type blog --query "소방공사" --display 3

# 실제 호출
python scripts/search_naver.py --type blog       --query "소방공사" --display 3 --live --json
python scripts/search_naver.py --type news       --query "소방설비" --display 5 --live
python scripts/search_naver.py --type cafearticle --query "소방시설" --display 3 --live
python scripts/search_naver.py --type shop       --query "소화기"   --display 5 --sort sim --live
python scripts/search_naver.py --type webkr      --query "안전관리" --display 5 --live

# 결과 저장 위치 변경
python scripts/search_naver.py --type blog --query "소방" --out-dir runs/naver
```

결과 파일은 다음 두 가지가 함께 생성된다.

- `runs/naver/naver_search_YYYYMMDD_HHMMSS.json`
- `runs/naver/naver_search_YYYYMMDD_HHMMSS.md`

## 6. 호출 한도 / 운영 주의

- 네이버 검색 Open API 는 일일 호출 한도가 있다. 자동 반복 호출 시 backoff/캐시 정책을 별도로 적용해야 한다.
- 본 PoC는 1회성 조회 / 검증 용도이며, 반복 수집 파이프라인은 별도 배치/스케줄러 단계에서 다룬다.
- 응답 본문에 secret이 포함될 가능성은 낮으나, 실패 시에도 본문 길이만 노출하고 본문 자체는 저장하지 않는다.

## 7. 금지 사항

- ❌ 네이버 브라우저 자동화 (Playwright/Selenium 등)
- ❌ 네이버 로그인 자동화 / OAuth 자동화
- ❌ 카페 가입, 글쓰기, 댓글 작성, 좋아요 등 **모든 쓰기 동작**
- ❌ Client ID / Client Secret 의 코드 / 문서 / 로그 / 테스트 출력
- ❌ `.env` 커밋
- ❌ `requests` 등 신규 외부 HTTP 라이브러리 추가

## 8. 다음 확장 (별도 단계)

- 키워드별 영상 / 블로그 / 카페 콘텐츠 분석 파이프라인
- 안전 / 소방 / 입찰 관련 콘텐츠 트렌드 수집 (배치)
- 자동 영상 소재 발굴 (검색 결과 → 요약 → 후보 큐)
- Naver Cafe OAuth(가입형 API) 는 **별도 승인 단계**에서만 검토.
  본 PoC 와 절대 혼합하지 않는다.
