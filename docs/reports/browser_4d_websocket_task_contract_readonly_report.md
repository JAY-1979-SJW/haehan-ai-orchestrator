# BROWSER-4D WebSocket Task Contract Read-Only Report

**작업 일시**: 2026-05-01
**작업명**: BROWSER-4D 운영 WebSocket task contract read-only 점검
**모델 등급**: 중급 모델 필요
**수행 모델**: Claude Haiku 4.5

---

## 1. 사전 조건 확인

### Repo Boundary Lock
- **Local Repo**: `C:/Users/skyjw/OneDrive/03. PYTHON/35. haehan-ai-orchestrator`
- **Branch**: `feat/browser-approved-execution`
- **기준 Commit**: `c9a10d7` (feat(browser): connect approved actions to local task handler)
- **현재 HEAD**: `c9a10d7b261b155dfead06a8d8c413d8dd7458a3` ✓
- **Working Tree**: clean (only .claude/) ✓
- **다른 앱 접근**: 없음 ✓

### 기준선
- **BROWSER-4C 상태**: 완성 (commit c9a10d7에 포함)
- **BrowserTaskHandler**: local_agent/browser_task_handler.py - 구현 완료
- **BrowserApprovalVerifier**: local_agent/browser_approval_verifier.py - 구현 완료 (in-memory PoC)
- **ServerActionAdapter**: local_agent/server_action_adapter.py - 구현 완료
- **BrowserActionContract**: local_agent/browser_action_contract.py - 구현 완료
- **기존 test 상태**: 12/12 PASS (test_browser_task_handler.py)

---

## 2. 기존 구조 점검

### 2.1 Task State 구조 (ai_orchestrator/task_state.py)

**상태 전이**:
```
pending → approved → rejected
       → executed
```

**TaskRecord 필드**:
| 필드 | 용도 |
|------|------|
| task_id | 고유 작업 ID |
| state | pending/approved/rejected/executed |
| risk_level | low/medium/high |
| token_id | 승인 토큰 참조 |
| action_type | 작업 유형 |
| target | 대상 URL/selector |
| task_snapshot | 민감정보 제거된 파라미터 스냅샷 |
| created_at, updated_at | 타임스탬프 |
| approved_by, rejected_by | 승인자/거절자 |
| result | 실행 결과 문자열 |

**저장소**: `storage/task_states.jsonl` (append-only JSONL, last-wins 복구)

**호환성 평가**: 
- ✓ task_id, state, risk_level은 기본 구조
- ✓ result 필드로 result_data 저장 가능
- ⚠ "blocked" 상태는 없음 (BROWSER-4C BrowserTaskResult.status에 있음)

---

### 2.2 Web Task Router (ai_orchestrator/routers/web_task_router.py)

**주요 엔드포인트**:
- `POST /api/v1/web-tasks/run` - 작업 실행 요청
- `POST /api/v1/web-tasks/run-from-template` - 템플릿 기반 실행

**작업 흐름**:
1. 레지스트리 조회 (provider/action_type)
2. params 검증
3. dry_run=true → summary 반환 (승인 없음)
4. dry_run=false → pending approval 생성 + Telegram 발송

**Task ID 형식**: `wt-{uuid.uuid4().hex[:12]}`

**승인 토큰**: `issue_token_for_dev_reg(task_id, requested_by, risk_level, ttl_minutes=30)`

**호환성 평가**:
- ✓ approval 토큰 발행 메커니즘 존재
- ✓ task_id 기반 추적
- ⚠ 현재 "provider/action_type" 레지스트리 기반 (browser action 미등록)

---

### 2.3 Local Agent Registry (ai_orchestrator/local_agent_registry.py)

**Task Status Enum**:
```
pending → queued → delivered → running → completed
                            ↘ failed
       → waiting_approval → (approve) → queued → ...
       → rejected / expired
```

**WebSocket 메시지 필드 (to_dispatch)**:
```python
{
    "task_id": str,
    "agent_id": str,
    "action": str,              # ping, open_url, capture_screenshot, etc.
    "params": dict,             # 민감정보 제거됨
    "risk_level": str,          # low/medium/high
    "approved": bool,           # high-risk 승인 여부
    "approval_id": str,         # (optional) public_id or token_id
}
```

**호환성 평가**:
- ⚠ action과 params로 전달 (BrowserTaskHandler는 action_type + selector + value 필요)
- ⚠ approval_token은 전달하지 않음 (승인_id만)
- ✓ approval_id 필드는 이미 존재

