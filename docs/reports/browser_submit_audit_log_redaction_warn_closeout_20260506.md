# Browser Submit Audit Log Redaction Warning Closeout

**작성일:** 2026-05-06  
**타스크:** BROWSER_SUBMIT_AUDIT_LOG_REDACTION_WARN_CLOSEOUT  
**상태:** ✓ 완료

---

## 1. 작업 목적

전체 감사 보고서(browser_submit_full_system_audit_push_check_20260506.md)에서 비차단 경고로 기록된
`test_browser_submit_audit_log_persistence_20260506.py` 2개 fail을 분석하고, 최소 수정으로 해결합니다.

---

## 2. 기준 HEAD

| 항목 | 값 |
|------|-----|
| **작업 전 HEAD** | febac9f |
| **수정 대상** | ai_orchestrator/browser_tool/submit_audit_log.py |

---

## 3. 재현 결과 (STEP 2)

### 3.1 test_05_preserve_safe_hidden_fields

| 항목 | 내용 |
|------|------|
| **입력** | `{"csrf_token": "safe_token_123"}` |
| **기대값** | `"safe_token_123"` (보존) |
| **실제값** | `{"masked": True}` (마스킹됨) |
| **원인** | `if _is_sensitive_field_name()` 체크가 `elif field_name in SAFE_HIDDEN_FIELD_NAMES` 보다 먼저 평가됨. "token"이 `csrf_token`에 포함되어 SAFE 분기에 도달 불가 |
| **분류** | TEST_EXPECTATION_FIX_REQUIRED → 코드 순서 수정으로 해결 |

### 3.2 test_07_redact_list_items

| 항목 | 내용 |
|------|------|
| **입력** | `{"fields": [{"name": "email", "value": "test@test.com"}, {"name": "password", "value": "secret"}]}` |
| **기대값** | `fields[1]["value"] == {"masked": True}` |
| **실제값** | `fields[1]["value"] == "secret"` (원문 노출) |
| **원인** | list 내 dict 재귀 처리 시 `name` 키의 값이 민감한 필드명인 경우 `value` 마스킹 로직 없음 |
| **분류** | **FAIL_FIX_REQUIRED** (민감정보 원문이 JSONL에 남을 수 있음) |

---

## 4. utcnow Warning (STEP 3)

| 항목 | 내용 |
|------|------|
| **위치** | `submit_approval_state.py` 66, 107번 줄 |
| **submit_audit_log.py 해당 여부** | ✗ 없음 (`datetime.now(timezone.utc)` 이미 사용 중) |
| **판정** | **WARN_EXTERNAL_DEPRECATION** (수정 금지 파일, 기능 영향 없음) |

---

## 5. Redaction 구조 감사 (STEP 4)

### 5.1 수정 전 문제

```python
# 문제 1: SAFE 체크가 SENSITIVE 체크 뒤에 위치
if field_name in SENSITIVE_FIELD_NAMES or any(  # csrf_token이 여기서 마스킹됨
    sensitive in field_name for sensitive in ["password", "token", ...]
):
    result[key] = {"masked": True}
elif field_name in SAFE_HIDDEN_FIELD_NAMES:  # 도달 불가
    result[key] = value

# 문제 2: list 내 dict에서 name 기반 마스킹 없음
result[key] = [
    redact_audit_payload(item) if isinstance(item, dict) else item
    # {"name": "password", "value": "secret"} → "secret" 그대로 남음
]
```

---

## 6. 최소 수정 내용 (STEP 5)

### 6.1 변경 파일

**ai_orchestrator/browser_tool/submit_audit_log.py** 만 수정

### 6.2 수정 사항 (3개)

**수정 1: `_is_sensitive_field_name()` 헬퍼 추출**
```python
def _is_sensitive_field_name(field_name: str) -> bool:
    return field_name in SENSITIVE_FIELD_NAMES or any(
        sensitive in field_name
        for sensitive in ["password", "token", "secret", "key", "cookie"]
    )
```

**수정 2: `_redact_list_item()` 추가 — name 기반 마스킹**
```python
def _redact_list_item(item: object) -> object:
    if not isinstance(item, dict):
        return item
    name_val = item.get("name", "")
    if isinstance(name_val, str) and _is_sensitive_field_name(name_val.lower()):
        result = {k: v for k, v in item.items()}
        if "value" in result:
            result["value"] = {"masked": True}
        return result
    return redact_audit_payload(item)
```

**수정 3: `redact_audit_payload()` 순서 변경**
```python
# SAFE 체크를 먼저 수행 (순서 변경)
if field_name in SAFE_HIDDEN_FIELD_NAMES:
    result[key] = value                     # csrf_token 보존
elif _is_sensitive_field_name(field_name):
    result[key] = {"masked": True}
```

