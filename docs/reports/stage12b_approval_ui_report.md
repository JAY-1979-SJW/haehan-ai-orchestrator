# Stage 12B approval UI report

## 1. 목적
Stage 12A GAP인 waiting_approval approve/reject UI 부재 보완

## 2. 확인한 backend approval API

| 항목 | 경로/필드 | 확인 파일 | 판정 |
|---|---|---|---|
| approve endpoint | `POST /api/v1/local-agents/{agent_id}/tasks/{task_id}/approve` | `local_agent_router.py:464` | OK |
| reject endpoint | `POST /api/v1/local-agents/{agent_id}/tasks/{task_id}/reject` | `local_agent_router.py:556` | OK |
| request body | `{ token_id: str, reason: str = "" }` (`AgentTaskApprovalRequest`) | `local_agent_router.py:59` | OK |
| response | `task.to_safe()` — `LocalAgentTask` + `token_id/approved_at/approved_by/rejected_at/reject_reason` | `local_agent_registry.py:151` | OK |
| 권한 조건 | `require_role("admin", "owner")` — viewer 불가 | `local_agent_router.py:469` | OK |
| waiting_approval 상태 | `to_list_safe()`에 token_id 없음. `to_safe()` (개별 조회)에만 포함 → 개별 조회 필요 | `local_agent_registry.py:180` | OK |

## 3. 수정 파일

| 파일 | 수정 내용 | 판정 |
|---|---|---|
| `admin-web/src/types/local-agent.ts` | `LocalAgentTaskDetail`, `ApprovalRequest`, `ApprovalResponse` 타입 추가 | PASS |
| `admin-web/src/lib/api.ts` | `getLocalAgentTask`, `approveLocalAgentTask`, `rejectLocalAgentTask` 함수 추가 | PASS |
| `admin-web/src/app/local-agents/LocalAgentsClient.tsx` | 승인/거절 모달 상태·핸들러·UI 추가, `TaskActionCell` waiting_approval 버튼 추가 | PASS |

## 4. UI 반영 내용

| 항목 | 반영 내용 | 판정 |
|---|---|---|
| 승인 대기 표시 | `waiting_approval` 상태 작업에 "승인·거절" 버튼 노출 (기존 StatusBadge 유지) | PASS |
| approve 버튼 | 모달 내 승인 선택 → "승인 확인" 버튼 활성화 → `approveLocalAgentTask()` 호출 | PASS |
| reject 버튼 | 모달 내 거절 선택 → reason textarea 노출 → "거절 확인" 버튼 활성화 → `rejectLocalAgentTask()` 호출 | PASS |
| 권한 없는 사용자 처리 | viewer/권한 확인 실패 시 "승인·거절" 버튼 `disabled`, title 안내 | PASS |
| 처리 중 상태 | `approvalLoading` 중 버튼 "처리 중…" 표시, 모달 닫기 차단 | PASS |
| 성공 후 refresh | approve/reject 성공 후 `fetchTasks` + `fetchAgents` 동시 갱신 | PASS |
| 실패 메시지 | HTTP 상태코드별 한국어 에러 메시지 (`approvalErrorMessage`) 모달 내 표시 | PASS |

## 5. 안전 조건 유지

| 조건 | 결과 | 판정 |
|---|---|---|
| viewer approve/reject 불가 | `canMutate` 조건 (admin/owner만) — viewer시 버튼 disabled | PASS |
| 권한 확인 실패 시 비활성화 | `userLoading` 또는 `userError` 중 `canMutate=false` → disabled | PASS |
| waiting_approval 외 버튼 미노출 | `isWaitingApproval` 조건으로만 "승인·거절" 버튼 렌더 | PASS |
| critical 정책 완화 없음 | backend policy.py/default_policy.yaml 미수정 | PASS |
| capture/cancel 로직 변경 없음 | `handleDryRun`, `handleCaptureSubmit`, `handleCancelSubmit` 미수정 | PASS |
| 실제 POST smoke 미수행 | 테스트 POST 없음. 서버 미접속 | PASS |

## 6. 검증 결과

| 검증 | 결과 |
|---|---|
| lint | PASS (next lint 무출력) |
| typecheck | PASS (tsc --noEmit 무출력) |
| API 경로 임의 생성 여부 | 없음 — 기존 router 경로 그대로 사용 |
| package/lockfile 변경 여부 | 없음 |
| secret 출력 여부 | 없음 |

## 7. 다음 단계 제안

권장 다음 단계:
- **Stage 12C**: approval UI 서버 반영 및 UI smoke — admin-web rebuild/up + waiting_approval 렌더 확인
- 또는 **Stage 12C**: local-agent 전용 dry_run smoke 스크립트 정리

## 8. 금지 작업 준수 확인

- 서버 접속: 없음
- docker 실행: 없음
- 실제 local-agent 실행: 없음
- 실제 approve/reject POST: 없음
- 실제 capture/cancel POST: 없음
- 정책 완화: 없음
- secret 출력: 없음
