# Stage 13D-1: Approval Task Detail 운영 검증 설계

## 1. 현재 상태 요약

| 단계 | 내용 | 상태 |
|------|------|------|
| Stage 13B | observe_summary 운영 반영 | 완료 |
| Stage 13C | audit_summary 운영 반영 | 완료 |
| Stage 13D-0 | Repo Boundary Lock 규칙 문서화 | 완료 |

현재 구현 기준:

- `to_safe()` — task detail API 응답. `token_id`, 승인 필드, `observe_summary`, `audit_summary` 포함.
- `to_list_safe()` — task list API 응답. `token_id` / 승인 필드 / `params` 제외. 요약 중심.
- approve endpoint: `POST /{agent_id}/tasks/{task_id}/approve`
- reject endpoint: `POST /{agent_id}/tasks/{task_id}/reject`
- `waiting_approval` 상태에서만 approve/reject 전환 가능.
- token_id는 `attach_token()` 이후 task에 저장되며, approve/reject body에서 필수.
- admin-web은 approve/reject 실행 전 개별 조회(`to_safe()`)로 `token_id`를 취득 (line 895).

---

## 2. Stage 13D 목표

`waiting_approval` task detail 화면에서 아래 정보가 함께 안전하게 표시되는지 검증한다.

- task 기본 정보 (task_id, action, status, created_at 등)
- `result_summary`
- `observe_summary` (안전 필드만)
- `audit_summary` (안전 필드만)
- approve / reject controls (명시 클릭 전용)

금지 항목:

- raw audit JSONL / raw event list / HTML 원문 / raw URL 표시 금지
- token/secret/password 값 화면 표시 금지
- 잘못된 상태(pending/running/completed 등)에서 approve/reject 버튼 표시 금지
- 자동 승인 / 자동 거절 금지

---

## 3. 상태별 UI/동작 기준

| 상태 | approve/reject 표시 | token_id 사용 | observe/audit_summary | 비고 |
|------|-------------------|--------------|----------------------|------|
| `pending` | 금지 | 없음 | null 가능 | — |
| `running` | 금지 | 없음 | 중간 원문 노출 금지 | — |
| `waiting_approval` | **허용** | detail에서만 | 안전 요약만 표시 | approve/reject 명시 클릭 전용 |
| `approved` | 재표시 금지 | — | 표시 가능 | 승인 결과 요약만 |
| `rejected` | 재표시 금지 | — | 표시 가능 | 거절 사유: 안전 문자열만 |
| `completed` | 금지 | — | 표시 가능 | result_summary 포함 |
| `failed` | 금지 | — | 안전 필드만 | error_category/blocked_reason 등 |
| `cancelled` | 금지 | — | 있으면 표시 | — |

---

## 4. token_id 노출/사용 정책

### 현재 구현 확인 결과

- `to_safe()`: `token_id` 포함 (registry.py line 167)
- `to_list_safe()`: `token_id` **제외** (주석: "params/token_id/승인 필드 제외", registry.py line 188)
- admin-web: approve/reject 실행 전 개별 조회로 `token_id` 취득 (LocalAgentsClient.tsx line 895)
- approve endpoint: request body에 `token_id` 필수 (router.py line 479)
- reject endpoint: request body에 `token_id` 필수 (router.py line 566)

### 정책 기준

| 항목 | 기준 |
|------|------|
| `to_list_safe()` token_id | **포함 금지** — 현재 구현 준수 |
| `to_safe()` token_id | 허용 (detail 전용) |
| 화면 텍스트 표시 | 금지 — UI에서 값을 사용하되 표시하지 않음 |
| approve/reject POST body | token_id 포함 (필수) — 로그/화면 출력은 금지 |
| token_id 없을 때 | approve/reject 버튼 비활성화 또는 숨김 |
| 자동 승인/거절 | 금지 — 명시 클릭으로만 가능 |

---

## 5. observe_summary 표시 검증 기준

| 항목 | 기준 |
|------|------|
| `final_url_sanitized` | 텍스트로만 표시 가능 |
| null 값 | 오류처럼 표시하지 않음 |
| `modal_candidates` 원문 | 표시 금지 |
| `page_structure` 원본 | 표시 금지 |
| HTML 원문 | 표시 금지 |
| `current_url` / query / fragment | 표시 금지 |
| count / category / status | 표시 허용 |
| `JSON.stringify` 전체 출력 | 금지 |

---

## 6. audit_summary 표시 검증 기준

| 항목 | 기준 |
|------|------|
| raw audit JSONL | 표시 금지 |
| raw event list | 표시 금지 |
| `STORE_ONLY` 필드 | 표시 금지 |
| `audit_summary_hash` | 표시 금지 |
| `local_audit_source` | 표시 금지 |
| dropped / redacted 상세 | 표시 금지 |
| count / category / status | 표시 허용 |
| `JSON.stringify` 전체 출력 | 금지 |

