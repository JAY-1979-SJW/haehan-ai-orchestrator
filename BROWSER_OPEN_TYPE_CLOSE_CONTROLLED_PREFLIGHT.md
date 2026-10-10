# browser.open_type_close_controlled Preflight Analysis

**목표**: 실제 브라우저 isolated context에서 sample text만 입력하는 controlled type action의 정책 확정

**현재 단계**: Preflight (정책/위험도/입력값 redaction/cleanup/테스트 기준만)

**금지**: 코드 수정, 브라우저 실행, type 입력, task submit, password/token/secret

---

## STEP 1. browser.plan_type 구현 상태 확인 ✅

| 항목 | 상태 |
|------|------|
| 커밋 | a9945f1 |
| 테스트 | 13/13 통과 |
| 정책 | low risk, no approval |
| typed | false (plan-only) |
| 보안 | raw input 없음 |

**판정**: ✅ PASS_PLAN_TYPE_완료

---

## STEP 2. actual type 위험도 확정

### Risk Assessment

**위험도: MEDIUM** ✅

| 항목 | 평가 | 이유 |
|------|------|------|
| 실제 입력 | ⚠️ YES | type 키 이벤트 실행 |
| 브라우저 실행 | ⚠️ YES | isolated context 생성 |
| 샘플 값만 | ✅ YES | 사용자 input 금지 |
| 네트워크 | ✅ NO | sample URL only |
| 파일 생성 | ✅ NO | cleanup 후 삭제 |
| approval | ⚠️ YES | 필수 |
| one-shot | ✅ YES | 즉시 종료 |

### 위험도 근거

**Medium 선정 이유**:
1. **Browser Execution**: 실제 브라우저 인스턴스 생성 (리소스)
2. **DOM Interaction**: type 입력 = DOM mutation
3. **Isolated Context**: 격리 → 낮은 risk
4. **Sample Input Only**: 사용자 control 없음 → risk 감소
5. **One-Shot**: 실행 후 즉시 cleanup

**높지 않은 이유**:
- ❌ password/token/secret 불가
- ❌ 사용자 raw text 불가
- ❌ 개인정보 불가
- ❌ multiple requests 불가 (one-shot)
- ✅ 완전 격리 context

**낮지 않은 이유**:
- ⚠️ 실제 DOM 수정
- ⚠️ 브라우저 리소스 사용
- ⚠️ 비상 cleanup 필요

### Approval Gate

```
browser.open_type_close_controlled:
  - risk: medium
  - requires_approval: true
  - dispatch: queued (승인 후)
```

### 판정 기준

- ✅ PASS: medium으로 확정
- ❌ FAIL: low로 시도 → FAIL_RISK_UNDERESTIMATED

**판정**: ✅ PASS_RISK_MEDIUM_확정

---

## STEP 3. 입력값 정책 확정

### 허용 입력값

#### 1. Sample Value (Internal Only)

```python
SAMPLE_TEXT_VALUES = {
    "sample_text_short": "sample input",
    "sample_text_medium": "sample input with more content",
    "sample_number": "1234",
    "sample_date": "2026-05-06",
    "sample_email": "user@example.com",  # NOT real, never stored
    "sample_phone": "010-1234-5678",     # sample only
}
```

**규칙**:
- sample_value_id enum으로만 선택
- 내부 고정값만 사용
- 사용자 raw input 금지
- 입력값 저장 금지

#### 2. Field Target

```python
ALLOWED_FIELD_IDS = {
    "sample_text_field",
    "sample_search_field",
}
```

### 금지 입력값

| 항목 | 예 | 이유 |
|------|-----|------|
| 사용자 raw text | 사용자 입력 | 검증 불가 |
| Password | "mypassword" | 보안 |
| Token | "sk-abc123" | 자격증명 |
| Secret | "secret_key" | 노출 금지 |
| API Key | "api_xyz" | 민감 정보 |
| 개인정보 | "010-1234-5678" | 규정 |
| 자유 입력 | 긴 문장 | 상태 저장 |
| Form Data | 원문 | 저장 금지 |

### Result Data Allowlist

**응답 포함 가능**:
- ✅ action
- ✅ typed (true)
- ✅ field_id
- ✅ field_role
- ✅ sample_value_id
- ✅ executed
- ✅ requires_approval
- ✅ lifecycle (opened, typed, closed)

**응답 미포함**:
- ❌ raw input value
- ❌ actual keyboard input sequence
- ❌ DOM element details
- ❌ selector (raw)
- ❌ field name (raw)
- ❌ label/placeholder

### 판정 기준

