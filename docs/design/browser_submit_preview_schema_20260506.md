# Browser Submit Preview Schema - 설계 문서
**Date**: 2026-05-06  
**Status**: DESIGN COMPLETE (BROWSER_SUBMIT_PREVIEW_SCHEMA_1)

---

## 1. 목적

submit 실행 기능을 구현하지 않고, submit 전에 사용자에게 보여줄 preview schema를 구현한다.

Submit은 고위험 작업(risk_level=HIGH, requires_approval=TRUE)이므로:
- 제출 전 사용자가 어떤 데이터를 제출하는지 명확히 볼 수 있어야 한다.
- 정책/검증 결과를 이해할 수 있어야 한다.
- 감시/감사 목적으로 완전한 기록이 남아야 한다.

---

## 2. 3계층 Preview 구조

### 2.1 Layer 1: UserPreviewSummary (사용자 승인 화면)

사용자가 **처음 보는** 짧은 승인 화면용 데이터.

**목표**: "뭘 제출하는 거예요?" 질문에 5초 안에 답하기

```python
@dataclass
class UserPreviewSummary:
    site_id: str                        # "allowed_internal_mock_form"
    form_title: str                     # "내부 연락처 양식 제출"
    target_description: str             # "제목: contact_form | 의도: submit_contact_form"
    field_summary: dict[str, str]       # {"email": "test@e****.com", "message": "[텍스트 입력]"}
    risk_level: str                     # "high"
    risk_description: str               # "제출된 데이터는 복구할 수 없습니다"
    is_destructive: bool                # False
    destructive_warning: str            # ""
    requires_confirmation: bool         # True
    confirmation_question: str          # "정말 제출하시겠습니까?"
```

**UI 표현 예시**:
```
┌─────────────────────────────────────┐
│  내부 연락처 양식 제출             │
├─────────────────────────────────────┤
│ 제목: contact_form                  │
│ 의도: submit_contact_form           │
│                                     │
│ 제출 필드:                          │
│  • email: test@e****.com            │
│  • message: [텍스트 입력]           │
│                                     │
│ ⚠️  위험도: HIGH                    │
│    제출된 데이터는 복구할 수 없습니다 │
│                                     │
│ [ 자세히 보기 ] [제출] [취소]       │
└─────────────────────────────────────┘
```

### 2.2 Layer 2: UserPreviewDetails (자세히 보기)

사용자가 **"자세히 보기"를 눌렀을 때** 보는 정책/검증 상세 데이터.

**목표**: "왜 이 제출이 안전한가요?" 질문에 상세하게 답하기

```python
@dataclass
class UserPreviewDetails:
    policy_verdict: str                 # "ALLOW"
    policy_reasons: list[str]           # ["모든 조건 충족"]
    form_id: str                        # "contact_form"
    submit_button_id: str               # "submit_btn"
    intent: str                         # "submit_contact_form"
    fields_display: list[dict]          # [{"name": "email", "display": "test@e****.com", "masked": True}]
    hidden_fields_count: int            # 1
    validation_checks: dict[str, str]   # {"allowlist_verdict": "FOUND", ...}
```

**UI 표현 예시**:
```
┌─────────────────────────────────────┐
│  정책 검증 상세                    │
├─────────────────────────────────────┤
│ 정책 결과: ALLOW                    │
│ 근거: 모든 조건 충족                │
│                                     │
│ 폼 정보:                            │
│  • Form ID: contact_form            │
│  • Button ID: submit_btn            │
│  • Intent: submit_contact_form      │
│                                     │
│ 제출 필드 (마스킹됨):               │
│  □ email: test@e****.com            │
│  □ message: [텍스트 입력]           │
│  □ Hidden field 1개                 │
│                                     │
│ 검증 결과:                          │
│  ✓ Allowlist: FOUND                 │
│  ✓ Origin: MATCH                    │
│  ✓ Form: FOUND                      │
│  ✓ Intent: ALLOWED                  │
│  ✓ Fields: SAFE                     │
│  ✓ Prompt Injection: PASS           │
│  ✓ Preview: SHOWN                   │
│  ○ User Confirm: PENDING            │
│                                     │
│ [ 제출 ] [ 취소 ]                  │
└─────────────────────────────────────┘
```

