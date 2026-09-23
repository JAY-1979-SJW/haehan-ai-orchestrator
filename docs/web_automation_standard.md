# 웹 자동화 표준 (Web Automation Standard)

적용 범위: `ai_orchestrator/sites/adapters/` 하위 모든 DevReg 어댑터

사이트별 확장 작업을 시작하기 전 `docs/site_automation_reference_index.md`를 먼저 확인한다.

---

## 1. 어댑터 생명주기

```
fill_form() ──→ capture_screenshot() ──→ [텔레그램 승인 대기]
                                                 │
                              ┌──────────────────┤
                         승인 │                  │ 거절/만료
                              ▼                  ▼
                       submit_form()        abort_form()
```

- **fill_form**: 폼 입력 전용. 제출 버튼 클릭 금지.
- **capture_screenshot**: fill_form 완료 후, 텔레그램 알림 전 캡처.
- **submit_form**: 승인 확정 후 runner가 호출. 직접 호출 금지.
- **abort_form**: 거절·만료·오류 시 브라우저 세션 정리.

---

## 2. 메서드별 역할 및 제약

### 2.1 `fill_form(page, params) → FormFillResult`

| 항목 | 기준 |
|------|------|
| 제출 버튼 | **클릭 금지** — submit_form 에서만 허용 |
| dry_run | `params["dry_run"]=True` 이면 page 조작 없이 검증·요약만 반환 |
| 민감정보 | summary 에 password / cookie / session / token / client_secret 포함 금지 |
| 에러 코드 | 실패 시 `error_code` 필드에 `ErrorCode.*` 상수 설정 |
| 페이지 로드 | goto 실패 → `PAGE_LOAD_FAILED` |
| 로그인 리다이렉트 | goto 후 URL에 login 힌트 포함 → `LOGIN_REQUIRED` |
| 필드 입력 실패 | DOM 변경 가능성 → `PROVIDER_LAYOUT_CHANGED` |

### 2.2 `submit_form(page) → SubmitResult`

| 항목 | 기준 |
|------|------|
| 호출 조건 | run_dev_reg에서 승인 토큰 확인 후에만 호출 |
| 버튼 확인 | `_has_element(page, selector)` 먼저 실행 |
| 버튼 없음 | `SUBMIT_BUTTON_NOT_FOUND` 반환 |
| 결과 검증 | page.inner_text("body") 에서 완료 키워드 확인 |
| 민감정보 | result_summary 에 민감값 포함 금지 |

### 2.3 `abort_form(page) → None`

| 항목 | 기준 |
|------|------|
| 목적 | 브라우저 세션 중단, 제출 방지 |
| 구현 | `page.goto("about:blank")` |
| 예외 | 모두 무시 (WARNING 로그만) |

### 2.4 `capture_screenshot(page, path: Path) → Path`

| 항목 | 기준 |
|------|------|
| 저장 위치 | `storage/screenshots/` 하위, task_id 기반 파일명 |
| 저장 형식 | PNG (Playwright 기본값) |
| 실패 처리 | 예외 무시, 경고 로그 후 path 반환 |
| 민감정보 | 스크린샷 경로는 `dev_reg_approvals.jsonl` 에 경로만 기록 (바이너리 금지) |
| API 노출 | `screenshot_path` 필드는 API 응답에서 제거 (`_SAFE_EXCLUDE`) |

---

## 3. 승인 전/후 동작 기준

```
┌─────────────────────────────────────────────────────┐
│  승인 전 (fill_form / screenshot / 텔레그램 발송)      │
│  ─────────────────────────────────────────────────  │
│  • 폼 입력 가능                                       │
│  • 스크린샷 캡처 가능                                  │
│  • submit 버튼 클릭 금지                               │
│  • 폼 데이터 민감정보 저장 금지                         │
└─────────────────────────────────────────────────────┘
         │ 텔레그램 [승인] 버튼
         ▼
┌─────────────────────────────────────────────────────┐
│  승인 후 (submit_form)                                │
│  ─────────────────────────────────────────────────  │
│  • submit 버튼 클릭 허용                               │
│  • 실행 결과를 result_summary 에 기록 (민감값 제외)      │
│  • 실패 시 error_code 설정                             │
└─────────────────────────────────────────────────────┘
```

---

## 4. Selector 작성 원칙

우선순위 (높음 → 낮음):

| 순위 | 방식 | 예시 |
|------|------|------|
| 1 | aria-label / role | `button[aria-label='Save and continue']` |
| 2 | name / id 속성 | `input[name='app_name']`, `input[formcontrolname='displayName']` |
| 3 | placeholder | `input[placeholder='Enter a URI']` |
| 4 | 텍스트 (Playwright) | `text='등록'` |
| 5 | CSS class (최후 수단) | `button.btn-register` — 폴백 전용 |
| 금지 | nth-child / nth-of-type | `div:nth-child(3) > input` — 사용 금지 |