- ✅ PASS: raw input 미저장, enum-based만
- ❌ FAIL: raw value 포함, raw selector 반환

**판정**: ✅ PASS_INPUT_ENUM_ONLY

---

## STEP 4. field selector 정책 확정

### Selector 정책

**허용**:
- ✅ field_id (enum): "sample_text_field"
- ✅ field_role (enum): "text_input"
- ✅ 내부 allowlist selector (server-only, client 불보)

**금지**:
- ❌ raw CSS selector: "#input-123"
- ❌ XPath: "//input[@id='x']"
- ❌ field name: "username"
- ❌ label/placeholder: "Enter name"
- ❌ coordinates: "[100, 200]"
- ❌ DOM path: "body > form > input"

### Redaction Strategy

```python
# Server-side enum-based targeting
def resolve_field_id(field_id: str) -> dict:
    """field_id enum을 내부 selector로 변환 (client 불보)."""
    FIELD_MAPPING = {
        "sample_text_field": {
            "selector": "#sample-input-text",  # server-only
            "role": "text_input",
        },
        "sample_search_field": {
            "selector": "#sample-input-search",
            "role": "search_input",
        },
    }
    
    if field_id not in FIELD_MAPPING:
        raise ValueError(f"unknown field_id: {field_id}")
    
    mapping = FIELD_MAPPING[field_id]
    
    return {
        "field_id": field_id,
        "field_role": mapping["role"],
        # selector는 클라이언트에 반환하지 않음 (server-side navigation만)
    }
```

### Response Redaction

```json
{
  "success": true,
  "action": "browser.open_type_close_controlled",
  "typed": true,
  "field_id": "sample_text_field",
  "field_role": "text_input",
  "sample_value_id": "sample_text_short",
  "executed": true,
  "lifecycle": {
    "opened": true,
    "typed": true,
    "closed": true
  }
}
```

❌ 응답에 포함 금지:
- selector (raw)
- field name
- DOM path
- actual input sequence

### 판정 기준

- ✅ PASS: enum + redacted 구조
- ❌ FAIL: raw selector/DOM path 반환

**판정**: ✅ PASS_SELECTOR_ENUM_REDACTED

---

## STEP 5. Lifecycle 설계

### 플로우

```
1. Request Input
   - action: "browser.open_type_close_controlled"
   - field_id: "sample_text_field" (enum)
   - sample_value_id: "sample_text_short" (enum)
   - url: "https://example.com" (allowlist 확인 필요)
   - requires_approval: true

2. Approval Gate
   - status: waiting_approval
   - approval_token: required
   - mark_approved() → queued

3. Worker Dispatch
   - dispatch: queued → delivered → running

4. Isolated Context Creation
   - browser: chromium (isolated)
   - user_data_dir: temp (session-only)
   - headless: true
   - no_sandbox: false

5. Navigation
   - goto(url)
   - wait_for_load_state("load")

6. Field Resolution
   - field_id enum → selector mapping (server-side)
   - find element
   - verify element exists and is interactive

7. Sample Text Typing
   - sample_value_id enum → sample_text
   - keyboard.type(sample_text)
   - sample_text는 절대 저장하지 않음

8. Screenshot Prevention
   - ❌ screenshot 금지
   - ❌ HAR 기록 금지

9. Context Cleanup
   - close browser
   - delete temp user_data_dir
   - clear cookies/cache/history

10. Response Return
    - status: completed
    - typed: true
    - lifecycle: {opened, typed, closed}
    - no raw input/selector in response
```

### Approval Requirements

```python
ApprovalGate:
  - action: browser.open_type_close_controlled
  - risk: medium
  - reason: actual DOM modification
  - token: required
  - status: waiting_approval → queued (on mark_approved)
```

### Cleanup Contract

```python
Cleanup:
  - context_closed: true
  - browser_closed: true
  - temp_files_deleted: true
  - cookies_cleared: true
  - screenshots_not_taken: true
  - logs_sensitive_redacted: true
```

### 판정 기준

- ✅ PASS: 1→10 단계 모두 정의됨
- ❌ FAIL: approval gate 없음, cleanup 불명확

**판정**: ✅ PASS_LIFECYCLE_완료

---

## STEP 6. 다음 구현 지시문

### Phase 1: browser.open_type_close_controlled 구현

**기준**:
1. browser.plan_type 상태: ✅ 완료
2. browser.open_click_close_controlled 상태: ✅ 완료 (smoke PASS)
3. 정책: ✅ 확정 (preflight 완료)

