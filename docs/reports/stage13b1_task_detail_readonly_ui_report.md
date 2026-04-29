# Stage 13B-1 task detail read-only UI report

## 1. 목적

Stage 13A 추천(A안)에 따라 backend API 변경 없이 기존 `LocalAgentTaskDetail`
응답만 사용하여 admin-web `/local-agents` 의 task detail read-only 표시를 보강한다.

새로운 실행 버튼/외부 URL observe/audit API/backend 변경은 없다.

---

## 2. 수정 파일

| 파일 | 수정 내용 | 판정 |
|---|---|---|
| `admin-web/src/app/local-agents/LocalAgentsClient.tsx` | (1) `LocalAgentTaskDetail` import 추가, (2) `TaskActionCell` 에 "상세" Btn(`variant=ghost`) 추가, (3) `detailTargetTask` / `detailData` / `detailLoading` / `detailError` 상태 + `handleOpenDetail` / `handleCloseDetail` 핸들러 추가 (`getLocalAgentTask` 재사용), (4) read-only `Modal` 신규 — `DetailRow` 헬퍼로 안전 필드만 표시 + 안전 문구 footer | PASS |
| `admin-web/src/types/local-agent.ts` | 변경 없음 (`LocalAgentTaskDetail` 기존 정의 재사용) | PASS |
| `admin-web/src/lib/api.ts` | 변경 없음 (`getLocalAgentTask` 기존 함수 재사용) | PASS |
| `ai_orchestrator/**`, `local_agent/**`, `tests/**`, `package.json`, lockfile | 변경 없음 | PASS |
| `docs/reports/stage13b1_task_detail_readonly_ui_report.md` | 신규 보고서 | PASS |

총 변경 파일 2개 (코드 1, docs 1).

---

## 3. 표시 데이터

| 필드 | 표시 여부 | sanitize 여부 | 비고 |
|---|---:|---:|---|
| task_id | ✅ | 불필요 | mono 폰트 |
| agent_id | ✅ | 불필요 | mono 폰트 |
| status | ✅ | 불필요 | enum 그대로 |
| action | ✅ | 불필요 | 기존 노출 |
| risk_level | ✅ | 불필요 | enum 그대로 |
| requested_by | ✅ | 불필요 | 기존 노출 |
| created_at / updated_at | ✅ | 불필요 | 기존 timestamp |
| delivered_at / started_at / completed_at | ✅ | 불필요 | null 시 `—` |
| result_summary | ✅ | 불필요 | 백엔드가 이미 요약된 문자열만 제공 |
| error_summary / failure_reason | ✅ | 불필요 | 있을 때만 표시, danger 색상 |
| timed_out_at | ✅ | 불필요 | 있을 때만 표시, danger 색상 |
| approval status (approved_at/by, rejected_at/reason) | ✅ | 불필요 | 있을 때만 표시 |
| cancel_requested_at/by, cancelled_at, cancel_reason | ✅ | 불필요 | 있을 때만 표시 |

`getLocalAgentTask` 응답에 포함된 `token_id` 는 **렌더하지 않음** (DetailRow 호출 목록에 부재).

---

## 4. 표시 금지 데이터

| 데이터 | 처리 |
|---|---|
| token_id | 렌더하지 않음 (기존 approval flow 내부 처리에만 사용, UI 텍스트로 표시 0) |
| cookie / session / token | 백엔드 응답에 부재, UI 추가 표시 없음 |
| Authorization | UI 어디에도 없음 |
| password | UI 어디에도 없음 |
| localStorage / sessionStorage | UI 어디에도 없음 (`grep` 0건) |
| HTML / body 전체 | API 응답에 부재 |
| raw audit JSONL | admin-web 에서 접근하지 않음 (PC local 파일) |
| query / fragment 원문 | UI 노출 없음 |

footer 안전 문구 추가:
> 민감정보(쿠키·세션·토큰·Authorization·password·HTML 본문·query 원문)는 표시하지 않습니다.
> 로컬 에이전트 감사 로그 원문은 PC에 보관되며 admin-web 에 노출하지 않습니다.

---

## 5. 기존 기능 유지 확인

| 기능 | 결과 |
|---|---|
| capture dry_run/real 모달 | 변경 없음 |
| cancel 버튼 | 변경 없음 (`onCancel` 동일) |
| approve/reject 버튼 | 변경 없음 (`onApprovalAction` 동일) |
| task refresh / agent list / polling | 변경 없음 |
| API 경로 변경 없음 | `getLocalAgentTask` 기존 함수 재사용, 새 엔드포인트 0 |
| 새 실행 버튼 | "상세" 버튼은 read-only 조회만 (mutation 없음, 권한 게이트 없음) |
| `TaskActionCell` 의 기존 early-return 제거 | 모든 task 에 "상세" 버튼이 항상 보이도록 변경 (기존 cancel/approval 동작 영향 없음) |

---

## 6. 검증 결과

| 명령 | 결과 |
|---|---|
| `npm run lint` (admin-web) | **✔ No ESLint warnings or errors** |
| `npm run typecheck` (admin-web, `tsc --noEmit`) | **PASS** (silent OK) |
| `python scripts/check_local_agent_noexec_smoke.py` | Total 39 / PASS 37 / WARN 2 / FAIL 0 → **WARN exit 0** |
| token_id UI 노출 grep | **0건** in detail modal 렌더 (기존 approval-flow 코드 4건은 사전부터 존재, 텍스트 렌더 아님) |
| cookie/sessionStorage/localStorage/Authorization grep | **0건** in `admin-web/src/app/local-agents/`, `admin-web/src/components/` |
| git diff 범위 | `admin-web/src/app/local-agents/LocalAgentsClient.tsx` (코드 1), `docs/reports/stage13b1_task_detail_readonly_ui_report.md` (docs 1) — backend/local_agent/tests/package 변경 없음 |

---

## 7. 다음 단계 제안

권장 다음 단계:

- **Stage 13B-2** — `LocalAgentTaskDetail` 응답에 옵션 `observe_summary` 필드 추가 설계
  - 운영자가 13B-1 사용 후 진짜 필요한 구조화 필드(url_category / status_category / pages_observed_count / blocked_reason)를 식별한 다음 진행
- 또는 **Stage 13C** — local-agent `~/.haehan_agent/audit.jsonl` 의 `browser_open_*` event 를 orchestrator 로 안전 보고하는 채널 설계

권장: 13B-1 운영 사용 후 피드백 수집 → 13B-2 vs 13C 분기 결정.

---

## 8. 금지 작업 준수 확인

- backend 변경: 없음
- local_agent 변경: 없음
- 새 실행 버튼: 없음 ("상세"는 read-only 조회만)
- 서버 접속: 없음
- docker 실행: 없음
- 브라우저 실행: 없음 (npm run lint/typecheck 만 실행)
- 실제 HTTP/POST: 없음
- 다른 앱 접근: 없음
- secret 출력: 없음

---

## 9. 최종 판정

**PASS**
