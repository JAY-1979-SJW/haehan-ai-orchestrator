# Naver Cafe Adapter

네이버 카페 전용 SiteAdapter. 프레임워크(SessionManager / JobState / Runner) 전반 설명은
`docs/session_reauth_flow.md` 참고.

## 동작 범위 (이번 단계)

허용:
- `https://cafe.naver.com/` 진입 (읽기 전용)
- 특정 카페 / 게시판 1페이지 URL 로 이동
- 공개 게시글 목록 최소 필드 파싱: `post_id`, `title`, `author`, `date`, `url`

금지 (의도적 비구현):
- 아이디/비밀번호 자동 입력
- CAPTCHA/OTP/2차 인증 자동 처리
- anti-bot 우회, fingerprint 조작
- 본문/댓글/좋아요/멤버정보 수집
- 대량 스크래핑, 다중 페이지 루프
- 글쓰기/삭제/가입/댓글 등 변경 작업

## 세션 우선 정책

이 어댑터는 **세션 재사용이 주력**이다. Runner 흐름:

```
persistent 프로필 로드
       │
       ▼
open_home() ──▶ check_logged_in()
       │                │
       │        ┌───────┴────────┐
       │        ▼                ▼
       │   ACTIVE          EXPIRED / UNKNOWN
       │        │                │
       │  (work 즉시 실행)  open_login_page()
       │                         │
       │                   wait_for_human_reauth()
       │                         │
       │                   post_login_verify() 주기 확인
       │                         │
       │                    성공 시 ACTIVE 갱신
       ▼                         ▼
  JOB_DONE                 JOB 재개 (RUNNING)
```

**핵심 규약**: 세션이 ACTIVE 로 판정되면 `open_login_page` 는 호출하지 않는다.
어댑터에는 `perform_login` / `type_password` / `submit_otp` 등의 메서드가 **존재하지 않는다**
(`test_active_session_bypasses_any_login_input` 로 강제).

## 로그인 상태 판정 규칙

URL + DOM 조합. 쿠키 단독 판정 금지. 판정 우선순위 (먼저 일치하는 쪽이 이김):

1. **REAUTH_URL_HINTS** 일치 → `is_logged_in=False`, `reason="reauth_required"` (보수적)
   - `nid.naver.com/login2`, `/otp`, `/nidotp`, `/push/nidlogin_otp`,
     `/user2/help`, `/user2/verify`, `/user2/api/login_otp`,
     `/login/ext/device`, `/ivp`
2. **LOGIN_URL_HINTS** 일치 → `is_logged_in=False`, `reason="redirected_to_login"`
   - `nid.naver.com/nidlogin`, `/login?`, `/login/`
3. **LOGGED_IN_SELECTORS** 중 하나라도 존재 → `is_logged_in=True`,
   `reason="logged_in_signals_matched"`
   - `a#gnb_logout_button`, `a[href*='nid.naver.com/nidlogout']`,
     `#gnb_my_layer`, `.MyView-module__link_logout`
4. 아무 신호도 없음 → `is_logged_in=False`, `reason="no_user_menu"`

모든 힌트/셀렉터는 `NaverCafeAdapter` 클래스 상수로 분리 — 사이트 DOM 이 바뀌면 이 상수만 수정.

## 상태 코드

사용자/대시보드에 그대로 노출해도 안전한 라벨 (민감 원문 없음):

| 코드 | 의미 |
|------|------|
| `SESSION_ACTIVE` | 세션 유효, 작업 진행 중 |
| `SESSION_EXPIRED` | 세션 만료 감지 |
| `REAUTH_REQUIRED` | 2차 인증/추가 확인 필요 |
| `REAUTH_IN_PROGRESS` | 사람이 브라우저에서 로그인 작업 중 |
| `REAUTH_SUCCESS_RESUMING` | 재인증 성공, 작업 이어감 |
| `JOB_RESUMED` | `resume_job` 으로 복귀 완료 |
| `LOGIN_CHECK_FAILED` | 목록 접근 시점에 세션 미확인 |
| `LIST_PAGE_READY` | 목록 페이지 진입 완료 |
| `LIST_PARSE_OK` | 목록 파싱 성공 |

**금지 문구**: "비밀번호를 입력하세요", "OTP 를 전송합니다" 같은 자동 처리 암시.
**권장 문구**: "브라우저에서 직접 로그인/2차 인증을 완료한 뒤 돌아오세요."

## 목록 수집 범위

```python
result = adapter.collect_list(page, cursor="https://cafe.naver.com/<cafe_id>")
# result = {
#     "items": [
#         {"post_id": "101", "title": "...", "author": "...", "date": "...", "url": "..."},
#         ...
#     ],
#     "cursor": "<원래 cursor>",
#     "done": True,
#     "status": "LIST_PARSE_OK",
# }
```

