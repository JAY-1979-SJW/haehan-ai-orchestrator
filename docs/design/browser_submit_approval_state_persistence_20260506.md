# Browser Submit Approval State Persistence 설계 문서

**작성일:** 2026-05-06  
**모듈:** ai_orchestrator/browser_tool/approval/submit_approval_state.py  
**상태:** ✓ 설계 완료, 테스트 30/30 PASS

---

## 1. 목적

승인 UI의 로컬 상태를 **감사 가능한 persistence 구조**로 확장합니다.

### 배경
- Submit Approval Panel은 현재 로컬 상태만 관리 (React useState)
- 사용자 승인/취소 결정이 영구 기록되지 않음
- 감사/컴플라이언스 요구사항 충족 필요

### 목표
- 승인 결정을 append-only JSONL로 기록
- 시간 기반 감사 추적 가능
- 중복 승인 방지 (validation_id + preview_hash 기반)
- 운영 환경 영향 없음 (DB/네트워크 호출 없음)

---

## 2. JSONL 이벤트 구조

### 2.1 전체 구조

```
approval_state.jsonl (append-only event log)
├─ 한 줄 = 한 이벤트 (JSONL format)
├─ 절대 truncate/overwrite하지 않음
├─ 새 이벤트는 항상 append
└─ 시간순으로 정렬됨
```

### 2.2 이벤트 스키마

모든 이벤트는 다음 필드를 포함합니다:

```json
{
  "schema_version": "1.0",
  "event_type": "approval_requested|approval_decision_approved|approval_decision_cancelled",
  "validation_id": "val_xxxxx",
  "preview_hash": "hash_xxxxx",
  "timestamp": "2026-05-06T14:15:30.123456Z"
}
```

### 2.3 이벤트 타입

#### 2.3.1 approval_requested
사용자가 승인을 요청했을 때 발행됩니다.

```json
{
  "schema_version": "1.0",
  "event_type": "approval_requested",
  "validation_id": "val_xxxxx",
  "preview_hash": "hash_xxxxx",
  "site_id": "site_1",
  "form_id": "form_1",
  "user_id": "user_1",
  "tenant_id": "tenant_1",
  "timestamp": "2026-05-06T14:15:30.123456Z"
}
```

**필드:**
- `schema_version` (string): 스키마 버전 (현재 "1.0")
- `event_type` (string): "approval_requested"
- `validation_id` (string, 필수): 검증 식별자 (submit_preview.validation_id와 동일)
- `preview_hash` (string, 필수): 미리보기 해시 (중복 승인 방지)
- `site_id` (string): 대상 사이트
- `form_id` (string): 대상 양식
- `user_id` (string, optional): 요청한 사용자
- `tenant_id` (string, optional): 테넌트 식별자
- `timestamp` (string): ISO 8601 UTC 타임스탬프

#### 2.3.2 approval_decision_approved
사용자가 승인했을 때 발행됩니다.

```json
{
  "schema_version": "1.0",
  "event_type": "approval_decision_approved",
  "validation_id": "val_xxxxx",
  "preview_hash": "hash_xxxxx",
  "approval_status": "approved",
  "decided_by": "user_admin",
  "timestamp": "2026-05-06T14:15:35.654321Z"
}
```

**필드:**
- `schema_version` (string): "1.0"
- `event_type` (string): "approval_decision_approved"
- `validation_id` (string, 필수): approval_requested 이벤트와 동일
- `preview_hash` (string, 필수): 동일 해시로 이벤트 연결
- `approval_status` (string): "approved"
- `decided_by` (string, optional): 결정한 사용자/시스템
- `timestamp` (string): ISO 8601 UTC 타임스탬프

#### 2.3.3 approval_decision_cancelled
사용자가 취소했을 때 발행됩니다.

```json
{
  "schema_version": "1.0",
  "event_type": "approval_decision_cancelled",
  "validation_id": "val_xxxxx",
  "preview_hash": "hash_xxxxx",
  "approval_status": "cancelled",
  "decided_by": "user_admin",
  "timestamp": "2026-05-06T14:15:40.111111Z"
}
```

**필드:**
- approval_decision_approved와 동일, event_type과 approval_status만 다름

---

## 3. 상태 모델

### 3.1 상태 전이도

```
[pending] 
  ↓
  ├─→ [approved] (사용자가 승인)
  └─→ [cancelled] (사용자가 취소)
```

