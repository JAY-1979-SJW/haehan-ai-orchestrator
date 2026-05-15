# App Construction Punch List (미처리 항목 목록)

작성일: 2026-05-15  
작업 ID: APP_CONSTRUCTION_SCHEDULE_DOCUMENTATION_01

---

## 미처리 항목 (Punch List)

2026-05-15 기준 완료되지 않은 항목 목록.  
Phase D 이후 각 작업에서 순차 처리한다.

---

## Phase D — 세대 외벽 미처리 항목

| 번호 | 항목 | 도메인 | 우선순위 | 비고 |
|------|------|--------|----------|------|
| P-D-001 | `scripts/g2b/profile.py` 생성 | G2B | HIGH | 투찰/전자서명 BLOCKED 게이트 포함 |
| P-D-002 | `scripts/g2b/gates.py` 생성 | G2B | HIGH | |
| P-D-003 | `scripts/g2b/validators.py` 생성 | G2B | HIGH | |
| P-D-004 | `scripts/g2b/router.py` 생성 | G2B | HIGH | |
| P-D-005 | `scripts/eum/profile.py` 생성 | Eum | HIGH | 22개 현장 임대 단말기 프로필 |
| P-D-006 | `scripts/eum/gates.py` 생성 | Eum | HIGH | |
| P-D-007 | `scripts/eum/validators.py` 생성 | Eum | HIGH | |
| P-D-008 | `scripts/gabia/profile.py` 생성 | Gabia | MEDIUM | |
| P-D-009 | `scripts/gabia/gates.py` 생성 | Gabia | MEDIUM | |
| P-D-010 | `scripts/gabia/validators.py` 생성 | Gabia | MEDIUM | |
| P-D-011 | `scripts/hiworks/profile.py` 생성 | Hiworks | MEDIUM | |
| P-D-012 | `scripts/hiworks/gates.py` 생성 | Hiworks | MEDIUM | |
| P-D-013 | `scripts/hiworks/validators.py` 생성 | Hiworks | MEDIUM | |
| P-D-014 | `scripts/google/router.py` 생성 | Google | LOW | |
| P-D-015 | `scripts/youtube/router.py` 생성 | YouTube | LOW | |
| P-D-016 | `scripts/cad/router.py` 생성 | CAD | LOW | L10 레이어 |
| P-D-017 | `scripts/hwpx/router.py` 생성 | HWPX | LOW | L10 레이어 |

---

## Phase C — 공용 설비 미처리 항목

| 번호 | 항목 | 우선순위 | 비고 |
|------|------|----------|------|
| P-C-001 | `core/action_registry.py` 구현 | MEDIUM | Action Registry |
| P-C-002 | `core/approval_gate.py` 구현 | MEDIUM | Approval Gate |
| P-C-003 | Workflow Queue 구현 | LOW | L6 레이어 |
| P-C-004 | Local Agent Gateway 구현 | LOW | L4 레이어 |
| P-C-005 | Notification Center 구현 | LOW | |

---

## 레거시 정리 항목 (별도 작업 필요)

| 번호 | 항목 | 우선순위 | 비고 |
|------|------|----------|------|
| L-001 | `data/` 루트 임시 파일 100+개 정리 | LOW | 사용자 명시 승인 필요 |
| L-002 | `data/audit/action_evidence.jsonl` 위치 정상화 | LOW | W8 창고로 이동 필요 |
| L-003 | `data/reports/` 하위 eum/g2b/hiworks/naver 구조 정비 | LOW | |
| L-004 | HOLD 파일 처리 (close_2_more.py, eum_docs.py) | HOLD | 사용자 지시 대기 |

---

## 완료 기준

각 P-번호 항목은 해당 도메인 작업 시 완료로 표시.  
감사 스크립트에서 자동 추적 불가 — 수동 체크 후 다음 작업 ID에 완료 표시.
