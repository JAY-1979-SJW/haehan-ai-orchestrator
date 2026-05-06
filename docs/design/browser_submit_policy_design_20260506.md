# Browser Submit Policy Design
**Date**: 2026-05-06  
**Stage**: Policy Design (No Implementation)  
**Status**: Design Phase for BROWSER_SUBMIT_POLICY_DESIGN_1

---

## 1. 목적

`browser.open_type_close_controlled` (type 입력)에 이어 `browser.submit` / `browser.click_submit` (제출 동작)을 안전하게 구현하기 위한 정책을 사전 설계합니다.

### 위험도 평가

- **type 입력**: risk_level = medium, requires_approval = True
  - 입력값: 사용자가 지정한 더미값 또는 sample_value_id 기반
  - 부작용: 필드 값 변경만 (form 미제출)
  - 복구 가능성: O (form 초기화 가능)

- **submit**: risk_level = **HIGH** (기본값), requires_approval = **True** (필수)
  - 부작용: form 제출, 운영 데이터 write, 되돌릴 수 없음
  - 결제/송금/삭제/신청 확정 등 심각한 후속 영향
  - 복구 불가능성: ✓ (rollback/취소 어려움)
  - **기본 정책**: **모든 submit 금지** (allowlist 미충족 시)

### 설계 원칙

1. **Zero Trust for Submit**: 명시적 allowlist 없으면 절대 허용 금지
2. **Multi-Layer Approval**: 정책 + preview + 사용자 확인 + 감사 로그
3. **Defense in Depth**: prompt injection, hidden field, iframe 등 모든 우회 차단
4. **Audit First**: submit 전에 모든 조건을 검증 후 로그 기록
5. **Transparency**: 사용자에게 위험도, 되돌릴 수 없음, 허용 근거를 명시

---

## 2. Submit 위험 분류

### Risk Classification

| 항목 | 기본값 | 이유 |
|------|--------|------|
| **risk_level** | HIGH | form 제출 = 데이터 쓰기, 복구 불가 |
| **requires_approval** | True | 모든 submit은 사전 승인 필수 |
| **read_only** | False | submit은 읽기 전용이 아님 |
| **destructive** | True | 운영 데이터 write 가능 |
| **reversible** | False | 제출 후 취소/복구 불가능 |

### Action Properties

```python
BrowserTaskPolicy(
    action="submit" or "click_submit",
    risk_level="high",            # 고정: 높음
    requires_approval=True,        # 고정: 필수
    requires_dry_run=False,        # type과 다름: 드라이런 불가
    requires_allowlist=True,       # NEW: allowlist 필수
    requires_user_preview=True,    # NEW: 제출 전 preview 필수
    requires_user_confirm=True,    # NEW: 사용자 확인 필수
    blocked=False,                 # 디자인 단계에서는 False
)
```

---

## 3. 허용 전제 조건 (All Must Be True)

Submit은 아래 조건을 **모두** 만족해야만 허용됩니다. 하나라도 실패하면 DENY입니다.

### 3.1 사이트 Allowlist 검증

```
✓ site_id가 submit_allowlist에 존재
✓ url origin이 allowlist와 **정확히** 일치 (subdomain 포함)
✓ allowlist 엔트리가 active=True
✓ site_id에 대한 admin approval이 존재
```

**예시 (허용)**:
```
site_id: "example_internal_mock"
url: "https://internal.mock/form"
allowed_origins: ["https://internal.mock"]
```

**예시 (거부)**:
```
# origin mismatch
url: "https://internal.mock.attacker.com/form"
allowed_origins: ["https://internal.mock"]
→ DENY (origin 일치 실패)
```

### 3.2 Form/Button Allowlist 검증

```
✓ form_id가 allowlist에 존재하거나
✓ submit_button_id가 allowlist에 존재
✓ form/button이 현재 DOM에 실제로 존재
✓ form/button의 텍스트나 속성이 allowlist와 일치
```

**예시 (허용)**:
```
form_id: "contact_form"
submit_button_id: "submit_btn"
allowed_form_ids: ["contact_form"]
allowed_submit_button_ids: ["submit_btn"]
```

**예시 (거부)**:
```
# allowlist 없음
submit_button_id: "delete_all"
allowed_submit_button_ids: []  # 빈 목록
→ DENY (allowlist 미충족)
```

