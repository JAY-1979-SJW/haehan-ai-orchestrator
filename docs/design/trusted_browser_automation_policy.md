# F-4C — Trusted Browser Automation 정책

본 문서는 대표님 PC에서만 동작하는 **trusted browser automation** 트랙의
설계 원칙을 정의한다. F-2/F-4B (Google open-only · public observer) 정책과
충돌하지 않으며, 그 위에 **사용자 본인 PC에서만 허용되는 사이트별 자동
로그인/자료 다운로드** 흐름을 별도로 얹는다.

본 문서가 정의하는 것은 **정책과 인터페이스 스켈레톤** 이다. 실제 자동
클릭/입력 구현은 본 단계에 포함되지 않는다.


## 목적

- 대표님이 매번 손으로 하는 홈택스 등 인증 필요 사이트의 read-only 다운
  로드 흐름을 사용자 PC에서만 자동화한다.
- 비밀번호/인증서 비밀번호 같은 비밀값은 **AI/GPT/서버가 절대 알지 않게**
  한다. 비밀값은 대표님 PC의 로컬 보안 저장소에서만 관리되고, 오케스트
  레이터·서버·로그·ActionResult 어디에도 노출되지 않는다.
- 신고/납부/제출/발행 등 되돌릴 수 없는 실행은 자동화하지 않는다.


## 적용 범위

본 정책은 **로컬 에이전트** (`local_agent` 패키지) 에만 적용된다.
서버 측 (`ai_orchestrator`) 은 본 정책에서 정의된 trusted automation
관련 코드를 직접 호출하지 않는다.

기존 트랙과의 관계:

- F-2 — Google/YouTube **open-only** 정책: 본 정책이 그 위에 새 도메인
  (홈택스 등) 을 trusted automation 으로 별도 허용해도, Google/YouTube
  여섯 도메인은 여전히 open-only 로 강제된다.
- F-4B — 공개 페이지 read-only observer: trusted automation 흐름과 모듈
  분리. observer 는 fresh BrowserContext, 본 trusted automation 은 별도
  trusted profile 사용 (구현은 본 단계 외).


## allowed_sites (host allowlist)

```
hometax.go.kr
www.hometax.go.kr
```

- 위 호스트와 정확히 일치하거나 서브도메인 (`host.endswith("." + d)`) 만
  허용한다.
- 그 외 호스트는 trusted automation 시작 단계에서 거절한다.
- 추가 사이트는 후속 단계에서 본 문서를 갱신해서만 허용한다.


## allowed_actions

| action 이름                  | 설명                                               |
|----------------------------- |---------------------------------------------------|
| `trusted_login`              | 사이트 로그인 시도 (구현은 후속 단계). secret_id 만 |
| `observe_authenticated_page` | 로그인 후 화면을 read-only 로 관찰                 |
| `navigate_readonly`          | 메뉴 이동 등 비파괴적 navigation                    |
| `download_file`              | 사용자 지정 폴더로 read-only 자료 저장              |
| `save_result`                | 다운로드/관찰 결과 메타데이터를 ActionResult 로 저장 |


## blocked_actions (절대 자동화 금지)

| action 이름                    | 차단 사유                              |
|------------------------------- |---------------------------------------|
| `submit_tax_return`            | 신고 제출 — 되돌릴 수 없음              |
| `pay_tax`                      | 납부 — 자금 이동 발생                   |
| `issue_tax_invoice`            | 세금계산서 발행 — 외부에 즉시 영향       |
| `change_business_info`         | 사업자 정보 변경                       |
| `delegate_permission_change`   | 위임/수임 권한 변경                     |
| `captcha_bypass`               | 보안문자 우회 — 사이트 정책 위반         |
| `export_cookie`                | 쿠키 추출 / 외부 전달 금지               |
| `export_session`               | 세션 추출 / 외부 전달 금지               |
| `export_storage`               | localStorage / sessionStorage 추출 금지  |
| `read_saved_password`          | 브라우저 저장 비밀번호 직접 read 금지    |


## requires_user_presence (대표님 직접 화면 확인 필요)

다음 상황은 자동 진행하지 않고 대표님의 명시적 화면 확인을 요구한다.

- `first_login_setup` — 최초 로그인/인증서 설치
- `ambiguous_certificate_selection` — 인증서 다중 선택 화면
- `mobile_2fa_push` — 휴대폰 2FA push 승인
- `captcha_or_bot_check` — 보안문자 / bot check
- `payment_or_submission_confirmation` — 결제/제출 직전 확인 화면


## Secret 원칙

- **AI/GPT/서버는 비밀값을 알지 않는다.** 절대 prompt/context/audit log/
  ActionResult 어디에도 비밀값이 들어가지 않는다.
- **secret_id 만 전달.** 오케스트레이터→로컬 에이전트로 가는 파라미터에
  비밀번호/인증서 비밀번호/쿠키/세션/스토리지 raw 값을 절대 포함하지
  않는다. 대신 사람이 읽을 수 있는 식별자 문자열 (`secret_id`) 만 전달.
- **로컬 resolve.** 로컬 에이전트만 `secret_id` 를 보안 저장소에서
  resolve 해 잠시 메모리에 보유한 채 브라우저에 입력한다.
- **redaction.** ActionResult / audit log / exception trace 어디에도
  resolve 된 평문 비밀값이 남지 않는다. 비밀값을 다룬 코드 경로는 평문을
  지역 변수에서만 보유하고 즉시 폐기한다.
- **금지 키워드.** `password`, `passwd`, `cert_password`,
  `certificate_password`, `otp`, `token`, `access_token`,
  `refresh_token`, `cookie`, `session`, `storage_state`, `localStorage`,
  `sessionStorage` 같은 키 이름이 raw 값과 함께 파라미터로 들어오면
  trusted automation 진입 단계에서 거절한다.