### 6.3 변경 원칙 준수

- ✓ 새 기능 추가 없음
- ✓ DB/API 연결 없음
- ✓ schema 변경 없음
- ✓ 기존 모듈 변경 없음 (submit_audit_log.py 내부만)
- ✓ production submit 없음

---

## 7. 테스트 재실행 결과 (STEP 6)

### 7.1 audit_log_persistence 테스트

```
python3 -m pytest -q tests/test_browser_submit_audit_log_persistence_20260506.py
27 passed in 0.63s   ← 수정 전 25 passed, 2 failed
```

| 테스트 | 수정 전 | 수정 후 |
|--------|---------|---------|
| test_05_preserve_safe_hidden_fields | ✗ FAILED | ✓ PASS |
| test_07_redact_list_items | ✗ FAILED | ✓ PASS |
| 나머지 25개 | ✓ PASS | ✓ PASS |

### 7.2 real_browser_audit_integration 테스트

```
python3 -m pytest -q tests/test_browser_submit_real_browser_audit_integration_20260506.py
5 passed, 1 failed
```

| 테스트 | 결과 | 원인 |
|--------|------|------|
| test_01_full_flow_real_browser_to_audit_log | ✗ FAILED | **pre-existing fail** — allowlist의 `allowed_form_ids: ["test_form"]`에 `form_id="contact_form"`이 없어 DENY. 우리 수정과 무관 |
| test_02 ~ test_06 | ✓ 5/5 PASS | — |

### 7.3 approval_state_persistence 테스트

```
python3 -m pytest -q tests/test_browser_submit_approval_state_persistence_20260506.py
30 passed, 29 warnings in 0.67s   ← 수정 영향 없음 확인
```

---

## 8. 금지 항목 준수 (STEP 7)

| 항목 | 상태 |
|------|------|
| production submit | ✓ 없음 |
| 실제 업무 사이트 접속 | ✓ 없음 |
| 운영 DB write | ✓ 없음 |
| SQL persistence | ✓ 없음 |
| API endpoint 연결 | ✓ 없음 |
| docker 작업 | ✓ 없음 |
| action registry 연결 | ✓ 없음 |
| task_executor 연결 | ✓ 없음 |
| package install | ✓ 없음 |
| package lock 변경 | ✓ 없음 |
| repo root 신규 .md | ✓ 없음 |
| destructive command | ✓ 없음 |
| secret 출력 | ✓ 없음 |

---

## 9. Untracked 상태

| 항목 | 상태 |
|------|------|
| BROWSER_OPEN_TYPE_CLOSE_CONTROLLED_PREFLIGHT.md | ✓ untracked 유지 |
| add/delete/수정 | ✓ 없음 |

---

## 10. 3자 동기화

| 항목 | HEAD |
|------|------|
| **Local** (commit 후) | 최종 commit |
| **origin/master** | 동기화 완료 |
| **Server (haehan-app)** | 동기화 완료 |

---

## 11. 잔여 경고 (비차단)

| 경고 | 위치 | 영향 | 처리 |
|------|------|------|------|
| `utcnow() deprecated` | submit_approval_state.py | 없음 | WARN_EXTERNAL_DEPRECATION (수정 금지 파일) |
| test_01 real browser fail | test_browser_submit_real_browser_audit_integration | pre-existing (allowlist form_id 불일치) | 별도 allowlist 수정 필요 |

---

## 12. 최종 판정

### 🟢 **PASS_AUDIT_LOG_REDACTION_WARN_CLOSED**

**판정 근거:**
- ✓ 2개 redaction fail 모두 해결 (27/27 PASS)
- ✓ 민감정보(list 내 password 필드) 원문 노출 수정
- ✓ SAFE 필드(csrf_token) 보존 동작 수정
- ✓ 수정 범위: submit_audit_log.py 내부만 (3함수 최소 변경)
- ✓ 전체 관련 테스트 영향 없음 (30/30 PASS)
- ✓ 금지 항목 100% 준수
- ✓ 3자 동기화 완료

**비차단 잔여:**
- utcnow deprecation (submit_approval_state.py, 수정 금지)
- test_01 real browser pre-existing fail (allowlist form_id 불일치)

---

**완료 일시:** 2026-05-06 17:00 KST  
**수정 파일:** ai_orchestrator/browser_tool/submit_audit_log.py (1개)  
**테스트:** 27/27 PASS (audit_log), 30/30 PASS (approval_state)  
**판정:** PASS_AUDIT_LOG_REDACTION_WARN_CLOSED
