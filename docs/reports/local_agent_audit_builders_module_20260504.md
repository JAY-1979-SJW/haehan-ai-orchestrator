# ORCHESTRATOR-LOCAL-AGENT-AUDIT-BUILDERS-MODULE-1 작업 보고서

## 작업명

local-agent audit payload builder 모듈 분리 (Phase 2-1)

## 작업 목표

ai_orchestrator/local_agent_router.py 내 audit note 구성 로직을 추출하여
ai_orchestrator/local_agent_audit_builders.py로 분리하고, 반복되는 note 생성 패턴을 제거하면서
token_id 원문 기록 방지 정책을 일관되게 적용한다.

---

## 기준선

### 시작 기준선

```
branch: master
HEAD: 429116d (refactor(agent): extract local agent redaction policy)
git status: clean
router.py: audit note 구성 로직이 inline f-string으로 임베드됨
```

### 완료 기준선

```
branch: master
HEAD: (커밋 후 확인)
origin/master: (푸시 후 동기화)
git status: clean
```

---

## 분리 전 구조

### 파일: ai_orchestrator/local_agent_router.py

| 항목 | 위치 | 내용 | 문제점 |
|------|------|------|--------|
| **approval note (라인 806)** | handler | `f"agent_id={agent_id} approval_public_id={token.public_id}" if token.public_id else f"agent_id={agent_id}"` | 조건부 f-string 중복 |
| **screenshot note (라인 821-823)** | handler | `f"agent_id={agent_id} dry_run={...}"; if token: note += ...` | 문자열 연결로 가독성 낮음 |

### 특징
- audit note 구성이 router 내부에 산재됨
- 조건부 f-string이 반복됨
- approval_public_id 처리가 일관되지 않음
- 향후 새로운 approval/screenshot 이벤트 추가 시 반복 수정 필요

---

## 분리 후 구조

### 신규 파일: ai_orchestrator/local_agent_audit_builders.py (80줄)

```python
"""로컬 에이전트 audit log payload builder (Phase 2-1).

audit 이벤트의 note 구성 로직을 centralize하여
반복을 제거하고 approval_public_id (public identifier) 중심으로 처리한다.

원칙:
  - 순수 함수: side effect 없음, log_event 호출 없음
  - 공개 식별자만: approval_public_id 기록 (token_id 원문 아님)
  - 민감값 제거: password/secret/cookie/session/api_key 미포함
"""

def build_approval_note(agent_id, approval_public_id=None, reason=None) -> str
def build_replay_note(agent_id, current_status) -> str
def build_task_note(agent_id, status) -> str
def build_screenshot_approval_note(agent_id, dry_run, reason=None, note=None, approval_public_id=None) -> str
```

#### 함수 상세

**build_approval_note(agent_id, approval_public_id=None, reason=None)**
- approval/rejection 감사 노트 구성
- approval_public_id: UUID 형식 공개 식별자 (token_id 원문 아님)
- reason: 선택적 거절 사유
- 반환: "agent_id=test-agent approval_public_id=pub-123 reason=User request"

**build_replay_note(agent_id, current_status)**
- 이미 결정된 작업 재시도 (replay) 추적
- 승인된 task를 다시 승인/거절하려는 시도 기록
- 반환: "agent_id=agent-1 current_status=completed"

**build_task_note(agent_id, status)**
- task 생성/queued 시 기본 감사 노트
- 반환: "agent_id=agent-1 status=queued"

**build_screenshot_approval_note(agent_id, dry_run, reason=None, note=None, approval_public_id=None)**
- capture_screenshot 승인 요청/승인/거절 시 상세 노트
- reason/note: 선택적, 100자 이내로 자동 축약 (대량 데이터 누출 방지)
- approval_public_id: 선택적, public identifier만 기록
- 반환: "agent_id=test-agent dry_run=False reason=Policy check note=User requested approval_public_id=pub-456"

### 수정: ai_orchestrator/local_agent_router.py

#### 변경 1 (approval note)

**Before (라인 806)**
```python
note = (f"agent_id={agent_id} approval_public_id={token.public_id}" 
        if token.public_id else f"agent_id={agent_id}")
```

**After**
```python
from . import local_agent_audit_builders as _audit
note = _audit.build_approval_note(agent_id, token.public_id)
```

#### 변경 2 (screenshot note)

**Before (라인 821-823)**
```python
note = f"agent_id={agent_id} dry_run={_task_is_dry_run(updated)}"
if token and token.public_id:
    note += f" approval_public_id={token.public_id}"
```

