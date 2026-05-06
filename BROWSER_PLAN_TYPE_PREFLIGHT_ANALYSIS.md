# Browser.plan_type Preflight Analysis

**목표**: browser.plan_type의 설계 및 정책 확정 (코드 수정 없음)

**현재 단계**: Preflight (정책/위험도/입력값 redaction/테스트 기준만 확정)

---

## STEP 1: browser.plan_type 역할 정의

### 목표
입력 계획만 반환. 실제 입력 없음.

### 기능
- ✅ HTML 요소 검사 (selector 제외)
- ✅ 입력 가능한 field 식별
- ✅ 입력 계획 (field_id, field_role) 반환
- ✅ 샘플 입력값 제안 (내부 고정값만)
- ❌ 실제 입력 실행 금지
- ❌ 브라우저 실행 금지
- ❌ DOM 접근 금지
- ❌ 입력값 저장 금지

### Response Schema
```json
{
  "success": true,
  "action": "browser.plan_type",
  "task_id": "task-123",
  "dry_run": true,
  "typed": false,
  "field_id": "sample_text_field",
  "field_role": "text_input",
  "sample_value_id": "sample_text_short",
  "sample_text": "[redacted]",
  "input_redacted": true,
  "requires_approval": true
}
```

### 판정 기준
- ✅ PASS: plan-only로 제한, typed=false, 브라우저 미실행
- ❌ FAIL: 실제 type 포함, DOM 접근, screenshot

---

## STEP 2: Risk Assessment

### 위험도: **LOW** (입력 없음)

| 항목 | 평가 |
|------|------|
| 실제 입력 | ❌ 없음 |
| 브라우저 실행 | ❌ 없음 |
| DOM 접근 | ❌ 없음 |
| Screenshot | ❌ 없음 |
| 입력값 저장 | ❌ 없음 |
| Network 요청 | ❌ 없음 |
| 파일 생성 | ❌ 없음 |

### 정책 검증

**In-browser validation (Playwright)**
- Dry_run: MockBackend 사용 (DOM 접근 없음)
- Actual: 금지 (browser.plan_type은 dry_run only)

**Server-side validation**
- Field allowlist: sample_text_field, sample_search_field 만
- Field_role allowlist: text_input, search_input 만
- Value allowlist: 내부 enum (sample_text_short, sample_text_long 등)
- No raw input processing

### 판정 기준
- ✅ PASS: low-risk 확정, 실제 입력 없음
- ❌ FAIL: password/token/secret 관련 logic

---

## STEP 3: 입력값 정책 확정

### 허용 입력값

#### 1. Field ID (Server-side enum)
```python
ALLOWED_FIELD_IDS = {
    "sample_text_field",      # 일반 텍스트
    "sample_search_field",    # 검색
}
```

#### 2. Field Role (Server-side enum)
```python
ALLOWED_FIELD_ROLES = {
    "text_input",
    "search_input",
}
```

#### 3. Sample Values (Internal fixed values only)

```python
SAMPLE_VALUES = {
    "sample_text_short": "sample input",
    "sample_text_medium": "sample input with more content",
    "sample_number": "1234",
    "sample_date": "2026-05-06",
}
```

**규칙**:
- params.value는 초기 구현에서 금지 또는 enum 내부값만
- raw user input 미허용
- 사용자가 입력한 값 저장 금지

### 금지 입력값

| 항목 | 예 | 이유 |
|------|-----|------|
| Password | "mypassword" | 민감 정보 |
| Token | "sk-abcd1234" | 보안 위험 |
| Secret | "secret_key" | 노출 금지 |
| API Key | "api_key_xyz" | 자격증명 |
| 개인정보 | "010-1234-5678" | 규정 위반 |
| 자유 입력 | 사용자 입력 | 검증 불가 |
| 긴 텍스트 | 여러 줄 | 상태 저장 |

### Result Data Allowlist