- 세션이 ACTIVE 가 아니면 즉시 `done=False, status="LOGIN_CHECK_FAILED"` 로 반환 (빈 목록).
- 현대 라우팅(`/articles/<id>`) / 레거시 쿼리(`articleid=<id>`) 둘 다 `post_id` 추출 지원.
- 한 행 파싱이 실패하면 해당 행만 스킵 (전체 중단하지 않음).
- 파서 셀렉터는 상수로 분리 — 카페 스킨이 바뀌면 `ROW_SELECTOR`, `LINK_SELECTOR`,
  `AUTHOR_SELECTOR`, `DATE_SELECTOR` 만 조정.

## 사용 예시

```python
from playwright.sync_api import sync_playwright
from ai_orchestrator.sites.adapters.naver_cafe_adapter import NaverCafeAdapter
from ai_orchestrator.sites import session_manager, runner

adapter = NaverCafeAdapter()

with session_manager.open_persistent_context("naver_cafe", headless=False) as ctx:
    page = ctx.new_page()

    def work(p):
        res = adapter.collect_list(p, cursor="https://cafe.naver.com/<cafe_id>")
        if res["status"] != "LIST_PARSE_OK":
            raise runner.SessionExpiredMidJob(reason=res.get("reason", "blocked"))
        return f"collected={len(res['items'])}"

    msg = runner.run_with_session(
        adapter, page,
        job_id="naver-cafe-list-2026-04-23",
        site_id="naver_cafe",
        work=work,
        auto_reauth=True,          # 세션 만료 시 사용자 로그인 대기
        reauth_timeout_sec=300,    # 5분 이내 재인증 미완료면 PAUSED_FOR_REAUTH 보존
    )
    print(msg)   # "JOB_DONE" | "SESSION_EXPIRED_REAUTH_REQUIRED" | "REAUTH_TIMED_OUT"
```

재인증 타임아웃은 **실패가 아니다** — job 은 `PAUSED_FOR_REAUTH` 로 남아있고, 사용자가
브라우저에서 직접 로그인 완료한 뒤 아래로 재개한다:

```python
runner.resume_job(adapter, page, job_id="naver-cafe-list-2026-04-23", work=work)
```

## 로그/보안 규약

**남길 수 있음**:
- `site_id`, `job_id`, 상태 코드, `detected_url`, 짧은 reason 코드
- 매칭된 selector/hint 의 식별자 (값이 아닌 이름)

**절대 남기지 않음**:
- 비밀번호, OTP 코드, CAPTCHA 응답
- 쿠키/세션 토큰 원문, `Authorization` 헤더 원문
- 로그인 화면 HTML, 사용자 입력값
- 네이버 ID/닉네임 등 개인정보 원문 (테스트에서 `password` / `cookie` / `session=` /
  `token=` 패턴이 로그에 나타나지 않는지 강제 검증함)

## 운영 주의사항

- 브라우저 프로필은 `secrets/browser_profiles/naver_cafe/` 에 고정. 절대 커밋하지 말 것
  (`.gitignore` 에 이미 반영됨).
- persistent context 는 반드시 `session_manager.open_persistent_context("naver_cafe")`
  로만 연다. 매 실행 신규 익명 브라우저 금지.
- 네이버 정책(ToS/로봇 정책)을 준수해야 하므로 이 어댑터로 **대량 수집/자동화 회원가입/
  자동 글쓰기** 등을 시도하지 말 것. 이 단계에서 구현되어 있지 않으며 앞으로도 추가하지 않는다.
- 2차 인증 흐름이 자주 뜨는 계정은 `default_reauth_timeout_sec` (기본 300s) 를 사용자가
  넉넉히 둘 것. 타임아웃은 실패가 아니므로 `resume_job` 으로 이어서 마무리 가능.
- 이 어댑터는 네이버 메인 계정용 자격증명을 **저장하지도, 전송하지도 않는다**. 시크릿
  디렉터리(`secrets/sites/naver_cafe.env`)에 아이디/비밀번호를 넣어도 어댑터가 읽지 않는다.

## 이번 단계에서 제외된 것

- 아이디/비밀번호 env 기반 자동 로그인 (의도적 비구현, 추후 단계에서도 보수적 검토)
- 2차 인증/CAPTCHA 자동화
- 카페 다중 페이지 수집, 상세 본문 수집
- 카페 글쓰기/삭제/가입
- 카페별 맞춤 셀렉터 프로파일 시스템 (현재는 표준 게시판 기준 상수 1세트)

## 관련 테스트

- `ai_orchestrator/tests/test_naver_cafe_adapter.py` — 19개 테스트
  - 로그인/재인증/애매 케이스 판정
  - 쿠키 단독 판정 거부
  - 세션 ACTIVE 시 로그인 페이지 진입 안 함 + 자동 로그인 메서드 부재 강제
  - PAUSED → resume 경로
  - 재인증 타임아웃 시 FAIL 아님 (PAUSED 보존, 나중에 resume 성공)
  - 목록 파싱 (현대 + 레거시 라우팅)
  - 민감정보 로그 패턴 미노출