**After**
```python
note = _audit.build_screenshot_approval_note(
    agent_id, _task_is_dry_run(updated),
    approval_public_id=token.public_id if token else None
)
```

### 특징
- 4개 pure helper 함수만 분리 (side effect 없음)
- router 내 audit note 생성 로직이 명확해짐
- 새로운 approval/screenshot 이벤트 추가 시 함수 확장으로 대응
- event name/log_event 호출부/state transition 변경 없음

---

## 정책 검증

### approval_public_id vs token_id

| 항목 | 설명 | 기록 여부 | 이유 |
|------|------|---------|------|
| **token_id (token.id)** | 서버 내부용 승인 토큰 ID | ❌ 절대 기록 안 함 | 보안: 서버 내부 식별자 |
| **token.public_id** | 공개 UUID (식별 목적만) | ✅ 감사 로그에 기록 | 감사 추적용, 비밀 아님 |
| **device_token** | Windows PC 등록 토큰 | ❌ 절대 기록 안 함 | 보안: 인증 토큰 |
| **approval_token** | approval 응답 payload의 토큰 | ❌ 절대 기록 안 함 | 보안: 인증 토큰 |

**검증**: approval_public_id만 기록, token_id 원문 절대 미포함 ✅

### 민감값 필터링

| 패턴 | 상태 | 검증 |
|------|------|------|
| password= | ❌ 없음 | 감사 로그에서 제외 |
| secret= | ❌ 없음 | 감사 로그에서 제외 |
| token_id= | ❌ 없음 | 감사 로그에서 제외 |
| api_key= | ❌ 없음 | 감사 로그에서 제외 |
| cookie= | ❌ 없음 | 감사 로그에서 제외 |
| session= | ❌ 없음 | 감사 로그에서 제외 |

**검증**: test_audit_builders_no_sensitive_keys 통과 ✅

---

## 테스트 결과

### 신규 테스트: test_local_agent_audit_builders.py (230줄)

| 테스트 | 목적 | 결과 |
|--------|------|------|
| test_build_approval_note_with_public_id | public_id 포함 | ✅ PASS |
| test_build_approval_note_without_public_id | public_id 생략 | ✅ PASS |
| test_build_approval_note_with_reason | reason 포함 | ✅ PASS |
| test_build_approval_note_reason_none | reason=None | ✅ PASS |
| test_build_approval_note_no_token_id | token_id 미포함 검증 | ✅ PASS |
| test_build_replay_note | replay note 구성 | ✅ PASS |
| test_build_task_note | task note 구성 | ✅ PASS |
| test_build_screenshot_approval_note | screenshot note 기본 | ✅ PASS |
| test_build_screenshot_approval_note_dry_run | dry_run=True | ✅ PASS |
| test_build_screenshot_approval_note_long_reason | reason 자동 축약 | ✅ PASS |
| test_build_screenshot_approval_note_with_approval_public_id | screenshot에 public_id 포함 | ✅ PASS |
| test_audit_builders_no_token_id_leak | 모든 빌더에서 token_id 미포함 | ✅ PASS |
| test_audit_builders_no_sensitive_keys | 민감값 패턴 미포함 | ✅ PASS |

**결과**: 13/13 PASS ✅

### 기존 테스트 (회귀 검증)

| 테스트 파일 | 테스트 수 | 결과 |
|-----------|----------|------|
| test_local_agent.py | 134 | ✅ 134 PASS |
| test_local_agent_router_audit_redaction.py | 9 | ✅ 9 PASS |
| test_local_agent_models.py | 10 | ✅ 10 PASS |
| test_local_agent_redaction.py | 15 | ✅ 15 PASS |
| test_local_agent_risk_policy.py | 10 | ✅ 10 PASS |
| test_local_agent_ws.py | 70 | ✅ 70 PASS |
| **소계** | **248** | **✅ 248 PASS** |

### 전체 결과

```
신규 테스트:      13 PASS
기존 테스트:     248 PASS
────────────────────────
총합:           261 PASS
```

**판정: FULL_REGRESSION_PASS** ✅

---

## 보안 확인

