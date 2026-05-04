# ORCHESTRATOR-LOCAL-AGENT-MODULARIZATION-AUDIT-1: STEP 2 보고서

## 작업 내용
- local_agent_registry.py의 책임 분리 상태를 read-only로 감사
- 코드 수정 없이 구조 분석 및 모듈화 후보 도출

---

## 기준선 (STEP 2-0)

**상태: PASS**

```
branch: master
HEAD: 1052f96982a6de905ec299fc457392491f75d89a
origin/master: 1052f96982a6de905ec299fc457392491f75d89a
git status: clean
```

---

## 전체 구조 (STEP 2-1)

| 항목 | 상세 |
|------|------|
| **라인 수** | 1293줄 |
| **클래스** | LocalAgent, LocalAgentTask, RegisterResult, UnknownActionError, InvalidTaskTransitionError, CancelNotAllowedError |
| **함수** | 약 30개 (agent 관리 8개, task 큐 10개, helper 12개) |
| **전역 상태** | `_lock` (threading.Lock), `_agents` (dict), `_tasks` (dict) |
| **lock 사용** | 26개 함수에서 명시적으로 사용 |

---

## Agent 관리 책임 (STEP 2-2)

**판정: PASS_AGENT_SECURITY + WARN_AGENT_STATUS_COUPLING**

| 함수 | 라인 | 역할 | 보안 | 분리 |
|------|------|------|------|------|
| register_agent | 486-512 | agent 등록, device_token 발급 | 높음 ✅ | 예 |
| authenticate_agent | 523-541 | device_token 검증 (secrets.compare_digest) | 높음 ✅ | 예 |
| get_agent | 515-516 | agent 조회 | 낮음 | 예 |
| list_agents | 519-520 | agent 목록 (to_safe 적용) | 낮음 | 예 |
| set_agent_connected | 383-391 | 연결 상태 업데이트 | 낮음 | 예 |
| set_agent_last_seen | 394-399 | heartbeat 타임스탐프 | 낮음 | 예 |
| set_agent_disconnected | 402-408 | 연결 해제 기록 | 낮음 | 예 |
| get_agent_status | 452-472 | 상태 계산 (live) | 낮음 | **부분** ⚠️ |

**약한 결합**: `get_agent_status()`가 `get_active_task_count()` 호출 → task queue 의존성

---

## Task Queue 책임 (STEP 2-3)

**판정: PASS_STATE_MACHINE + WARN_APPROVAL_COUPLING**

### 상태 전이 흐름

```
LOW/MEDIUM RISK:
  enqueue_task (queued) 
    → mark_delivered → mark_running → apply_result (completed/failed)

HIGH RISK:
  enqueue_task (waiting_approval) 
    → mark_approved (queued) 또는 mark_rejected/mark_expired (rejected)
    → mark_delivered → mark_running → apply_result

CANCEL:
  cancel_task: queued/waiting_approval → cancelled (즉시)
  cancel_task: delivered/running → cancel_requested

TIMEOUT:
  expire_stale_tasks: delivered/running/cancel_requested → failed
  fail_active_tasks_for_agent: ACTIVE_TASK_STATUSES → failed
```

### 함수별 책임

| 함수 | 라인 | 책임 | router | WebSocket |
|------|------|------|--------|-----------|
| enqueue_task | 550-595 | 작업 생성, 초기 상태 | ✓ | - |
| mark_approved | 637-658 | waiting_approval → queued | ✓ | - |
| mark_rejected | 661-678 | waiting_approval → rejected | ✓ | - |
| mark_delivered | 860-873 | queued → delivered | - | ✓ |
| mark_running | 876-890 | delivered → running | - | ✓ |
| apply_result | 893-945 | running → completed/failed | - | ✓ |
| cancel_task | 982-1050 | 취소 엔진 | ✓ | ✓ |
| expire_stale_tasks | 724-781 | timeout 만료 처리 | - | - |
| fail_active_tasks_for_agent | 784-817 | 연결 해제 처리 | - | - |

**강점**:
- 상태 전이가 VALID_TASK_TRANSITIONS로 중앙화됨 ✅
- _ensure_task_transition으로 검증됨 ✅
- 상태 머신이 명확함 ✅

**약한 결합**: approval 게이트(mark_approved/mark_rejected)가 registry에 포함 ⚠️

---

## Risk/Approval Boundary (STEP 2-4)

**판정: PASS_RISK_POLICY_SEPARATION + WARN_ACTION_COUPLING**

### ACTION_RISK 정책