### 2.3 Layer 3: AuditPreviewRecord (감사/추적)

**관리자/감사/사고 추적용** 전체 기록 데이터. 사용자에게는 보이지 않음.

**목표**: "언제 누가 뭘 제출하려고 했는가?" 완벽한 기록

```python
@dataclass
class AuditPreviewRecord:
    validation_id: str                  # validator로부터 받음
    site_id: str
    form_id: str
    intent: str
    redacted_payload: dict              # {"fields": [{"name": "email", "value": "r*d*ct*d"}], ...}
    preview_hash: str                   # SHA256(canonical_payload)
    preview_timestamp: str              # "2026-05-06T10:30:45.123Z"
    policy_verdict: str                 # "ALLOW"
    risk_level: str                     # "high"
    submitted: bool = False
    submit_timestamp: str = ""
    submit_result: str = None
    approved_by: str = None
    approved_at: str = None
    approval_notes: str = ""
```

**저장 위치**: 감사 로그 DB (향후 단계에서 구현)

---

## 3. 사용자 화면 설계 원칙

### 3.1 Summary 화면
- **짧음**: 핵심 정보만 (필드 5개 미만)
- **명확함**: "뭘 제출하는가"를 한눈에
- **경고**: 위험도 명시, 되돌릴 수 없음 표시
- **행동**: 자세히 보기 / 제출 / 취소 3개 버튼

### 3.2 Details 화면
- **모든 필드 표시** (마스킹 적용)
- **검증 결과** 전체 표시
- **정책 근거** 명확히
- **숨겨진 필드 개수** 표시 (원문 금지)

---

## 4. Redaction/Masking 기준

### 4.1 원문 금지 필드 (Denied Keywords)
```
password, passwd, pwd
token, access_token, session_token, jwt
secret, api_secret, client_secret
key, api_key, private_key
cookie, session_id
authorization, bearer
otp, 2fa
pin, cvv, security_code
```

**처리 방식**: `****` 또는 `[숨겨진 필드]`

**예시**:
```
Field: password
Value: "secret123"
Display: "****"
```

### 4.2 마스킹 필드 (Sensitive PII)

| 필드 유형 | 원문 | 마스킹 |
|----------|------|--------|
| email | test@example.com | test@e****.com |
| phone | 010-1234-5678 | 010-****-5678 |
| business_id | 123-45-67890 | 123-**-67890 |
| url | https://internal.mock/admin | [URL 입력] |
| 긴 텍스트 (>100자) | Lorem ipsum dolor ... | [텍스트 입력 3줄] |

### 4.3 Hidden Field
- **절대 원문 표시 금지**
- **필드명 표시 금지** (또는 generic "Hidden field N")
- **개수만 표시** (audit에는 count만 저장)

**예시**:
```
summary: "Hidden field 1개"
details: "hidden_fields_count: 1"
audit: {"hidden_fields_count": 1} (원문 미포함)
```

### 4.4 표시 가능
- 회사명, 공사명, 프로젝트명
- 금액 (단위 포함)
- 날짜
- 선택지 (옵션 선택 값)
- 아이디/로그인명 (비밀번호와 분리되면)

---

## 5. Preview Hash 정책

### 5.1 목적
- **Deterministic**: 같은 입력 → 같은 hash
- **Immutable**: audit log에 저장 후 검증용
- **Canonical**: dict key 순서 무관
- **Redacted basis**: 원문이 아닌 redacted payload 기준

### 5.2 Hash 계산

```python
def canonical_preview_payload(payload: dict) -> str:
    """Canonical JSON with sorted keys"""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

def compute_preview_hash(payload: dict) -> str:
    """SHA256(canonical_payload)"""
    canonical = canonical_preview_payload(payload)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()
```

### 5.3 예시