복수 선택자 폴백 패턴:
```python
_SUBMIT_BTN_SELECTORS = (
    "button[aria-label='Save and continue']",  # 1순위
    "button.save-button",                       # 폴백
)
btn_sel = next((s for s in _SUBMIT_BTN_SELECTORS if _has_element(page, s)), None)
```

---

## 5. Timeout 기준

| 상황 | 권장값 | 비고 |
|------|--------|------|
| `page.goto` | 기본값 (30s) | wait_until 별도 지정 |
| `networkidle` 대기 | 적합한 단순 폼 페이지 | SPA는 domcontentloaded 우선 |
| `wait_for_selector` | 15000ms | Google Console Angular SPA 기준 |
| `page.fill` | 기본값 | 선택자 미발견 시 즉시 예외 |

---

## 6. Screenshot 저장 원칙

1. 저장 경로: `{LOG_DIR}/screenshots/{task_id}_{timestamp}.png`
2. 타이밍: `fill_form()` 완료 직후, `submit_form()` 호출 전
3. 실패 허용: 스크린샷 실패는 WARN 로그만, 승인 흐름 중단 금지
4. 경로 기록: JSONL 에 경로(str)만 기록, 바이너리 내용 금지
5. API 노출: `screenshot_path` 필드는 `_SAFE_EXCLUDE` 에 포함하여 API 응답 제거

---

## 7. 민감정보 마스킹 원칙

| 항목 | 처리 방법 |
|------|-----------|
| password / cookie / session / token | summary 에 포함 금지, `_SAFE_SUMMARY_FIELDS` 화이트리스트만 허용 |
| client_secret | summary 및 로그에 포함 금지 |
| contact_email | `_mask_email()` 적용 (앞 3자리만 노출) |
| approval_token_hash | SHA256(token_id) 만 저장, 원문 저장 금지 |
| screenshot_path | API 응답 제거 (`_SAFE_EXCLUDE`) |
| HTML 전체 내용 | 로그 금지, result_summary 는 200자 이내로 잘라낸다 |

---

## 8. 실패 시 `error_code` 기준

| 코드 | 발생 조건 | 적용 메서드 |
|------|-----------|-------------|
| `PAGE_LOAD_FAILED` | `page.goto()` 예외 | `fill_form` |
| `LOGIN_REQUIRED` | goto 후 URL 에 login 힌트 포함 | `fill_form` |
| `CAPTCHA_REQUIRED` | CAPTCHA 감지 (자동 우회 금지) | `fill_form` |
| `FORM_FIELD_MISSING` | `validate_params()` 실패 | `fill_form` |
| `SUBMIT_BUTTON_NOT_FOUND` | `_has_element()` 가 False | `submit_form` |
| `APPROVAL_REQUIRED` | 승인 없이 submit 시도 | `submit_form` (runner 레벨) |
| `PROVIDER_LAYOUT_CHANGED` | DOM 선택자 일치 실패 | `fill_form` |

에러 코드는 `FormFillResult.error_code` 및 `SubmitResult.error_code` 필드에 기록된다.

---

## 9. Provider별 특이사항

| Provider | URL | 특이사항 |
|----------|-----|----------|
| hiworks | `https://developers.hiworks.com/apply` | `networkidle` 사용. button[type='submit'] 폼 내 유일. |
| naver | `https://developers.naver.com/apps/#/register` | `networkidle` 사용. 스코프 체크박스 별도 처리. submit 버튼 class/type 이중 폴백. |
| google | `https://console.cloud.google.com/apis/credentials/consent` | Angular SPA — `domcontentloaded` + `wait_for_selector`. 리다이렉트 URI 는 Add 버튼 클릭 후 입력. submit 버튼 aria-label 우선. |

---

## 10. 로그인 / CAPTCHA / 2FA 정책

- **로그인 자동화 금지**: 세션은 사전에 사람이 완료
- **CAPTCHA 우회 금지**: `CAPTCHA_REQUIRED` 에러 반환 후 중단
- **2FA / OTP 우회 금지**: `LOGIN_REQUIRED` 에러 반환 후 중단
- **재인증**: `SiteAdapter.wait_for_human_reauth()` 로 사람이 직접 처리

---

## 11. 웹 작업 레지스트리 (web_task_registry.py)

### 구조

`ai_orchestrator/services/web_task_registry.py` 에 중앙 레지스트리를 정의한다.
하드코딩은 허용하되 **이 파일 한 곳에만** 두어야 한다.

```
WebTaskEntry
├── task_key        : "{provider}/{action_type}"
├── provider        : hiworks / naver / google
├── action_type     : developer_apply / app_register / oauth_submit
├── adapter_class   : DevRegAdapterBase 구현체 (외부 노출 금지)
├── risk_level      : high
├── requires_approval: True
├── read_only       : False
└── description     : 한글 설명
```

### 등록된 작업