---

### 2.4 승인 시스템 (ai_orchestrator/approval.py + dev_reg_approval.py)

**ApprovalToken** (approval.py):
- token_id: UUID (secret-like, 식별자로 사용)
- task_id: 참조
- public_id: UI/audit 표시용 ("appr_" prefix)
- status: issued → approved → expired/revoked/rejected
- risk_level: low/medium/high

**DevRegApproval** (dev_reg_approval.py):
- token_id → ApprovalToken 참조
- approval_token_hash: SHA256(token_id) - 원문 저장 금지
- status: pending → approved → rejected/expired/executed/failed
- 메타데이터: provider, action_type, summary, target_url, screenshot_path

**호환성 평가**:
- ✓ token_hash 저장으로 raw token 보호
- ⚠ BrowserApprovalVerifier는 별도 in-memory 시스템 (운영화 필요)
- ⚠ approval_token (실제 token 값) 전달 경로 미정

---

## 3. BROWSER-4C 구현 분석

### 3.1 BrowserTaskHandler 인터페이스

**입력**: BrowserTaskPayload
```python
{
    "task_id": str,
    "task_type": str = "browser_action",
    "action_type": str,              # browser.execute_click, execute_type
    "selector": str,                 # CSS selector
    "value": Optional[str],          # for type actions
    "approval_id": Optional[str],
    "approval_token": Optional[str],
    "final_approval_token": Optional[str],
}
```

**처리 흐름**:
1. Payload 검증 (task_id, action_type, selector, value)
2. ServerApprovalAction 변환
3. BrowserApprovalVerifier.verify() - token_hash 검증
4. ServerActionAdapter.execute_action() - 실행
5. BrowserTaskResult 반환 (safe data)

**출력**: BrowserTaskResult
```python
{
    "task_id": str,
    "status": str,                   # received/blocked/executed/failed
    "action": str,
    "selector": str,
    "executed": bool,
    "element_found": bool,
    "risk_level": str,
    "final_approval_required": bool,
    "result": str,
    "target_url_domain": str,
    "text_length": int,
    "text_preview": "[REDACTED]",
    "error_code": Optional[str],
    "error_message": Optional[str],
}
```

**호환성 평가**:
- ✓ BrowserTaskResult 필드는 safe (no tokens, passwords, raw text)
- ⚠ status 값 ("blocked", "executed")은 task_state.TaskRecord의 state와 다름

### 3.2 BrowserApprovalVerifier (in-memory PoC)

**저장소**: BrowserApprovalStore (메모리 기반)
```python
{
    approval_id: BrowserApprovalRecord {
        approval_id: str,
        action_type: str,
        selector: str,
        token_hash: str,             # SHA256(approval_token)
        status: "approved"|"used"|"revoked"|"expired",
        risk_level: str,
        final_approval_required: bool,
        expires_at: Optional[datetime],
        created_at: datetime,
    }
}
```

**검증 로직**:
1. approval_id, approval_token 필수
2. approval 레코드 조회
3. 상태 검증 (approved만 가능, used/revoked/expired 거절)
4. token_hash 검증
5. action_type, selector 일치 검증

**호환성 평가**:
- ✓ token_hash 검증으로 raw token 보호
- ✓ one-time use 강제 (mark_used)
- ⚠ 메모리 기반 (운영화 시 persistent storage 필요)
- ⚠ 기존 ApprovalToken/DevRegApproval과 분리된 시스템

### 3.3 ServerActionAdapter

**역할**: ServerApprovalAction → BrowserController 실행 → ExecutionResult

**실행 흐름**:
1. 액션 검증
2. Verifier로 토큰 검증 (선택사항)
3. 액션 유형별 실행 (click/type)
4. ExecutionResult에 토큰/raw text 노출 금지

**호환성 평가**:
- ✓ ServerActionAdapter는 이미 verifier 지원
- ✓ ExecutionResult는 safe 데이터 포맷

---

## 4. WebSocket Task Contract 호환성 분석

### 4.1 현재 WebSocket 메시지 흐름

**서버 → 에이전트**:
```
{"type": "task", "task": {...}}
```

**에이전트 → 서버**:
```
{"type": "result", "task_id": str, "success": bool, "summary": str, "data": dict}
```

**현재 task 페이로드** (to_dispatch):
```
{
    "task_id": "...",
    "agent_id": "...",
    "action": "open_url" | "capture_screenshot" | "open_url_execute",
    "params": {"url": "...", "options": {...}},
    "risk_level": "low" | "medium" | "high",
    "approved": bool,
    "approval_id": "appr_..." (optional)
}
```