## 로컬 보안 저장소 원칙

- 비밀값은 **대표님 PC 의 OS 키 저장소** (Windows Credential Manager)
  에만 보관한다.
- 비밀값을 평문 파일로 디스크에 두지 않는다 (`.env`, JSON 등 금지).
- 비밀값을 git 저장소/오케스트레이터/원격 서버로 전송하지 않는다.


## F-4D — Secret Backend 구조

`local_agent.trusted_secrets` 는 본 단계에서 backend 추상화를 갖는다.

### Backend 종류

| backend                          | 위치     | 용도                                         |
|--------------------------------- |--------- |--------------------------------------------- |
| `MockSecretBackend`              | 테스트   | dict 주입형. 실제 OS 저장소 미접근.            |
| `WindowsKeyringSecretBackend`    | 운영자 PC | `keyring` 패키지 위임. service=`haehan_local_agent` |

### 인터페이스

- `resolve_secret(secret_id, *, backend=...)` — backend 미지정 시
  의도적으로 `NotImplementedError`. 자동 resolve 금지.
- `get_secret_backend(name=None)` — `"mock"` 또는 keyring backend.
- 예외 (메시지에 평문 미포함):
  - `SecretResolutionError` — base.
  - `SecretNotFoundError` — secret_id 미존재.
  - `SecretBackendUnavailableError` — keyring 미설치 등.

### 보안 계약

- backend 의 `resolve()` 반환값은 **호출자 지역 변수만** 보유한다.
- 반환값은 ActionResult / audit / exception / log 어디에도 들어가지
  않는다. backend 자체의 `__repr__` / `__str__` 도 평문 비밀값을 절대
  드러내지 않는다.
- raw 비밀값을 파라미터로 받는 경로는 기존대로 차단 (`password`,
  `cookie`, `session`, `storage_state` 등).
- `keyring` 미설치 환경에서도 본 모듈 import 자체는 깨지지 않는다 —
  `WindowsKeyringSecretBackend` 인스턴스화 시점에 한해서만
  `SecretBackendUnavailableError` 로 전환된다.

### 본 단계에 **포함되지 않는** 것

- 실제 secret 등록 CLI (F-4E 후속).
- DPAPI / pywin32 직접 호출.
- 새 의존성 자동 설치 (`keyring` 은 운영자 PC 에 수동 설치).
- 실제 홈택스 자동 로그인 클릭/입력 (F-4F 이후).
- `runner.py` 의 pre-existing `login_with_secret` 코드 변경.


## 다운로드 폴더 원칙

- 다운로드 대상 폴더는 **사용자가 명시적으로 지정한 allowlist 폴더** 이
  거나 그 하위만 허용한다.
- 기본 `Downloads/` 외 임의 경로 (`C:\Windows`, `C:\Program Files` 등
  시스템 영역) 는 차단한다.
- 다운로드된 파일은 ActionResult 에 **분류 + 파일명** 만 기록하고, 파일
  내용은 본 단계에서 추출하지 않는다.


## CAPTCHA / 2FA / 보안문자 처리

- CAPTCHA 또는 보안문자 화면이 감지되면 **자동 시도하지 않고** 즉시
  `requires_user_presence: captcha_or_bot_check` 로 사용자에게 화면을
  넘긴다.
- CAPTCHA 우회/이미지 인식/외부 풀이 서비스 사용은 정책상 금지.
- 모바일 2FA push 도 사용자 휴대폰에서 승인되어야 진행 가능. 자동
  승인/캐시된 push 응답 사용 금지.


## 신고/납부/제출 차단 원칙

- 신고서 제출 / 납부 / 발행 / 위임 변경 / 사업자 정보 변경 같은
  되돌릴 수 없는 화면은 **classifier 단계에서 차단** 으로 분류한다.
- 자동으로 클릭/제출하지 않는다.
- 화면 분류 결과를 ActionResult 에 `blocked_reason` 으로 명시한다.


## 모듈/파일 매핑 (본 단계 산출)

| 파일                                                                | 역할                                          |
|-------------------------------------------------------------------- |---------------------------------------------- |
| `docs/design/trusted_browser_automation_policy.md`                  | 본 정책 문서                                   |
| `local_agent/trusted_secrets.py`                                    | secret_id 인터페이스 + raw 비밀 차단 + redact |
| `local_agent/trusted_browser_policy.py`                             | host/action allowlist + 결과 sanitizer       |
| `local_agent/site_adapters/__init__.py`                             | site_adapters 패키지                          |
| `local_agent/site_adapters/hometax.py`                              | 홈택스 page classifier + download plan        |
| `ai_orchestrator/tests/test_trusted_browser_policy.py`              | trusted_browser_policy 단위 테스트            |
| `ai_orchestrator/tests/test_trusted_secrets.py`                     | trusted_secrets 단위 테스트                   |
| `ai_orchestrator/tests/test_trusted_secret_backend.py`              | F-4D backend (Mock + 선택적 keyring) 단위 테스트 |
| `ai_orchestrator/tests/test_hometax_adapter.py`                     | 홈택스 page classifier 단위 테스트            |


## 본 단계에 **포함되지 않는** 것

- 실제 홈택스 자동 로그인 클릭/입력 구현
- 실제 홈택스 다운로드 클릭 구현
- 실제 Windows Credential Manager 연동 (interface stub 만)
- Naver/Hiworks/CAD/MCP 트랙
- 서버측 자동 호출 경로
- runner.py 의 pre-existing `login_with_secret` 코드 변경
