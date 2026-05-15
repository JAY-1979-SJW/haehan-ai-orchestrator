# App Foundation Shared Warehouse Lock 보고서

작성일: 2026-05-15  
작업 ID: APP_FOUNDATION_SHARED_WAREHOUSE_LOCK_01  
커밋 기준: 003fa2a → (이번 커밋)

---

## 1. 목적

APP_FOUNDATION_DOMAIN_ROOM_ALLOCATION_01에서 미확정으로 남은  
Evidence/Report 공용창고 위치와 사용 규칙을 고정한다.

---

## 2. 현재 창고 인벤토리 (read-only 조사)

| 항목 | 현황 |
|------|------|
| data/ 루트 | 임시 파일 100+개 산재 (레거시) |
| data/reports/ | eum/g2b/hiworks/naver 분산 존재 |
| data/manual_visits/ | 17개 호스트 스냅샷 존재 |
| data/sessions/ | 5개 파일 존재 — 내용 열람 금지 (BLOCKED) |
| data/logs/ | app.log/ops.log/cdp.db 존재 |
| data/audit/ | action_evidence.jsonl (위치 혼재) |
| data/evidence/ | **미존재 (이번에 확정)** |
| data/artifacts/ | **미존재 (이번에 확정)** |
| data/uploads/ | youtube만 있음 (통합 경로 없음) |
| data/drafts/ | **미존재 (이번에 확정)** |
| data/approvals/ | **미존재 (이번에 확정)** |

---

## 3. Shared Warehouse 표준 위치 (10개 창고 고정)

| 번호 | 창고명 | 표준 경로 | 정책 |
|------|--------|-----------|------|
| W1 | Draft | `data/drafts/{domain}/{task_id}/` | DRAFT_ALLOWED |
| W2 | Approval | `data/approvals/{domain}/{task_id}/` | APPROVAL_REQUIRED, 불변 |
| W3 | Execution Plan | `data/execution_plans/{domain}/{task_id}/` | ALLOWED_AFTER_APPROVAL |
| W4 | Evidence | `data/evidence/{domain}/{task_id}/` | READ_ONLY_AFTER_CREATION, 불변 |
| W5 | Report (human) | `docs/reports/` | ALLOWED |
| W5 | Report (machine) | `data/reports/{domain}/` | ALLOWED |
| W6 | Artifact | `data/artifacts/{domain}/{task_id}/` | ALLOWED |
| W7 | Upload | `data/uploads/{domain}/{task_id}/` | IMMUTABLE_ORIGIN |
| W8 | Audit Log | `data/logs/` | APPEND_ONLY |
| W9 | Manual Visit | `data/manual_visits/{host}/` | READ_ONLY_EVIDENCE |
| W10 | Session Store | `data/sessions/` | **BLOCKED (봉인)** |

---

## 4. Domain별 창고 배정

12개 Domain Unit에 대해 창고 경로·허용 action·금지 action 정의 완료:  
gabia / g2b / hiworks / google / youtube / eum / cad / hwpx /  
document_automation / attendance / safety_docs / risk_assessment / common

---

## 5. 저장소 정책 요약

| 항목 | 정책 |
|------|------|
| 허용 | draft/report/evidence/approval/execution_plan/artifact/upload 생성 |
| 금지 | data/sessions 읽기/파싱/재사용 |
| session policy | **BLOCKED** |
| manual visit policy | READ_ONLY_EVIDENCE |
| evidence policy | 불변, task_id 의무, 민감정보 포함 금지 |
| report policy | docs/reports (human) / data/reports (machine) 역할 분리 |
| upload policy | 원본 불변, 처리 결과는 artifacts로 분리 |

---

## 6. 생성/수정 파일

| 파일 | 종류 |
|------|------|
| `docs/architecture/shared_warehouse_model.md` | 창고 상세 정책 (10개 창고) |
| `docs/architecture/domain_warehouse_allocation.md` | 12개 Domain 창고 배정 |
| `docs/architecture/storage_boundary_policy.md` | 허용/금지 정책 상세 |
| `docs/architecture/shared_warehouse_manifest.json` | 기계 검사용 manifest |
| `scripts/ops/audit_shared_warehouse_policy.py` | 감사 스크립트 |
| `tests/test_shared_warehouse_policy.py` | 65개 테스트 |
| `docs/reports/app_foundation_shared_warehouse_lock_20260515.md` | 본 보고서 |

---

## 7. 테스트/게이트 결과

| 항목 | 결과 |
|------|------|
| `test_shared_warehouse_policy.py` | **65/65 PASS** |
| `audit_shared_warehouse_policy.py` | **75/75 PASS** |
| 기존 domain room allocation 테스트 | **69/69 PASS** |
| governance 테스트 | **50/50 PASS** |
| P1 gate 테스트 | **28/28 PASS** |
| Gabia 테스트 | **26/26 PASS** |
| site_engine 테스트 | PASS 유지 |
| layer audit (FORBIDDEN=0, SECURITY=0) | **PASS** |
| quality gate errors=0 / warnings=0 | **PASS** |
| governance audit 82/82 | **PASS** |

---

## 8. 안전 확인

| 항목 | 결과 |
|------|------|
| 기능 코드 변경 | 없음 |
| site module 변경 | 없음 |
| runtime data 파일 변경 | 없음 |
| DB/schema 변경 | 없음 |
| session/cookie 접근 | 없음 (존재 여부만 확인) |
| secret/env 출력 | 없음 |
| 삭제/권한 변경 | 없음 |
| 서버 재시작/배포 | 없음 |
| HOLD 파일 stage | 없음 (close_2_more.py, eum_docs.py 유지) |

---

## 9. 다음 단계 제안

1. **G2B skeleton 생성** — `scripts/g2b/profile.py`, `gates.py`, `validators.py`
2. **Eum 집 보강** — `scripts/eum/profile.py`, `gates.py`, `validators.py`
3. **Gabia DNS 집 구현** — `scripts/gabia/dns_assist.py` + router 연결
4. **CAD/HWPX 독립 집 생성** — `scripts/cad/`, `scripts/hwpx/`
5. **실제 창고 디렉터리 생성** — `data/drafts/`, `data/evidence/`, `data/artifacts/`, `data/approvals/` (별도 단계)

---

## 10. 최종 판정

**PASS**