```
Input:
{
  "site_id": "allowed_internal_mock_form",
  "form_id": "contact_form",
  "intent": "submit_contact_form",
  "fields": [
    {"name": "email", "value": "test@example.com"},
    {"name": "message", "value": "Hello"}
  ],
  "hidden_fields_count": 1
}

Redacted:
{
  "site_id": "allowed_internal_mock_form",
  "form_id": "contact_form",
  "intent": "submit_contact_form",
  "fields": [
    {"name": "email", "value": "test@e****.com", "masked": true},
    {"name": "message", "value": "Hello", "masked": false}
  ],
  "hidden_fields_count": 1
}

Canonical:
{"fields":[{"masked":true,"name":"email","value":"test@e****.com"},{"masked":false,"name":"message","value":"Hello"}],"form_id":"contact_form","hidden_fields_count":1,"intent":"submit_contact_form","site_id":"allowed_internal_mock_form"}

Hash:
a7f3c8d2e5b1f4g9h2i3j4k5l6m7n8o9p0q1r2s3t4u5v6w7x8y9z0a1b2c3d4
```

### 5.4 Hash 불변성

```python
# Same input → Same hash (regardless of order)
payload1 = {"a": 1, "b": 2}
payload2 = {"b": 2, "a": 1}
compute_preview_hash(payload1) == compute_preview_hash(payload2)  # True
```

---

## 6. Submit과의 관계

### 6.1 이번 단계 (BROWSER_SUBMIT_PREVIEW_SCHEMA_1)
- ✓ Preview schema 정의
- ✓ Preview 생성 함수 구현
- ✓ Preview hash 계산
- ✗ 실제 submit 실행 (금지)

### 6.2 다음 단계 (BROWSER_SUBMIT_MOCK_ACTION_1)
- preview를 받아서 사용자 승인 처리
- 승인 후 실제 submit 실행 (여전히 mock)
- preview_hash와 audit log 연결

### 6.3 향후 단계
- 실제 업무 사이트와 연결
- 감사 로그 저장 및 조회

---

## 7. 금지 조건

| 항목 | 상태 |
|------|------|
| 실제 submit 실행 | ✗ 금지 |
| 실제 click 실행 | ✗ 금지 |
| 실제 브라우저 실행 | ✗ 금지 |
| 비밀번호/OTP/인증서/토큰 원문 표시 | ✗ 금지 |
| 외부 실제 업무 사이트 값 사용 | ✗ 금지 |
| root 레벨 문서 생성 | ✗ 금지 |
| action registry 연결 | ✗ 금지 |
| task_executor 연결 | ✗ 금지 |
| DB write | ✗ 금지 |
| docker 작업 | ✗ 금지 |

---

## 8. 파일 구성

### 8.1 모듈
```
ai_orchestrator/browser_tool/submit/submit_preview.py
  - SubmitPreviewInput
  - UserPreviewSummary
  - UserPreviewDetails
  - AuditPreviewRecord
  - SubmitPreviewBundle
  - mask_field_value()
  - redact_fields()
  - canonical_preview_payload()
  - compute_preview_hash()
  - build_submit_preview()
```

### 8.2 테스트
```
tests/test_browser_submit_preview_schema_20260506.py
  - 17개 테스트 케이스
```

### 8.3 설계 문서
```
docs/design/browser_submit_preview_schema_20260506.md
  - 이 문서
```

---

## 9. 구현 체크리스트

- [x] SubmitPreviewInput 클래스 정의
- [x] UserPreviewSummary 클래스 정의
- [x] UserPreviewDetails 클래스 정의
- [x] AuditPreviewRecord 클래스 정의
- [x] SubmitPreviewBundle 클래스 정의
- [x] mask_field_value() 구현
- [x] redact_fields() 구현
- [x] canonical_preview_payload() 구현
- [x] compute_preview_hash() 구현
- [x] build_submit_preview() 구현
- [ ] Unit tests (STEP 6)
- [ ] Integration tests (STEP 6)

---

## Document Version
- **Version**: 1.0 (Design Complete)
- **Date**: 2026-05-06
- **Status**: Ready for Testing (STEP 6)
