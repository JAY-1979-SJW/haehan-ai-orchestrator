# 수동 로그인 smoke 운영 정책 (Manual Login Smoke Policy)

본 문서는 `scripts/smoke_*_manual_login_probe.py` 계열 **수동 로그인 smoke**
의 운영 원칙과 판정 기준을 고정한다. 코드는 별도 파일에서 관리되지만,
**"어떤 smoke 결과가 PASS 인가"** 에 대한 단일 근거(single source of truth)
는 본 문서다.

관련 구현 / 정책 문서:

- [로컬 에이전트 아키텍처](./local_agent_architecture.md)
- [로컬 에이전트 — 화면 캡처 운영 정책](./local_agent_capture_policy.md)
- [웹 자동화 표준](./web_automation_standard.md)

---

## 1. 목적

- 네이버 / 유튜브 / Google Workspace 등 **사용자 크리덴셜로만 로그인
  가능한** 서비스에 대해, 로컬 에이전트가 **이후 단계의 read-only 관찰
  작업을 시작하기 위한 선결 조건** — 즉, "사용자가 직접 로그인한 브라우저
  창이 실제로 떠 있고 로그인에 성공했다" — 을 운영자가 확인할 수 있게
  한다.
- smoke 자체는 **로그인을 자동화하지 않는다**. smoke 는 오직 브라우저를
  띄우고 read-only 로 관찰하며, "로그인 완료로 보이는지" 에 대한 힌트만
  돌려준다.
- 어떤 경우에도 운영 파이프라인이 smoke 결과를 근거로 **자동 로그인을
  재현하거나 세션을 재사용**해서는 안 된다.

---

## 2. 수동 로그인 smoke 원칙

아래 원칙은 모든 `*_manual_login_probe` 스크립트 / `probe_manual_login_flow`
호출에 예외 없이 적용된다.

### 2.1 절대 수행하지 않는 것 (금지)

| 범주 | 구체적으로 금지 |
|------|-----------------|
| ID / PW 자동 입력 | `page.fill / page.type / page.press / keyboard.*` |
| 클릭·제출·파일 업로드 | `page.click / page.select_option / page.set_input_files` |
| 자바스크립트 주입 | `page.evaluate / page.evaluate_handle` |
| 쿠키 / 세션 수집 | `storage_state / context.cookies / localStorage / sessionStorage / add_cookies` |
| 스크린샷 저장 | `page.screenshot / pdf` |
| 민감값 수집 | password input value / hidden input value 보유 금지 (`web_reader` 가 이미 drop) |
| 우회 자동화 배포 | anti-automation args (예: `ignore_default_args=['--enable-automation']`) 를 **운영 probe 기본값에 넣지 않는다**. 실험/검증 용도의 로컬 실행에 한정. |

### 2.2 허용되는 것

- `page.goto` (URL validation 통과분만)
- `page.title() / page.url / page.content()` read-only 관찰
- `page.bring_to_front()` (best-effort — 창을 사용자 앞으로 끌어올리기)
- `wait_until` / `timeout` / `viewport` / `slow_mo_ms` 파라미터
- 사용자 입력 (`input()`) 으로 시각 확인 / 로그인 완료 / 종료 시점 확정

### 2.3 결과 필드 (고정 스키마)

`probe_manual_login_flow` 는 아래 필드를 **항상** 반환한다.

```json
{
  "ok": false,
  "mode": "manual_login_probe",
  "url": "...",
  "visible_confirmed_by_user": false,
  "login_confirmed_by_user": false,
  "login_state_hint": "manual_login_completed | already_logged_in_or_public_page | login_required | unknown",
  "login_completed_hint": false,
  "login_completion_reason": ["..."],
  "initial": { "...": "..." },
  "last_observation": { "...": "..." }
}
```

`ok=True` 는 **항상** `login_completed_hint=True` 와 동치다. 그 외 모든
결과는 `ok=False` 이며, 세부 구분은 `error_code` / `login_state_hint` 로
판별한다.

