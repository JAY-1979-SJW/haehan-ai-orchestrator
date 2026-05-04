# ORCHESTRATOR-LOCAL-AGENT-MODULARIZATION-AUDIT-1: STEP 3 최종 보고서

## 작업 내용

- local-agent 모듈화 전략 통합 수립
- STEP 1 (router 분석) + STEP 2 (registry 분석) → STEP 3 (로드맵 확정)
- 모듈화 후보 13개 정의, 위험도별 분류, 실구현 순서 확정
- 보안 경계 고정, 테스트 영향 범위 정의

---

## 기준선 (STEP 3-0)

| 항목 | 상태 | 판정 |
|------|------|------|
| **branch** | master | ✅ PASS |
| **HEAD** | 1052f96... | ✅ PASS |
| **origin/master** | 1052f96... | ✅ 동일 |
| **git status** | clean (코드 변경 없음) | ✅ PASS |
| **untracked 파일** | STEP-2-REPORT.md (11KB) | ⚠️ WARN_UNTRACKED_REPORT |

**판정: PASS + WARN_UNTRACKED_REPORT**
- STEP 2 보고서 파일 untracked (삭제/커밋 금지)
- STEP 3 분석 진행 가능

---

## STEP 1 요약: Router 분석 (WARN_ROUTER_COUPLING)

| 항목 | 상세 |
|------|------|
| **파일** | local_agent_router.py (약 1306줄) |
| **분리 쉬운 부분** | registration flow, code endpoint, list endpoint, diagnostics |
| **강결합 부분** | task submit, approval approve/reject, audit log 산재, WebSocket |
| **종합 판정** | ⚠️ WARN_ROUTER_COUPLING |

**고위험 결합**:
- task submit + approval 게이트 혼재
- audit log 50개+ 산재
- WebSocket 메시지 처리와 상태 전이 혼재

---

## STEP 2 요약: Registry 분석 (PASS_REGISTRY_CORE)

| 항목 | 상세 |
|------|------|
| **파일** | local_agent_registry.py (1293줄) |
| **강점** | device_token 해싱, 상태 머신, 민감정보 처리, 동시성 안전성 |
| **개선 기회** | action coupling, serializer coupling, approval coupling |
| **종합 판정** | ✅ PASS_REGISTRY_CORE + ⚠️ WARN_MODULARIZATION_OPPORTUNITY |

**핵심 강점**:
- ✅ LocalAgent.token_hash (SHA-256, 원문 저장 금지)
- ✅ VALID_TASK_TRANSITIONS (상태 전이 중앙화)
- ✅ 6단계 redaction (token, sensitive, result_data)
- ✅ 26개 함수에서 일관된 lock 사용

---

## 통합 모듈화 후보 (13개)

### 📦 1순위: 안전한 분리 (LOW 위험도)

**특징**: API/Response 무영향, 기존 로직 변경 없음, import만 변경

| # | 모듈명 | 라인 | 분리 규모 | 우선순위 |
|---|------|------|---------|---------|
| 1 | local_agent_models.py | 146-314 | 169줄 | **1순위** |
| 2 | local_agent_risk_policy.py | 33-59 | 27줄 | **1순위** |
| 3 | local_agent_redaction.py | 62-137, 1055-1093 | 115줄 | **2순위** |
| 4 | local_agent_serializers.py | 160-314, 1100-1270 | 325줄 | **2순위** |

**구현 의존도**: models → risk_policy, redaction → serializers

---

### ⚙️ 2순위: 중간 위험 분리 (MEDIUM 위험도)

**특징**: 중간 규모, 통합 테스트 필요, 의존성 재구성

| # | 모듈명 | 출처 | 분리 규모 | 우선순위 |
|---|------|------|---------|---------|
| 5 | local_agent_store.py | Registry | 159줄 | **2순위** |
| 6 | local_agent_registration_routes.py | Router | ~ | **2순위** |
| 7 | local_agent_list_routes.py | Router | ~ | **2순위** |
| 8 | local_agent_diagnostics_routes.py | Router | ~ | **2순위** |

