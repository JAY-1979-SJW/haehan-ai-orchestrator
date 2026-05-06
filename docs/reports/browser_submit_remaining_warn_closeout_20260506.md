# Browser Submit Remaining Warning Closeout 보고서

**작성일:** 2026-05-06  
**타스크:** BROWSER_SUBMIT_REMAINING_WARN_CLOSEOUT_1  
**상태:** ✓ 완료

---

## 1. 작업 목적

전체 감사 보고서에서 비차단 경고로 남았던 2개 항목을 최소 수정으로 해결합니다.

| 잔여 경고 | 원인 | 처리 방향 |
|----------|------|-----------|
| test_01 real browser fail | allowlist submit_button_id 불일치 + 테스트 인자 오류 + page.url() API 오류 | allowlist fixture + 테스트 최소 수정 |
| utcnow deprecation | submit_approval_state.py 66, 107번 줄 | datetime.now(timezone.utc) 교체 |

---

## 2. 기준선

| 항목 | HEAD |
|------|------|
| **작업 전 local** | 57e6a50 |
| **작업 전 origin/master** | 57e6a50 |
| **작업 전 server** | 57e6a50 |

---

## 3. test_01 처리

### 3.1 재현 결과

`test_01_full_flow_real_browser_to_audit_log` 3개 연속 오류:

| 순서 | 오류 | 원인 |
|------|------|------|
| 1차 | `policy_result.verdict == "ALLOW"` 실패 | allowlist `allowed_submit_button_ids`에 `"submit_button_id"` 없음 |
| 2차 | `TypeError: build_controlled_submit_result() got unexpected keyword argument 'site_id'` | 테스트가 없는 인자 전달 |
| 3차 | `TypeError: 'str' object is not callable` at `page.url()` | Playwright API: `page.url`은 속성, 메서드 아님 |

### 3.2 수정 파일 및 내용

**① tests/fixtures/browser_submit_policy_allowlist_20260506.json**

```json
"allowed_submit_button_ids": [
    "submit_btn",
    "send_btn",
    "contact_submit",
    "submit_button_id"   ← 추가 (HTML fixture id와 일치)
],
```

**② tests/test_browser_submit_real_browser_audit_integration_20260506.py**

```python
# 수정 1: 불필요한 인자 제거
submit_result = build_controlled_submit_result(
-   site_id=policy_request.site_id,
-   url="https://internal.mock/form",
-   form_id=policy_request.form_id,
    preview_bundle=preview_bundle,
    user_confirmed=True,
)

# 수정 2: 잘못된 assert 속성명 수정
- assert submit_result.allowed is True
+ assert submit_result.submit_result == "success"

# 수정 3: Playwright API 오류 수정
- assert page.url() == fixture_data_url
+ assert page.url == fixture_data_url
```

**수정 원칙 준수:**
- ✓ allowlist origin/form_id/submit_button_id/intent 일치만 맞춤
- ✓ 새 기능 추가 없음
- ✓ 실제 업무 도메인 추가 없음
- ✓ production submit 관련 문구 없음
- ✓ submit_policy.py 변경 없음

### 3.3 결과

```
python3 -m pytest -q tests/test_browser_submit_real_browser_audit_integration_20260506.py
6 passed in 17.12s   ← 수정 전 1 failed
```

---

## 4. utcnow 처리

### 4.1 위치

| 파일 | 줄 | 내용 |
|------|-----|------|
| submit_approval_state.py | 66 | `datetime.utcnow().isoformat() + "Z"` |
| submit_approval_state.py | 107 | `datetime.utcnow().isoformat() + "Z"` |

### 4.2 수정 내용

**ai_orchestrator/browser_tool/submit_approval_state.py**

```python
# import 수정
- from datetime import datetime
+ from datetime import datetime, timezone

# 2곳 교체 (replace_all)
- "timestamp": datetime.utcnow().isoformat() + "Z",
+ "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
```

### 4.3 결과

```
python3 -m pytest -q tests/test_browser_submit_approval_state_persistence_20260506.py -W default
30 passed in 0.51s   ← DeprecationWarning 없음
```

---

## 5. 검증 결과

| 검증 항목 | 결과 |
|----------|------|
| real browser audit integration test | ✓ 6/6 PASS |
| audit log persistence test | ✓ 27/27 PASS |
| approval state persistence test | ✓ 30/30 PASS |
| py_compile | ✓ COMPILE OK |
| git diff --check | ✓ CLEAN |
| 민감정보 검사 | ✓ 없음 |
| 실제 업무 도메인 미포함 | ✓ 없음 |
| 금지 연결 미포함 (network/DB/docker/action_registry/task_executor) | ✓ 없음 |

---

## 6. 금지 항목 준수

| 항목 | 상태 |
|------|------|
| production submit | ✓ NO |
| 실제 업무 사이트 접속 | ✓ NO |
| 운영 DB write | ✓ NO |
| SQL persistence | ✓ NO |
| API endpoint | ✓ NO |
| docker 작업 | ✓ NO |
| action registry 연결 | ✓ NO |
| task_executor 연결 | ✓ NO |
| package install | ✓ NO |
| package lock 변경 | ✓ NO |
| root 신규 문서 생성 | ✓ NO |
| destructive command | ✓ NO |
| secret 출력 | ✓ NO |

---

## 7. Untracked 상태

| 항목 | 상태 |
|------|------|
| BROWSER_OPEN_TYPE_CLOSE_CONTROLLED_PREFLIGHT.md | ✓ untracked 유지 |
| add/delete/수정 | ✓ NO |

---

## 8. 3자 동기화

| 항목 | 작업 전 | 작업 후 |
|------|---------|---------|
| local | 57e6a50 | 최종 commit |
| origin/master | 57e6a50 | 동기화 완료 |
| server | 57e6a50 | 동기화 완료 |

---

## 9. 수정 파일 목록

| 파일 | 수정 내용 |
|------|----------|
| ai_orchestrator/browser_tool/submit_approval_state.py | utcnow → now(timezone.utc) 2곳 |
| tests/fixtures/browser_submit_policy_allowlist_20260506.json | submit_button_id 추가 |
| tests/test_browser_submit_real_browser_audit_integration_20260506.py | 인자 제거, 속성명 수정, page.url API 수정 |

---

## 10. 최종 판정

### 🟢 **PASS_REMAINING_WARN_CLOSED**

**판정 근거:**
- ✓ test_01 fail 해결 → 6/6 PASS
- ✓ utcnow DeprecationWarning 해소 → 30 passed, 0 warnings
- ✓ 전체 관련 테스트 통과
- ✓ 수정 범위: 허용 파일 3개만
- ✓ 금지 항목 100% 준수
- ✓ 3자 동기화 완료

---

**완료 일시:** 2026-05-06 18:00 KST  
**수정 파일:** 3개  
**테스트:** 6/6 + 27/27 + 30/30 모두 PASS  
**판정:** PASS_REMAINING_WARN_CLOSED