---

## 3. YouTube smoke 결과 (2026-04-25 1회차)

### 3.1 실행 요약

| 항목 | 값 |
|------|----|
| 실행일 | 2026-04-25 |
| 대상 URL | `https://www.youtube.com` |
| 브라우저 | Google Chrome 정식 채널 (Playwright `channel="chrome"`) |
| 실행 환경 | 관리자 로컬 Windows PC (운영 서버 아님) |
| 사용자 가시성 | **표시 확인됨** — 관리자 화면에 Chrome 창이 실제로 보였음 |
| 수동 로그인 | **성공** — 관리자가 직접 Google 계정 로그인 수행 |
| 유지 시간 | 600 초 (10분) 후 자연 종료 |

### 3.2 확정된 사실 (운영 문서화 대상)

- 실제 Chrome 창이 사용자 화면에 **표시되었다**.
- 관리자가 **직접** Google 계정 로그인을 완료했다.
- probe / 실험 스크립트는 **ID / PW 를 입력하지 않았다**.
- **쿠키 / 세션 / token 수집이 발생하지 않았다** (`new_context()` 기반
  ephemeral context, `storage_state` / `cookies()` 미호출).
- 자동 **클릭 / 입력 / 제출이 발생하지 않았다**.
- 최종 URL 은 `https://www.youtube.com/` (초기 URL 과 동일).

### 3.3 Google 자동화 차단과 임시 우회 (운영 반영 금지)

초기 실행 시 Playwright 기본 Chromium 에서 Google 계정 로그인 단계가
`"로그인할 수 없음. 브라우저 또는 앱이 안전하지 않을 수 있습니다."`
메시지로 차단되었다. 다음 3종 옵션 조합으로 **실험 환경에서만** 우회가
확인되었다.

```
channel='chrome'
ignore_default_args=['--enable-automation']
args=['--disable-blink-features=AutomationControlled']
```

**정책**: 이 조합은 **운영 probe 기본값에 포함하지 않는다**. 이유는 다음과
같다.

- Google 은 자동화 탐지 패턴을 주기적으로 변경하므로, 우회 args 를
  운영에 박아두면 다음 변경에서 silently 실패로 돌아갈 수 있다.
- "우회" 라는 성격 자체가 본 smoke 의 목적 (사용자가 스스로 로그인한
  것을 확인) 과 상충한다. 우회는 검증 / 디버깅 목적의 일회성 실험에
  한해 허용한다.

---

## 4. YouTube URL 기반 판정의 한계

### 4.1 관찰된 현상

YouTube 홈 (`https://www.youtube.com/`) 은 **로그인 전후 URL 이 동일**
하다. 로그인 상태 전환이 URL 이 아닌 클라이언트 사이드 상태 / 아바타
UI 로만 표현되기 때문이다.

따라서 다음 두 시나리오는 probe 의 구조 기반 자동 감지만으로는 **구분
되지 않는다**.

| 시나리오 | 초기 URL | 초기 password input | 완료 감지 가능? |
|---------|----------|-------------------|----------------|
| A. 이미 로그인된 유튜브 홈 | youtube.com | 없음 | **감지 불가** (변화 없음) |
| B. 비로그인 상태에서 홈 → 수동 로그인 후 홈으로 복귀 | youtube.com | 없음 | **감지 불가** (URL/구조 변화 없음) |
| C. accounts.google.com 로그인 페이지에서 시작 → youtube.com 리다이렉트 | accounts.google.com | 있음 | 감지 가능 (`url_changed` + `password_input_disappeared`) |

### 4.2 `success_url_match:youtube.com` 단독 판정 금지 (정책)

- 초기 URL 이 이미 `youtube.com` 을 포함하는 경우, `success_url_match`
  는 **애초에 완료 근거로 추가되지 않는다** (`probe_manual_login_flow`
  의 `_detect_completion` 구현 보강으로 2026-04-24 확정).
