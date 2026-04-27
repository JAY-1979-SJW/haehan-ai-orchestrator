# Naver Cafe — 특정 게시판 증분 수집 (1단계)

`NaverCafeAdapter` 위에 얇게 얹은 증분 수집 계층(`naver_cafe_collection.py`).
공식 카페 화면을 사람이 직접 로그인한 세션으로만 읽고, 1페이지의 공개 목록
필드만 누적 저장한다. 본문/댓글/대량 순회는 모두 의도적으로 제외했다.

---

## 1. 사용 방법

### 1-1. 환경 설정

`.env` 또는 환경변수에 카페/게시판 ID 를 주입한다 (실제 값은 커밋 금지):

```bash
NAVER_CAFE_CLUB_ID=<카페ID(숫자)>
NAVER_CAFE_MENU_ID=<게시판ID(숫자)>
# 저장 파일 경로 override (선택). 기본은 <repo>/data/naver_cafe_posts.json
NAVER_CAFE_STORE_PATH=
```

`naver_cafe_collection.NAVER_CAFE_TARGET` 가 모듈 import 시점에 위 환경변수를
읽는다. 테스트/스크립트에서는 `run_naver_cafe_collect_job(..., club_id=, menu_id=)`
인자로 직접 주입할 수도 있다.

### 1-2. 1회 실행 (예시 코드)

```python
from ai_orchestrator.sites import session_manager
from ai_orchestrator.sites.adapters.naver_cafe_adapter import NaverCafeAdapter
from ai_orchestrator.sites.adapters import naver_cafe_collection as nc

adapter = NaverCafeAdapter()
with session_manager.open_persistent_context("naver_cafe", headless=False) as ctx:
    page = ctx.new_page()
    msg = nc.run_naver_cafe_collect_job(
        adapter, page,
        job_id="nc-2026-04-23-1",
        club_id="...",      # 또는 NAVER_CAFE_TARGET 사용
        menu_id="...",
        page_num=1,
        max_pages=1,        # 1페이지로 제한 (대량 스크래핑 금지)
        auto_reauth=True,
    )
print(msg)  # JOB_DONE / SESSION_EXPIRED_REAUTH_REQUIRED / REAUTH_TIMED_OUT 등
```

세션이 만료되어 일시정지된 작업은 사람이 브라우저에서 로그인을 끝낸 뒤
`runner.resume_job(adapter, page, job_id=..., work=...)` 로 재개한다.

---

## 2. 세션 재사용 방식

- `session_manager.open_persistent_context("naver_cafe")` 가 사이트 전용
  user data dir(`secrets/browser_profiles/naver_cafe/`)을 사용한다.
- 매 실행 신규 컨텍스트가 아닌 **persistent profile** 이므로 한 번 사람이
  로그인하면 다음 실행에서도 쿠키/스토리지가 유지된다.
- 세션 메타데이터(`secrets/browser_state/naver_cafe.meta.json`)에 ACTIVE /
  EXPIRED / REAUTH_REQUIRED / UNKNOWN 만 기록한다 (쿠키/토큰 원문 금지).

---

## 3. 재인증 흐름 (PAUSED → RESUMABLE → DONE)

1. `run_naver_cafe_collect_job` 호출 → `runner.run_with_session` 진입.
2. `adapter.open_home(page)` + `check_logged_in(page)` 로 URL/DOM 신호 검사.
3. 로그인 신호가 없거나 nid 로그인/2차 인증 페이지로 튕기면:
   - `session_manager.mark_reauth_required(...)` 으로 메타 업데이트.
   - `auto_reauth=True` 면 로그인 페이지를 열고 사람이 끝낼 때까지 대기
     (`wait_for_human_reauth`, 기본 300초).
   - `auto_reauth=False` 면 즉시 `PAUSED_FOR_REAUTH` 로 보존.
4. 작업 도중 세션이 만료되면 collection 계층이
   `runner.SessionExpiredMidJob` 을 raise → runner 가 다시 PAUSED 처리.
