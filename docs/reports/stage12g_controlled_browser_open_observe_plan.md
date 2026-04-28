# Stage 12G controlled browser open/observe dry-run plan

## 1. 목적

실제 local-agent / 브라우저 실행 전, controlled browser open/observe dry-run의
허용 범위와 차단 조건을 사전 정의한다. 이 문서는 설계 단계이며 실제 실행은 별도 승인 후 진행한다.

기 구현 확인:
- `local_agent/browser_reader.py::open_url_readonly` — title/url/html 만 수집 후 종료
- `local_agent/actions.py::action_web_open_url_readonly` — 클릭/입력/제출/다운로드 금지
- `local_agent/actions.py::action_open_url` — http(s)만 허용, file://, javascript:, data: 차단
- `local_agent/browser_login_probe.py::_observe` — read-only 관찰(`page.url` / `page.title` / `page.content` 만)

---

## 2. 현재 기준

| 항목 | 상태 | 판정 |
|---|---|---|
| approval UI | admin-web에 approve/reject 추가 (Stage 12B/12C) | PASS |
| approval fixture | 28 passed (Stage 12E) | PASS |
| noexec smoke | Total 39 / PASS 37 / WARN 2 / FAIL 0 | WARN exit 0 |
| 실제 local-agent 실행 | 미수행 | PASS |
| 실제 브라우저 실행 | 미수행 | PASS |

origin/master 최신: `bc0d067`

---

## 3. 첫 실행 허용 범위

| 항목 | 허용 여부 | 기준 |
|---|---:|---|
| `about:blank` open | 허용 | risk=low, 외부 통신 없음 |
| 내부 테스트 페이지 open | 조건부 허용 | localhost/repo 내 정적 페이지에 한해, 12H 이후 단계에서 별도 승인 후 |
| 외부 사이트 open | **금지** | 첫 단계에서는 외부 URL 차단 |
| title / url 관찰 | 허용 | `page.title()`, `page.url` property 만 |
| screenshot | **금지** (dry_run only) | `_capture_screenshot_dry_run` 경로 외 실 캡처 금지 |
| DOM 입력 (`fill`) | **금지** | 입력은 첫 실행 범위 밖 |
| 클릭 (`click`) | **금지** | 사용자 행동 모방 금지 |
| 로그인 | **금지** | credentials 사용 금지 |
| POST/PUT/PATCH/DELETE | **금지** | navigation 외 mutation 금지 |
| 파일 다운로드/업로드 | **금지** | 디스크 변경 금지 |
| 쿠키/session/token 읽기 | **금지** | secret 노출 위험 |

---

## 4. 수집 가능 결과와 금지 결과

| 구분 | 항목 | 판정 |
|---|---|---|
| 허용 | `final_url` (navigation 후 최종 URL) | 허용 |
| 허용 | `title` (≤300자 truncate) | 허용 |
| 허용 | `status_category` (예: ok / blocked / error) | 허용 |
| 허용 | `pages_observed_count` | 허용 |
| 허용 | `error_category` (네트워크/타임아웃 등 분류 명) | 허용 |
| 허용 | `timestamp` (ISO8601) | 허용 |
| 허용 | `audit_event_id` | 허용 |
| 금지 | cookie / session / `document.cookie` | BLOCK |
| 금지 | Authorization header (요청·응답 모두) | BLOCK |
| 금지 | password input value / hidden token field | BLOCK |
| 금지 | localStorage / sessionStorage 내용 | BLOCK |
| 금지 | 개인정보가 담긴 화면 본문 (이름/주민/계좌/카드) | BLOCK |
| 금지 | 로그인 세션 식별자 (JSESSIONID, JWT 등) | BLOCK |

---

## 5. audit event 기준

첫 실제 실행 전후 반드시 기록할 audit event:

| 이벤트 | 목적 |
|---|---|
| `browser_open_requested` | 사용자/오케스트레이터가 open 요청한 시점 기록 |
| `browser_open_dry_run_checked` | dry_run 플래그·정책 게이트 통과 여부 확인 |
| `browser_open_started` | 브라우저 프로세스 기동 직전 (URL 정규화 후) |
| `browser_open_observed` | title/url/status 관찰 결과 1회 기록 |
| `browser_open_completed` | 브라우저 정상 종료 (수집 결과 회수 완료) |
| `browser_open_blocked` | 정책/allowlist/risk gate에 의해 차단 |
| `browser_open_failed` | 실행 중 예외/타임아웃 |

기록 위치: 기존 `audit_logger.log_event` 경로 사용 권장 (별도 audit 채널 신설 금지).
이벤트명은 기존 `LOCAL_AGENT_TASK_*` 네이밍과 정합되게 prefix 통일을 12H 단계에서 결정.

---

## 6. 차단 조건

| 조건 | 판정 |
|---|---|
| URL이 allowlist 밖 (외부 도메인 / file:// / javascript: / data:) | BLOCK |
| action risk가 medium / high / critical | BLOCK |
| `dry_run=false` 인데 approval 토큰 없음 | BLOCK |
| 로그인 페이지로 navigation (URL 패턴 또는 password input 감지) | BLOCK |
| cookie / session / token 접근 시도 (eval, evaluate, document.cookie) | BLOCK |
| POST / PUT / PATCH / DELETE 발생 가능성 (form submit, fetch, XHR) | BLOCK |
| 입력/클릭이 필요한 흐름 (fill, click, press) | BLOCK |
| 파일 업로드/다운로드 가능성 (`accept_downloads`, file chooser) | BLOCK |
| 결제/송금/삭제/가입/댓글/권한 변경 액션 | BLOCK |
| policy gate 결과가 불명확 / 검증되지 않은 사이트 | BLOCK |
| audit log 기록 불가 (디스크 풀, 권한 부재) | BLOCK |

---

## 7. 다음 단계 제안

권장 순서 (먼저 fixture, 그 다음 실제 smoke):

1. **Stage 12H** — browser open/observe **fixture 테스트 보강**
   - `web_open_url_readonly`, `open_url_readonly` 의 정책/차단/관찰 결과 fixture 검증
   - 실제 브라우저 미기동, monkeypatch / mock page 사용
2. **Stage 12I** — `about:blank` controlled open/observe **실제 smoke**
   - 단일 호출, 외부 통신 없음, audit event 7종 기록 확인
3. **Stage 12J** — 내부 테스트 URL (localhost / 정적 파일) controlled open/observe smoke
   - 12I 통과 후, 별도 대표님 승인 게이트

---

## 8. 금지 작업 준수 확인

- 코드 수정: 없음
- 테스트 수정: 없음
- 서버 접속: 없음
- docker 실행: 없음
- local-agent 실행: 없음
- 브라우저 실행: 없음
- 실제 POST: 없음
- 다른 앱 접근: 없음
- secret 출력: 없음

---

## 9. 최종 판정

**PASS**

설계 문서로서 허용 범위·차단 조건·audit 기준·다음 단계 순서를 명시하였다.
실제 실행은 12H(fixture) → 12I(about:blank smoke) → 12J(internal URL smoke) 순으로
승인 게이트를 통과해야 진행한다.