| task_key | provider | action_type | risk_level | requires_approval |
|----------|----------|-------------|------------|-------------------|
| hiworks/developer_apply | hiworks | developer_apply | high | True |
| naver/app_register | naver | app_register | high | True |
| google/oauth_submit | google | oauth_submit | high | True |

### 접근 함수

| 함수 | 설명 |
|------|------|
| `get_entry(provider, action_type)` | 레지스트리 조회, 미등록 시 `None` |
| `list_entries()` | 안전 필드만 반환 (`adapter_class` 제외) |

---

## 12. 표준 실행 API

### 엔드포인트

| 메서드 | 경로 | 권한 | 설명 |
|--------|------|------|------|
| GET | `/api/v1/web-tasks/registry` | admin / owner | 등록된 작업 목록 조회 |
| POST | `/api/v1/web-tasks/run` | admin / owner | 작업 실행 요청 |

### POST /run 요청 모델

```json
{
  "provider": "hiworks",
  "action_type": "developer_apply",
  "params": {
    "app_name": "MyApp",
    "company_name": "MyCo",
    "contact_email": "dev@example.com"
  },
  "dry_run": true
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| provider | ✓ | 레지스트리에 등록된 값만 허용 |
| action_type | ✓ | 레지스트리에 등록된 값만 허용 |
| params | - | 어댑터 validate_params() 통과해야 함 |
| dry_run | - | 기본값 false |

---

## 13. dry_run과 real_run 차이

```
POST /run (dry_run=true)
  │
  ├─ 레지스트리 조회 (미등록 → 404)
  ├─ validate_params() (실패 → 422 FORM_FIELD_MISSING)
  ├─ adapter.fill_form(page=None, dry_run=True)
  │     → DOM 조작 없이 검증·요약만 생성
  └─ 응답 반환: {dry_run, summary, field_names, target_url}
     (approval 생성 없음, submit 없음)

POST /run (dry_run=false)
  │
  ├─ 레지스트리 조회 (미등록 → 404)
  ├─ validate_params() (실패 → 422)
  ├─ adapter.fill_form(page=None, dry_run=True) → summary 생성
  ├─ issue_token_for_dev_reg() → 승인 토큰 발행 (TTL 30분)
  ├─ dev_reg_approval.create_pending() → pending 레코드 생성
  ├─ log_event("WEB_TASK_RUN_REQUESTED")
  ├─ log_event("WEB_TASK_PENDING_APPROVAL_CREATED")
  ├─ telegram_sender.send_message() → 승인 요청 발송
  └─ 즉시 응답: {status: "pending_approval", task_id, ...}
```

---

## 14. Approval Required Flow

```
[POST /run dry_run=false]
        │
        ▼
  pending approval 생성
        │
        ▼
  텔레그램 승인 요청 발송 (send_message)
        │
   (인간 검토)
        │
   ┌────┴────┐
승인│         │거절
   ▼         ▼
 DEV_REG_APPROVED   DEV_REG_REJECTED
 (기존 webhook 처리)
```

- `dry_run=false` API 는 **즉시 반환**. 승인을 기다리지 않는다.
- 텔레그램 [승인] / [거절] 버튼은 기존 `handle_telegram_decision()` 이 처리한다.
- 실제 폼 제출(submit_form)은 브라우저 세션이 있는 `run_dev_reg()` 로 별도 실행한다.

---

## 15. 금지 사항

| 항목 | 이유 |
|------|------|
| 미등록 provider/action_type 실행 | 임의 사이트 자동화 방지 |
| 승인 없이 submit_form 호출 | 무인 제출 방지 |
| params 원문 audit log 기록 | 민감정보 보호 |
| adapter_class 외부 노출 | 구현 세부 사항 캡슐화 |
| viewer 역할 run/registry 접근 | 최소 권한 원칙 |
| 로그인 / CAPTCHA / 2FA 자동 우회 | 보안 정책 |
| 로컬 PC 제어 | 웹 자동화만 허용 |
| 프론트 UI 구현 | 이번 단계 범위 외 |

---

## 16. 감사 로그 이벤트 (웹 작업)

| 이벤트 | 발생 시점 |
|--------|-----------|
| `WEB_TASK_RUN_REQUESTED` | dry_run=false 실행 요청 수신 |
| `WEB_TASK_DRY_RUN_COMPLETED` | dry_run=true 완료 |
| `WEB_TASK_PENDING_APPROVAL_CREATED` | pending 레코드 생성 + 텔레그램 발송 완료 |
| `WEB_TASK_REJECTED_UNKNOWN_TASK` | 미등록 provider/action_type 요청 |
| `WEB_TASK_VALIDATION_FAILED` | validate_params() 실패 |
| `WEB_TASK_REGISTRY_LISTED` | GET /registry 호출 |

> 민감정보 포함 금지: `note` 필드에 params 원문 기록 금지. provider / action_type / success 여부만 기록.
