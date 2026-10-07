# Naver 검색 OpenAPI 수집 — 비로그인 공개 검색 (1단계)

블로그 / 쇼핑 검색 결과를 **공식 OpenAPI** 로만 수집한다. 로그인/세션/스크래핑은
일절 사용하지 않으며, 본문/댓글/구매 등 권한이 필요한 영역은 의도적으로 제외했다.

---

## 1. 공식 API 우선 원칙

- 모든 호출은 `https://openapi.naver.com` 의 공식 검색 엔드포인트 (`/v1/search/blog.json`,
  `/v1/search/shop.json`) 로만 수행한다.
- 사용자 동의 / OAuth 흐름이 없는 **애플리케이션 키 (X-Naver-Client-Id /
  X-Naver-Client-Secret)** 만 사용한다 — 비로그인 공개 검색의 표준 방식.
- 비공식 스크래핑(검색 결과 화면 HTML 파싱, 자동 로그인 후 셀렉터 수집 등) 금지.
- robots.txt / 사이트 약관을 우회하는 동작 금지.

---

## 2. 사용 범위 — 블로그 & 쇼핑 검색

### 2-1. 블로그 검색 (`collect_blog_search`)

- 엔드포인트: `GET /v1/search/blog.json`
- 정규화 필드: `title / link / blogger_name / blogger_link / description / post_date / source="naver_blog"`
- HTML 강조 태그(`<b>...</b>`)와 엔티티는 `strip_html` 로 정리.
- `post_date` 는 `YYYYMMDD` → `YYYY-MM-DD` 표준화.

### 2-2. 쇼핑 검색 (`collect_shopping_search`)

- 엔드포인트: `GET /v1/search/shop.json`
- 정규화 필드: `title / link / image / lprice / hprice / mall_name / product_id /
  product_type / brand / maker / category1..4 / source="naver_shop"`
- 가격 문자열(`"29,800"`, `"10000원"`)은 `to_int_price` 로 정수화.
- 구매/장바구니/찜 같은 쓰기 동작은 본 모듈에서 절대 호출하지 않는다.

---

## 3. 비로그인 공개 수집 구조

```
NaverOpenApiConfig (env)
        │
        ▼
NaverSearchClient (GET only, transport DI, dry_run)
   ├─ search_blog(query, display, start, sort)
   └─ search_shop(query, display, start, sort)
        │  → SearchResult { source, status, items, item_count, raw, ... }
        ▼
collect_blog_search / collect_shopping_search  ← 정규화 (HTML 정리, 가격 변환)
        ▼
run_naver_blog_search_job / run_naver_shopping_search_job  ← 결과 저장
```

추가로 `naver_public_page_reader.fetch_public_page_summary(url, transport=...)`
가 있다. 이건 "검색 결과 link 의 메타(title/description/canonical)만 안전하게
한 번 더 읽어보고 싶을 때" 쓰는 **선택적 fallback** 이다:

- transport 미주입 → `unsupported`
- 로그인 필요 호스트(`nid.naver.com`, `mail.naver.com`, `cafe.naver.com`,
  `band.us`, `checkout.naver.com`, `order.pay.naver.com` 등) → `blocked`
- 401/403 응답 → `blocked`
- HTML 이 아닌 응답 → `unsupported`
- 그 외 정상 HTML → `<title>` / `meta description` / `og:title` / `<link rel="canonical">` 만 파싱

본문/이미지/댓글/대량 페이지 순회는 어느 경로에서도 수행하지 않는다.

---

## 4. 환경변수

`.env.example` 에 키 이름만 추가됨. 실제 값은 절대 커밋하지 않는다.

| 키 | 용도 | 비고 |
|----|------|------|
| `NAVER_OPENAPI_BASE_URL` | API base | 기본 `https://openapi.naver.com` |
| `NAVER_OPENAPI_CLIENT_ID` | 애플리케이션 ID | developers.naver.com 에서 발급 |
| `NAVER_OPENAPI_CLIENT_SECRET` | 애플리케이션 Secret | 〃 |
| `NAVER_OPENAPI_DRY_RUN` | true 면 외부 호출 차단 | 기본 `true` |
| `NAVER_BLOG_STORE_PATH` | 블로그 결과 저장 경로 override | 기본 `<repo>/data/naver_blog_search.json` |
| `NAVER_SHOPPING_STORE_PATH` | 쇼핑 결과 저장 경로 override | 기본 `<repo>/data/naver_shopping_search.json` |

---

## 5. dry_run / live 구분

- 기본값은 `dry_run=true` — 어떤 환경변수도 설정되어 있지 않으면 외부 호출 없이
  mock 응답이 반환된다 (PII 미포함 placeholder).
