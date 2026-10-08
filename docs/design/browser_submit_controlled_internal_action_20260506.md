# Browser Submit Controlled Internal Action - 설계 문서
**Date**: 2026-05-06  
**Status**: DESIGN COMPLETE (BROWSER_SUBMIT_CONTROLLED_INTERNAL_ACTION_1)

---

## 1. 목적

Mock-only submit을 넘어, controlled internal submit action을 구현한다.

실제 업무 사이트 제출이 아니면서도, policy validator → preview → user confirmation → controlled internal submit 흐름을 내부 테스트 환경에서만 안전하게 검증한다.

---

## 2. 제출 흐름

```
┌─────────────────────────────────────────────────────────────┐
│ STEP 1: Policy Validation                                   │
│ validator.validate_submit_policy()                          │
│ Result: SubmitPolicyResult (ALLOW/DENY)                     │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ↓ (ALLOW only)
┌─────────────────────────────────────────────────────────────┐
│ STEP 2: Preview Generation                                  │
│ preview.build_submit_preview()                              │
│ Result: SubmitPreviewBundle (summary + details + audit)     │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 3: User Confirmation                                   │
│ preview_shown=True + user_confirmed=True                    │
│ Result: User explicit approval                              │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ↓ (user_confirmed=True only)
┌─────────────────────────────────────────────────────────────┐
│ STEP 4: Controlled Internal Submit                          │
│ controlled.build_controlled_submit_result()                 │
│ Checks:                                                     │
│  - origin is internal.mock/localhost/data URL              │
│  - no blocked domain keywords                               │
│  - form_id/button_id match                                  │
│ Result: ControlledSubmitResult (no actual submit)           │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 5: Audit-Safe Result                                   │
│ - submitted=True/False (pending=success/blocked)            │
│ - redacted_payload (no original secrets)                    │
│ - preview_hash (for validation tracking)                    │
│ - lifecycle (decision timestamps)                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 허용되는 Submit 대상

### 3.1 Internal Mock
```
https://internal.mock/form
https://internal.mock:8080/form
```

### 3.2 Localhost
```
http://localhost/form
http://localhost:3000/form
http://127.0.0.1/form
http://127.0.0.1:5000/form
```

### 3.3 Data URL
```
data:text/html,<form><input name="email" value="test@example.com"></form>
```

### 3.4 Fixture HTML
```
tests/fixtures/browser_controlled_submit_form_20260506.html
```

---

## 4. 금지되는 Submit 대상

### 4.1 실제 업무 사이트
```
✗ 조달청 (bid.go.kr, tendernet.kr)
✗ G2B (g2b.go.kr)
✗ 나라장터 (www.korea.go.kr)
✗ 공공기관 (정부, 지자체, 공기업)
✗ 민간 업무 (쇼핑, 결제, 은행)
```

### 4.2 민감한 폼
```
✗ 로그인 페이지
✗ 비밀번호 입력
✗ OTP/인증서 입력
✗ 토큰/세션 입력
```

### 4.3 실제 트랜잭션
```
✗ 결제/송금
✗ 계약/입찰 제출
✗ 삭제/취소/확정/승인 액션
✗ DB write 발생 URL
```

---

## 5. ControlledSubmitInput (입력)

```python
@dataclass
class ControlledSubmitInput:
    """Controlled submit request (post-approval)"""
    
    # From preview stage
    preview_bundle: SubmitPreviewBundle
    
    # User action
    user_confirmed: bool = False
    user_id: str = ""
    
    # Origin restrictions
    allow_internal_mock: bool = True
    allow_localhost: bool = True
    allow_data_url: bool = True
```

---

## 6. ControlledSubmitResult (출력)

```python
@dataclass
class ControlledSubmitResult:
    """Controlled internal submit result (no actual submit, no DB write)"""
    
    # Identifiers
    preview_hash: str                   # SHA256 from preview
    validation_id: str                  # validator ID
    
    # Status
    submitted: bool = False             # True = allowed, False = blocked
    submit_timestamp: str = ""          # ISO8601 if allowed, "" if blocked
    
    # Result
    submit_result: str = "pending"      # "pending", "success", "blocked", "error"
    error_reason: str = ""              # reason if blocked
    
    # Audit record
    audit_record: dict[str, Any] = {}   # redacted payload + decision
    
    # Lifecycle
    lifecycle: dict[str, str] = {}      # timestamps for each decision point
