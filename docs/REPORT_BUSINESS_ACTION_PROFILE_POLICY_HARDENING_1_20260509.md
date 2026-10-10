# BUSINESS_ACTION_PROFILE_POLICY_HARDENING_1 구현 완료 보고서

## 프로젝트 개요

**작업명**: BUSINESS_ACTION_PROFILE_POLICY_HARDENING_1  
**시작일**: 2026-05-09  
**완료일**: 2026-05-09  
**상태**: ✅ 완료  

### 목표

업무 액션(business.prepare_action, business.execute_with_user_approval)의 프로필 정책을 통합하고 강화하여 보안과 심사 기준을 강화합니다.

---

## 핵심 변경사항

### 1. 신규 모듈: business_action_profiles.py

**파일**: `ai_orchestrator/agent_hub/business_action_profiles.py` (163줄)

#### 주요 내용:
- **BusinessProfile 불변 데이터클래스**: 모든 프로필의 정책을 단일 소스에서 정의
  - name, label, risk_level
  - requires_approval (승인 필수 여부)
  - required_summary_fields (필수 필드)
  - optional_summary_fields (선택 필드)
  - forbidden_fields (금지 필드)
  - approval_scope_fields (심사 범위 필드)
  - required_evidence_fields (증거 필수 필드)
  - allowed_result_fields (허용 결과 필드)
  - default_expiry_seconds (토큰 만료 시간, 300초)
  - allowed_execution_location (실행 위치: LOCAL_AGENT_REQUIRED)

- **COMMON_FORBIDDEN_FIELDS**: 모든 프로필에 공통으로 적용되는 금지 필드
  - password, otp, cert_password, private_key
  - cookie, session, storage_state
  - localStorage, sessionStorage
  - access_token, refresh_token
  - npki_data, certificate_file_path

- **6개 비즈니스 프로필 정의**:

| 프로필 | 위험도 | 승인 필수 | 필수 필드 | 심사 범위 필드 |
|---|---|---|---|---|
| bid_submission | HIGH | ✓ | notice_id, notice_title, organization_name, bid_amount, due_date, target_site | business_profile, notice_id, bid_amount, organization_name, due_date |
| erp_save | MEDIUM | ✗ | erp_name, menu_path, record_type, record_title, changed_fields | business_profile, erp_name, record_type, record_title |
| erp_submit_approval | HIGH | ✓ | erp_name, menu_path, approval_title, attached_files, submit_button_text | business_profile, erp_name, approval_title, approval_amount |
| document_submission | MEDIUM | ✗ | target_site, document_title, recipient_or_organization, submit_button_text | business_profile, document_title, recipient_or_organization |
| public_agency_upload | MEDIUM | ✗ | agency_name, service_name, application_title, attached_files | business_profile, agency_name, application_title |
| esign_request | HIGH | ✓ | document_title, signer_name, organization_name, signature_method, target_site | business_profile, document_title, signer_name |

#### 헬퍼 함수:
- `get_profile(name)` → BusinessProfile | None
- `list_profiles()` → list[str]
- `validate_summary_fields(profile, params)` → (bool, list[str])
- `build_approval_scope(profile, params)` → dict
- `build_evidence_policy(profile)` → dict

---

### 2. 수정된 핸들러

#### business_prepare_action.py

**변경 사항**:
- 제거: BUSINESS_PROFILES dict (이전 분산 정의)
- 제거: FORBIDDEN_FIELD_KEYWORDS tuple
- 추가: business_action_profiles 모듈 임포트
- 수정: `execute()` 함수
  - `get_profile()` 호출로 프로필 조회
  - `validate_summary_fields()` 호출로 필수 필드 검증
  - `build_approval_scope()` 호출로 심사 범위 생성
  - `build_evidence_policy()` 호출로 증거 정책 생성
  - approval_scope, evidence_policy를 응답에 포함

**응답 필드 추가**:
```python
{
    "approval_scope": {
        "business_profile": str,
        "notice_id": str,
        "bid_amount": str,
        ...
    },
    "evidence_policy": {
        "profile_name": str,
        "required_fields": list[str],
        "forbidden_fields": list[str],
        "execution_location": "LOCAL_AGENT_REQUIRED",
        ...
    }
}
```

#### business_execute_with_user_approval.py

**변경 사항**:
- 제거: BUSINESS_PROFILES set
- 제거: FORBIDDEN_FIELDS set
- 추가: business_action_profiles 모듈 임포트
- 수정: `execute()` 함수
  - `get_profile()` 호출로 프로필 조회
  - `build_evidence_policy()` 호출로 증거 정책 생성
  - evidence_policy를 handoff_payload에 포함
  - evidence_policy를 응답에 포함