### 3.3 Action Intent 검증

```
✓ action 목적이 user-approved task와 일치
✓ action 목적이 submit_allowlist의 allowed_intents에 포함
✓ "delete", "payment", "submit_application" 등 명시적 intent 기록
```

**허용 intent 예시**:
- "submit_contact_form"
- "apply_for_service"
- "update_profile"

**금지 intent 예시**:
- "delete_account"
- "transfer_money"
- "place_bid"
- "cancel_subscription_permanently"

### 3.4 입력값 Preview 검증

```
✓ type된 모든 필드가 preview에 표시됨
✓ 숨겨진 필드(hidden input) 목록 표시
✓ submit 전 되돌릴 수 없음을 사용자에게 표시
✓ preview hash를 audit log에 저장 (나중에 검증용)
```

### 3.5 Prompt Injection 검증 (PASS 필수)

```
✓ prompt에 우회 문구 없음
✓ 이전 지시 무시 문구 없음
✓ 승인 생략 문구 없음
✓ 정책 우회 문구 없음
```

검사 대상:
- 초기 요청 text
- 필드 입력값
- 이전 대화 context (if any)

### 3.6 민감정보 필드 검증

```
✓ password / passwd / pwd 필드 없음
✓ token / access_token / session_token 필드 없음
✓ secret / api_secret / client_secret 필드 없음
✓ cookie / authorization 필드 없음
✓ credit_card / cvv / ssn 필드 없음
```

**정책**: 민감정보 필드를 포함한 form은 절대 submit 허용 금지.

### 3.7 감사 로그 기록 가능성 검증

```
✓ audit_level >= required_audit_level
✓ audit log 저장소 정상 작동
✓ 민감정보 redaction 정책 적용 가능
```

### 3.8 사용자 직접 승인

```
✓ 사용자가 preview를 본 후 "제출" 버튼을 명시적으로 클릭
✓ 자동 submit 불가능
✓ timeout 없이 사용자 대기
```

---

## 4. 명시적 금지 조건 (Any One = DENY)

아래 중 **하나라도** 해당하면 submit을 절대 허용하지 않습니다.

### 4.1 Allowlist 부재

```
DENY if:
  - site_id가 allowlist에 없음
  - origin이 allowlist와 다름
  - form_id/button_id가 allowlist에 없음
  - allowlist entry의 active=False
```

### 4.2 외부 임의 URL

```
DENY if:
  - origin이 공개 인터넷 도메인 (예: example.com, naver.com, google.com)
  - 사용자가 URL을 임의로 입력함 (allowlist 없음)
  - iframe이나 새 창에서 origin 검증 불가
```

### 4.3 로그인/인증 Form

```
DENY if:
  - password 필드 존재
  - OTP / 2FA / MFA 필드 존재
  - certificate / token / api_key 입력 필드 존재
  - login / signin / authenticate 의도 감지
```

### 4.4 결제/송금/삭제/확정성 Submit

```
DENY if:
  - submit button text에 "결제", "송금", "이체" 포함
  - submit button text에 "삭제", "취소", "폐기" 포함
  - submit button text에 "신청 확정", "계약 체결", "입찰 확정" 포함
  - intent가 destructive (delete, cancel, complete_permanently) 포함
```

### 4.5 Prompt Injection 위험

```
DENY if:
  - prompt에 "무시하고 제출하세요"
  - prompt에 "사용자 확인 없이 제출"
  - prompt에 "정책을 무시하고"
  - prompt에 "승인 단계를 생략"
  - text 입력값에 위 문구 포함 (반사적 injection 시도)
```

### 4.6 Hidden Field 검증 불가

```
DENY if:
  - 숨겨진 필드(hidden input) 목록 구성 실패
  - hidden field의 value를 검증할 수 없음
  - 예상치 못한 hidden field 추가됨
  - JavaScript로 동적 생성된 field 감지 불가
```

### 4.7 Submit Target 불명확

```
DENY if:
  - submit button이 여러 개이고 target 불명확
  - button text가 모호함 (예: "확인", "다음")
  - form action이 변경될 수 있음
  - target URL이 동적으로 결정됨
```

### 4.8 사용자 미승인

