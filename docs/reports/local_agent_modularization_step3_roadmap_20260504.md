# ORCHESTRATOR-LOCAL-AGENT-MODULARIZATION-AUDIT-1: STEP 3 로드맵

## 📊 통합 모듈화 후보 (13개)

### **1순위: 안전한 분리 (즉시 실행 가능)**

위험도: **LOW**, API/Response 영향: **무**

| # | 모듈명 | 출처 | 분리 규모 | 기술 위험 | 테스트 |
|---|------|------|---------|---------|--------|
| 1 | local_agent_models.py | Registry | 작음 (169줄) | 매우 낮음 | unit |
| 2 | local_agent_risk_policy.py | Registry | 매우 작음 (27줄) | 매우 낮음 | unit |
| 3 | local_agent_redaction.py | Registry | 작음 (76+39줄) | 낮음 | unit |
| 4 | local_agent_serializers.py | Registry | 중간 (155+170줄) | 낮음 | unit |

**구현 전략**:
- 모델 → 정책 → 유틸리티 → 직렬 순서
- import 의존성: models → redaction/risk_policy → serializers
- 기존 registry에서는 import만 변경, 로직 복제 금지

---

### **2순위: 중간 위험 분리 (준비 후 실행)**

위험도: **MEDIUM**, API/Response 영향: **부분**

#### **Registry 저장소 분리**

| # | 모듈명 | 분리 규모 | 기술 위험 | 영향 |
|---|------|---------|---------|------|
| 5 | local_agent_store.py | 중간 (159줄) | 중간 | agent lifecycle API |

**기술 위험 사항**:
- authenticate_agent가 device_token 검증 → 토큰 저장소 경계 명확화 필요
- register_agent의 device_token 원문 반환 → RegisterResult 유지
- _agents/_tasks 메모리 저장소 → lock 경계 이전
- 현재 registry에서 호출: get_agent_status, list_agents 등

**영향도**:
- router의 직접 호출 함수들: register_agent, get_agent, list_agents, authenticate_agent
- registry 내부 호출: get_agent_status (get_agent 참조)

---

#### **Router Route 분리**

| # | 모듈명 | 분리 라인 | 기술 위험 | 영향 |
|---|------|---------|---------|------|
| 6 | local_agent_registration_routes.py | route handler | 중간 | registration flow |
| 7 | local_agent_list_routes.py | GET routes | 낮음 | 조회 전용 |
| 8 | local_agent_diagnostics_routes.py | GET routes | 낮음 | 진단 전용 |

**기술 위험 사항**:
- registration code flow: code 발행, 저장, 검증 (현재 registry와 router 혼재)
- list routes: to_safe 호출 (serializer 의존성)
- diagnostics: 계산 로직만 분리

**영향도**:
- endpoint 경로 유지 필수 (API 호환성)
- 현재 audit log 호출 분산 (통합 필요)

---

### **3순위: 고위험 분리 (신중한 검토 & 테스트)**

위험도: **HIGH**, API/Response 영향: **높음**

#### **Registry 핵심 기능**

| # | 모듈명 | 분리 규모 | 고위험 사유 | 영향 |
|---|------|---------|-----------|------|
| 9 | local_agent_task_queue.py | 큼 (507줄) | 상태 전이, stateful | task lifecycle API |

**고위험 사항**:
- VALID_TASK_TRANSITIONS 중앙화 필수
- approval 게이트 (mark_approved/mark_rejected)
- 타임아웃 처리 (_mark_task_failed)
- router의 직접 호출: enqueue_task, mark_approved, mark_rejected, apply_result
- WebSocket의 직접 호출: mark_delivered, mark_running, apply_result
- 취소 엔진: cancel_task (router/WebSocket 모두)

**테스트 영향**:
- action_registry approval policy 재검증 필수
- approval audit log 재검증 필수
- state transition matrix 고정 테스트 필수
- timeout 로직 회귀 테스트

---

#### **Router 승인 게이트 분리**

| # | 모듈명 | 분리 라인 | 고위험 사유 |
|---|------|---------|-----------|
| 10 | local_agent_approval_gateway.py | route handler (task approve/reject) | approval 결정, token 검증 |