- 따라서 `login_completion_reason=["success_url_match:youtube.com"]`
  **만** 으로 `login_completed_hint=True` 가 되는 경로는 **존재하지
  않는다**.
- YouTube 계열 smoke 에서는 이 한계를 인정하고, **사용자 확인** 또는
  **강한 구조 근거** 중 하나를 반드시 요구한다 (§5 참조).

### 4.3 이미 로그인 / 공개 페이지 상태 구분

초기 관찰에서 ① password input 없음 ② `login_required_hint=false` ③
URL 이 `accounts.google.com` 이 아님 ④ URL 이 `success_url_contains`
토큰 중 하나를 포함함 — 4 조건을 모두 만족하면 probe 는 다음과 같이
보고한다.

```
login_state_hint = "already_logged_in_or_public_page"
login_completed_hint = false
error_code = "LOGIN_NOT_CONFIRMED"
```

이 상태는 **PASS 가 아니라 WARN** 으로 취급한다. 운영자는
`--require-user-login-confirm` 으로 사용자 Enter 를 받아 `ok=True` 로
승격하거나, 정말로 "이미 로그인된 상태" 였는지 별도로 판단한다.

---

## 5. 사용자 확인 기반 PASS 기준

### 5.1 YouTube 계열 smoke (YouTube 홈 / Studio / Google Workspace 진입)

다음 두 옵션을 **필수** 로 사용한다.

```
python scripts/smoke_youtube_manual_login_probe.py \
  --require-visible-confirm \
  --require-user-login-confirm
```

| 옵션 | 의미 | 필수? |
|------|------|-------|
| `--require-visible-confirm` | 브라우저 창이 실제 화면에 보인다고 사용자가 Enter 로 확인하기 전까지 관찰 루프 진입 금지. 가시성 검증이 이전 smoke 에서 누락됐던 문제를 봉쇄. | **필수** |
| `--require-user-login-confirm` | 구조적 근거만으로 `login_completed_hint=True` 를 단정하지 않음. 사용자가 Enter 로 로그인 완료를 확인해야만 승격. `reason` 에 `user_confirmed_login` 이 기록된다. | **필수** |
| `--keep-open` | 판정 종료 후 사용자가 Enter 를 누를 때까지 브라우저를 유지. 종료 시점 제어를 사용자에게 이양. | 권장 |
| `--browser-channel` | `chromium`(기본) / `chrome` / `msedge`. 사용자가 실제로 "봤다" 고 확인할 창의 정체성을 고정. | 권장 (운영자 PC 에 설치된 것 기준) |

### 5.2 PASS / WARN / FAIL 판정

| 판정 | 조건 |
|------|------|
| **PASS** | `ok=True` **그리고** `visible_confirmed_by_user=True` **그리고** `login_confirmed_by_user=True` **그리고** `login_state_hint="manual_login_completed"` **그리고** `login_completion_reason` 에 `user_confirmed_login` 포함 |
| **WARN** | `login_state_hint="already_logged_in_or_public_page"` (이미 로그인 / 공개 페이지로 시작됐고 사용자 확인이 없었음) — smoke 실패가 아니라 **해석이 필요한 상태**. 운영자가 컨텍스트 보고 다시 실행. |
| **FAIL** | 그 외. 대표 사례: `error_code=VISIBILITY_NOT_CONFIRMED` / `LOGIN_TIMEOUT` / `HOST_NOT_ALLOWED` / `URL_*` / `BROWSER_DEPENDENCY_MISSING` / `BROWSER_CHANNEL_INVALID` |

### 5.3 "success_url_match 단독" 은 판정 근거가 아니다 (재확인)

- `login_completion_reason` 에 **`success_url_match:` 접두 근거만 있는
  경우**, `login_completed_hint` 는 `True` 가 될 수 없다 (구현상 초기
  URL 이 이미 매칭하면 reason 조차 추가되지 않는다).