**응답에 포함 가능**:
- ✅ field_id (enum from server)
- ✅ field_role (enum from server)
- ✅ sample_value_id (enum pointer)
- ✅ input_redacted: true
- ✅ typed: false
- ✅ requires_approval: true

**응답에 미포함**:
- ❌ raw input value
- ❌ sample_text (실제 값, redacted만 반환)
- ❌ selector/css_selector/xpath
- ❌ field name (raw)
- ❌ label/placeholder/element text
- ❌ coordinates
- ❌ DOM path

### 판정 기준
- ✅ PASS: raw input 미저장, enum 기반만 사용
- ❌ FAIL: raw value 포함, raw selector 반환

---

## STEP 4: Field/Target 정책 확정

### 허용 Field

```json
{
  "field_id": "sample_text_field",
  "field_role": "text_input",
  "is_required": true
}
```

```json
{
  "field_id": "sample_search_field",
  "field_role": "search_input",
  "is_required": false
}
```

### 허용 Targeting Method

| 방식 | 예 | 상태 |
|------|-----|------|
| field_id (enum) | "sample_text_field" | ✅ 허용 |
| field_role (enum) | "text_input" | ✅ 허용 |
| CSS selector | "#input-123" | ❌ 금지 |
| XPath | "//input[@id='x']" | ❌ 금지 |
| Placeholder | "Enter name" | ❌ 금지 |
| Label text | "Username" | ❌ 금지 |
| Coordinates | "[100, 200]" | ❌ 금지 |
| DOM path | "body > form > input" | ❌ 금지 |

### 판정 기준
- ✅ PASS: enum-based field_id/field_role만 사용
- ❌ FAIL: raw selector/XPath/coordinates 반환

---

## STEP 5: 보안 체크리스트

### Password/Token/Secret
- [ ] password 입력 선택지 없음
- [ ] token 저장 경로 없음
- [ ] secret key 로깅 금지
- [ ] raw input value 미저장

### Raw Value/Selector
- [ ] raw input string 미반환
- [ ] raw selector 미반환
- [ ] XPath 미반환
- [ ] CSS selector 미반환

### DOM/Screenshot
- [ ] DOM 접근 없음
- [ ] screenshot 생성 안 함
- [ ] 스크린 샷 저장 안 함

### Cookie/Session/Profile
- [ ] cookie 접근 불가
- [ ] session 저장 불가
- [ ] browser profile 생성 안 함
- [ ] 상태 persistence 없음

### 운영 DB
- [ ] DB write 금지
- [ ] schema 변경 금지
- [ ] user data 저장 금지

### 판정 기준
- ✅ PASS: 모든 금지 항목 준수
- ❌ FAIL: 하나라도 위반

---

## STEP 6: 다음 단계 로드맵

### 단계별 구현 순서

#### Phase 1: browser.plan_type (현재 preflight)
- [x] 역할 정의 (plan-only)
- [x] Risk assessment (low)
- [x] 입력값 정책 확정 (enum-based)
- [x] Field 정책 확정 (allowlist)
- [x] 보안 체크리스트 작성
- [ ] 실제 구현 (다음 단계)

#### Phase 2: browser.plan_type 구현
```python
def plan_type(
    field_id: str,           # enum: "sample_text_field"
    sample_value_id: str,    # enum: "sample_text_short"
) -> dict:
    """입력 계획 반환 (실제 입력 없음)."""
    return {
        "typed": False,
        "field_id": field_id,
        "field_role": FIELD_ROLES[field_id],
        "sample_value_id": sample_value_id,
        "input_redacted": True,
        "requires_approval": True
    }
```

#### Phase 3: browser.open_type_close_controlled (후속)
- 실제 type 입력 (approval 필수)
- Field 검증 강화
- 에러 처리

### 구현 지시문 (다음 단계)
- ✅ browser.plan_type: dry_run only, no DOM access, enum-based
- ⚠️ browser.open_type_close_controlled: approval required, strong validation
- ❌ password/token/secret: 설계 단계부터 금지