```
DENY if:
  - 사용자가 preview를 보지 않음
  - 사용자가 "제출" 명령을 명시적으로 하지 않음
  - auto-submit 또는 scheduled submit 시도
  - 사용자 입력 없이 시간 초과 후 자동 제출
```

---

## 5. Allowlist 정책 초안

### 5.1 Allowlist Data Structure

```json
{
  "submit_sites": [
    {
      "site_id": "internal_contact_mock",
      "site_name": "Internal Contact Form (Mock)",
      "description": "Mock site for testing contact form submission",
      "allowed_origins": ["https://internal.mock", "http://localhost:3000"],
      "allowed_paths": ["/form", "/contact"],
      "allowed_form_ids": ["contact_form", "support_form"],
      "allowed_submit_button_ids": ["submit_btn", "send_btn"],
      "allowed_intents": ["submit_contact_form", "report_issue"],
      "denied_fields": ["password", "token", "api_key", "credit_card"],
      "requires_preview": true,
      "requires_user_confirm": true,
      "requires_human_approval": false,
      "audit_level": "detailed",
      "max_risk_level": "high",
      "active": true,
      "created_at": "2026-05-06T00:00:00Z",
      "admin_approved_by": "admin@internal",
      "admin_approved_at": "2026-05-06T00:00:00Z",
      "notes": "Mock site for validation tests only"
    },
    {
      "site_id": "denied_example_public",
      "site_name": "Public Example (Denied)",
      "description": "Example public site - submit denied",
      "allowed_origins": [],
      "allowed_form_ids": [],
      "allowed_intents": [],
      "requires_preview": false,
      "requires_user_confirm": false,
      "requires_human_approval": false,
      "active": false,
      "reason_denied": "Public site - not whitelisted"
    }
  ]
}
```

### 5.2 Allowlist 필드 설명

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| site_id | str | ✓ | 고유 site identifier |
| site_name | str | ✓ | 인간 가독형 이름 |
| allowed_origins | list[str] | ✓ | 허용 origin list (정확 일치) |
| allowed_paths | list[str] | ○ | 허용 path prefix |
| allowed_form_ids | list[str] | ✓ | 허용 form id list |
| allowed_submit_button_ids | list[str] | ✓ | 허용 button id list |
| allowed_intents | list[str] | ✓ | 허용 intent list |
| denied_fields | list[str] | ○ | 금지 필드명 (password, token 등) |
| requires_preview | bool | ✓ | preview 필수 여부 |
| requires_user_confirm | bool | ✓ | 사용자 확인 필수 여부 |
| requires_human_approval | bool | ○ | 추가 인간 승인 필요 여부 |
| audit_level | str | ✓ | "basic" / "detailed" / "verbose" |
| max_risk_level | str | ✓ | "low" / "medium" / "high" |
| active | bool | ✓ | 현재 활성화 여부 |

---

## 6. Prompt Injection 방어 기준

### 6.1 검사 대상

```
검사할 모든 입력:
  1. 초기 사용자 요청 text
  2. 모든 type된 필드값
  3. 이전 대화 context (if any)
  4. form hidden field values (동적 생성 여부)
```

### 6.2 차단 패턴

```python
INJECTION_PATTERNS = [
    # 지시 무시
    r"ignore.*previous.*instruction",
    r"무시하고.*제출",
    r"지시를.*무시.*하고",
    
    # 승인 우회
    r"without.*approval",
    r"승인.*없이.*제출",
    r"확인.*생략",
    
    # 정책 우회
    r"bypass.*policy",
    r"정책.*무시",
    r"제한.*해제",
    
    # 자동 완료
    r"auto.*submit",
    r"자동.*제출",
    r"승인.*절차.*건너뛰기",
    
    # 숨겨진 field 조작
    r"hidden.*field",
    r"숨겨진.*필드",
    r"보이지.*않는.*필드",
]
```

### 6.3 검증 로직

```
1. 모든 입력을 소문자로 정규화
2. INJECTION_PATTERNS 반복 매칭
3. 하나라도 일치 → prompt_injection_verdict = FAIL
4. 모두 미일치 → prompt_injection_verdict = PASS
5. FAIL인 경우 submit 절대 허용 금지
```

---

## 7. Submit 전 Preview 구조

### 7.1 Preview 필수 표시 항목