**고위험 사항**:
- approval token 검증 (token_id → task 역인덱스)
- approval public_id 발행 (audit trail)
- approval_token 원문은 절대 로그 금지
- task 상태 전이 (waiting_approval → queued/rejected)

---

#### **Router Audit Events 통합**

| # | 모듈명 | 분리 라인 | 고위험 사유 |
|---|------|---------|-----------|
| 11 | local_agent_audit_events.py | log_event 산재 (50개+) | audit log 정책, 민감정보 방어 |

**고위험 사항**:
- token_hash, approval_token, device_token 원문 절대 금지
- registration_code 원문 절대 금지
- audit log 필드 선택 (response key 반영)
- log_event 호출 위치 재구성 필요

---

#### **Router WebSocket Handler 분리**

| # | 모듈명 | 분리 라인 | 고위험 사유 |
|---|------|---------|-----------|
| 12 | local_agent_websocket_handler.py | WebSocket connect/message/disconnect | device_token 인증, 상태 전이 |

**고위험 사항**:
- device_token 원문 검증 (authenticate_agent)
- device_token 원문은 절대 로그 금지
- mark_delivered/running/apply_result 호출
- agent 연결/해제 상태 관리
- WebSocket 메시지 직렬화 (to_dispatch)

---

#### **Registry Timeout/Cleanup 분리**

| # | 모듈명 | 분리 라인 | 선택성 |
|---|------|---------|--------|
| 13 | local_agent_timeout.py | 94줄 (expire_stale_tasks, fail_active_tasks) | **선택적** |

**기술 위험 사항**:
- 낮음 (read-heavy, 상태 전이는 task_queue에 의존)
- scheduler에서 주기적 호출 (cron job)
- 타임아웃 종결 로그 필수

---

## 🎯 권장 실구현 순서

### Phase 1: 기초 모듈 (1-4번, 1-2주)

**목표**: registry 모듈화 기초 정립

```
1. local_agent_models.py       (순수 데이터)
   ↓
2. local_agent_risk_policy.py  (정책 상수)
   ↓
3. local_agent_redaction.py    (보안 정책)
   ↓
4. local_agent_serializers.py  (응답 변환)
```

**특징**:
- 기존 registry에서는 import만 변경
- API/Response 변경 없음
- unit test만 유지 가능
- 롤백 간단함

---

### Phase 2: 저장소 & 라우트 분리 (5-8번, 2-3주)

**목표**: agent lifecycle과 router endpoint 분리

```
5. local_agent_store.py (agent 저장소)
   ↓
6-8. registration/list/diagnostics routes (엔드포인트)
```

**특징**:
- registry와 router의 책임 경계 명확화
- 기존 endpoint 경로 유지
- integration test 수정 필요
- approval 게이트는 아직 registry에 포함

---

### Phase 3: 핵심 기능 분리 (9-13번, 3-4주)

**목표**: task queue, approval, audit, WebSocket 모듈화

```
9. local_agent_task_queue.py (task 상태 관리)
   ↓
10. local_agent_approval_gateway.py (승인 게이트)
    ↓
11. local_agent_audit_events.py (감사 로그)
    ↓
12. local_agent_websocket_handler.py (WebSocket)
    ↓
13. local_agent_timeout.py (선택적)
```

**특징**:
- 가장 복잡하고 위험도 높음
- 상태 전이 테스트 강화 필수
- approval/audit 정책 재검증 필수
- WebSocket 인증 경계 재검증

---

## 🔒 보안 경계 (모듈화 필수 지킬 사항)

### Token 처리

| 항목 | 원칙 | 예외 |
|------|------|------|
| **device_token 원문** | registry에 저장 금지 | RegisterResult로 1회 반환 (라우터에서 노출 후 폐기) |
| **token_hash** | SHA-256 저장만 | 모든 인증 검증은 compare_digest 사용 |
| **approval_token** | 원문 저장 금지 | token_id (UUID)와 public_id (UUID)로 분리 |
| **registration_code** | 원문 저장 금지 | code_hash만 저장, 검증 시 compare_digest |

### Redaction 정책

