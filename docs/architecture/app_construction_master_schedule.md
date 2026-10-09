# App Construction Master Schedule (앱 건설 마스터 공정표)

작성일: 2026-05-15  
작업 ID: APP_CONSTRUCTION_SCHEDULE_DOCUMENTATION_01  
상태: LOCKED

---

## 개요

haehan-ai-orchestrator 앱을 건물로 비유하여 공사 전체 일정을 정의한다.  
각 공정(Phase)은 완료 조건(DoD)을 만족해야 다음 공정으로 진행한다.  
"건물"의 각 층이 레이어(L1~L12)에 대응하며, "집"이 Domain Unit에 대응한다.

---

## 공정 전체 목록

| 공정 | 코드 | 명칭 | 비유 | 상태 |
|------|------|------|------|------|
| A | FOUNDATION | 기초 공사 | 건물 기초·지반 | ✅ 완료 |
| B | STRUCTURAL | 구조 공사 | 철근·콘크리트 골조 | ✅ 완료 |
| C | SHARED_FACILITY | 공용 설비 | 엘리베이터·계단·전기 간선 | ✅ 완료 |
| D | DOMAIN_SHELL | 세대 외벽 | 각 집 외벽·출입문 | 🔨 진행 중 |
| E | DOMAIN_INTERIOR | 세대 내장 | 내부 마감·방 구성 | ⬜ 예정 |
| F | INTEGRATION | 통합 배선 | 세대 간 통신·공용망 연결 | ⬜ 예정 |
| G | INSPECTION | 준공 검사 | 소방·전기·구조 최종 검사 | ⬜ 예정 |
| H | HANDOVER | 입주 준비 | 청소·열쇠 전달·사용 설명 | ⬜ 예정 |
| I | OPERATION | 운영·유지보수 | 관리사무소·하자 보수 | ⬜ 예정 |

---

## Phase A — 기초 공사 (Foundation) ✅

**비유:** 건물이 서기 위한 지반 조사·말뚝·기초 슬래브  
**실제:** 거버넌스 게이트, 레이어 정책, 보안 정책, 감사 인프라

### 완료 항목

| 항목 | 증거 |
|------|------|
| P0 게이트 구현 (FORBIDDEN_IMPORT, CIRCULAR_IMPORT, SECURITY_PATTERN, FAT_SITE) | `tools/repo_gates/codebase_layer_audit.py` |
| P1 게이트 구현 (ROUTER_THINNESS, STORAGE_BOUNDARY, SERVER_BROWSER_GUARD) | `tools/repo_gates/codebase_layer_audit.py` |
| Quality Gate 구현 | `tools/quality/quality_gate.py` |
| Governance Gate Matrix 문서 | `docs/architecture/governance_gate_matrix.md` |
| Layer 정책 문서 | `docs/architecture/layer_policy.md` |
| Storage Audit Evidence Model | `docs/architecture/storage_audit_evidence_model.md` |

**DoD:** FORBIDDEN=0, SECURITY=0, quality errors=0, 모든 게이트 문서 존재  
**완료일:** 2026-05 이전

---

## Phase B — 구조 공사 (Structural) ✅

**비유:** 철근·콘크리트 골조 — 하중을 버티는 뼈대  
**실제:** 공용 창고 정책 고정, 도메인 집 배정 규칙 확정

### 완료 항목

| 항목 | 증거 |
|------|------|
| Domain Room Allocation Rule (11개 방) | `docs/architecture/domain_room_allocation_rule.md` |
| Gabia 집 배정 (6개 세부 집) | `docs/architecture/domain_units/gabia_room_allocation.md` |
| G2B 집 배정 (9개 세부 집) | `docs/architecture/domain_units/g2b_room_allocation.md` |
| 공통 도메인 집 배정 | `docs/architecture/domain_units/common_domain_room_allocation.md` |
| 공용 시설 배정 (11개) | `docs/architecture/shared_facility_allocation.md` |
| Shared Warehouse Lock (10개 창고) | `docs/architecture/shared_warehouse_model.md` |
| Domain Warehouse Allocation (12개 도메인) | `docs/architecture/domain_warehouse_allocation.md` |
| Storage Boundary Policy | `docs/architecture/storage_boundary_policy.md` |
| Shared Warehouse Manifest | `docs/architecture/shared_warehouse_manifest.json` |
| Shared Warehouse Physical Skeleton | `data/drafts/`, `data/evidence/` 등 6개 디렉터리 |