사용자에게 submit 전 아래 정보를 명확히 표시합니다:

```
┌─────────────────────────────────────────────┐
│ ⚠️  중요: 이 작업은 되돌릴 수 없습니다    │
├─────────────────────────────────────────────┤
│ 사이트:     Internal Contact Form (Mock)    │
│ URL:        https://internal.mock/contact   │
│ Form ID:    contact_form                    │
│ Button:     submit_btn ("제출하기")         │
├─────────────────────────────────────────────┤
│ 입력 필드 요약:                              │
│   □ name: [사용자명 입력됨]                 │
│   □ email: [이메일 입력됨]                  │
│   □ message: [메시지 입력됨]                │
├─────────────────────────────────────────────┤
│ 숨겨진 필드 (hidden):                       │
│   • csrf_token (값 길이: 64 char)           │
│   • timestamp (2026-05-06T10:00:00Z)        │
│   • user_agent (자동 수집됨)                │
├─────────────────────────────────────────────┤
│ ⚠️  경고:                                    │
│   • 제출 후 취소 불가능                     │
│   • 서버에 저장됨                           │
│   • 감사 로그에 기록됨                      │
├─────────────────────────────────────────────┤
│ 위험도:       HIGH (높음)                   │
│ 승인 상태:    관리자 사전 승인됨            │
│ 감사 수준:    detailed (상세 로깅)         │
├─────────────────────────────────────────────┤
│ [제출 취소]  [제출하기]                     │
└─────────────────────────────────────────────┘
```

### 7.2 Preview 데이터

```python
preview_data = {
    "site_name": str,           # 사이트명
    "url": str,                 # 전체 URL
    "origin": str,              # origin만 추출
    "form_id": str,             # form ID
    "submit_button_id": str,    # button ID
    "submit_button_text": str,  # button 텍스트
    "typed_fields": {           # 사용자 입력 필드
        "field_name": "redacted"  # 값은 redact
    },
    "hidden_fields": {          # 숨겨진 필드
        "field_name": "(hidden)"   # 값은 표시 안 함
    },
    "risks": [
        "데이터 쓰기",
        "되돌릴 수 없음",
        "감사 로그 기록"
    ],
    "preview_hash": "sha256_hash_of_preview",
    "preview_timestamp": "2026-05-06T10:00:00Z"
}
```

### 7.3 Preview Hash

```
preview_hash = SHA256(
    site_id + "|" +
    origin + "|" +
    form_id + "|" +
    submit_button_id + "|" +
    sorted(typed_fields.keys()).join("|")
)
```

Preview hash는 audit log에 저장되어, 나중에 실제 제출된 데이터와 검증 가능합니다.

---

## 8. 감시 로그 (Audit Log) 기준

### 8.1 Audit Log Schema

Submit 시도(성공/실패 모두)마다 아래를 기록합니다:

```python
audit_log = {
    # Action ID
    "action_id": "uuid",                    # 고유 요청 ID
    "action_type": "browser.submit",        # 액션 타입
    "timestamp": "2026-05-06T10:00:00Z",    # 기록 시각
    
    # Site & Form Info
    "site_id": "internal_contact_mock",     # allowlist site_id
    "url_origin": "https://internal.mock",  # origin (path 제외)
    "form_id": "contact_form",              # form id
    "submit_button_id": "submit_btn",       # button id
    
    # Approval & Policy
    "approved_by": "user_id",               # 승인한 사용자
    "approved_at": "2026-05-06T10:00:00Z",  # 승인 시각
    "policy_verdict": "ALLOW",              # ALLOW / DENY
    "policy_rule_matched": "allowlist_site_id",  # 어떤 규칙이 적용됐나
    
    # Validation Results
    "prompt_injection_verdict": "PASS",     # PASS / FAIL
    "preview_hash": "sha256_...",           # preview hash
    "preview_shown": true,                  # preview 표시 여부
    "user_confirmed": true,                 # 사용자 확인 여부
    
    # Execution Result
    "submitted": true,                      # 실제 제출 여부
    "submit_result": "success",             # success / failed / blocked
    "submit_http_code": 200,                # HTTP response code
    "submit_error": "",                     # 에러 메시지 (실패 시)
    
    # Security
    "csrf_token_validated": true,           # CSRF 검증 여부
    "tls_verified": true,                   # TLS 인증서 검증
    
    # Lifecycle
    "lifecycle": {
        "opened": true,
        "typed": true,
        "preview_shown": true,
        "user_confirmed": true,
        "submitted": true,
        "closed": true
    }
}
```