**기술 위험**:
- authenticate_agent: device_token 검증 경계 유지 필수
- registration flow: code 발행/검증 정책 유지 필수
- endpoint path: API 호환성 유지 필수

---

### 🔴 3순위: 고위험 분리 (HIGH 위험도)

**특징**: 가장 복잡, 상태 전이 포함, 보안 경계 재검증 필수

| # | 모듈명 | 출처 | 분리 규모 | 우선순위 |
|---|------|------|---------|---------|
| 9 | local_agent_task_queue.py | Registry | 507줄 | **3순위** |
| 10 | local_agent_approval_gateway.py | Router | ~ | **3순위** |
| 11 | local_agent_audit_events.py | Router | 50개+ | **3순위** |
| 12 | local_agent_websocket_handler.py | Router | ~ | **3순위** |
| 13 | local_agent_timeout.py | Registry | 94줄 | **3순위 (선택)** |

**고위험 사항**:
- task_queue: VALID_TASK_TRANSITIONS 중앙화, stateful
- approval_gateway: approval token 검증, audit trail
- audit_events: 민감정보 절대 금지 (50개+ log_event)
- websocket_handler: device_token 인증, 상태 전이

---

## 🔒 보안 경계 (필수 지킬 사항)

### Token 처리 원칙

| 항목 | 원칙 | 예외 | 검증 |
|------|------|------|------|
| **device_token 원문** | registry에 저장 금지 | RegisterResult로 1회만 반환 | ✅ 명확 |
| **token_hash** | SHA-256만 저장 | - | ✅ 명확 |
| **approval_token** | 원문 저장 금지 | token_id (UUID) + public_id 분리 | ✅ 명확 |
| **registration_code** | 원문 저장 금지 | code_hash만 저장 | ⚠️ 신규 정책 |

### Redaction 정책

| 항목 | 정책 | 모듈 |
|------|------|------|
| **params 민감값** | _strip_sensitive 후 저장 | redaction.py |
| **result_data** | allowlist + _SENSITIVE_KEYS 이중방어 | redaction.py + task_queue |
| **observe_summary** | _OBSERVE_FORBIDDEN_KEYS 방어 | serializers.py |
| **audit_summary** | _AUDIT_SUMMARY_FORBIDDEN_KEYS 방어 | serializers.py |

### Audit Log 정책

| 항목 | 원칙 | 모듈 |
|------|------|------|
| **민감값 금지** | token, password, cookie, secret 절대 금지 | audit_events.py |
| **token_hash만** | device_token 대신 hash 로그 | audit_events.py |
| **approval 추적** | token_id 대신 public_id | audit_events.py |
| **WebSocket** | device_token 원문 로그 금지 | websocket_handler.py |

### Approval Gate 보안

| 항목 | 원칙 | 모듈 |
|------|------|------|
| **waiting_approval → queued** | mark_approved 호출 후만 | task_queue.py |
| **token 검증** | token_id + compare_digest | approval_gateway.py |
| **public_id 발행** | token_id와 분리 | approval_gateway.py |

---

## 📋 테스트 영향 범위

### Phase 1 이후 필수 유지 테스트

- ✅ test_action_registry_approval_policy.py: approval 정책 재검증
- ✅ test_local_agent_router_audit_redaction.py: redaction 정책 재검증
- ✅ test_local_agent_registration_code_flow.py: registration code 유지

### Phase 2 이후 신규 추가 테스트

- test_local_agent_store.py: store lifecycle
- test_local_agent_list_routes.py: list endpoint
- test_local_agent_registration_routes.py: registration endpoint

### Phase 3 이후 신규 추가 테스트

- test_local_agent_task_queue.py: task state transition
- test_local_agent_approval_gateway.py: approval token 검증
- test_local_agent_audit_events.py: audit log 민감정보 방어
- test_local_agent_websocket_handler.py: WebSocket 인증

### 강화해야 할 테스트