---

## 7. approve/reject API 검증 기준

### 현재 구현 (router.py 기준)

| 항목 | 내용 |
|------|------|
| approve endpoint | `POST /{agent_id}/tasks/{task_id}/approve` |
| reject endpoint | `POST /{agent_id}/tasks/{task_id}/reject` |
| request body | `{ token_id, actor?, role?, reason? }` |
| 권한 조건 | `actor` / `role` 기록용 (현재 별도 인증 없음) |
| 상태 전이 조건 | `waiting_approval` → `queued` (approve) / `rejected` (reject) |
| 이미 처리된 경우 | 현재 상태 그대로 반환 (idempotent) |
| 토큰 만료 | `waiting_approval` → `rejected` 자동 종결 |
| 실패 시 에러 | `token_not_found` 404 / `task_mismatch` 400 / `expired` 200 |
| 응답 | `to_safe()` 반환 |

### Stage 13D-1 범위

- 실제 approve/reject POST는 이번 단계에서 하지 않는다.
- Stage 13D-2에서도 fixture/noexec 중심으로 먼저 검증한다.
- 실제 POST는 Stage 13D-3 이후 별도 승인 후 진행한다.

---

## 8. 운영 검증 방식 대안

### A안: fixture 기반 UI/API 테스트 (권장)

- `waiting_approval` 상태 task fixture를 직접 주입하여 detail 응답 검증
- approve/reject endpoint에 실제 POST 없이 상태 확인
- 장점: 안전, 반복 가능, 실제 승인 없음
- 단점: 실제 운영 task와 완전히 동일하지 않을 수 있음

### B안: read-only 운영 task detail 조회

- 운영 환경에 `waiting_approval` task가 존재할 경우 GET으로만 확인
- 장점: 운영 반영 상태 직접 확인 가능
- 단점: 운영에 해당 task가 없으면 SKIP 처리

### C안: controlled dummy task 생성 후 dry-run

- 테스트용 task를 생성하고 approve/reject 흐름 전체 확인
- 장점: 실제 흐름 전체 확인 가능
- 단점: API/상태 변경 발생 → 별도 사용자 승인 필요

### 최종 추천

| 단계 | 방식 |
|------|------|
| Stage 13D-2 | A안 — fixture 기반 Python 테스트 |
| Stage 13D-3 | B안 — read-only 운영 확인 (task 있으면) |
| Stage 13D-4 이후 | C안 — 사용자 명시 승인 후 실제 POST |

---

## 9. Stage 13D-2 최소 구현 제안

### 검증 목표

- `to_safe()` / `to_list_safe()` token_id 노출 차이 테스트
- `waiting_approval` fixture task에서 detail 응답 구조 검증
- observe_summary / audit_summary 안전 필드만 포함 여부 검증
- approve/reject 버튼 조건부 렌더: `waiting_approval`에서만 표시 (정적 grep 검증)
- raw JSON / token 값 / raw audit 화면 표시 금지 (정적 grep 검증)

### 변경 대상 후보

| 파일 | 내용 |
|------|------|
| `tests/test_local_agent_approval_detail_fixture.py` | 신규 — fixture 기반 detail 응답 검증 |
| `docs/reports/stage13d2_approval_detail_verify.md` | 신규 — 검증 계획 및 결과 |

### 변경 금지

- Python 코드 변경 금지
- TypeScript / admin-web 수정 금지
- API/schema 변경 금지
- 기존 테스트 수정 금지
- 서버 접속 / docker / local-agent 실행 금지
- 실제 approve/reject POST 금지

### 검증 계획

1. `LocalAgentTask` fixture 생성 → `to_safe()` 응답에 `token_id` 포함 확인
2. `to_list_safe()` 응답에 `token_id` 없음 확인
3. `waiting_approval` 상태 fixture → approve endpoint mock 호출 시 `queued` 전환 확인
4. `observe_summary` / `audit_summary` 필드 존재 및 금지 필드 미포함 확인
5. admin-web: `isWaitingApproval` 조건 grep — 다른 상태에서 approve/reject 렌더 방지 정적 확인

---

## 10. Stage 13D 중단 조건

아래 조건이 발생하면 즉시 STOP 보고한다.

- 실제 approve/reject POST가 필요해지는 경우
- local-agent 실제 실행이 필요한 경우
- 브라우저 실행이 필요한 경우
- 외부 URL 접속이 필요한 경우
- raw audit / HTML / URL / token 값을 UI에 표시해야 하는 경우
- DB / schema 변경이 필요한 경우
- task 생성 / 상태 변경이 별도 승인 없이 필요한 경우
- token_id를 list API 또는 화면 텍스트에 표시해야 하는 경우
- Repo Boundary Lock 위반이 필요한 경우