```

### 6.1 Submit Result Values

| Value | Meaning | submitted |
|-------|---------|-----------|
| success | 모든 조건 통과, controlled internal submit 허용 | True |
| blocked | 조건 불일치, submit 거부 | False |
| pending | 아직 결정 안 함 | False |
| error | 예상 외 오류 | False |

---

## 7. 차단 조건

Submit이 차단되는 경우:

```
1. user_confirmed=False
   → "user not confirmed"

2. preview_hash 없음
   → "preview_hash missing"

3. policy_verdict != "ALLOW"
   → "policy_verdict not ALLOW: {verdict}"

4. Origin not controlled internal
   → "origin not controlled internal: {url}"

5. 차단 도메인 키워드 포함
   Keywords:
   - 조달 (bid, tender)
   - g2b (government-to-business)
   - 나라장터 (national procurement)
   - 결제 (payment)
   - 송금 (transfer)
   - 계약 (contract)
   - 입찰 (bidding)
   - 삭제 (delete)
   - 취소 (cancel)
   - 확정 (confirm)
   - 승인 (approve)

6. Form ID / Button ID에 차단 키워드
   → "blocked keyword '{keyword}' in form_id/submit_button_id"
```

---

## 8. Lifecycle 추적

Submit 결정의 각 단계별 타임스탐프:

```python
lifecycle = {
    "preview_timestamp": "2026-05-06T10:00:00Z",    # 미리보기 생성
    "confirmation_check": "2026-05-06T10:05:00Z",   # 사용자 확인 검증
    "origin_check": "2026-05-06T10:05:01Z",         # Origin 검증 (차단시 비움)
    "domain_check": "2026-05-06T10:05:02Z",         # 도메인 키워드 검증 (차단시 비움)
}
```

---

## 9. Audit Record (감사)

실제 submit은 아니지만, 감시/감사 목적의 완전한 기록:

```python
audit_record = {
    "validation_id": "val_123",
    "site_id": "allowed_internal_mock_form",
    "form_id": "contact_form",
    "intent": "submit_contact_form",
    "preview_hash": "abc123hash",
    "policy_verdict": "ALLOW",
    "redacted_payload": {
        "fields": [{"name": "email", "value": "test@e****m.com"}],
        "hidden_fields_count": 1
    },
    "user_confirmed": True,
    "user_id": "user_456",
}
```

**중요**: redacted_payload는 원문 금지. 마스킹된 값만 저장.

---

## 10. 실제 Submit과의 차이

| 항목 | Controlled Internal | 실제 Submit |
|------|-------------------|-----------|
| 네트워크 호출 | ✗ NO | ✓ YES |
| 브라우저 실행 | ✗ NO (추후 추가 가능) | ✓ YES |
| DB write | ✗ NO | ✓ YES |
| 실제 부작용 | ✗ NO | ✓ YES |
| Origin 제한 | ✓ internal.mock/localhost | ✗ unrestricted |
| Keyword 검증 | ✓ strict | ✗ none |
| 사용 목적 | 테스트/검증 | 실제 운영 |

---

## 11. 구현 체크리스트

- [x] ControlledSubmitInput dataclass
- [x] ControlledSubmitResult dataclass
- [x] is_controlled_internal_origin() function
- [x] get_blocking_reason() function
- [x] build_controlled_submit_result() function
- [x] 38개 test case
- [x] 차단 조건 10가지 구현
- [x] 도메인 키워드 검증
- [x] Lifecycle 추적
- [x] Audit record 생성

---

## 12. 보안 원칙

### 12.1 Default Deny
- 조건 중 하나라도 실패하면 차단
- 명시적 허용만 통과

### 12.2 Controlled Origin Only
- internal.mock/localhost/data URL만 허용
- 외부 네트워크 차단
- 도메인 키워드 차단

### 12.3 Redaction Only
- Audit에는 redacted payload만 저장
- 원문 값 절대 노출 금지
- Preview hash로 검증

### 12.4 No Side Effects
- 순수 판정 함수
- 실제 submit 없음
- DB write 없음
- 환경 변경 없음

---

## 13. 파일 구성

```
ai_orchestrator/browser_tool/submit/controlled_submit.py (269줄)
  - ControlledSubmitInput
  - ControlledSubmitResult
  - is_controlled_internal_origin()
  - get_blocking_reason()
  - build_controlled_submit_result()

tests/test_browser_submit_controlled_internal_20260506.py (330줄)
  - 38개 test case
  - 7개 test class
  - Blocking, origin, lifecycle, side effects 검증

docs/design/browser_submit_controlled_internal_action_20260506.md (이 파일)
```

---

## Document Version
- **Version**: 1.0 (Design Complete)
- **Date**: 2026-05-06
- **Status**: Ready for Deployment (STEP 8+)