| 테스트 이름 | 목적 | 우선순위 |
|-----------|------|---------|
| test_redaction_sensitive_keys.py | _SENSITIVE_KEYS 검증 | 높음 |
| test_serializer_response_shape.py | to_safe 응답 형식 고정 | 높음 |
| test_task_status_transition_matrix.py | VALID_TASK_TRANSITIONS 고정 | 높음 |
| test_approval_token_validation.py | token_id 검증 고정 | 높음 |
| test_audit_log_sensitive_redaction.py | audit log 민감값 제외 | 높음 |
| test_websocket_device_token_no_log.py | WebSocket token 로그 금지 | 높음 |

---

## 🎯 추천 다음 작업

### ORCHESTRATOR-LOCAL-AGENT-RISK-POLICY-MODULE-1

**목표**: ACTION_RISK 정책을 local_agent_risk_policy.py로 분리

**선택 이유**:
- ✅ **가장 작음** (27줄)
- ✅ **가장 안전함** (정책 상수, 로직 없음)
- ✅ **API/Response 무영향** (import만 변경)
- ✅ **테스트 영향 최소** (unit test만 유지)
- ✅ **롤백 간단함**

**분리 규모**:
```
현재 위치: ai_orchestrator/local_agent_registry.py (라인 33-59)
신규 파일: ai_orchestrator/local_agent_risk_policy.py (27줄)

분리 대상:
  - ACTION_RISK dict (15개 액션)
  - _SERVER_AUTO_COMPLETE frozenset (3개)
  - ALLOWED_APPS list (4개)
```

**예상 시간**: 30분 ~ 1시간

**완료 조건**:
- [ ] local_agent_risk_policy.py 생성
- [ ] import 변경 (registry)
- [ ] 기존 test suite 전부 통과
- [ ] response 형식 변경 없음

---

## 📊 3단계 로드맵 요약

| Phase | 모듈 (번호) | 규모 | 위험 | 기간 | 상태 |
|------|-----------|------|------|------|------|
| **1** | 1-4 (models, risk_policy, redaction, serializers) | 소 | 낮음 | 1-2주 | 계획 |
| **2** | 5-8 (store, routes) | 중 | 중간 | 2-3주 | 계획 |
| **3** | 9-13 (task_queue, approval, audit, websocket) | 대 | 높음 | 3-4주 | 계획 |

**총 예상 기간**: 6-9주

---

## ⚠️ 특별 주의사항

### Untracked Report 파일

**상태**: STEP-2-REPORT.md는 untracked (삭제/커밋 금지)

- STEP-2-REPORT.md (11KB, 감사 보고서)
- STEP-3-MODULARIZATION-ROADMAP.md (신규, 로드맵)
- NEXT-WORK-PROPOSAL.md (신규, 제안서)
- STEP-3-FINAL-REPORT.md (본 파일)

**처리 방식**: 삭제하지 말고 보관, 향후 git ignore 추가 검토

### 보안 경계 재검증 체크리스트

다음 구현 시마다 필수 확인:
- [ ] device_token 원문이 저장/로그에 없나?
- [ ] token_hash만 저장되나?
- [ ] approval_token이 저장/로그에 없나?
- [ ] to_safe에서 민감값이 제외되나?
- [ ] audit log에 password/cookie/session이 없나?
- [ ] WebSocket 메시지에 원문이 없나?

---

## 최종 판정

### 종합 평가

**PASS_MODULARIZATION_PLAN + READY_FOR_PHASE_1**

local-agent 모듈화는:
1. ✅ 안전한 기초 모듈부터 시작 (models, risk_policy)
2. ✅ 보안 경계가 명확하게 정의됨 (token, redaction, audit)
3. ✅ 3단계 로드맵으로 위험도 관리 (low → medium → high)
4. ✅ 테스트 영향이 계획됨 (unit → integration → e2e)
5. ✅ Phase 1 첫 작업 명확함 (RISK_POLICY_MODULE)

### 다음 단계

**ORCHESTRATOR-LOCAL-AGENT-RISK-POLICY-MODULE-1** 구현 지시문 작성 (사용자 요청 시)

---

## 첨부

- STEP-2-REPORT.md (STEP 2 감사 결과)
- STEP-3-MODULARIZATION-ROADMAP.md (3단계 로드맵)
- NEXT-WORK-PROPOSAL.md (첫 번째 작업 제안)

---