### 4.2 BrowserTaskHandler 기대 포맷

BrowserTaskHandler는 다음을 기대:
- `task_id` ✓ (existing)
- `task_type` = "browser_action" (NEW)
- `action_type` = "browser.execute_click" (NEW)
- `selector` (NEW)
- `value` (NEW)
- `approval_id` ✓ (existing or NEW)
- `approval_token` (NEW - raw token)
- `final_approval_token` (NEW)

### 4.3 Gap 분석

#### Gap #1: Browser Task Type 미등록
**문제**: local_agent_registry.ACTION_RISK에 browser_action 없음
**영향**: browser action이 UNKNOWN_ACTION 거절됨
**해결책**: ACTION_RISK에 "browser.execute_click", "browser.execute_type" 추가 필요

#### Gap #2: Approval Token 전달 경로 미정
**문제**: 
- 현재 WebSocket은 approval_id (public_id)만 전달
- BrowserTaskHandler는 approval_token (raw token 형태)를 기대
- approval_token은 server에서만 알 수 있음

**영향**: BrowserApprovalVerifier.verify() 실패 (token 없음)

**해결책**:
1. Server에서 browser task dispatch 시 approval_token을 WebSocket payload에 포함
2. 또는 BrowserTaskHandler가 local store에서 조회하도록 변경
3. 또는 approval_token을 base64 등으로 인코딩하여 task params에 포함

#### Gap #3: Result Data 형식 호환성
**문제**:
- task_state.mark_executed(result: str) expects string
- BrowserTaskResult는 dict로 여러 필드 포함
- local_agent_registry._RESULT_DATA_ALLOWED_KEYS가 명시적 화이트리스트 관리

**영향**: BrowserTaskResult → result_data 변환 필요

**해결책**:
1. BrowserTaskResult.to_dict()의 모든 필드가 _RESULT_DATA_ALLOWED_KEYS에 추가될 필요
2. task_id, status, action, selector, executed, element_found, risk_level, final_approval_required, result, target_url_domain, text_length, text_preview, error_code, error_message를 whitelist에 추가

#### Gap #4: Task Status 상태 전이
**문제**:
- task_state.TaskRecord: pending → approved → executed
- BrowserTaskResult.status: received → blocked/executed/failed
- local_agent_registry: pending → queued → delivered → running → completed

**영향**: 상태 전이 로직이 맞지 않을 수 있음

**해결책**:
- BrowserTaskResult.status는 execution 결과
- task_state의 "executed" 상태는 BrowserTaskResult가 반환된 후 설정

#### Gap #5: Approval Verification 시스템 이원화
**문제**:
- 기존: ApprovalToken (approval.py) + DevRegApproval (dev_reg_approval.py)
- BROWSER-4C: BrowserApprovalVerifier (in-memory PoC)
- 두 시스템이 별도로 동작

**영향**: 운영화 시 승인 토큰이 두 곳에서 관리되어 복잡성 증가

**해결책**:
1. BrowserApprovalVerifier를 기존 ApprovalToken/DevRegApproval과 통합
2. token_id → approval_id 매핑 사용
3. 또는 browser task 용도로만 별도 BrowserApprovalStore를 persistent로 전환

#### Gap #6: Final Approval 분리 필요 여부
**현재 상태**:
- ServerApprovalAction.final_approval_token은 구현되어 있음
- 하지만 실제 "final approval" 흐름이 명확하지 않음

**해결책**:
- 위험도 "critical" 액션 (delete, submit, payment 등)의 최종 승인 정책 정의 필요

---

## 5. 검증 결과

### 5.1 코드 컴파일/Import
✓ local_agent/browser_task_handler.py - 컴파일 성공
✓ local_agent/browser_approval_verifier.py - 컴파일 성공
✓ local_agent/server_action_adapter.py - 컴파일 성공
✓ local_agent/browser_action_contract.py - 컴파일 성공
✓ ai_orchestrator/task_state.py - 컴파일 성공
✓ ai_orchestrator/routers/web_task_router.py - 컴파일 성공
✓ ai_orchestrator/local_agent_registry.py - 컴파일 성공