**DoD:** 감사 스크립트 PASS, 모든 테스트 PASS, 창고 디렉터리 물리 존재  
**완료일:** 2026-05-15

---

## Phase C — 공용 설비 (Shared Facility) ✅

**비유:** 엘리베이터·계단·전기 간선·소방 배관 — 모든 세대가 공유하는 설비  
**실제:** 브라우저 엔진, CDP 클라이언트, 팝업 감지, 네비게이터, 로깅

### 완료 항목

| 항목 | 증거 |
|------|------|
| CDP Client (`cdp_client.py`) | goto/click/type/paste-image 명령 집합 |
| Popup Watcher (`popup_watcher.py`) | MutationObserver 기반 DOM 팝업 감지 |
| Browser Navigator (`navigator.py`) | goto + wait-login 통합 진입점 |
| App/Ops Logging | `data/logs/app.log`, `data/cdp.db` |

**DoD:** Naver 블로그 글쓰기 자동화 검증, cdp.db 기록 확인  
**완료일:** 2026-05-11

---

## Phase D — 세대 외벽 (Domain Shell) 🔨

**비유:** 각 세대(집)의 외벽과 출입문 — 집의 경계와 진입점  
**실제:** Domain Unit별 router, profile, gates, validators 골격

### 진행 현황

| 도메인 | router | profile | gates | validators | 상태 |
|--------|--------|---------|-------|------------|------|
| Gabia | ✅ | ⬜ | ⬜ | ⬜ | 골격만 |
| Hiworks | ✅ | ⬜ | ⬜ | ⬜ | 골격만 |
| G2B | ⬜ | ⬜ | ⬜ | ⬜ | 미시작 |
| Eum | 부분 | ⬜ | ⬜ | ⬜ | 부분 |
| Google | ⬜ | ⬜ | ⬜ | ⬜ | 미시작 |
| YouTube | ⬜ | ⬜ | ⬜ | ⬜ | 미시작 |
| CAD | ⬜ | ⬜ | ⬜ | ⬜ | 미시작 |
| HWPX | ⬜ | ⬜ | ⬜ | ⬜ | 미시작 |

**DoD:** 각 도메인 router → site_engine 연결, profile/gates/validators 존재, 테스트 PASS

---

## Phase E — 세대 내장 (Domain Interior) ⬜

**비유:** 주방·화장실·방 마감 — 실제 거주 가능한 내부 완성  
**실제:** Domain Unit별 usecase, adapter, workflow 구현

**DoD:** 각 업무 흐름 E2E 동작, evidence 자동 생성, audit log 기록

---

## Phase F — 통합 배선 (Integration) ⬜

**비유:** 세대 간 인터폰·공용망·전화 배선  
**실제:** 도메인 간 공용 서비스 연결, Approval Gate 통합, Workflow Queue 연결

**DoD:** cross-domain 요청이 공용 시설을 경유, FORBIDDEN_IMPORT=0 유지

---

## Phase G — 준공 검사 (Inspection) ⬜

**비유:** 소방서·전기안전공사·구청 준공 검사  
**실제:** E2E 테스트 전체 PASS, 보안 감사, 성능 측정

**DoD:** 전체 게이트 PASS, E2E 시나리오 커버리지 80% 이상

---

## Phase H — 입주 준비 (Handover) ⬜

**비유:** 청소·열쇠 전달·사용 설명서  
**실제:** 운영 배포, 사용자 가이드, 모니터링 설정

**DoD:** 서버 배포 완료, 운영 모니터링 대시보드 가동

---

## Phase I — 운영·유지보수 (Operation) ⬜

**비유:** 관리사무소·엘리베이터 점검·하자 보수  
**실제:** 주기적 감사, 업데이트, 장애 대응

**DoD:** 주 1회 감사 자동 실행, 장애 감지 → 알림 → 대응 체계 가동

---

## 관련 문서

- `docs/architecture/app_construction_as_built_matrix.md` — 현재 시공 현황 매트릭스
- `docs/architecture/app_construction_completion_checklist.md` — 공정별 완료 체크리스트
- `docs/architecture/app_construction_next_sequence.md` — 다음 공정 순서
- `docs/reports/app_construction_punch_list_20260515.md` — 미처리 항목 목록
