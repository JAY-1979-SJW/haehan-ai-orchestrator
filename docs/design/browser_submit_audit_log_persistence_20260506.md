# Design Document: Browser Submit Audit Log Persistence

**Document Date:** 2026-05-06  
**Status:** Design Phase (Pre-Implementation)  
**Scope:** Audit log writer module (no DB, no production paths)

---

## 1. 목적 (Purpose)

### Primary Goal
- Submit 전후 정책 검증, 미리보기, 사용자 승인, 제어된 제출 결과를 감사 가능하도록 저장
- 민감정보 원문 제외 (redacted payload만)
- Append-only JSONL 구조로 로그 무결성 보장

### Non-Goals (This Phase)
- 운영 DB 저장 (다음 단계)
- 실제 업무 사이트 submit 기능 (다음 단계)
- 로그 조회/검색 UI (다음 단계)
- 분석/리포팅 (다음 단계)

---

## 2. JSONL 구조 (Log Format)

### Overview
```
파일: audit.jsonl (또는 {validation_id}.jsonl)
구조: append-only
한 줄: 하나의 SubmitAuditEvent (JSON object)
```

### Example Event
```json
{
  "schema_version": "1.0",
  "event_id": "evt_20260506_001_abc123",
  "created_at": "2026-05-06T11:00:00Z",
  "validation_id": "smoke_real_001",
  "action_id": "browser.submit.policy_check",
  "site_id": "allowed_internal_mock_form",
  "form_id": "contact_form",
  "submit_button_id": "submit_button_id",
  "intent": "submit_contact_form",
  "preview_hash": "abcd1234...",
  "policy_verdict": "ALLOW",
  "risk_level": "high",
  "user_confirmed": true,
  "submitted": true,
  "submit_result": "success",
  "approved_by": "user_12345",
  "approved_at": "2026-05-06T11:00:15Z",
  "submit_timestamp": "2026-05-06T11:00:20Z",
  "redacted_payload": {
    "fields": [
      {"name": "email", "masked": true},
      {"name": "message", "value": "msg content"}
    ],
    "hidden_fields": [
      {"name": "csrf_token", "masked": true},
      {"name": "form_version", "value": "1.0"}
    ]
  },
  "result_summary": "Internal form submitted (no external navigation)",
  "error_reason": null,
  "metadata": {
    "browser": "chromium_headless",
    "network_isolation": "data_url",
    "external_navigation_detected": false
  }
}
```

---

## 3. Audit Event 필드 (Required Fields)

### Schema Version & IDs
| 필드 | 타입 | 설명 | 예제 |
|------|------|------|------|
| `schema_version` | string | Audit log schema version | "1.0" |
| `event_id` | string | Unique event identifier | "evt_20260506_001_abc123" |
| `created_at` | ISO8601 | Event creation timestamp | "2026-05-06T11:00:00Z" |
| `validation_id` | string | Link to validation request | "smoke_real_001" |

### Request Context
| 필드 | 타입 | 설명 |
|------|------|------|
| `action_id` | string | "browser.submit.policy_check" or "browser.submit.controlled_click" |
| `site_id` | string | Internal site ID |
| `form_id` | string | Form identifier |
| `submit_button_id` | string | Button element ID |
| `intent` | string | User intent (e.g., "submit_contact_form") |

### Policy & Preview
| 필드 | 타입 | 설명 | 값 |
|------|------|------|-----|
| `preview_hash` | string | SHA256 hash of preview | "abcd1234..." (64 chars) |
| `policy_verdict` | string | Policy result | "ALLOW" or "DENY" |
| `risk_level` | string | Risk assessment | "low" / "medium" / "high" |

### User Approval
| 필드 | 타입 | 설명 | 필수 |
|------|------|------|------|
| `user_confirmed` | bool | User clicked OK | YES |
| `approved_by` | string / null | User ID if confirmed | Nullable |
| `approved_at` | ISO8601 / null | Approval timestamp | Nullable |

### Submit Result
| 필드 | 타입 | 설명 | 값 |
|------|------|------|------|
| `submitted` | bool | Was form actually submitted | true/false |
| `submit_result` | string | Result status | "success" / "blocked" / "error" / "pending" |
| `submit_timestamp` | ISO8601 / null | When submit happened | Nullable |
| `error_reason` | string / null | Error message if failed | Nullable |

### Payload (Redacted)
| 필드 | 타입 | 설명 |
|------|------|------|
| `redacted_payload` | object | Form data (sensitive values masked) |
| `result_summary` | string | Human-readable result |

