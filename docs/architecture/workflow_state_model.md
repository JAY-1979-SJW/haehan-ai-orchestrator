# 작업흐름 / 상태 모델 (Workflow State Model)

고정일: 2026-05-15  
작업 ID: APP_FOUNDATION_GOVERNANCE_LOCK_01  
상태: LOCKED

---

## 1. 상태 목록 (States)

| 상태 | 코드 | 설명 |
|------|------|------|
| 요청됨 | REQUESTED | 작업이 시스템에 접수됨 |
| 검증됨 | VALIDATED | 입력값·형식·범위 유효성 확인 완료 |
| 초안 생성 | DRAFT_CREATED | 실행 계획·초안 문서 생성 완료 |
| 승인 대기 | APPROVAL_REQUIRED | 지정 권한자의 명시적 승인 대기 중 |
| 승인됨 | APPROVED | 승인 완료. 실행 조건 충족. |
| 사용자 직접 대기 | USER_DIRECT_REQUIRED | AI 실행 불가. 사용자가 외부에서 직접 수행 필요. |
| 로컬 에이전트 대기 | LOCAL_AGENT_REQUIRED | 서버 실행 불가. 사용자 PC 에이전트 대기. |
| 실행 준비 | EXECUTION_READY | 모든 gate 통과. 실행 직전 상태. |
| 실행 중 | EXECUTING | 작업 실행 중 |
| 실행 완료 | EXECUTED | 실행 완료. 증거 수집 전. |
| 증거 수집 | EVIDENCE_COLLECTED | 실행 결과·스크린샷·로그 기록 완료 |
| 완료 | COMPLETED | 전체 흐름 완료. 감사로그 기록됨. |
| 거부됨 | REJECTED | 승인 거부 또는 gate 거절 |
| 차단됨 | BLOCKED | 보안 정책상 실행 불가. 실행계획도 없음. |
| 실패 | FAILED | 실행 중 오류 발생 |
| 취소됨 | CANCELLED | 사용자 또는 시스템이 중단 |

---

## 2. 표준 전이 흐름

```
REQUESTED
  → VALIDATED         (입력 검증 통과)
  → DRAFT_CREATED     (초안 생성)
  → APPROVAL_REQUIRED (gate: APPROVAL_REQUIRED)
    → APPROVED        (승인자 명시적 승인)
    → EXECUTION_READY
    → EXECUTING
    → EXECUTED
    → EVIDENCE_COLLECTED
    → COMPLETED

  또는
  → USER_DIRECT_REQUIRED (gate: USER_DIRECT_REQUIRED)
    (사용자가 외부 사이트에서 직접 수행)
    → COMPLETED (사용자 확인 후)

  또는
  → LOCAL_AGENT_REQUIRED (gate: LOCAL_AGENT_REQUIRED)
    (사용자 PC 에이전트가 수행)
    → EXECUTING
    → EXECUTED
    → EVIDENCE_COLLECTED
    → COMPLETED
```

---

## 3. 금지 전이 (이 전이는 절대 일어나서는 안 됨)

| 금지 전이 | 이유 |
|----------|------|
| DRAFT_CREATED → EXECUTING | 승인 없이 실행 금지 |
| APPROVAL_REQUIRED → EXECUTING | 승인 단계 건너뛰기 금지 |
| USER_DIRECT_REQUIRED → EXECUTING | AI가 직접 실행 금지 |
| BLOCKED → 임의 상태 | BLOCKED는 종착 상태 |
| REJECTED → EXECUTING | 거부된 작업 재실행 금지 (재요청 필요) |

---

## 4. 감사 로그 의무

다음 전이는 반드시 감사로그에 기록한다:

```
REQUESTED         → who, what, when, params
VALIDATED         → validation results
DRAFT_CREATED     → draft content hash, generated_at
APPROVAL_REQUIRED → gate decision, required_approver
APPROVED          → approver_id, approved_at, scope
REJECTED          → rejector_id, reason, rejected_at
EXECUTING         → executor, started_at, action_params
EXECUTED          → result_summary, ended_at
EVIDENCE_COLLECTED→ evidence_path, screenshot_path
COMPLETED         → completed_at, total_duration
FAILED            → error_type, error_message, stack_trace
CANCELLED         → cancelled_by, reason
BLOCKED           → gate_decision, blocked_at, reason
```

---

## 5. 위험 작업별 필수 상태 포함

| 작업 | 필수 상태 |
|------|----------|
| DNS 레코드 추가 | DRAFT_CREATED → APPROVAL_REQUIRED → APPROVED → USER_DIRECT_REQUIRED |
| DNS 레코드 삭제 | DRAFT_CREATED → APPROVAL_REQUIRED → APPROVED → USER_DIRECT_REQUIRED |
| 도메인 등록 | DRAFT_CREATED → USER_DIRECT_REQUIRED |
| 결제 | USER_DIRECT_REQUIRED (초안도 AI가 생성 불가) |
| 외부 로그인 (서버) | BLOCKED |
| 외부 로그인 (PC) | LOCAL_AGENT_REQUIRED |
| 공동인증서 사용 | USER_DIRECT_REQUIRED |
| 유튜브 업로드 | DRAFT_CREATED → APPROVAL_REQUIRED → EXECUTING |
| 메일 발송 | DRAFT_CREATED → APPROVAL_REQUIRED → EXECUTING |
| 입찰 제출 | DRAFT_CREATED → APPROVAL_REQUIRED → USER_DIRECT_REQUIRED |