**응답 필드 추가**:
```python
{
    "evidence_policy": {
        "profile_name": str,
        "required_fields": list[str],
        "forbidden_fields": list[str],
        "execution_location": "LOCAL_AGENT_REQUIRED",
        ...
    },
    "handoff_payload": {
        "evidence_policy": {...},
        ...
    }
}
```

---

## 신규 테스트 작성

### 1. test_business_action_profile_policy_20260509.py (19개 테스트)

프로필 정책 모듈 자체에 대한 단위 테스트:
- ✅ 6개 프로필 모두 등록 확인
- ✅ 프로필별 required_summary_fields 존재 확인
- ✅ unknown profile → None 반환
- ✅ 프로필별 구성 필드 검증
- ✅ COMMON_FORBIDDEN_FIELDS 포함 확인
- ✅ approval_scope_fields에 business_profile 포함
- ✅ validate_summary_fields() 함수 동작
- ✅ build_approval_scope() 함수 동작
- ✅ build_evidence_policy() 함수 동작
- ✅ 실행 위치 = LOCAL_AGENT_REQUIRED
- ✅ BusinessProfile 불변성 (frozen dataclass)

**결과**: 19/19 ✅ PASSED

### 2. test_business_prepare_profile_validation_20260509.py (18개 테스트)

business.prepare_action 통합 테스트:
- ✅ 6개 프로필 모두 필수 필드 검증
- ✅ 필수 필드 누락 → PREPARE_WARN + warnings
- ✅ 금지 필드 (password, cookie, storage_state) → BLOCKED_SENSITIVE
- ✅ URL 안전 변환 (query string 제거)
- ✅ 파일명 안전 변환 (basename만 추출)
- ✅ approval_scope 응답 포함
- ✅ approval_scope 필드 정확성
- ✅ evidence_policy 응답 포함
- ✅ evidence_policy 구조 검증

**결과**: 18/18 ✅ PASSED

### 3. test_business_execute_profile_scope_20260509.py (12개 테스트)

business.execute_with_user_approval 통합 테스트:
- ✅ 유효 토큰 → EXECUTE_HANDOFF_READY
- ✅ handoff_payload에 evidence_policy 포함
- ✅ 응답에 evidence_policy 포함
- ✅ 금지 필드 미포함 확인
- ✅ 토큰 1회 사용 후 재사용 차단
- ✅ 프로필별 실행 경로 (erp_save, esign_request)
- ✅ approval_status = APPROVED_AND_CONSUMED
- ✅ handoff_payload 필드 정확성
- ✅ 잘못된 토큰 거절
- ✅ 토큰 없음 → APPROVAL_REQUIRED

**결과**: 12/12 ✅ PASSED

---

## 기존 테스트 수정 및 검증

### 수정된 기존 테스트:

#### test_business_prepare_action_20260509.py
- **수정 전**: 필드명이 프로필 정의와 불일치 (target_id → notice_id, erp_module → erp_name 등)
- **수정 사항**:
  - test_bid_submission_prepare_success: 정확한 필드명으로 수정
  - test_erp_save_prepare_success: 필수 필드 추가 (menu_path, changed_fields)
  - test_document_submission_prepare_success: 필수 필드 추가 (target_site, submit_button_text)
- **신규 테스트 추가**:
  - test_response_has_approval_scope: approval_scope 응답 검증
  - test_response_has_evidence_policy: evidence_policy 응답 검증
- **결과**: 16/16 ✅ PASSED

#### test_business_execute_with_user_approval_20260509.py
- **신규 테스트 추가**:
  - test_response_has_evidence_policy: 응답의 evidence_policy 검증
  - test_handoff_payload_has_evidence_policy: handoff_payload의 evidence_policy 검증
- **결과**: 13/13 ✅ PASSED

#### 회귀 테스트:
- test_business_api_flow_20260509.py: 9/9 ✅ PASSED
- test_browser_prepare_submit_action_20260509.py: 9/9 ✅ PASSED
- test_browser_submit_with_user_approval_action_20260509.py: 6/6 ✅ PASSED
- test_browser_submit_api_flow_20260509.py: 13/13 ✅ PASSED

---

## 전체 테스트 결과

```
============================== SUMMARY ==============================
전체 테스트: 5032 PASSED ✅
스킵됨: 7 (의도적)
경고: 200 (deprecation warnings, 미해결 기술부채)
실행 시간: 390.35초 (6분 30초)

신규/수정 테스트 분석:
- business_action_profile_policy: 19/19 ✅
- business_prepare_profile_validation: 18/18 ✅
- business_execute_profile_scope: 12/12 ✅
- business_prepare_action (수정): 16/16 ✅
- business_execute_with_user_approval (수정): 13/13 ✅
- API flow (회귀): 9/9 ✅
- Browser actions (회귀): 28/28 ✅

신규 및 수정 테스트 총계: 115개 ✅ 100% 통과
========================================================================
```