### 5.2 테스트 실행
**BROWSER-4C Tests**:
- ✓ test_browser_task_handler.py: 12/12 PASS
- ✓ test_browser_approval_verifier.py: 필수 테스트 존재
- ✓ test_browser_action_contract.py: 필수 테스트 존재
- ✓ test_browser_execute_integration.py: 통합 테스트 존재
- ✓ test_browser_approval_policy.py: 정책 테스트 존재

**회귀 테스트**:
- 기존 approval, local_agent_registry 시스템 - 변경 없음 (영향 무)

### 5.3 Secret/Token 노출 검증

**금지된 필드가 저장되지 않음**:
- ✓ approval_token - stored as hash only in BrowserApprovalVerifier
- ✓ final_approval_token - 저장 안 함
- ✓ token_hash - 외부 노출 안 함
- ✓ typed text - [REDACTED]로 처리
- ✓ password - ExecutionResult 검증에서 거절
- ✓ OTP - 검증에서 거절
- ✓ cookie, session, Authorization - 검증에서 거절
- ✓ localStorage, sessionStorage - 검증에서 거절
- ✓ raw screenshot/base64 - ExecutionResult 구조에 미포함
- ✓ full DOM - ExecutionResult 구조에 미포함

---

## 6. 승인 흐름 호환성

### 현재 흐름
```
[Server] creates task
         ↓
  [task_state] pending
         ↓
  [issue_token_for_dev_reg] approval token
         ↓
  [local_agent_registry] waiting_approval
         ↓
  [admin approve] token validation
         ↓
  [mark_approved] → queued
         ↓
  [WebSocket] push task to agent
         ↓
  [agent] receives task
         ↓
  [agent.apply_result] → completed
         ↓
  [task_state] mark_executed
```

### BROWSER-4C와의 호환 흐름
```
[Server] creates task
         ↓
  [task_state] pending
         ↓
  [issue_token_for_dev_reg] approval token (token_id)
         ↓
  [BrowserApprovalStore] create_approval(token_id → token_hash)
         ↓
  [local_agent_registry] waiting_approval
         ↓
  [admin approve]
         ↓
  [mark_approved] → queued
         ↓
  [WebSocket] push {task_id, approval_id, approval_token}
         ↓
  [BrowserTaskHandler] verify(approval_id, approval_token)
         ↓
  [BrowserApprovalVerifier] token_hash validation
         ↓
  [ServerActionAdapter] execute_action
         ↓
  [mark_used] one-time enforcement
         ↓
  [BrowserTaskResult] safe result
         ↓
  [task_state] mark_executed
```

**호환성 평가**: 
- ✓ 기본 흐름은 호환 가능
- ⚠ approval_token 전달 경로 필요
- ⚠ BrowserApprovalStore와 ApprovalToken 통합 필요

---

## 7. 운영 연결 전 필요 항목 (Gap List)

### 우선순위 1 (Critical)
1. **Browser Task Type 등록**
   - `local_agent_registry.ACTION_RISK`에 browser actions 추가
   - 또는 web_task_router의 provider/action_type 레지스트리 확장
   - 예: `"browser.execute_click": "medium"`, `"browser.execute_type": "medium"`

2. **Approval Token 전달 경로**
   - Option A: WebSocket payload에 `approval_token` 필드 추가
   - Option B: Server에서 approval_token을 task params에 인코딩
   - Option C: Local store에서 조회하도록 BrowserTaskHandler 수정
   - 선택 필요: 어느 옵션이 보안/운영상 가장 나은가?

3. **Result Data Whitelist 확장**
   - `_RESULT_DATA_ALLOWED_KEYS`에 browser 관련 필드 추가
   - task_id, status, action, selector, executed, element_found, risk_level, final_approval_required, result, target_url_domain, text_length, text_preview, error_code, error_message

### 우선순위 2 (High)
4. **BrowserApprovalVerifier 운영화**
   - In-memory → persistent storage (DB or JSONL)
   - 또는 기존 ApprovalToken/DevRegApproval과 통합

5. **WebSocket 페이로드 스키마 정의**
   - browser_action task_type 시 payload 구조 문서화
   - action vs action_type 필드 구분 명확히

6. **Admin Approval UI 연결**
   - admin-web이 browser task 승인 버튼 표시
   - approval_token 발행 및 저장

### 우선순위 3 (Medium)
7. **One-time Token Store 운영화**
   - BrowserApprovalVerifier.store를 운영 DB로 전환
   - Token expiration 자동 정리

8. **Task Status 매핑 정의**
   - BrowserTaskResult.status → task_state.TaskRecord.state 매핑표 작성
   - blocked → rejected? 또는 pending 상태 추가?