| 항목 | 원칙 | 모듈 |
|------|------|------|
| **params 민감값** | _strip_sensitive 적용 후 저장 | redaction.py |
| **result_data 필터** | allowlist + _SENSITIVE_KEYS 이중방어 | redaction.py + task_queue.py |
| **observe_summary** | _OBSERVE_FORBIDDEN_KEYS로 방어 | redaction.py + serializers.py |
| **audit_summary** | _AUDIT_SUMMARY_FORBIDDEN_KEYS로 방어 | redaction.py + serializers.py |

### Audit Log 정책

| 항목 | 원칙 | 모듈 |
|------|------|------|
| **민감 값 로그 금지** | token, password, cookie, session, secret 절대 금지 | audit_events.py |
| **token_hash만 로그** | device_token 원문 대신 hash | audit_events.py |
| **approval 추적** | token_id 대신 public_id 로그 | audit_events.py |
| **WebSocket 인증** | device_token 원문 로그 금지 | websocket_handler.py |

### Approval Gate 보안

| 항목 | 원칙 | 모듈 |
|------|------|------|
| **waiting_approval → queued** | mark_approved 호출 후만 | task_queue.py |
| **approval token 검증** | token_id로 역인덱싱 + compare_digest | approval_gateway.py |
| **public_id 발행** | token_id와 분리, audit trail용만 | approval_gateway.py |

---

## 📋 테스트 영향 & 유지 전략

### 필수 유지 테스트

#### **1단계 (Phase 1 이후)**
- test_action_registry_approval_policy.py: approval 정책 재검증
- test_local_agent_router_audit_redaction.py: redaction 정책 재검증
- test_local_agent_registration_code_flow.py: registration code 흐름 유지

#### **2단계 (Phase 2 이후)**
- test_local_agent_store.py: store lifecycle 신규 추가
- test_local_agent_list_routes.py: list endpoint 신규 추가
- test_local_agent_registration_routes.py: registration endpoint 신규 추가

#### **3단계 (Phase 3 이후)**
- test_local_agent_task_queue.py: task state transition 신규 추가
- test_local_agent_approval_gateway.py: approval token 검증 신규 추가
- test_local_agent_audit_events.py: audit log 민감정보 방어 신규 추가
- test_local_agent_websocket_handler.py: WebSocket 인증 신규 추가

### 새로 작성할 테스트

| 테스트 이름 | 목적 | 우선순위 |
|-----------|------|---------|
| test_redaction_sensitive_keys.py | _strip_sensitive, _strip_result_data 검증 | 높음 |
| test_serializer_response_shape.py | to_safe 응답 형식 고정 | 높음 |
| test_task_status_transition_matrix.py | VALID_TASK_TRANSITIONS 고정 | 높음 |
| test_approval_token_validation.py | token_id 검증 로직 고정 | 높음 |
| test_audit_log_sensitive_redaction.py | audit log에 민감값 없음 | 높음 |
| test_websocket_device_token_no_log.py | WebSocket에서 token 원문 로그 금지 | 높음 |

---

## ✅ 최종 체크리스트

### Phase 1 완료 조건

- [ ] local_agent_models.py 분리, import 확인
- [ ] local_agent_risk_policy.py 분리, ACTION_RISK 참조 검증
- [ ] local_agent_redaction.py 분리, _SENSITIVE_KEYS 참조 검증
- [ ] local_agent_serializers.py 분리, to_safe 호출 확인
- [ ] 기존 registry unit test 통과

### Phase 2 완료 조건

- [ ] local_agent_store.py 분리, authenticate_agent token 검증 유지
- [ ] registration/list/diagnostics routes 분리
- [ ] endpoint path 변경 없음 (API 호환성)
- [ ] 기존 integration test 통과

### Phase 3 완료 조건

- [ ] local_agent_task_queue.py 분리, VALID_TASK_TRANSITIONS 유지
- [ ] local_agent_approval_gateway.py 분리, approval token 검증 유지
- [ ] local_agent_audit_events.py 분리, log_event 민감정보 방어 유지
- [ ] local_agent_websocket_handler.py 분리, device_token 인증 유지
- [ ] 모든 신규 테스트 통과

---