- 운영 단계에서 `NAVER_OPENAPI_DRY_RUN=false` + `CLIENT_ID/SECRET` 가 설정되어
  있어야 실제 호출이 일어난다. 누락 시 `status="unconfigured"` + `MISSING_CREDENTIALS`
  로 안전 종료 (저장 파일도 생성하지 않음).
- transport 는 의존성 주입 — 실제 운영에서는 httpx 등으로 wiring 한다.
  현재 골격은 transport 미연결 시 `TRANSPORT_NOT_WIRED` 로 종료한다.

저장 구조 (예: `data/naver_blog_search.json`):

```json
{
  "source": "naver_blog",
  "query": "파이썬",
  "collected_at": "2026-04-23T10:00:00+00:00",
  "items": [
    {"title": "...", "link": "...", "blogger_name": "...", "post_date": "2026-04-23", ...}
  ]
}
```

이번 단계는 동일 query 의 **최신 실행 결과를 덮어쓰는** 단순 저장이다. 증분
수집(같은 link 재수집 시 누락 통합)은 다음 단계에서 분리.

---

## 6. 금지 사항

- 네이버 로그인 자동화 / 쿠키 주입 / CAPTCHA / OTP 자동 처리
- 비공개 게시판·메일·캘린더·결제 등 권한 페이지 접근
- 상세 본문 / 댓글 / 첨부 / 이미지 대량 수집
- 쇼핑 구매·장바구니·찜·리뷰 등 쓰기 동작
- robots.txt / 사이트 정책 우회

`NaverSearchClient` 는 GET 외 메서드를 호출 시점에 차단하고
(`METHOD_NOT_ALLOWED`), `naver_public_page_reader` 는 로그인 필요 호스트
힌트와 401/403/non-HTML 응답을 모두 자동 차단한다.

---

## 7. 2단계: DB 적재 / 3단계: 증분 / 4단계: 조회·점검

### 2단계 — 운영 가능한 데이터 자산 전환

- `NAVER_SEARCH_DB_ENABLED=true` 일 때만 stdlib `sqlite3` 로 자동 적재.
  DRY_RUN 이나 미설정 상태에서는 DB write 없음.
- 테이블: `naver_blog_posts` (UNIQUE `link`), `naver_shopping_items` (UNIQUE `product_id`).
  중복은 `INSERT OR IGNORE` 로 조용히 제거되고, `shopping` 에서 `product_id` 가 없는
  항목은 insert 대상에서 제외되며 WARN 로그 + `skipped_count` 누적.
- 증분 수집 기초 상태: `data/naver_search_state.json` 에 query 별 `last_collected_at`
  기록. 환경변수 `NAVER_SEARCH_STATE_PATH` 로 override 가능.

### 3단계 — 실제 증분 호출

- `max_pages` kwarg (기본 1) 로 페이지 루프 노출.
- **blog**: state 의 `last_collected_at` 에서 `YYYY-MM-DD` prefix 를 cutoff 로 삼아,
  과거 post_date 를 만나는 순간 루프 종료 (`early_stop_reason="date_cutoff"`).
  dry_run 은 cutoff 무적용.
- **shopping**: post_date 가 없으므로 DB 적재 중 연속 duplicate 를 추적해
  `DUPLICATE_STOP_THRESHOLD=20` 도달 시 이후 페이지 API 콜 중단
  (`early_stop_reason="duplicate_threshold"`). DB flag off 시에는 단일 페이지 동작 유지.
- **state 갱신 조건**: `inserted_count > 0` 일 때만 `last_collected_at` 을
  갱신해 "전부 중복이었지만 시간만 미는" 누락 리스크 차단.

### 4단계 — 조회 API + 운영 점검

Read-only API (admin/owner 권한, 쓰기 없음):

| 메서드/경로 | 설명 |
|--------------|------|
| `GET /api/v1/external/naver/blog-search` | query / date_from / date_to / limit(≤200) / offset. 정렬: post_date DESC NULLS LAST, collected_at DESC |
| `GET /api/v1/external/naver/shopping-search` | query / min_price / max_price / brand / mall_name / sort(`collected_at_desc` default, `lprice_asc/desc`) / limit(≤200) / offset |
| `GET /api/v1/external/naver/search-status` | db_enabled / db_exists / row_counts / latest_collected_at / last_blog_queries / last_shop_queries / warnings |

경로는 `db_path_basename / state_path_basename` 만 응답 — 풀 경로/시크릿은 절대
응답에 포함되지 않는다 (`X-Naver-Client-Secret` 헤더 키조차 노출되지 않음을 테스트로 검증).