---

## 구현 순서 및 단계별 완료

| 단계 | 작업 | 상태 |
|---|---|---|
| 1 | business_action_profiles.py 신규 작성 | ✅ 완료 |
| 2 | business_prepare_action.py 수정 | ✅ 완료 |
| 3 | business_execute_with_user_approval.py 수정 | ✅ 완료 |
| 4 | test_business_action_profile_policy_20260509.py 신규 (19개) | ✅ 완료 |
| 5 | test_business_prepare_profile_validation_20260509.py 신규 (18개) | ✅ 완료 |
| 6 | test_business_execute_profile_scope_20260509.py 신규 (12개) | ✅ 완료 |
| 7 | 기존 테스트 수정 (approval_scope, evidence_policy 추가) | ✅ 완료 |
| 8 | 기존 business 테스트 회귀 | ✅ 완료 |
| 9 | 전체 회귀 테스트 (5032개) | ✅ 완료 |
| 10 | 종합 보고서 작성 | ✅ 완료 |

---

## 보안 강화 효과

### 승인 게이트 강화:
1. **프로필별 필수 필드 검증**: 누락된 필드 → PREPARE_WARN으로 조기 감지
2. **금지 필드 통합 차단**: COMMON_FORBIDDEN_FIELDS로 일관된 보안 정책
3. **심사 범위 명시화**: approval_scope_fields로 승인할 필드 명확히 정의
4. **증거 정책 자동 생성**: 실행 중 감시할 필드와 금지 필드 자동 적용

### 감사 추적 강화:
1. **evidence_policy 포함**: 준비/실행 단계에서 감시 기준 명시
2. **evidence_policy in handoff_payload**: local agent가 실행 조건 알고 실행
3. **allowed_result_fields**: 실행 결과에서 검증할 필드 사전 정의

### 일관성:
1. **단일 소스**: business_action_profiles.py가 유일한 정책 정의 소스
2. **프로필별 정책**: 6개 프로필이 각자 명확한 정책 가짐
3. **frozen dataclass**: 런타임 정책 변조 불가능 (불변성)

---

## 기술 채무 해소

### 이전 상태:
- ❌ BUSINESS_PROFILES가 두 파일에 이중 정의 (dict vs set)
- ❌ 프로필별 금지 필드가 명확히 정의되지 않음
- ❌ 승인 범위(scope)에 business_profile 미포함
- ❌ prepare/execute 간 정책 불일치 가능성
- ❌ evidence_policy가 고정적이고 프로필별 차이 없음

### 현재 상태:
- ✅ 단일 모듈에서 모든 프로필 정책 관리
- ✅ 각 프로필마다 명확한 forbidden_fields, required_fields, optional_fields 정의
- ✅ approval_scope_fields에 business_profile 명시적 포함
- ✅ prepare/execute가 동일한 profile policy 참조
- ✅ evidence_policy가 프로필별로 자동 생성되어 차이 없음

---

## 향후 확장 가능성

현재 구현의 장점:
1. **신규 프로필 추가 용이**: BusinessProfile을 _PROFILES dict에 추가하면 자동으로 prepare/execute에 적용
2. **정책 수정 중앙화**: business_action_profiles.py 한 곳에서만 수정
3. **테스트 자동화**: 각 프로필별 테스트가 독립적으로 추가 가능
4. **확장된 검증**: required_evidence_fields, allowed_result_fields를 이용해 더 엄격한 검증 가능

---

## 결론

**BUSINESS_ACTION_PROFILE_POLICY_HARDENING_1** 작업을 성공적으로 완료했습니다.

- **신규 코드**: 163줄 (business_action_profiles.py)
- **수정 코드**: 2개 핸들러 (business_prepare_action.py, business_execute_with_user_approval.py)
- **신규 테스트**: 49개 (profile policy, prepare validation, execute scope)
- **수정 테스트**: 5개 (기존 핸들러 테스트에 approval_scope, evidence_policy 검증 추가)
- **전체 테스트 통과**: 5032/5032 ✅

**보안 및 감사 기준이 강화되었으며, 향후 유지보수와 확장이 용이한 아키텍처가 확립되었습니다.**

---

**작성일**: 2026-05-09  
**작성자**: Claude Code  
**상태**: ✅ 완료 및 배포 준비 완료