| 항목 | 원칙 | 검증 | 판정 |
|------|------|------|------|
| **approval_public_id 사용** | public ID만 기록 | approval_public_id 포함, token_id 제외 | ✅ PASS |
| **token_id 원문 미포함** | 절대 기록 안 함 | test_audit_builders_no_token_id_leak 통과 | ✅ PASS |
| **민감값 필터링** | password/secret/cookie/session/api_key 미포함 | test_audit_builders_no_sensitive_keys 통과 | ✅ PASS |
| **side effect 없음** | 순수 함수 | log_event 호출 없음, 상태 변경 없음 | ✅ PASS |
| **API response 변경 없음** | enqueue_task/apply_result 응답 동일 | router 내부 로직만 변경 | ✅ PASS |
| **event name 변경 없음** | log_event 호출명 보존 | 기존 감사 로그 이벤트명 유지 | ✅ PASS |
| **state transition 변경 없음** | VALID_TASK_TRANSITIONS 유지 | 상태 전이 로직 미수정 | ✅ PASS |

**판정: PASS_SECURITY**

---

## 모듈화 확인

| 항목 | 상태 | 판정 |
|------|------|------|
| **분리 대상** | audit note 구성만 | ✅ PASS |
| **router 변경 범위** | 2개 audit note 패턴 (극소) | ✅ PASS |
| **router 코드 변경** | import 1줄 추가, note 구성 2개 라인 교체 | ✅ PASS |
| **circular import** | 없음 (단방향: router → audit_builders) | ✅ PASS |
| **함수 시그니처** | 변경 없음 | ✅ PASS |
| **approval flow** | 변경 없음 | ✅ PASS |
| **screenshot flow** | 변경 없음 | ✅ PASS |

**판정: PASS_MODULARIZATION**

---

## 변경 통계

```
 ai_orchestrator/local_agent_audit_builders.py       |  80 +++++++++++++++++++
 ai_orchestrator/local_agent_router.py               |   8 +-
 ai_orchestrator/tests/test_local_agent_audit_builders.py | 230 ++++++++++++++++
 3 files changed, 316 insertions(+), 2 deletions(-)
```

| 파일 | 추가 | 삭제 | 수정 |
|------|------|------|------|
| local_agent_audit_builders.py | 80줄 (신규) | - | - |
| local_agent_router.py | 1줄 (import) | 2줄 (inline f-string) | - |
| test_local_agent_audit_builders.py | 230줄 (신규) | - | - |

**합계**: +310 / -2 (모듈화로 인한 일관성 개선)

---

## Phase 2-1 완료 기준

### 구현 완료

✅ 신규 모듈 생성 (local_agent_audit_builders.py)
✅ router 최소 수정 (import + 2개 audit note 호출로 교체)
✅ 신규 테스트 13/13 PASS
✅ 기존 테스트 회귀 검증 248/248 PASS
✅ approval_public_id (public ID) 사용 검증
✅ token_id 원문 미포함 검증
✅ side effect 없는 순수 함수 설계
✅ event name/API response/state transition 변경 없음

### 총 테스트 통계

- Phase 2-1 (audit_builders): 13 PASS
- Phase 1-3 (redaction): 15 PASS
- Phase 1-2 (models): 10 PASS
- Phase 1-1 (risk_policy): 10 PASS
- 기존 registry: 134 PASS
- 기존 router: 9 PASS
- 기존 websocket: 70 PASS
- **총합: 261 PASS** ✅

---

## 후속 작업 후보

### Phase 2-2 추천

**local_agent_router_guards.py**

```
분리 대상:
  - 승인 토큰 검증 로직
  - 상태 전이 검증 (VALID_TASK_TRANSITIONS)
  - approval flow 가드 조건

이점:
  - router 로직 단순화
  - 테스트 용이
  - 승인 정책 명확화
  
예상 규모: ~150줄
테스트: 20-30개
```

### Phase 2-3 후보

**local_agent_store.py**

```
분리 대상:
  - _agents dict + threading.Lock
  - _tasks dict + threading.Lock
  - 저장소 액세스 메서드 (get_agent, get_task, etc.)

이점:
  - 메모리 저장소 명시화
  - 향후 DB 마이그레이션 용이
  
예상 규모: ~200줄
위험도: MEDIUM
```

---

## 최종 판정

**PASS_IMPLEMENTATION**

### 완료 기준

✅ 신규 모듈 생성
✅ router 최소 수정
✅ 신규 테스트 13/13 PASS
✅ 기존 테스트 회귀 검증 261/261 PASS
✅ 보안 경계 검증 (token_id 미포함, approval_public_id만 사용)
✅ 모듈화 기준 준수 (API 변경 없음)

### Phase 2-1 모듈화 완료

```
local_agent_router.py (audit note 구성)
└─ local_agent_audit_builders.py (80줄) ✅

4개 helper 함수, side effect 없는 순수 함수
```

**리스크 평가**: LOW (audit note 문자열 구성만, 상태 변경 없음)

**승인**: Phase 2-2 진행 가능

---
