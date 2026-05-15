# Shared Warehouse Model (공용 창고 모델)

고정일: 2026-05-15  
작업 ID: APP_FOUNDATION_SHARED_WAREHOUSE_LOCK_01  
상태: LOCKED

---

## 1. 개요

모든 Domain Unit이 공통으로 사용하는 저장소(창고)의 위치·역할·접근 규칙을 고정한다.  
이 모델은 기능 구현 명세가 아니라 경계(boundary)와 정책(policy)을 정의한다.

핵심 금지: session/cookie/token/password 저장 금지, data/sessions 봉인, manual_visit READ_ONLY_EVIDENCE 전용

---

## 2. 창고 전체 목록 (10개)

| 번호 | 창고명 | 표준 경로 | 역할 | 접근 정책 |
|------|--------|-----------|------|----------|
| W1 | Draft Warehouse | `data/drafts/{domain}/{task_id}/` | 초안, 검토 전 자료 | DRAFT_ALLOWED |
| W2 | Approval Warehouse | `data/approvals/{domain}/{task_id}/` | 승인 요청·기록·범위·만료 | APPROVAL_REQUIRED |
| W3 | Execution Plan Warehouse | `data/execution_plans/{domain}/{task_id}/` | 실행 전 계획, handoff plan | ALLOWED (생성) |
| W4 | Evidence Warehouse | `data/evidence/{domain}/{task_id}/` | 실행 증거, 스냅샷, 첨부 해시 | READ_ONLY (조회), ALLOWED (저장) |
| W5 | Report Warehouse | `docs/reports/` (human) + `data/reports/{domain}/` (machine) | 최종 보고서, 감사 결과 | ALLOWED (생성), READ_ONLY (조회) |
| W6 | Artifact Warehouse | `data/artifacts/{domain}/{task_id}/` | 생성 문서, 변환 파일, 산출물 | ALLOWED |
| W7 | Upload Warehouse | `data/uploads/{domain}/{task_id}/` | 사용자 업로드 원본 | ALLOWED (저장), READ_ONLY (원본) |
| W8 | Audit Log Warehouse | `data/logs/` | 상태전이·gate decision·오류 기록 | APPEND_ONLY |
| W9 | Manual Visit Snapshot | `data/manual_visits/{host}/` | 사용자 직접 방문 화면 read-only 증거 | READ_ONLY_EVIDENCE |
| W10 | Session Store | `data/sessions/` | (봉인된 위험구역) | **BLOCKED** |

---

## 3. 창고별 상세 정책

### W1. Draft Warehouse — `data/drafts/{domain}/{task_id}/`

**역할:** 사용자 검토 전 초안, 입력값 검증 결과, AI 생성 초안  
**접근 정책:**
- 생성: DRAFT_ALLOWED (승인 불필요)
- 조회: ALLOWED
- 삭제: APPROVAL_REQUIRED
- 승격(→ Artifact): APPROVAL_REQUIRED

**금지:**
- task_id 없는 임시 초안 루트 저장 금지
- 초안에 secret/token/password/session/cookie 저장 금지

---

### W2. Approval Warehouse — `data/approvals/{domain}/{task_id}/`

**역할:** 승인 요청, 승인 범위, 승인자, 승인 시각, 유효기간, 거부 사유  
**접근 정책:**
- 생성: 승인 게이트가 자동 생성
- 조회: 승인자 + 시스템만 허용
- 수정: 금지 (불변)
- 삭제: 금지 (불변)

**필수 필드:** approver / timestamp / scope / expiry / decision  
**금지:**
- 승인 레코드 임의 수정
- 승인 없이 EXECUTING 상태 전이
- session/cookie를 승인 증거로 사용

---

### W3. Execution Plan Warehouse — `data/execution_plans/{domain}/{task_id}/`

**역할:** 실행 전 계획서, local-agent handoff plan, user-direct 실행 가이드  
**접근 정책:**
- 생성: APPROVAL_REQUIRED 이후에만
- 조회: ALLOWED
- 수정: 재승인 필요
- 실행: LOCAL_AGENT_REQUIRED 또는 USER_DIRECT_REQUIRED

**금지:**
- 계획서 없이 실행 시작 금지
- task_id 없는 계획서 생성 금지

---

### W4. Evidence Warehouse — `data/evidence/{domain}/{task_id}/`

**역할:** 실행 증거, 화면 스냅샷, 결과 첨부파일 해시, 실행 로그 참조  
**접근 정책:**
- 생성: 실행 후 자동 저장
- 조회: READ_ONLY (원본 불변)
- 수정: 금지 (불변)
- 삭제: 금지

**필수 연결:** task_id 없는 evidence 생성 금지  
**금지:**
- 임시 파일을 evidence로 승격 금지
- session/cookie/token을 evidence에 저장 금지
- manual_visits를 evidence로 재사용 (read-only 참조만 허용)

---

### W5. Report Warehouse

**이중 구조:**
- `docs/reports/` → 사람이 읽는 Markdown 보고서 (closeout, 감사, 의사결정)
- `data/reports/{domain}/` → machine-readable JSON 보고서 (자동화 처리용)