### 8.2 Log Storage & Retention

```
저장소:   audit_logs table (or collection)
접근:     read-only (admin + security team)
보존:     6개월 이상
암호화:   AES-256 at rest
감사:     정기적 합법성 검토
```

### 8.3 민감정보 Redaction

```
저장하지 않는 값:
  - submitted field 원문 (예: email, phone 등)
  - hidden field 원문 (CSRF token, session_id 등)
  - 응답 body
  - 쿠키 값

저장 가능:
  - field name (필드명)
  - field type (text, email, etc)
  - field length (숫자 자릿수, 문자열 길이 범위)
  - 필드 존재 여부
  - lifecycle flags (opened, typed, submitted)
```

---

## 9. 다음 구현 단계 제안

이 설계 문서를 바탕으로 다음 단계에서 순차적으로 구현합니다:

### Phase 1: Foundation (Fixture + Test)

1. **BROWSER_SUBMIT_POLICY_FIXTURE_1**
   - Submit allowlist fixture 구성
   - test case (allowed/denied) 정의
   - JSON schema validation

2. **BROWSER_SUBMIT_POLICY_VALIDATOR_1**
   - Allowlist validator 구현 (정책만)
   - Prompt injection detector 구현
   - Unit test 작성

3. **BROWSER_SUBMIT_PREVIEW_SCHEMA_1**
   - Preview data structure 정의
   - Preview hash 계산 로직
   - Preview serialization/deserialization

### Phase 2: Mock & Audit

4. **BROWSER_SUBMIT_MOCK_ONLY_ACTION_1**
   - Mock backend submit handler (실제 submit 없음)
   - Audit log schema 구현
   - Redaction 로직 통합

5. **BROWSER_SUBMIT_CONTROLLED_SMOKE_1**
   - Controlled mock site에서 submit 1회 실행
   - Preview 검증
   - Audit log 기록 확인
   - Policy validator 작동 검증

### Phase 3: Real Execution (Future)

6. **BROWSER_SUBMIT_POLICY_APPROVAL_1**
   - Approval workflow 구현
   - User confirmation UI

7. **BROWSER_SUBMIT_ACTUAL_EXECUTION_1**
   - Actual submit execution
   - Error handling & rollback planning
   - Real site allowlist 구성

---

## 10. 설계 문서 승인 기준

이 설계 문서는 다음을 만족할 때 **완성**됩니다:

```
✓ Submit 위험도 분류 명확함 (risk_level=HIGH)
✓ Allowlist 조건 구체적 (site_id, origin, form_id)
✓ 금지 조건 명시적 (password, payment, intent 등)
✓ Prompt injection 차단 기준 명확 (pattern list)
✓ Preview 구조 정의됨 (필수 항목 list)
✓ Audit log schema 정의됨 (민감정보 제외)
✓ 다음 구현 단계 제안됨 (5단계)
✓ 실제 submit 구현 없음 (이 단계는 설계만)
✓ 실제 브라우저 submit 실행 없음
✓ 외부 업무 사이트 접속 없음
✓ DB write 없음
```

---

## 11. 참고: 기존 Type Action과의 비교

| 항목 | Type (open_type_close_controlled) | Submit (설계) |
|------|--------------------------------|---------------|
| 위험도 | medium | **HIGH** |
| 승인 | 필수 | 필수 |
| 부작용 | 필드값 변경 | **데이터 쓰기** |
| 복구 가능성 | O (form 초기화) | **X (불가능)** |
| Allowlist | optional | **필수** |
| Preview | 권장 | **필수** |
| 자동 실행 | 불가능 | 불가능 |
| 사용자 확인 | 권장 | **필수** |
| Prompt injection | 기본 차단 | **강화된 차단** |

---

## Document Version

- **Version**: 1.0 (Design Phase)
- **Created**: 2026-05-06
- **Status**: Ready for Implementation Planning
- **Next Review**: After Phase 1 (BROWSER_SUBMIT_POLICY_FIXTURE_1 completion)