5. 사람이 로그인 완료 후 `runner.resume_job(...)` 으로 재개 → ACTIVE 면 RUNNING
   → DONE.

자동 입력 금지 원칙:
- 비밀번호/OTP/CAPTCHA 자동 처리 없음.
- 로그인 페이지로 이동만 한다 (`adapter.open_login_page`).

---

## 4. 수집 범위 (목록 only)

수집 항목 (1페이지, 게시글당 5개 필드):

| 필드 | 출처 |
|------|------|
| `post_id` | `/articles/<id>` 또는 `articleid=<id>` 에서 추출 |
| `title` | `a.article` 의 inner text |
| `author` | `td.td_name a` / `td.p-nick a` |
| `created_at` | `td.td_date` (어댑터 내부 키 `date` → 저장 시 매핑) |
| `url` | 게시글 절대 URL (본문 진입은 안 함) |

URL 빌더(`build_board_url`)는 ArticleList 레거시 라우팅을 사용한다:

```
https://cafe.naver.com/ArticleList.nhn?
  search.clubid=<club_id>&search.menuid=<menu_id>&search.boardtype=L&search.page=<n>
```

---

## 5. 증분 수집 방식

```
load_stored(path)         # 기존 JSON 로드 (없으면 빈 레코드)
existing = existing_ids(record)
collect_new_posts(adapter, page, existing, club_id=, menu_id=, page_num=1, max_pages=1)
  └─ adapter.collect_list(...)  # 1페이지만 읽음
  └─ filter_new_posts(items, existing)
        ├─ post_id 정규화 (date → created_at 매핑 포함)
        ├─ existing 에 이미 있으면 skip
        ├─ 같은 호출 내 중복도 skip
        └─ 빈 post_id skip
merge_record(record, new_posts, club_id=, menu_id=)
  └─ post_id 키 dict 로 last-wins 병합 (중복 자동 제거)
save_stored(path, merged)  # atomic replace (.tmp → rename)
```

저장 구조:

```json
{
  "site": "naver_cafe",
  "club_id": "...",
  "menu_id": "...",
  "posts": [
    {"post_id": "101", "title": "...", "author": "...",
     "created_at": "2026.04.23.", "url": "..."}
  ]
}
```

상태 코드 (응답/로그):
- `NAVER_CAFE_COLLECTED` — 신규 글 1건 이상
- `NAVER_CAFE_NO_NEW` — 모두 기존에 있음
- `NAVER_CAFE_BLOCKED_NOT_LOGGED_IN` — 로그인 신호 없음 → 세션 재인증 흐름으로 위임

---

## 6. 제한 사항

- **1페이지 한정** — `DEFAULT_MAX_PAGES=1`, `HARD_MAX_PAGES=5` 안전 상한
  (현재 호출은 어차피 1페이지만 순회하지만, 미래 확장 시에도 5페이지 초과
  요청은 잘라낸다).
- **본문/댓글/이미지/첨부 미수집** — 외부 정책 위반/대량 트래픽 방지.
- **로그인 자동 입력/CAPTCHA/OTP 자동 처리 금지** — 어댑터에 함수 자체가 없다.
- **공개 목록 외 비공개/회원 전용 게시판은 보장 안 함** — 권한이 없으면 빈
  목록으로 종료. 권한 우회 로직 없음.
- **사이트 약관/robots 준수 책임은 운영자에게 있다** — 본 모듈은 1페이지·읽기
  전용·증분 호출이라는 최소 시나리오만 전제한다.

---

## 7. 관련 파일

- `ai_orchestrator/sites/adapters/naver_cafe_adapter.py` — 어댑터 (변경 최소: `page_num`/`max_pages` 인자 추가)
- `ai_orchestrator/sites/adapters/naver_cafe_collection.py` — 증분 수집 / 저장 / Runner 연동
- `ai_orchestrator/sites/session_manager.py` — 세션 메타/persistent context
- `ai_orchestrator/sites/runner.py` — `run_with_session` / `resume_job`
- `ai_orchestrator/tests/test_naver_cafe_collection.py` — 11 케이스