**접근 정책:**
- 생성: ALLOWED
- 조회: READ_ONLY
- 수정: 금지 (새 버전 생성)
- 삭제: 금지

**금지:**
- docs/reports와 data/reports 역할 혼용 금지
- evidence와 report 혼용 금지

---

### W6. Artifact Warehouse — `data/artifacts/{domain}/{task_id}/`

**역할:** 생성 문서, 변환 파일, 다운로드 파일, AI 생성 산출물  
**접근 정책:**
- 생성: DRAFT_ALLOWED 또는 APPROVAL_REQUIRED (위험도에 따라)
- 조회: ALLOWED
- 원본 수정: 금지 (새 버전 생성)

**금지:**
- task_id 없는 artifact 루트 저장 금지
- secret/token/password artifact에 포함 금지

---

### W7. Upload Warehouse — `data/uploads/{domain}/{task_id}/`

**역할:** 사용자가 업로드한 원본 파일  
**접근 정책:**
- 저장: 사용자 직접 또는 LOCAL_AGENT_REQUIRED
- 조회: ALLOWED
- 원본 수정: **절대 금지** (불변)
- 삭제: USER_DIRECT_REQUIRED

**금지:**
- 원본 파일 자동 수정 금지
- 자동 업로드 (외부 사이트 제출) 금지

---

### W8. Audit Log Warehouse — `data/logs/`

**역할:** 모든 작업 상태 전이, gate decision, 실행 결과, 오류 이벤트 실시간 기록  
**현재 파일:** `data/logs/app.log`, `data/logs/ops.log`, `data/cdp.db`, `data/audit/action_evidence.jsonl`

**접근 정책:**
- 쓰기: APPEND_ONLY (덮어쓰기 금지)
- 조회: 운영자 READ_ONLY
- 삭제: **절대 금지**
- 수정: **절대 금지**

**필수 기록 항목:** who / when / what / result / task_id

---

### W9. Manual Visit Snapshot — `data/manual_visits/{host}/`

**역할:** 사용자가 직접 브라우저로 방문한 화면의 read-only 증거 스냅샷  
**현재 호스트:** gabia.com / google.com / hiworks / eum 등 17개

**접근 정책:**
- 생성: 사용자 직접 방문 시에만
- 조회: READ_ONLY_EVIDENCE (참조만)
- 재실행 우회: **절대 금지**
- 로그인 우회 재사용: **절대 금지**

**금지:**
- manual visit snapshot을 서버 사이드 자동화에 사용 금지
- snapshot을 session 대체재로 사용 금지
- snapshot 내 cookie/session 추출 금지

---

### W10. Session Store — `data/sessions/` ← 봉인된 위험구역

**상태: BLOCKED (봉인)**  
**존재 파일:** eum.cw.or.kr.json, gabia.com.json, my.gabia.com.json, naver.com.json, office.hiworks.com.json  
(파일 내용 열람·파싱·재사용 전면 금지)

**접근 정책:**
- 읽기: **BLOCKED**
- 파싱: **BLOCKED**
- 재사용: **BLOCKED**
- 신규 생성: **BLOCKED**

**이유:** session 파일은 로그인 상태를 포함하며, 서버 사이드 자동 재사용 시 외부 사이트 무단 로그인으로 이어질 수 있음  
**접근 발견 시 처리:** 즉시 STOP 보고 → 설계 변경 승인 전까지 사용 금지

---

## 4. task_id 의무 사용 규칙

- W1~W7 모든 창고는 `{domain}/{task_id}/` 하위에 저장
- task_id 형식: `{YYYYMMDD}_{action}_{seq}` 또는 UUID
- task_id 없는 임시 파일은 `data/drafts/{domain}/temp/`에 격리 후 24시간 내 삭제 또는 승격
- 루트 `data/` 직접 저장은 레거시 파일만 허용 (신규 금지)

---

## 5. 창고 간 전환 규칙

```
Draft → Artifact:      APPROVAL_REQUIRED
Draft → Evidence:      금지 (evidence는 실행 후 자동 생성)
Upload → Artifact:     LOCAL_AGENT_REQUIRED 또는 USER_DIRECT_REQUIRED
Execution Plan → 실행: LOCAL_AGENT_REQUIRED 또는 USER_DIRECT_REQUIRED
Evidence → Report:     ALLOWED (참조만, 원본 불변)
Session → 어디든:      BLOCKED
Manual Visit → 어디든: READ_ONLY_EVIDENCE (원본 불변, 자동화 재사용 금지)
```

---

## 6. 관련 문서

- `docs/architecture/domain_warehouse_allocation.md` — Domain별 창고 배정
- `docs/architecture/storage_boundary_policy.md` — 허용/금지 정책 상세
- `docs/architecture/shared_warehouse_manifest.json` — 기계 검사용 manifest
- `docs/architecture/storage_audit_evidence_model.md` — 기존 저장소 모델 (상위 문서)