**상태 정의:**

| 상태 | 의미 | 최신 이벤트 | 다음 가능 상태 |
|------|------|-----------|-------------|
| pending | 승인 대기 중 | approval_requested | approved, cancelled |
| approved | 사용자가 승인함 | approval_decision_approved | (종료) |
| cancelled | 사용자가 취소함 | approval_decision_cancelled | (종료) |

### 3.2 상태 조회 로직

```python
def get_approval_status(event: Optional[dict]) -> str:
    """
    이벤트로부터 상태 문자열 반환
    
    event=None          → "pending"
    event_type=...requested  → "pending"
    event_type=...approved   → "approved"
    event_type=...cancelled  → "cancelled"
    """
```

---

## 4. API 인터페이스

### 4.1 Event Creation

#### create_approval_requested_event()
```python
def create_approval_requested_event(
    validation_id: str,
    preview_hash: str,
    site_id: str,
    form_id: str,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> dict
```

**역할:** 승인 요청 이벤트 생성  
**파라미터:** 검증 ID, 해시, 사이트/양식, 선택적 사용자/테넌트  
**반환:** 이벤트 dict  
**예외:** ValidationError (필수 필드 누락)

#### create_approval_decision_event()
```python
def create_approval_decision_event(
    validation_id: str,
    preview_hash: str,
    approval_status: str,  # "approved" or "cancelled"
    decided_by: Optional[str] = None,
) -> dict
```

**역할:** 승인 결정 이벤트 생성 (승인 또는 취소)  
**파라미터:** 검증 ID, 해시, 상태, 선택적 결정자  
**반환:** 이벤트 dict  
**예외:** ValidationError (필드 누락 또는 상태 유효하지 않음)

### 4.2 Persistence

#### append_approval_state_event()
```python
def append_approval_state_event(log_path: Path, event: dict) -> None
```

**역할:** 이벤트를 JSONL 로그에 append (절대 truncate하지 않음)  
**파라미터:** 로그 파일 경로, 이벤트 dict  
**부작용:** 파일 생성/append  
**예외:** ValidationError (event 검증 실패), IOError (파일 쓰기 실패)  
**중요:** 기존 파일을 절대 덮어쓰지 않음

#### read_approval_state_events()
```python
def read_approval_state_events(log_path: Path) -> list[dict]
```

**역할:** JSONL 로그의 모든 이벤트를 읽음  
**파라미터:** 로그 파일 경로  
**반환:** 이벤트 list (시간순, 파일 없으면 [])  
**예외:** ApprovalStateError (JSON parse 오류)  
**동작:**
- 파일 없음 → []
- 빈 줄 skip
- 한 줄 = 한 JSON 객체
- JSON 오류 시 예외

### 4.3 State Query

#### latest_approval_state()
```python
def latest_approval_state(
    events: list[dict],
    preview_hash: str,
) -> Optional[dict]
```

**역할:** 주어진 preview_hash의 최신 이벤트 반환  
**파라미터:** 이벤트 list, preview_hash  
**반환:** 최신 이벤트 or None  
**로직:**
1. events에서 preview_hash 일치하는 모든 이벤트 찾기
2. 마지막 이벤트 (가장 최신) 반환

**예시:**
```
events = [
  {event_type: "approval_requested", preview_hash: "h1", ...},
  {event_type: "approval_decision_approved", preview_hash: "h1", ...},
]
latest_approval_state(events, "h1") → approval_decision_approved 이벤트
```

#### get_approval_status()
```python
def get_approval_status(event: Optional[dict]) -> str
```

**역할:** 이벤트로부터 상태 문자열 반환  
**파라미터:** 이벤트 dict or None  
**반환:** "pending", "approved", "cancelled", "unknown"  
**매핑:**
- None → "pending"
- event_type="approval_requested" → "pending"
- event_type="approval_decision_approved" → "approved"
- event_type="approval_decision_cancelled" → "cancelled"

---

## 5. 사용 예시

### 5.1 기본 흐름