### Metadata
| 필드 | 타입 | 설명 |
|------|------|------|
| `metadata` | object | Additional context (browser type, isolation level, etc.) |

---

## 4. 민감정보 Redaction Rules

### 금지된 필드 (Never Store Raw)
```
password, passwd, pwd
token, access_token, refresh_token, api_key, apikey, api-key
secret, secrets
credential, credentials
session, sessionid, session_id
cookie, cookies
private_key, private-key, pkey
auth, authorization
bearer, jwt, signature
otp, totp, mfa, 2fa
card, cc_number, cvv, cvc
ssn, social_security
license_key, license-key
encryption_key, enc_key
```

### 처리 방식

**Option A: Masked (권장)**
```json
{"name": "password", "masked": true}
```

**Option B: Hashed (선택사항)**
```json
{"name": "api_token", "hash": "sha256:abc123..."}
```

**Option C: Safe Value (일부 필드)**
```json
{"name": "form_version", "value": "1.0"}
```

### Redaction 로직
1. 필드 이름이 금지 리스트에 있으면 → masked: true
2. 필드 값이 URL, email, phone 같은 민감 형식이면 → origin만 추출 또는 masked
3. 숨겨진 필드 중 non-sensitive (csrf_token, timestamp, version) → value 보존 가능
4. 중첩 dict/list의 민감 필드도 재귀적으로 처리

---

## 5. 구현 모듈 (Implementation)

### File: `ai_orchestrator/browser_tool/approval/submit_audit_log.py`

#### Dataclasses
```python
@dataclass
class SubmitAuditEvent:
    """Audit event for submit lifecycle."""
    schema_version: str
    event_id: str
    created_at: str  # ISO8601
    validation_id: str
    action_id: str
    site_id: str
    form_id: str
    submit_button_id: str
    intent: str
    preview_hash: str
    policy_verdict: str
    risk_level: str
    user_confirmed: bool
    submitted: bool
    submit_result: str  # "success" / "blocked" / "error" / "pending"
    redacted_payload: dict
    result_summary: str
    approved_by: str = None
    approved_at: str = None
    submit_timestamp: str = None
    error_reason: str = None
    metadata: dict = field(default_factory=dict)

@dataclass
class SubmitAuditWriteResult:
    """Result of audit event write."""
    success: bool
    path: str
    event_count: int  # Total events in file after write
    error_message: str = None
```

#### Functions
```python
def build_submit_audit_event(
    validation_id: str,
    action_id: str,
    site_id: str,
    form_id: str,
    submit_button_id: str,
    intent: str,
    policy_verdict: str,
    risk_level: str,
    preview_hash: str,
    user_confirmed: bool,
    submitted: bool,
    submit_result: str,
    redacted_payload: dict,
    result_summary: str,
    approved_by: str = None,
    submit_timestamp: str = None,
    error_reason: str = None,
    metadata: dict = None,
) -> SubmitAuditEvent:
    """Build audit event from components."""
    
def redact_audit_payload(payload: dict) -> dict:
    """Remove/mask sensitive data from payload."""
    # Returns redacted dict
    
def validate_submit_audit_event(event: SubmitAuditEvent) -> list[str]:
    """Validate event has all required fields.
    
    Returns:
        List of error messages (empty = valid)
    """
    
def serialize_audit_event(event: SubmitAuditEvent) -> str:
    """Convert event to JSON string (one line).
    
    Uses: sort_keys=True, ensure_ascii=False
    """
    
def append_submit_audit_event(
    path: Path,
    event: SubmitAuditEvent,
) -> SubmitAuditWriteResult:
    """Append event to JSONL file (append-only, no overwrite).
    
    Behavior:
        - If file doesn't exist, create it
        - If file exists, append to end
        - Never overwrite existing content
        - Parent directory must exist
    
    Raises:
        ValueError if event validation fails
        IOError if write fails
    """
    
def read_submit_audit_events(path: Path) -> list[dict]:
    """Read all events from JSONL file (test only).
    
    Returns:
        List of event dicts (parsed from JSON)
    
    Raises:
        FileNotFoundError if file doesn't exist
        ValueError if any line is not valid JSON
    """
```

---

## 6. 테스트 전략 (Testing Strategy)

### Scope
- Unit tests only (no integration, no DB)
- Use `tmp_path` for file operations
- No external network
- No docker/production paths