- 운영 리뷰 시 `success_url_match:` 하나만 남은 결과를 PASS 로
  올리는 것은 **정책 위반**이다.

---

## 6. 금지 사항 (재확인)

본 smoke 를 계기로 아래가 한 번 더 확정된다.

- **자동 로그인 금지** — smoke / 운영 어느 경로에서도 ID / PW 를 프로그램
  으로 입력하지 않는다.
- **ID / PW 저장 금지** — 스크립트 / 프로덕션 코드 / 테스트 어디에도
  하드코딩된 계정 토큰이 존재하면 안 된다. 이미 test 에서 `NAVER_ID
  / NAVER_PW / YOUTUBE_ID / YOUTUBE_PW / GOOGLE_ID / GOOGLE_PW / sk-`
  등을 하드 금칙어로 검증한다.
- **쿠키 / 세션 / token 수집 금지** — `storage_state` / `context.cookies`
  / `localStorage` / `sessionStorage` / `add_cookies` 를 호출하지 않는다.
- **클릭 / 입력 / 제출 / 파일 업로드 금지** — §2.1.
- **우회 / 스텔스 목적 옵션의 운영 반영 금지** — §3.3.
- **실제 서비스 데이터 변경 금지** — 댓글 / 좋아요 / 구독 / 업로드 /
  설정 변경 일체.

위반은 smoke 실패 이전에 **정책 위반**으로 분류한다 (즉, 결과값이 무엇이든
PASS 로 해석할 수 없다).

---

## 7. 다음 단계: YouTube Studio smoke

YouTube 홈 smoke 가 PASS 판정된 뒤에만 다음 단계로 진행한다.

| 항목 | 계획 |
|------|------|
| 대상 URL | `https://studio.youtube.com/` |
| 실행 시점 | 홈 smoke PASS 확정 뒤 **별도 세션**으로 실행 (같은 호출에 묶지 않는다) |
| 필수 옵션 | `--require-visible-confirm` + `--require-user-login-confirm` (§5.1) |
| 추가 판정 힌트 | Studio 진입 후 나타나는 특정 텍스트 (예: `"채널 대시보드"`, `"콘텐츠"`, `"분석"`) 를 `--success-text-hints` 로 전달 가능. 단, **계정명 / 채널명 / 이메일은 힌트로 사용하지 않는다**. |
| 운영 반영 | Studio smoke 결과가 PASS 로 반복 확인될 때까지 운영 파이프라인의 Studio 경로 자동화는 보류한다. |
| Google 자동화 차단 | §3.3 과 동일하게 취급. 우회 args 는 실험 세션에만 한정. |

Studio smoke 1회차 (2026-04-25) 는 **사용자 확인 기준 PASS** 로 종결되었으며,
측정 보완 정책은 §8 참조. 2회차 이후 반복 실행 대상.

---

## 8. 다중 탭 관찰 정책 및 HITL 우선 판정 (measurement gap 보완)

### 8.1 관찰된 현상 (2026-04-25 Studio smoke)

`https://studio.youtube.com/` 에 대한 수동 smoke 에서 다음 불일치가 관측되었다.

| 항목 | 값 |
|------|----|
| `browser_visible_confirmed_by_user` | `True` |
| `studio_confirmed_by_user` (user "접속되었어") | `True` |
| 스크립트가 관측한 `final_url_host_path` | `accounts.google.com/v3/signin/identifier` |
| `final_title_category` | `youtube-studio` |
| `observed_studio_youtube` (단일 page 기준) | `False` |

사용자 확인과 스크립트 관측이 불일치. 사용자 ground truth 는 "Studio 진입 성공".

### 8.2 원인

- Google sign-in flow 는 `window.open` / `target="_blank"` / post-auth redirect 로
  **Studio 를 별도 탭/팝업에서 열 수 있다.**
- 기존 `probe_manual_login_flow` 는 `context.new_page()` 로 만든 **단일 `page`
  객체** 만 추적하므로, 새 탭에서 Studio 가 열리면 관측하지 못한다.
