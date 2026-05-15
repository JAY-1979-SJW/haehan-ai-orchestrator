# 저장소 / 증거 / 감사 모델 (Storage, Audit & Evidence Model)

고정일: 2026-05-15  
작업 ID: APP_FOUNDATION_GOVERNANCE_LOCK_01  
상태: LOCKED

---

## 1. 저장소 분류

| 분류 | 코드 | 위치 | 설명 | 접근 주체 |
|------|------|------|------|----------|
| Task Store | TASK | ai_orchestrator/storage/, data/test_runtime/ | 작업 상태·요청·결과 | Workflow Layer |
| Approval Store | APPROVAL | data/audit/, data/logs/ | 승인 기록: 누가/언제/무엇을/범위 | Permission Gate |
| Draft Store | DRAFT | data/hiworks_runs/, data/youtube_upload_plans/ 등 | 초안·실행계획 문서 | Usecase Layer |
| Execution Plan Store | PLAN | data/eum_plans/, data/google_prepares/ 등 | 실행 계획·파라미터 | Workflow Layer |
| Evidence Store | EVIDENCE | data/audit/L2_audit/, data/screenshots/ | 실행 결과·스크린샷·응답 원문 | Audit Layer |
| Audit Log | LOG | data/logs/app.log, data/cdp.db | 전체 시스템 감사 로그 | System |
| Report Store | REPORT | docs/reports/, data/reports/ | 감사·운영 보고서 | Audit Layer |
| Artifact Store | ARTIFACT | data/downloads/, data/eum_downloads/ | 다운로드·생성 파일 | Local Agent |
| Manual Visit Snapshot | SNAPSHOT | data/manual_visits/ | 사람이 브라우저로 방문한 스냅샷 (read-only) | Read-only reference |
| Session Store | SESSION | data/sessions/ | ⚠️ 금지 대상 (아래 참조) | BLOCKED |

---

## 2. Session Store 정책 (⚠️ 중요)

`data/sessions/` 경로의 파일은 **금지 대상**으로 분류한다.

```
data/sessions/gabia.com.json      → 읽기/파싱/재사용 금지
data/sessions/my.gabia.com.json   → 읽기/파싱/재사용 금지
data/sessions/www.gabia.com.json  → 읽기/파싱/재사용 금지
data/sessions/*.json               → 모두 동일 정책 적용
```

금지 이유:
- session/cookie/token은 개인 인증 정보로 보안 경계 대상
- AI/서버가 재사용할 경우 인증 사기·세션 탈취와 동일한 위험
- 사용자가 브라우저에서 직접 로그인한 session만 유효

유일한 허용:
- 파일 존재 여부 확인 (audit 목적)
- 내용 읽기, 파싱, 전달, 재사용은 BLOCKED

---

## 3. Manual Visit Snapshot 정책

`data/manual_visits/` 경로는 **read-only evidence**로만 사용한다.

허용:
- 과거 방문 기록 read-only 참조
- DNS 레코드 스냅샷 분석
- 사이트 구조 파악

금지:
- session 정보 추출
- 로그인 정보 추출
- 자동 재현 목적 사용

---

## 4. Audit Log 원칙

모든 다음 이벤트는 감사로그에 남긴다:

```
작업 요청 (REQUESTED)
검증 실패 (VALIDATION_FAILED)
gate 결정 (GATE_DECISION)
승인 (APPROVED) — 승인자, 시각, 범위
거부 (REJECTED) — 거부자, 사유
실행 시작 (EXECUTION_STARTED)
실행 완료 (EXECUTION_COMPLETED) — 결과 요약
실행 실패 (EXECUTION_FAILED) — 오류 내용
차단 (BLOCKED) — 사유
```

로그 위치:
- `data/logs/app.log` — 애플리케이션 이벤트
- `data/cdp.db` — 브라우저 CDP 이벤트
- `data/audit/L2_audit/` — L2 구조 감사
- `data/audit/L3_session/` — 세션 감사 (금지 검증용)

---

## 5. Approval Store 원칙

승인 기록은 반드시 다음을 포함한다:

| 필드 | 설명 |
|------|------|
| approver_id | 승인자 식별자 |
| approved_at | 승인 시각 (UTC ISO8601) |
| scope | 승인 범위 (어떤 작업, 어떤 파라미터) |
| expiry | 승인 유효 기간 (없으면 단회성) |
| action | 승인된 action 코드 |
| gate_decision | 원래 gate 결정 |
| evidence_path | 승인 증거 파일 경로 |

---

## 6. Report Store 원칙

보고서는 두 위치를 사용한다:

| 위치 | 용도 |
|------|------|
| `docs/reports/` | git에 커밋되는 공식 감사/운영 보고서 |
| `data/reports/` | 실행 시 생성되는 런타임 보고서 (git 미포함 가능) |

보고서 파일명 규칙: `{도메인}_{작업}_{YYYYMMDD}.md`

---

## 7. 저장소 경계 위반 금지

| 금지 | 이유 |
|------|------|
| Router 계층에서 직접 파일 쓰기 | L10 Storage 경유 필수 |
| Domain/Policy 계층에서 DB 접근 | 순수 정책은 I/O 없음 |
| Session Store 내용 파싱 | 보안 금지 |
| Audit Log 수정/삭제 | 감사 무결성 |
| Evidence 위조 | 감사 무결성 |