```python
from pathlib import Path
from ai_orchestrator.browser_tool.approval.submit_approval_state import (
    create_approval_requested_event,
    create_approval_decision_event,
    append_approval_state_event,
    read_approval_state_events,
    latest_approval_state,
    get_approval_status,
)

# 로그 파일 (테스트: tmp_path, 운영: 구성된 경로)
log_path = Path("/tmp/approval_state.jsonl")

# 1. 승인 요청
event1 = create_approval_requested_event(
    validation_id="val_abc123",
    preview_hash="hash_xyz789",
    site_id="site_1",
    form_id="form_1",
    user_id="user_john",
)
append_approval_state_event(log_path, event1)

# 2. 사용자 승인
event2 = create_approval_decision_event(
    validation_id="val_abc123",
    preview_hash="hash_xyz789",
    approval_status="approved",
    decided_by="user_john",
)
append_approval_state_event(log_path, event2)

# 3. 상태 조회
events = read_approval_state_events(log_path)
latest_event = latest_approval_state(events, "hash_xyz789")
status = get_approval_status(latest_event)  # "approved"
```

### 5.2 UI 통합 (개념)

```python
# SubmitApprovalPanel에서:

# UI 상태 변경 시
def handleApprove():
    # 1. UI 상태 업데이트 (기존)
    setState("approved")
    
    # 2. Persistence 기록 (신규)
    import submit_approval_state
    event = submit_approval_state.create_approval_decision_event(
        validation_id=preview.validation_id,
        preview_hash=preview.preview_hash,
        approval_status="approved",
        decided_by=current_user_id,
    )
    submit_approval_state.append_approval_state_event(
        log_path,
        event,
    )
    
    # 3. 콜백 실행
    onApprove?.(preview.validation_id)
```

---

## 6. 구현 원칙

### 6.1 순수 Python

- 외부 라이브러리 없음 (json, pathlib만 사용)
- 네트워크 호출 없음
- DB 호출 없음
- 환경변수 읽기 없음
- 외부 시스템 의존성 없음

### 6.2 Append-Only

- JSONL 파일 절대 truncate하지 않음
- 파일 덮어쓰기 없음
- 항상 append 모드로 열기
- 기존 데이터 변경 불가

### 6.3 테스트 경로

- 실제 운영 경로: 적용 시 구성
- 테스트: tmp_path만 사용
- 테스트에서 /home/ubuntu/apps 같은 운영 경로 접근 금지

### 6.4 검증

- validation_id 필수
- preview_hash 필수
- approval_status는 "approved" 또는 "cancelled"만 허용
- 필수 필드 누락 시 ValidationError 발생

### 6.5 보안

- 로그에 민감정보(비밀번호, 토큰) 저장 금지
- preview_hash로만 연결 (실제 내용 미저장)
- validation_id도 마스킹 필요 시 추후 처리

---

## 7. 테스트 커버리지

### 테스트 30/30 PASS (2026-05-06)

| 카테고리 | 테스트 수 | 상태 |
|---------|---------|------|
| approval_requested 이벤트 | 4 | ✓ |
| approval_decision 이벤트 | 6 | ✓ |
| Append-only 동작 | 3 | ✓ |
| JSONL 읽기 | 4 | ✓ |
| 최신 상태 조회 | 5 | ✓ |
| 상태 문자열 | 4 | ✓ |
| End-to-end 흐름 | 2 | ✓ |
| 외부 의존성 없음 | 2 | ✓ |

---

## 8. 다음 단계

### 8.1 UI 통합 (STEP 7)
- SubmitApprovalPanel에서 approval state 기록
- validation_id + preview_hash로 이벤트 생성
- approve/cancel 클릭 시 이벤트 append

### 8.2 운영 경로 구성
- 로그 파일 경로 결정
- 권한 설정 (읽기/쓰기)
- 로그 로테이션 정책 (선택사항)

### 8.3 감사 리포트
- 승인 히스토리 조회 UI
- 감사 경로 추적
- 컴플라이언스 보고서

---

## 9. 알려진 제한사항

### 9.1 충돌 처리
- approved 이후 cancelled 같은 중복 승인은 latest 기반으로 처리
- 애플리케이션 로직에서 충돌 처리 필요

### 9.2 파일 잠금
- 동시 쓰기 안전성 미보장 (단일 프로세스 환경 가정)
- 멀티 프로세스 환경에서는 파일 잠금 추가 필요

### 9.3 로그 크기
- 무제한 append로 파일 커질 수 있음
- 로테이션 정책 필요 (운영 단계)

---

**설계 완료 일시:** 2026-05-06 14:30 KST  
**상태:** ✓ 설계 문서 완성, 테스트 30/30 PASS  
**다음:** STEP 7 UI 통합 (계획)