| Risk Level | 액션 |
|-----------|------|
| **low** | ping, system_info, list_allowed_apps, open_url, browser.inspect/plan_* |
| **medium** | list_files_readonly, browser.execute_* |
| **high** | open_url_execute, capture_screenshot |

### 정책 분리

| 정책 | 관리 위치 | 범위 |
|------|---------|------|
| **로컬 액션** | local_agent_registry.py (ACTION_RISK) | 로컬 에이전트 액션만 |
| **웹 액션** | agent/action_registry.py (requires_approval) | 브라우징 액션들 |

**강점**:
- 로컬/웹 정책이 명확하게 분리됨 ✅
- risk_level 산정이 명확함 ✅

**약점**: action 정의가 registry에 포함 ⚠️

---

## Safe Serialization (STEP 2-5)

**판정: PASS_TOKEN_EXCLUSION + PASS_PARAM_REDACTION + WARN_SERIALIZER_COUPLING**

### 민감정보 처리

| 항목 | 처리 방식 | 검증 |
|------|---------|------|
| **device_token 원문** | RegisterResult로만 반환 (라우터가 1회 노출 후 폐기) | ✅ PASS |
| **token_hash** | SHA-256만 저장, to_safe()에서 제외 | ✅ PASS |
| **approval_token** | _SENSITIVE_KEYS에 포함, 절대 저장/노출 금지 | ✅ PASS |
| **token_id** | to_dispatch()에서 제외, 서버 검증용만 보관 | ✅ PASS |
| **params 민감값** | _strip_sensitive() 적용 후 저장 | ✅ PASS |
| **result_data 필터** | allowlist + _SENSITIVE_KEYS 이중방어 | ✅ PASS |
| **observe_summary** | _OBSERVE_FORBIDDEN_KEYS로 방어 | ✅ PASS |
| **audit_summary** | _AUDIT_SUMMARY_FORBIDDEN_KEYS로 방어 | ✅ PASS |

### Serialization 메서드

| 메서드 | 역할 | 위치 |
|------|------|------|
| LocalAgent.to_safe() | API 응답용 | 160-178 |
| LocalAgentTask.to_safe() | 상세 조회용 | 225-257 |
| LocalAgentTask.to_list_safe() | 목록 조회용 | 259-281 |
| LocalAgentTask.to_dispatch() | WebSocket 전달용 | 283-314 |
| _build_audit_summary() | audit 요약 안전 처리 | 1118-1202 |
| _build_observe_summary() | observe 요약 안전 처리 | 1205-1270 |

**강점**: 민감정보가 명확하게 제외됨 ✅

**약점**: serialization 로직이 분산 (6개 메서드) ⚠️

---

## Concurrency / Lock / Memory Store (STEP 2-6)

**판정: PASS_LOCK_USAGE + PASS_MEMORY_ONLY + WARN_VOLATILE_STATE_DOCUMENTATION**

| 항목 | 상세 |
|------|------|
| **_lock** | threading.Lock() (라인 369) |
| **lock 사용** | 26개 함수에서 일관되게 사용 |
| **_agents** | dict[str, LocalAgent] (메모리 전용) |
| **_tasks** | dict[str, LocalAgentTask] (메모리 전용) |
| **상태 유실** | 서버 재시작 시 모든 agent/task 소실 |

**강점**:
- Lock 사용이 일관되고 명확함 ✅
- 메모리 저장소 정책이 단순명확함 ✅

**약점**: 휘발성 상태 정책이 주석/문서화 부족 ⚠️

---

## 모듈화 후보 (STEP 2-7)

### 우선순위별 분리 전략

#### **1순위: 기초 모듈 (위험도 낮음, 즉시 분리 가능)**

| 모듈명 | 분리 대상 | 라인 | 목적 | 이점 |
|------|---------|------|------|------|
| **local_agent_models.py** | LocalAgent, LocalAgentTask, RegisterResult | 146-314 | 순수 데이터 모델 | 다른 모듈의 import 기초 |
| **local_agent_risk_policy.py** | ACTION_RISK, _SERVER_AUTO_COMPLETE, ALLOWED_APPS | 33-59 | risk 정책 중앙화 | **WARN_ACTION_COUPLING 해결** |

#### **2순위: 유틸리티 모듈 (위험도 낮음, 준비 필요)**

| 모듈명 | 분리 대상 | 라인 | 목적 | 이점 |
|------|---------|------|------|------|
| **local_agent_redaction.py** | _SENSITIVE_KEYS, _strip_sensitive, sanitization 정책 | 62-137, 1055-1093 | 민감정보 처리 표준화 | 보안 정책 중앙화 |
| **local_agent_serializers.py** | to_safe, to_list_safe, to_dispatch, _build_* | 160-314, 1100-1270 | serialization 로직 | **WARN_SERIALIZER_COUPLING 해결** |