운영 CLI: `python scripts/audit_naver_search_status.py [--top N] [--json]`
- DB 파일/테이블/row count, 최근 collected_at, query 별 최근 수집 상위 N, state 파일 주요 키
- DB 와 state 간 명백한 불일치(예: state 에는 있는 query 가 DB 에 0건)도 체크
- 마지막 줄 `RESULT: PASS|WARN|FAIL` 로 CI 에서 grep 가능. exit code: 0=PASS, 2=WARN, 3=FAIL

### 5단계 — 운영 스케줄 편입 + 자동 상태 기록

#### 스케줄 편입 방식

`server.py` `lifespan` 에서 `asyncio.create_task(schedule_loop())` 로 백그라운드 태스크 등록.
신규 스케줄러 프레임워크 없음 — `asyncio.sleep` 루프 + `asyncio.to_thread` 만 사용.

| 환경변수 | 용도 | 기본값 |
|----------|------|--------|
| `NAVER_SEARCH_SCHEDULE_ENABLED` | `true` 로 설정해야 활성화 | `false` |
| `NAVER_SEARCH_SCHEDULE_INTERVAL_SEC` | 수집 간격(초), 최소 60 | `3600` |
| `NAVER_BLOG_SEARCH_QUERIES` | 블로그 수집 쿼리 (콤마 분리) | 빈값 → skip |
| `NAVER_SHOPPING_SEARCH_QUERIES` | 쇼핑 수집 쿼리 (콤마 분리) | 빈값 → skip |
| `NAVER_SEARCH_RUN_LOG_PATH` | 실행 기록 JSONL 경로 override | `<repo>/data/naver_search_runs.jsonl` |

예시:
```
NAVER_SEARCH_SCHEDULE_ENABLED=true
NAVER_SEARCH_SCHEDULE_INTERVAL_SEC=3600
NAVER_BLOG_SEARCH_QUERIES=파이썬,FastAPI,클로드
NAVER_SHOPPING_SEARCH_QUERIES=기계식키보드,모니터
```

#### 실행 기록 구조

`data/naver_search_runs.jsonl` — JSONL append-only (최신이 파일 뒤). 민감정보 없음.

```jsonl
{"job_type": "blog", "query": "파이썬", "started_at": "2026-04-24T01:00:00+00:00", "finished_at": "2026-04-24T01:00:01+00:00", "status": "ok", "scanned_count": 10, "inserted_count": 3, "duplicate_count": 7, "skipped_count": 0, "early_stop_reason": null, "db_status": "ok", "error_summary": null}
```

필드: `job_type / query / started_at / finished_at / status(ok|warn|fail|skipped) / scanned_count / inserted_count / duplicate_count / skipped_count / early_stop_reason / db_status / error_summary`

#### search-status 추가 항목

`GET /api/v1/external/naver/search-status` 응답에 추가:

```json
{
  "recent_runs": [...],         // 최근 10건 요약 (최신순)
  "last_success_at": "...",     // 마지막 ok 실행 시각
  "last_warn_at": null,
  "last_fail_at": null
}
```

#### audit 확장 판정

`scripts/audit_naver_search_status.py` 에 추가된 판정:

| 조건 | 판정 |
|------|------|
| 실행 기록 없음 | WARN (NO_RECENT_RUNS) |
| 최근 실행이 모두 fail | WARN (RECENT_RUNS_ALL_FAIL) |
| state 있는데 실행 기록 없음 | WARN (STATE_EXISTS_BUT_NO_RUNS) |
| 실행 있는데 DB 누적 건수 0 | WARN (RUNS_EXIST_BUT_DB_EMPTY) |

#### 추후 확장 (다음 단계)

| 단계 | 범위 | 추가 보호 장치 |
|------|------|---------------|
| 6단계 | 결과 분석/요약 (LLM 사용 시) | 분석 입력의 PII 마스킹 + 호출량 제한 |
| 7단계 | Telegram/메일 알림 훅 실발송 | dry_run 우선 + 발송 화이트리스트 |
| 8단계 | 다른 검색 엔드포인트 (news 등) | 각 엔드포인트별 약관 검토 후 추가 |

---

## 8. 관련 파일

- `scripts/naver/shopping/naver_openapi_config.py` — env 설정
- `scripts/naver/shopping/naver_search_client.py` — GET-only 클라이언트
- `scripts/naver/shopping/naver_search_utils.py` — strip_html / 가격 / 날짜
- `ai_orchestrator/connectors/naver_blog/naver_blog_collectors.py` — 블로그 수집
- `scripts/naver/shopping/naver_shopping_collectors.py` — 쇼핑 수집
- `ai_orchestrator/connectors/naver_public_page_reader.py` — 공개 페이지 fallback
- `ai_orchestrator/connectors/naver_search/naver_search_jobs.py` — 저장 + Job 진입점
- `ai_orchestrator/tests/test_naver_openapi_collection.py` — 27 케이스
