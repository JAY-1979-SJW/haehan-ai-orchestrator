# Browser Submit Approval UI State Integration 설계 문서

**작성일:** 2026-05-06  
**아키텍처:** UI Local State → Callback → Approval Event Payload  
**상태:** ✓ 설계 완료, 테스트 준비

---

## 1. 목적

Submit Approval Panel의 UI 로컬 상태(pending/approved/cancelled)를 **approval event payload**로 변환하고, 콜백 기반 흐름으로 backend approval state persistence와 연결합니다.

**지금까지 구현된 것:**
- STEP 2-3: UI 표준화 (SubmitApprovalPanel, Summary, Details, AuditRecord)
- STEP 2.5: Backend approval state persistence (append-only JSONL)

**이번 STEP의 목표:**
- UI 승인/취소 결정 → ApprovalDecisionPayload 생성
- Payload 검증 (required fields, enum values)
- Callback-based 흐름 (no direct API/DB call from UI)
- submitted=false 유지 (UI 상태만, 실제 제출 아님)

---

## 2. 아키텍처

### 2.1 전체 흐름

```
User clicks "제출 승인" or "취소"
         ↓
handleApprove() / handleCancel()
         ↓
createApprovalPayload(validation_id, preview_hash, "approved"|"cancelled")
         ↓
ApprovalDecisionPayload {
  approval_status: "approved" | "cancelled"
  validation_id: string
  preview_hash: string
  submitted: false
  approved_by?: string
  approved_at?: string
  cancelled_by?: string
  cancelled_at?: string
}
         ↓
UI state: pending → approved/cancelled
         ↓
onApprovalDecision(payload) ← callback invoked
         ↓
[Next: Backend receives payload and calls
 submit_approval_state.append_approval_state_event() to log]
```

### 2.2 컴포넌트 구조

**SubmitApprovalPanel.tsx**
- Props: `onApprovalDecision?: (payload: ApprovalDecisionPayload) => void`
- State: `state: "pending" | "approved" | "cancelled"`
- Handlers:
  - `handleApprove()`: 상태 변경 + payload 생성 + callback 호출
  - `handleCancel()`: 상태 변경 + payload 생성 + callback 호출

**approvalStatePayload.ts** (신규)
- `createApprovalPayload()`: 승인/취소 payload 생성
- `validateApprovalPayload()`: payload 타입 검증

### 2.3 상태 전이

```
       ┌─── [pending] ───┐
       │                 │
   [approve]         [cancel]
       │                 │
       ▼                 ▼
   [approved]       [cancelled]
       │                 │
       └── [terminal] ───┘
```

**각 상태에서의 UI:**
- `pending`: 승인/취소 버튼 표시
- `approved`: "✓ 승인 완료" 메시지 표시
- `cancelled`: "✗ 취소됨" 메시지 표시

---

## 3. API 인터페이스

### 3.1 ApprovalDecisionPayload 타입

```typescript
export interface ApprovalDecisionPayload {
  approval_status: 'approved' | 'cancelled';
  approved_by?: string;
  approved_at?: string;
  cancelled_by?: string;
  cancelled_at?: string;
  submitted: boolean;  // always false (UI state only)
  submit_result?: string;  // undefined (no actual submit)
  preview_hash: string;  // required (link to approval state log)
  validation_id: string;  // required (link to approval state log)
}
```

### 3.2 createApprovalPayload()

```typescript
export function createApprovalPayload(
  validation_id: string,
  preview_hash: string,
  approval_status: 'approved' | 'cancelled',
  decided_by?: string,
): ApprovalDecisionPayload
```

**동작:**
- `approval_status="approved"` → `approved_by`, `approved_at` 설정
- `approval_status="cancelled"` → `cancelled_by`, `cancelled_at` 설정
- `submitted=false` 항상 유지
- `timestamp` ISO 8601 형식으로 생성

**예시:**
```typescript
const payload = createApprovalPayload(
  "val_abc123",
  "hash_xyz789",
  "approved",
  "user_admin",
);
// {
//   approval_status: "approved",
//   approved_by: "user_admin",
//   approved_at: "2026-05-06T14:35:00.123Z",
//   submitted: false,
//   preview_hash: "hash_xyz789",
//   validation_id: "val_abc123",
// }
```

### 3.3 validateApprovalPayload()

```typescript
export function validateApprovalPayload(
  payload: unknown,
): payload is ApprovalDecisionPayload
```

**검증 규칙:**
- `approval_status` 필수, "approved" 또는 "cancelled"만
- `validation_id` 필수, 비어있지 않은 문자열
- `preview_hash` 필수, 비어있지 않은 문자열
- `submitted` 필수, **반드시 false**
- `approved_at` / `cancelled_at`: ISO 8601 형식 (있으면)
- `approved_by` / `cancelled_by`: 문자열 (선택사항)

**예시:**
```typescript
const payload = { /* ... */ };
if (validateApprovalPayload(payload)) {
  // payload is ApprovalDecisionPayload
  console.log(payload.validation_id);
}
```

---

## 4. SubmitApprovalPanel 콜백 통합

### 4.1 Props 변경

**변경 전:**
```typescript
interface SubmitApprovalPanelProps {
  preview: SubmitApprovalPreviewFixture;
  onApprove?: (validationId: string) => void;
  onCancel?: (validationId: string) => void;
  showAuditRecord?: boolean;
}
```

**변경 후:**
```typescript
interface SubmitApprovalPanelProps {
  preview: SubmitApprovalPreviewFixture;
  onApprovalDecision?: (payload: ApprovalDecisionPayload) => void;
  showAuditRecord?: boolean;
}
```

### 4.2 핸들러 구현