### Test File: `tests/test_browser_submit_audit_log_persistence_20260506.py`

#### Test Categories

**1. Event Building**
- Build event with all required fields
- Build with optional fields (None/default)
- Build with custom metadata

**2. Validation**
- All required fields present → pass
- Missing preview_hash → fail
- Missing policy_verdict → fail
- Missing submitted field → fail
- Missing schema_version → fail
- Missing event_id → fail
- Missing created_at → fail
- submit_result not in [success, blocked, error, pending] → fail

**3. Redaction**
- password/token/secret/cookie → masked: true
- Safe hidden fields (csrf_token, version) → value preserved
- Nested dict/list with sensitive keys → redacted
- No raw password/token in output

**4. Serialization**
- Event → JSON string (one line)
- Parseable back to dict
- sort_keys=True applied
- UTF-8 (ensure_ascii=False) supported

**5. Append-Only**
- Write first event → file created
- Write second event → appended (not overwritten)
- Read file → both events present
- No data loss

**6. File Operations**
- Path must be Path-like (pathlib.Path)
- Parent directory must exist (create file, not dirs)
- Multiple events preserve order
- Empty file handled
- Permission errors handled

**7. Interop with Existing Modules**
- Can accept SubmitPolicyResult fields
- Can accept SubmitPreviewBundle.preview_hash
- Can accept ControlledSubmitResult fields
- Can combine all three into one audit event

**8. Production Safeguards**
- No actual file created in production paths
- Test uses tmp_path only
- Audit path constants defined but not written to
- No actual submit execution
- No network calls

---

## 7. Integration Points (Future)

### When Combined with Existing Modules

**Flow 1: Policy Check**
```
SubmitValidationRequest
  ↓
validate_submit_policy()
  ↓ SubmitPolicyResult
build_submit_audit_event(
    policy_verdict=result.verdict,
    risk_level=result.risk_level,
    ...
)
  ↓
append_submit_audit_event(path, event)
```

**Flow 2: Preview Generation**
```
SubmitPreviewInput
  ↓
build_submit_preview()
  ↓ SubmitPreviewBundle
build_submit_audit_event(
    preview_hash=bundle.audit.preview_hash,
    ...
)
```

**Flow 3: Controlled Submit**
```
ControlledSubmitInput
  ↓
build_controlled_submit_result()
  ↓ ControlledSubmitResult
build_submit_audit_event(
    submitted=result.submitted,
    submit_result=result.submit_result,
    submit_timestamp=result.submit_timestamp,
    ...
)
  ↓
append_submit_audit_event(path, event)
```

---

## 8. 운영 경로 (Production Paths - Future)

### Defined but NOT Written This Phase
```python
# Placeholder constants (not used in test)
AUDIT_LOG_BASE_PATH = "/var/log/haehan/browser_submit"
AUDIT_LOG_FILE_PATTERN = "{validation_id}_audit.jsonl"
ARCHIVE_PATH = "{base_path}/archive"
```

### Next Phase (DB Persistence)
- Read from JSONL file
- Insert into audit_events table
- Setup log rotation
- Setup log archival

---

## 9. Error Handling

### Validation Errors
- Missing required field → ValueError (clear message listing missing fields)
- Invalid submit_result value → ValueError
- Invalid preview_hash format → ValueError

### Write Errors
- Path doesn't exist → Create file (parent must exist)
- File permission denied → IOError
- Disk full → IOError
- Invalid JSON serialization → ValueError

### Read Errors
- File doesn't exist → FileNotFoundError
- Invalid JSON line → ValueError (with line number)

---

## 10. Non-Functional Requirements

| Requirement | Detail |
|-------------|--------|
| Append-Only | Never overwrite existing lines |
| Immutability | Event once written cannot be modified |
| Traceability | preview_hash links back to preview |
| Redaction | No raw secrets in any field |
| JSON Compatible | Valid JSON per line |
| Sortable | sort_keys=True for consistency |
| Timestamp | ISO8601 for machine readability |
| Idempotency | Event ID ensures uniqueness |

---

## 11. Future Extensions (Not This Phase)

- [ ] Log compression/rotation (gzip, numbered files)
- [ ] Central log aggregation
- [ ] SQL import (audit_events table)
- [ ] Query/search API
- [ ] Dashboard visualization
- [ ] Alert triggers
- [ ] Retention policy
- [ ] Compliance reporting

---

**Design Frozen:** 2026-05-06  
**Approval Status:** Awaiting Implementation