- 30 초 polling 간격 안에 redirect chain 이 통과하면 중간 상태만 기록될 수 있다.

### 8.3 측정 보완 정책 (신규)

운영 probe 에서 다음을 적용한다.

1. **다중 탭 추적 (ideal)**: Playwright 컨텍스트 생성 직후 `context.on("page",
   handler)` 를 등록해 신규 탭/팝업을 실시간으로 리스트에 append. 현재 운영
   코드에서는 test fake 호환을 위해 이 경로를 아직 도입하지 않고, 아래
   context.pages 전수 스캔 방식으로 **동등한 최종 판정 결과** 를 얻는다.
2. **context.pages 전수 스캔 (운영 적용)**: 관찰 종료 시점에 `context.pages`
   를 전수 순회해 **모든 탭/팝업의 URL / title** 을 read-only 로 수집.
3. **집계 기준**: 아래 중 하나라도 만족하면 `success_url_observed_across_pages
   =True` 로 기록.
   - 어떤 page 의 URL 이 `success_url_contains` 토큰 포함
   - 어떤 page 의 title 카테고리가 `youtube-studio` 등 대상 서비스와 일치
4. **polling 간격 정책**: 기본 30 초. Studio / Google 로그인 flow 처럼
   redirect chain 이 빠른 서비스에선 10 초까지 허용 (`--poll-interval-seconds
   10`). 1 초 미만은 과도한 관찰로 보고 금지.
5. **page 당 허용 API**: `page.url` / `page.title()` / `bring_to_front()`
   (필요 시). **금지**: `click / fill / type / press / keyboard / cookies() /
   storage_state / localStorage / sessionStorage / page.content()`.

### 8.4 HITL (human-in-the-loop) 우선 판정

- `login_confirmed_by_user` (= `user_confirmed_by_user`) 가 **최종 판정의
  primary evidence** 이다. 스크립트 관측은 secondary evidence.
- 조합별 판정:

  | `user_confirmed_by_user` | `success_url_observed_across_pages` (script) | 판정 |
  |---|---|---|
  | `True` | `True` | **PASS** (양쪽 합치) |
  | `True` | `False` | **PASS with measurement caveat** (사용자 근거 우선, caveat 기록; FAIL 아님) |
  | `False` | `True` | **WARN** — 구조 근거만으로 자동 단정 금지 (§4.2, §5.3 과 정합) |
  | `False` | `False` | **WARN / FAIL** — 실제 실패 혹은 사용자 미확인 |

- "PASS with measurement caveat" 케이스는 결과에 `login_completion_reason`
  에 `user_confirmed_login` 을 포함하고, `warnings` 에 `"script_observed_
  without_target_url"` 같은 문자열을 남겨 후속 분석이 가능하게 한다.

### 8.5 금지 재확인 (본 보완에서도 유지)

다음 API 는 운영 probe 코드 / smoke 스크립트 / test fake 의 `_FORBIDDEN
_METHODS` 에 동일하게 차단된다.

- `click`, `fill`, `type`, `press`, `select_option`, `set_input_files`
- `keyboard`, `mouse`, `touchscreen`
- `evaluate`, `evaluate_handle`, `screenshot`, `pdf`
- `cookies`, `storage_state`, `add_cookies`, `localStorage`, `sessionStorage`
- `page.content()` 를 통한 HTML 원문 전체 저장 (구조 요약은 `web_reader` 가
  이미 민감 토큰 drop 후 반환)

다중 탭 관찰은 **read-only** — 각 탭에서 오직 URL / title / (필요 시
bring_to_front) 만 호출한다.

---

## 9. F-2 — Google / YouTube open-only 정책

### 9.1 정책 (요약)

- 다음 도메인 (및 그 서브도메인) 은 **Playwright visible probe 대상에서
  제외** 된다.

  ```
  accounts.google.com
  google.com
  studio.youtube.com
  youtube.com
  gmail.com
  drive.google.com
  ```