```typescript
const handleApprove = () => {
  // 1. Payload 생성
  const payload = createApprovalPayload(
    preview.validation_id,
    preview.preview_hash,
    "approved",
  );
  
  // 2. UI 상태 변경
  setState("approved");
  
  // 3. 콜백 호출 (backend로 전달)
  onApprovalDecision?.(payload);
};

const handleCancel = () => {
  // 1. Payload 생성
  const payload = createApprovalPayload(
    preview.validation_id,
    preview.preview_hash,
    "cancelled",
  );
  
  // 2. UI 상태 변경
  setState("cancelled");
  
  // 3. 콜백 호출
  onApprovalDecision?.(payload);
};
```

### 4.3 주요 특징

- ✓ 순수 UI 상태 변경 (React useState)
- ✓ Callback 기반 흐름 (payload 전달만)
- ✓ 실제 submit/fetch/API 호출 없음
- ✓ submitted=false 유지
- ✓ 민감정보 미포함 (validation_id, preview_hash만)

---

## 5. 테스트 전략

### 5.1 approvalStatePayload 단위 테스트 (19 tests)

**createApprovalPayload():**
- ✓ approved payload 생성
- ✓ cancelled payload 생성
- ✓ decided_by 선택사항 처리
- ✓ timestamp ISO 8601 형식
- ✓ 잘못된 status 시 error throw

**validateApprovalPayload():**
- ✓ 유효한 payload 검증
- ✓ 필드 누락 시 false 반환
- ✓ 잘못된 approval_status 거부
- ✓ submitted=true 거부
- ✓ 타입 불일치 거부

### 5.2 SubmitApprovalPanel 통합 테스트 (18 tests)

**상태 변경 (4 tests):**
- ✓ pending → approved
- ✓ pending → cancelled
- ✓ 버튼 렌더링 (pending 상태)
- ✓ 확인 메시지 표시

**Payload 생성 (5 tests):**
- ✓ onApprovalDecision callback 호출 (approved)
- ✓ onApprovalDecision callback 호출 (cancelled)
- ✓ validation_id 포함
- ✓ preview_hash 포함
- ✓ Payload 구조 완전성

**네트워크 금지 (3 tests):**
- ✓ fetch 호출 없음 (approve)
- ✓ fetch 호출 없음 (cancel)
- ✓ 실제 submit 없음 (submitted=false)

**Payload 검증 (4 tests):**
- ✓ approved payload 유효성
- ✓ cancelled payload 유효성
- ✓ submitted=false 유지
- ✓ 필수 필드 포함

**기존 호환성 (2 tests):**
- ✓ Details 토글 동작
- ✓ Audit record 표시 (showAuditRecord=true)

### 5.3 테스트 도구

- Framework: Jest + React Testing Library
- Utilities: @testing-library/react, @testing-library/user-event
- Mocking: jest.fn() for callbacks

---

## 6. 구현 원칙

### 6.1 UI는 상태 변경만 (Submit은 하지 않음)

✓ **허용:**
- setState("approved")
- onApprovalDecision(payload) 콜백

✗ **금지:**
- fetch(), axios()
- document.querySelector("form").submit()
- window.location.href = "..."

### 6.2 Payload는 metadata only

✓ **포함:**
- validation_id (approval state log 연결용)
- preview_hash (approval state log 연결용)
- approval_status ("approved" | "cancelled")
- timestamp

✗ **미포함:**
- 폼 입력값 원문
- 비밀번호, 토큰, API 키
- 사용자 개인정보

### 6.3 submitted는 항상 false

```typescript
submitted: false  // UI 상태만, 실제 제출 아님
```

Backend approval flow와 별개입니다:
- UI approval: "이 요청을 승인합니다" (UI 상태)
- Form submit: "이 폼을 실제로 제출합니다" (별도 단계)

### 6.4 타입 안정성

- TypeScript interface로 payload 정의
- validateApprovalPayload() 런타임 검증
- Jest 테스트로 타입 일치 검증

---

## 7. 다음 단계

### 7.1 Backend 통합 (STEP 10 - 미래)

```
UI callback:
onApprovalDecision(payload)
         ↓
Backend handler receives payload
         ↓
submit_approval_state.create_approval_decision_event()
         ↓
submit_approval_state.append_approval_state_event()
         ↓
Append-only JSONL log recorded
```

### 7.2 감사 흐름 (STEP 11 - 미래)

- 승인 히스토리 조회 API
- 감사 리포트 UI
- 컴플라이언스 보고서

---

## 8. 파일 구조

```
admin-web/src/components/browser-submit/
├── SubmitApprovalPanel.tsx (수정)
├── approvalStatePayload.ts (신규)
├── __fixtures__/
│   └── submitApprovalPreview.fixture.ts
└── __tests__/
    ├── SubmitApprovalPanel.test.tsx (기존, Props 업데이트)
    ├── SubmitApprovalPanel.approval-integration.test.tsx (신규, 18 tests)
    └── approvalStatePayload.test.ts (신규, 19 tests)

docs/
├── design/
│   └── browser_submit_approval_ui_state_integration_20260506.md (이 파일)
└── reports/
    └── browser_submit_approval_ui_state_integration_20260506.md (다음 STEP)
```

---

## 9. 보안 체크리스트

| 항목 | 상태 |
|------|------|
| 실제 form submit 없음 | ✓ |
| Network call 없음 | ✓ |
| DB 호출 없음 | ✓ |
| 민감정보 원문 미포함 | ✓ |
| submitted=false 유지 | ✓ |
| Production safeguard notice | ✓ |

---

**설계 완료 일시:** 2026-05-06 15:00 KST  
**상태:** ✓ 설계 문서 완성  
**다음:** STEP 8 Commit 및 검증