**지시문**:
```python
def open_type_close_controlled(
    field_id: str,              # enum: "sample_text_field"
    sample_value_id: str,       # enum: "sample_text_short"
    url: str = "https://example.com",
) -> dict:
    """
    Isolated context에서 sample text만 입력.
    
    1. approval 필수 (medium risk)
    2. enum 검증
    3. isolated browser 생성
    4. sample text만 입력 (raw input 금지)
    5. 즉시 cleanup
    6. no password/token/secret
    7. no raw selector in response
    8. typed=true, lifecycle metadata만 반환
    """
```

**구현 대상 파일**:
- browser_tool/worker_backend.py (actual execution)
- browser_tool/mock_backend.py (dry_run)
- browser_tool/policy.py (unblock action)
- local_agent_redaction.py (response allowlist)
- local_agent_risk_policy.py (risk=medium 확인)
- tests/test_browser_open_type_close_controlled.py (신규)

### Phase 2: Smoke Test (실제 구현 완료 후)

**지시문**: BROWSER_ACTUAL_TYPE_SMOKE 승인

**테스트 범위**:
- dry_run=true with sample input
- actual execution with approval
- isolated context validation
- cleanup verification
- no password/token/secret logging

**성공 기준**:
- typed=true ✅
- lifecycle.opened=true ✅
- lifecycle.typed=true ✅
- lifecycle.closed=true ✅
- 샘플 텍스트만 입력됨 ✅
- 원본 sample_text 미저장 ✅
- raw selector 미반환 ✅

---

## STEP 7. 최종 보고

### 작업 내용

**이전 완료**:
- ✅ browser.plan_type 구현
- ✅ browser.open_click_close_controlled 구현 & smoke PASS
- ✅ smoke_test marker cleanup policy 검증
- ✅ DB-backed registration code

**이번 preflight**:
- ✅ actual type 위험도 확정: MEDIUM
- ✅ approval gate 정책 확정
- ✅ 입력값 정책: enum-based sample only
- ✅ field selector: enum + redacted
- ✅ lifecycle 설계: 10단계
- ✅ cleanup contract 명시
- ✅ 다음 구현 지시문 확정

### 현재 기준

| 항목 | 상태 |
|------|------|
| browser.plan_type | ✅ 완료 (a9945f1) |
| browser.open_click_close_controlled | ✅ 완료 (smoke PASS) |
| DB backend | ✅ 정상 |
| smoke cleanup | ✅ 통과 |

### 정책 확정

| 항목 | 값 |
|------|-----|
| action | browser.open_type_close_controlled |
| risk | medium |
| approval required | YES |
| actual type | YES (enum sample only) |
| actual browser | YES (isolated context) |
| password/token/secret | NO (금지) |
| raw input storage | NO (금지) |
| raw selector response | NO (redacted) |
| lifecycle | 10-step designed |
| cleanup | automated |

### 보안 체크리스트

| 항목 | 상태 |
|------|------|
| raw input 미저장 | ✅ |
| password/token/secret 금지 | ✅ |
| raw selector 미반환 | ✅ |
| DOM detail 미노출 | ✅ |
| screenshot 금지 | ✅ |
| cookie/session/profile 격리 | ✅ |
| cleanup automation | ✅ |

### 다음 단계

**구현 지시문**: ORCHESTRATOR-LOCAL-AGENT-PC-BROWSER-OPEN-TYPE-CLOSE-CONTROLLED-IMPLEMENT-1

**Smoke 지시문**: BROWSER_ACTUAL_TYPE_SMOKE 승인 후 ORCHESTRATOR-LOCAL-AGENT-PC-BROWSER-OPEN-TYPE-CLOSE-CONTROLLED-SMOKE-1

**승인 필요**:
- medium risk action
- approval gate implementation
- isolated context lifecycle

---

## 🎯 최종 판정

### 🟢 **PASS_OPEN_TYPE_CLOSE_PREFLIGHT_READY**

모든 preflight 기준 충족:

✅ **STEP 1**: browser.plan_type 완료 확인
✅ **STEP 2**: actual type 위험도 = MEDIUM 확정
✅ **STEP 3**: 입력값 정책 = enum-based sample only
✅ **STEP 4**: field selector = enum + redacted
✅ **STEP 5**: lifecycle = 10단계 완전 설계
✅ **STEP 6**: 구현 지시문 명확
✅ **STEP 7**: 보안 체크리스트 완성

**결론**: browser.open_type_close_controlled의 구현 설계가 완료되었습니다.
다음 단계에서 실제 코드 구현을 진행할 수 있습니다.

---

**분석 완료**: 2026-05-06 23:57 UTC