#### **2순위: 저장소 모듈 (위험도 낮음)**

| 모듈명 | 분리 대상 | 라인 | 목적 | 이점 |
|------|---------|------|------|------|
| **local_agent_store.py** | register_agent, get_agent, list_agents, authenticate_agent, clear() | 383-541 | agent lifecycle 관리 | agent 저장소 명확화 |

#### **3순위: 핵심 모듈 (위험도 높음, 신중한 검토 필요)**

| 모듈명 | 분리 대상 | 라인 | 목적 | 주의사항 |
|------|---------|------|------|---------|
| **local_agent_task_queue.py** | enqueue, mark_*, apply_result, cancel_task | 544-1050 | task 상태 관리 | stateful, 많은 의존성, 테스트 영향 큼 |
| **local_agent_timeout.py** | expire_stale_tasks, fail_active_tasks_for_agent | 724-817 | timeout/cleanup | optional 모듈 |

### 분리 영향도 분석

**API/Response 영향**:
- ✅ models 분리: 무영향 (내부 import)
- ✅ risk_policy 분리: 무영향 (내부 참조)
- ✅ serializers 분리: 무영향 (to_safe 메서드 시그니처 유지)
- ⚠️ task_queue 분리: 승인 게이트 분리로 router 호출 패턴 명확화 필요

**테스트 영향**:
- models, risk_policy, redaction, serializers: 낮음 (unit test 유지)
- store, task_queue: 중간 (integration test 수정 필요)

---

## STEP 2 종합 판정

### 각 구성요소별 판정

| 구성요소 | 판정 | 근거 |
|---------|------|------|
| **Agent 관리** | ✅ PASS_AGENT_SECURITY | token_hash/device_token 처리 명확 |
| **Task Queue** | ✅ PASS_STATE_MACHINE | 상태 전이 중앙화, VALID_TASK_TRANSITIONS |
| **Risk Policy** | ✅ PASS_RISK_POLICY_SEPARATION | 로컬/웹 정책 분리 |
| **Safe Serialization** | ✅ PASS_TOKEN_EXCLUSION | 민감정보 제외 명확 |
| **Lock/Memory** | ✅ PASS_LOCK_USAGE | 동시성 처리 명확 |

### 개선 필요 항목

| 항목 | 판정 | 우선순위 | 해결책 |
|------|------|---------|-------|
| **Action Coupling** | ⚠️ WARN_ACTION_COUPLING | 높음 | local_agent_risk_policy.py 분리 |
| **Serializer Coupling** | ⚠️ WARN_SERIALIZER_COUPLING | 높음 | local_agent_serializers.py 분리 |
| **Approval Coupling** | ⚠️ WARN_APPROVAL_COUPLING | 중간 | 모듈 경계 명확화 (분리 선택) |
| **Agent Status Coupling** | ⚠️ WARN_AGENT_STATUS_COUPLING | 낮음 | 필요한 결합 (해결 불필요) |
| **Volatile State Doc** | ⚠️ WARN_VOLATILE_STATE_DOCUMENTATION | 중간 | clear() 주석 추가, 문서화 |

---

## 최종 평가

### 종합 판정

**PASS_REGISTRY_CORE + WARN_MODULARIZATION_OPPORTUNITY**

local_agent_registry.py는:
1. ✅ 핵심 기능(agent 등록, task 큐, 상태 관리)이 명확하고 안전함
2. ✅ 보안 경계(token, sensitive, redaction)가 잘 구현됨
3. ✅ 동시성 처리(lock, memory store)가 일관됨
4. ⚠️ 1293줄에 6개 책임이 섞여 있음 → 모듈화 기회
5. ⚠️ 일부 정책(action, serializer)이 router와 중복 가능 → 분리 권장

### 모듈화 로드맵

**STEP 3**에서 다음 순서로 진행 권장:
1. local_agent_models.py: 기초 모듈
2. local_agent_risk_policy.py: action 정책 분리 (WARN_ACTION_COUPLING 해결)
3. local_agent_redaction.py: 민감정보 정책 분리
4. local_agent_serializers.py: serialization 통합 (WARN_SERIALIZER_COUPLING 해결)
5. local_agent_store.py: agent 저장소 분리
6. local_agent_task_queue.py: task 큐 분리 (신중한 검토 필요)
7. local_agent_timeout.py: timeout 처리 분리 (선택적)

---

## 다음 단계

**STEP 3**: 모듈화 후보 통합 로드맵 및 구현 계획 수립