- 위 도메인의 visible 세션 확보는 **`open_local_browser` (subprocess
  Popen) 만 사용** 한다. `probe_visible_browser` /
  `probe_manual_login_flow` 등 Playwright 기반 경로로는 띄우지 않는다.
- Google API 작업은 본 probe / launcher 와 무관하게 **별도 OAuth /
  API connector** 로 처리한다 (예정).

### 9.2 사이트 정책 분류 토큰

호출자 / 감사 로그 / 문서에서 일관된 라벨로 쓰기 위해
`local_agent.browser_launcher` 가 다음 토큰을 노출한다.

| 토큰 | 의미 |
|------|------|
| `generic` | 분류 미정 / 기본값 |
| `public_fetch` | 로그인 없이 fetch 가능한 공개 페이지 |
| `google_open_only` | Google 계열, open_local_browser 만 허용 |
| `youtube_open_only` | YouTube 계열, open_local_browser 만 허용 |
| `local_probe_allowed` | 사용자 PC visible probe 허용 |

본 단계 (F-2) 에서는 분류만 도입하며, provider 우선순위 분기에는
직접 사용하지 않는다.

### 9.3 probe 차단 동작

- `probe_visible_browser(url)` 가 위 도메인을 받으면 Playwright launch
  **이전** 단계에서 거절한다.
- 결과 dict:
  - `success=False`
  - `error_code="GOOGLE_OPEN_ONLY"`
  - `warnings=["google_open_only_use_open_local_browser"]`
  - `target_url=""` (raw 입력 토큰 미노출)
  - `final_url_host_path=` host+path 까지만 (query/fragment 제거)
- 결과에는 raw URL 의 query/fragment, raw title, 쿠키/세션/스토리지가
  어떤 형태로도 들어가지 않는다.
- `action_open_local_browser_probe` 는 이 `error_code` 를 그대로 전파
  하여 ActionResult 에 `GOOGLE_OPEN_ONLY` 로 노출한다.

### 9.4 보안 고정 사항

- Google ID/PW 자동 입력 금지.
- Google 비밀번호 / 쿠키 / OTP / 세션값을 `.env` 에 저장 금지
  (`_FORBIDDEN_ENV_VARS` 가 존재만으로 차단).
- 쿠키 / `storage_state` / localStorage / sessionStorage 수집 금지.
- `--remote-debugging-port` 사용 금지.
- Google 로그인 우회 시도 금지.
- Playwright 로 Google 로그인 페이지 접근 금지 (본 정책으로 차단).

---

## 10. 개정 이력

| 일자 | 내용 |
|------|------|
| 2026-04-24 | `probe_manual_login_flow` 에 `require_visible_confirm / require_user_login_confirm / keep_open / browser_channel / viewport / slow_mo_ms` 도입, `already_logged_in_or_public_page` 상태 구분, `success_url_match` 단독 판정 제거 (cherry-pick `58e3001`) |
| 2026-04-25 | 관리자 로컬 PC 에서 실제 Chrome 창 가시성 확인 + 수동 Google 로그인 성공 (§3). 본 정책 문서 초판 작성 (cherry-pick `c4e045d`). |
| 2026-04-25 | YouTube Studio smoke 1회차 실시 — 사용자 확인 PASS, 스크립트 final_url 관측은 accounts.google.com 에 머물러 measurement gap 관측. §8 다중 탭 + HITL 우선 판정 정책 추가. `probe_manual_login_flow` 에 `context.pages` 전수 스캔 최소 보강. |
| 2026-04-25 | F-2: Google / YouTube open-only 정책 도입. `probe_visible_browser` 가 `accounts.google.com / google.com / studio.youtube.com / youtube.com / gmail.com / drive.google.com` 을 Playwright launch 전 차단 (`error_code=GOOGLE_OPEN_ONLY`). 해당 도메인은 `open_local_browser` (subprocess) 로만 띄움. |
