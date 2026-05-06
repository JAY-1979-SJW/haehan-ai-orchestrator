# Browser Actual Type Smoke Test Report
**Date**: 2026-05-06  
**Target**: haehan-app (ai-orchestrator-api container)  
**Action**: browser.open_type_close_controlled  
**Status**: PASS_ACTUAL_TYPE_SMOKE

---

## 1. 작업 내용
서버 런타임에 반영된 `browser.open_type_close_controlled` 액션을 실제 controlled mock 실행으로 1회 검증했습니다. 실제 입력 가능 여부만 확인하고 submit, 외부 업무 사이트 접속, DB write 등은 일절 수행하지 않았습니다.

---

## 2. 승인 문구 확인
✓ **CONFIRMED**: "BROWSER_ACTUAL_TYPE_SMOKE 실행 승인" 포함

---

## 3. 기준선 (STEP 1)

| 항목 | 값 | 상태 |
|------|-----|------|
| server HEAD | 90d8260 | ✓ 예상값 일치 |
| origin/master | 90d8260 | ✓ HEAD와 일치 |
| HEAD == origin/master | Yes | ✓ PASS |
| git status (tracked dirty) | 없음 | ✓ PASS |
| git status (untracked) | 없음 | ✓ PASS |

---

## 4. API 상태 (STEP 2)

| 항목 | 값 | 상태 |
|------|-----|------|
| Container | haehan-ai-orchestrator-api | ✓ Running |
| Status | Up 8 minutes (healthy) | ✓ PASS |
| Image | haehan-ai-orchestrator-api:local | ✓ 최신 |
| Backend DB | 운영 상태 유지 | ✓ PASS |

---

## 5. Action/Policy/Redaction 확인 (STEP 3)

| 확인 항목 | 값 | 상태 |
|----------|-----|------|
| enum 존재 | `open_type_close_controlled` | ✓ PASS |
| risk_level | medium | ✓ PASS |
| requires_approval | True | ✓ PASS |
| redaction allowlist (lifecycle) | opened, typed, closed | ✓ PASS |
| redaction allowlist (field_id) | 포함됨 | ✓ PASS |
| action schema | url, field_id, sample_value_id | ✓ PASS |
| submit 동작 | 없음 | ✓ PASS |

---

## 6. Smoke 실행 대상 (STEP 5)

| 항목 | 값 | 상태 |
|------|-----|------|
| 대상 유형 | mock backend (메모리 실행) | ✓ Controlled |
| 외부 접근 | 없음 | ✓ PASS |
| 네트워크 | 로컬만 | ✓ PASS |
| 샘플 데이터 | 고정값만 | ✓ PASS |

---

## 7. Smoke 실행 결과 (STEP 6)

**입력값**:
```json
{
  "field_id": "sample_text_field",
  "sample_value_id": "sample_text_short",
  "url": "https://example.com/smoke-test"
}
```

**결과 요약**:

| 단계 | 결과 | 상태 |
|------|------|------|
| browser open | ✓ lifecycle.opened=True | PASS |
| field_id detect | ✓ field_id matched | PASS |
| type 입력 | ✓ typed=True | PASS |
| close | ✓ lifecycle.closed=True | PASS |
| action accepted | ✓ success=True | PASS |
| approval 정책 | ✓ requires_approval=True | PASS |
| submit 발생 | ✗ 없음 | PASS |
| lifecycle redaction | ✓ {opened, typed, closed} | PASS |
| raw input 노출 | ✗ 없음 | PASS |

**상세 검증** (14/14 통과):
- ✓ success=True
- ✓ action="open_type_close_controlled"
- ✓ backend="mock"
- ✓ typed=True
- ✓ field_id="sample_text_field"
- ✓ field_role="text_input"
- ✓ sample_value_id="sample_text_short"
- ✓ executed=True
- ✓ requires_approval=True
- ✓ lifecycle.opened=True
- ✓ lifecycle.typed=True
- ✓ lifecycle.closed=True
- ✓ raw_value/actual_input 미포함
- ✓ timestamp 존재

---

## 8. 금지 항목 준수 여부

| 금지 항목 | 실행 여부 | 상태 |
|----------|----------|------|
| submit 동작 | ✗ 하지 않음 | ✓ PASS |
| 외부 업무 사이트 | ✗ 접근 없음 | ✓ PASS |
| DB migration | ✗ 실행 없음 | ✓ PASS |
| secret/token 출력 | ✗ 없음 | ✓ PASS |
| volume 삭제 | ✗ 없음 | ✓ PASS |
| 파괴 명령 | ✗ 없음 | ✓ PASS |

---

## 9. 변경 파일 여부 (STEP 7)

**git status --short**: (비어있음)

- ✓ tracked dirty: 없음
- ✓ untracked: 없음
- ✓ 예상 외 변경: 없음

---

## 최종 판정

**PASS_ACTUAL_TYPE_SMOKE**

✓ controlled page에서 open/type/close 모두 성공  
✓ submit 발생 없음  
✓ 외부 사이트 접근 없음  
✓ secret 노출 없음  
✓ health 정상 (healthy)  
✓ git 상태 문제 없음 (HEAD==origin/master)  
✓ 모든 금지 항목 준수  
✓ 모든 validation 통과 (14/14)

---

## 실행 환경 정보

- **Server**: haehan-app
- **Repo Path**: /home/ubuntu/apps/haehan-ai-orchestrator
- **Docker Compose Service**: ai-orchestrator-api
- **Container Image**: haehan-ai-orchestrator-api:local
- **Runtime**: Python + uvicorn
- **Execution Mode**: Mock backend (no actual browser)
- **Execution Time**: 2026-05-06T01:26:08 UTC