### Approval 필요 여부
- browser.plan_type: **NO** (plan-only, 브라우저 미실행)
- browser.open_type_close_controlled: **YES** (실제 입력 실행)

---

## STEP 7: 테스트 기준 (구현 시)

### Unit Tests
```python
def test_plan_type_valid_field():
    """Allowed field_id만 허용."""
    assert plan_type("sample_text_field", "sample_text_short") is not None
    
def test_plan_type_invalid_field():
    """Unknown field_id 거부."""
    with pytest.raises(ValueError):
        plan_type("invalid_field", "sample_text_short")
        
def test_plan_type_no_raw_input():
    """Raw input 미저장."""
    result = plan_type("sample_text_field", "sample_text_short")
    assert result["input_redacted"] == True
    assert "raw_value" not in result
```

### Integration Tests
```python
def test_plan_type_dry_run_only():
    """browser.plan_type은 dry_run=true만 허용."""
    response = client.post(
        "/browser/plan_type",
        json={"field_id": "sample_text_field", "dry_run": False}
    )
    assert response.status_code == 400  # Actual execution not allowed
```

### Security Tests
```python
def test_no_password_field():
    """password field 없음."""
    assert "password_field" not in ALLOWED_FIELD_IDS
    
def test_no_secret_in_response():
    """Response에 secret 없음."""
    result = plan_type("sample_text_field", "sample_text_short")
    assert "secret" not in result
    assert "token" not in result
```

---

## 최종 판정

### 현재 상태
- ✅ STEP 1: browser.plan_type 역할 정의 완료
- ✅ STEP 2: Risk assessment (LOW) 확정
- ✅ STEP 3: 입력값 정책 확정 (enum-based)
- ✅ STEP 4: Field/target 정책 확정 (allowlist)
- ✅ STEP 5: 보안 체크리스트 준비
- ✅ STEP 6: 다음 단계 로드맵 확정
- ✅ STEP 7: 테스트 기준 정의

### 최종 판정

## 🟢 **PASS_PLAN_TYPE_PREFLIGHT_READY**

모든 preflight 항목 통과:
- ✅ 역할 명확 (plan-only, 입력 없음)
- ✅ 위험도 낮음 (LOW, 브라우저 미실행)
- ✅ 입력값 정책 엄격 (enum-based, raw input 금지)
- ✅ Field 정책 제한적 (allowlist 기반)
- ✅ 보안 요구사항 명시
- ✅ 다음 단계 지시문 명확

**결론**: browser.plan_type의 구현 설계가 완료되었습니다.
다음 단계에서 실제 코드 구현을 진행할 수 있습니다.

---

## Appendix: 구현 체크리스트 (다음 단계)

### Router 엔드포인트
- [ ] POST /browser/plan_type (dry_run=true만)
- [ ] Validation: field_id enum check
- [ ] Validation: sample_value_id enum check
- [ ] Response: input_redacted=true, typed=false

### Schemas
- [ ] WorkerBrowserRequest.field_id
- [ ] WorkerBrowserRequest.sample_value_id
- [ ] WorkerBrowserResponse.input_redacted
- [ ] WorkerBrowserResponse.typed

### Policy
- [ ] policy.py: ALLOWED_ACTIONS_DRY_RUN에 "browser.plan_type" 추가
- [ ] policy.py: DISABLED_ACTIONS_ACTUAL에서 "browser.plan_type" 유지 (dry_run only)
- [ ] Enum definitions: FIELD_IDS, FIELD_ROLES, SAMPLE_VALUES

### Backend
- [ ] MockPlaywrightBackend.handle_browser_plan_type() 구현
- [ ] Input validation: enum check
- [ ] Output redaction: sensitive data exclude

### Tests
- [ ] test_plan_type_valid_field()
- [ ] test_plan_type_invalid_field()
- [ ] test_plan_type_dry_run_only()
- [ ] test_plan_type_no_raw_input()
- [ ] test_plan_type_response_redacted()