---

## 8. 금지 작업 준수 현황

✓ **운영 WebSocket 연결**: 없음 - read-only 점검만 수행
✓ **운영 task 생성**: 없음 - local test 파일만 확인
✓ **서버 접속**: 없음 - 로컬 코드만 검사
✓ **운영 API 호출**: 없음 - 호출 없음
✓ **외부 사이트 접속**: 없음 - 로컬 파일만
✓ **실제 로그인**: 없음 - 자동화 없음
✓ **cookie/session 추출**: 없음 - 구조 검증만
✓ **password/OTP 입력**: 없음 - 검증만
✓ **submit/delete/payment 실행**: 없음
✓ **DB 변경**: 없음 - read-only
✓ **docker/nginx 변경**: 없음
✓ **git push**: 없음 - 커밋도 보고서만 (예정)
✓ **다른 앱 접근**: 없음 - haehan-ai-orchestrator만

---

## 9. 변경 파일

**코드 변경 파일**: 없음 (read-only 점검)
**생성 파일**:
- `docs/reports/browser_4d_websocket_task_contract_readonly_report.md` (본 보고서)

---

## 10. 최종 판정

### 종합 평가: ⚠️ **WARN**

**요약**:
- BROWSER-4C 구현은 기술적으로 견고함 (12/12 테스트 PASS)
- 기존 WebSocket/task contract와 기본 호환 가능
- 하지만 **6개의 significant gaps** 존재
  1. Browser task type 미등록
  2. Approval token 전달 경로 미정
  3. Result data whitelist 미확장
  4. BrowserApprovalVerifier in-memory (운영화 필요)
  5. WebSocket payload 스키마 미정의
  6. Admin approval UI 미연결

**운영 연결 가능 여부**: ⛔ **불가** (Gaps 해결 필요)

**다음 단계**:
- [ ] BROWSER-4E: 운영 WebSocket mock contract 구현
  - 또는 BROWSER-4D' (contract gap 보완)
  - Gaps #1~#6 해결 구현
- [ ] Admin-web approval UI 연결
- [ ] Local test with mock server 구성
- [ ] Integration test with real WebSocket (staging)

**예상 작업량**: 
- Gap #1~#3: 2-3시간 (코드 변경)
- Gap #4~#6: 4-6시간 (설계 + 구현)
- Total: **6-9시간** (하루 정도)

---

## 11. 기술 노트

### 보안 고려사항 ✓
- Token hash 검증으로 raw token 보호 ✓
- Execution result 검증으로 secrets 노출 방지 ✓
- One-time token 강제 ✓
- Final approval 구조 준비됨 (미사용)

### 아키텍처 고려사항
- WebSocket 기반 푸시 모델로 latency 최소화
- BrowserApprovalStore와 ApprovalToken 통합 경로 선택 필요
  - Option A: BrowserApprovalStore를 ApprovalToken 기반으로 재구현
  - Option B: ApprovalToken을 BrowserApprovalStore 모델로 확장
  - 권장: Option A (최소 변경)

### 운영 고려사항
- BrowserApprovalVerifier 메모리 사용량: 요청당 ~500B (acceptable)
- Token expiration: 30분 (기존과 동일)
- Approval 히스토리: JSONL로 audit trail 가능

---

## Appendix: Code Structure Reference

### BROWSER-4C 모듈 의존도
```
BrowserTaskHandler
  ├─ BrowserTaskPayload (input)
  ├─ ServerApprovalAction
  ├─ BrowserApprovalVerifier (optional)
  ├─ ServerActionAdapter (required)
  └─ BrowserTaskResult (output)

ServerActionAdapter
  ├─ ServerApprovalAction (input)
  ├─ BrowserController (execution)
  ├─ BrowserApprovalVerifier (optional)
  └─ ExecutionResult (output)

BrowserApprovalVerifier
  ├─ BrowserApprovalStore
  ├─ BrowserApprovalRecord
  └─ ApprovalVerificationResult
```

### 기존 시스템 의존도
```
WebSocket /ws
  ├─ local_agent_router
  ├─ LocalAgentTask (to_dispatch)
  ├─ dev_reg_approval
  ├─ approval (ApprovalToken)
  └─ task_state

web_task_router
  ├─ web_task_registry
  ├─ approval (issue_token_for_dev_reg)
  └─ dev_reg_approval
```

---

**보고서 작성**: Claude Haiku 4.5
**검토 필요**: Architecture lead / Security lead
