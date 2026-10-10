# App Construction As-Built Matrix (시공 현황 매트릭스)

작성일: 2026-05-15  
작업 ID: APP_CONSTRUCTION_SCHEDULE_DOCUMENTATION_01  
상태: LOCKED

---

## 개요

2026-05-15 기준 실제 시공 완료 현황을 Domain Unit × Phase 매트릭스로 표시한다.  
범례: ✅ 완료 / 🔨 진행 중 / ⬜ 미시작 / ❌ 해당 없음

---

## 1. 거버넌스 인프라 (공통 기반)

| 항목 | 레이어 | 상태 | 증거 파일 |
|------|--------|------|-----------|
| Layer Audit (P0 게이트) | L2 | ✅ | `tools/repo_gates/codebase_layer_audit.py` |
| Quality Gate | L2 | ✅ | `tools/quality/quality_gate.py` |
| Governance Gate Matrix | L12 | ✅ | `docs/architecture/governance_gate_matrix.md` |
| Domain Room Allocation Rule | L12 | ✅ | `docs/architecture/domain_room_allocation_rule.md` |
| Shared Warehouse Model | L12 | ✅ | `docs/architecture/shared_warehouse_model.md` |
| Storage Boundary Policy | L12 | ✅ | `docs/architecture/storage_boundary_policy.md` |
| Shared Warehouse Manifest | L12 | ✅ | `docs/architecture/shared_warehouse_manifest.json` |
| Physical Warehouse Skeleton | L7 | ✅ | `data/drafts/`, `data/evidence/` 등 6개 |

---

## 2. 공용 시설 (Shared Facility)

| 시설 | 레이어 | 상태 | 위치 |
|------|--------|------|------|
| CDP Client | L4 | ✅ | `scripts/browser/agent/cdp_client.py` |
| Popup Watcher | L4 | ✅ | `scripts/browser/agent/popup_watcher.py` |
| Browser Navigator | L4 | ✅ | `scripts/browser/agent/navigator.py` |
| App Logger | L7 | ✅ | `data/logs/app.log` + `data/cdp.db` |
| Ops Logger | L7 | ✅ | `data/logs/ops.log` |
| Action Registry | L2 | ⬜ | 미구현 |
| Approval Gate | L2 | ⬜ | 미구현 |
| Workflow Queue | L6 | ⬜ | 미구현 |
| Local Agent Gateway | L4 | ⬜ | 미구현 |

---

## 3. Domain Unit 시공 현황

### 3-1. Gabia (도메인·호스팅)

| 방 | 코드명 | 상태 | 위치 |
|----|--------|------|------|
| 입구 (router) | entrance | 🔨 | `scripts/gabia/router.py` |
| 입주자 카드 (profile) | resident_card | ⬜ | 미구현 |
| 보안문 (gates) | security_door | ⬜ | 미구현 |
| 검수실 (validators) | inspection | ⬜ | 미구현 |
| 거실 (usecase) | living_room | ⬜ | 미구현 |
| 외부문 (adapter) | external_door | ⬜ | 미구현 |
| 주차장 (workflow) | parking | ⬜ | 미구현 |
| 창고 (storage) | warehouse | 부분 | `data/reports/gabia/` 존재 |
| CCTV (audit) | cctv | ⬜ | 미구현 |
| 화재경보 (tests) | alarm | 부분 | `tests/test_gabia_site.py` |
| 규약집 (docs) | rulebook | ✅ | `docs/architecture/domain_units/gabia_room_allocation.md` |

### 3-2. Hiworks (그룹웨어)

| 방 | 코드명 | 상태 | 위치 |
|----|--------|------|------|
| 입구 (router) | entrance | 🔨 | `scripts/hiworks/router.py` |
| 입주자 카드 (profile) | resident_card | ⬜ | 미구현 |
| 보안문 (gates) | security_door | ⬜ | 미구현 |
| 검수실 (validators) | inspection | ⬜ | 미구현 |
| 거실 (usecase) | living_room | ⬜ | 미구현 |
| 외부문 (adapter) | external_door | ⬜ | 미구현 |
| 주차장 (workflow) | parking | ⬜ | 미구현 |
| 창고 (storage) | warehouse | ⬜ | 미구현 |
| CCTV (audit) | cctv | ⬜ | 미구현 |
| 화재경보 (tests) | alarm | ⬜ | 미구현 |
| 규약집 (docs) | rulebook | ✅ | `docs/architecture/domain_units/common_domain_room_allocation.md` |

### 3-3. Eum (건설근로자공제회)

| 방 | 코드명 | 상태 | 위치 |
|----|--------|------|------|
| 입구 (router) | entrance | 부분 | `scripts/eum/` (부분 구현) |
| 입주자 카드 (profile) | resident_card | ⬜ | 미구현 |
| 보안문 (gates) | security_door | ⬜ | 미구현 |
| 검수실 (validators) | inspection | ⬜ | 미구현 |
| 거실 (usecase) | living_room | 부분 | `scripts/eum_business_dashboard.py` |
| 외부문 (adapter) | external_door | 부분 | `scripts/eum_extract_all_devices.py` |
| 주차장 (workflow) | parking | ⬜ | 미구현 |
| 창고 (storage) | warehouse | 부분 | `data/reports/eum/` 존재 |
| CCTV (audit) | cctv | ⬜ | 미구현 |
| 화재경보 (tests) | alarm | ⬜ | 미구현 |
| 규약집 (docs) | rulebook | ✅ | `docs/architecture/domain_units/common_domain_room_allocation.md` |

### 3-4. G2B (나라장터) — 미시작

| 방 | 상태 |
|----|------|
| 모든 방 | ⬜ 미시작 |
| 규약집 | ✅ `docs/architecture/domain_units/g2b_room_allocation.md` |

### 3-5. Google / YouTube / CAD / HWPX / 기타 — 미시작

| 도메인 | 규약집 | 나머지 방 |
|--------|--------|-----------|
| Google | ✅ (common) | ⬜ 전체 미시작 |
| YouTube | ✅ (common) | ⬜ 전체 미시작 |
| CAD | ✅ (common) | ⬜ 전체 미시작 |
| HWPX | ✅ (common) | ⬜ 전체 미시작 |
| 문서자동화 | ✅ (common) | ⬜ 전체 미시작 |
| 출퇴근 | ✅ (common) | ⬜ 전체 미시작 |
| 위험성평가 | ✅ (common) | ⬜ 전체 미시작 |

---

## 4. 창고 현황

| 창고 | 경로 | 물리 디렉터리 | 정책 문서 | manifest |
|------|------|--------------|-----------|---------|
| W1 Draft | `data/drafts/` | ✅ | ✅ | ✅ |
| W2 Approval | `data/approvals/` | ✅ | ✅ | ✅ |
| W3 Execution Plan | `data/execution_plans/` | ✅ | ✅ | ✅ |
| W4 Evidence | `data/evidence/` | ✅ | ✅ | ✅ |
| W5 Report (human) | `docs/reports/` | ✅ | ✅ | ✅ |
| W5 Report (machine) | `data/reports/` | ✅ | ✅ | ✅ |
| W6 Artifact | `data/artifacts/` | ✅ | ✅ | ✅ |
| W7 Upload | `data/uploads/` | ✅ | ✅ | ✅ |
| W8 Audit Log | `data/logs/` | ✅ | ✅ | ✅ |
| W9 Manual Visit | `data/manual_visits/` | ✅ | ✅ | ✅ |
| W10 Session Store | `data/sessions/` | BLOCKED | ✅ | ✅ |

---

## 5. 종합 진행률

| Phase | 항목 | 완료 | 진행 중 | 미시작 | 완료율 |
|-------|------|------|---------|--------|--------|
| A 기초 | 거버넌스 인프라 | 8 | 0 | 0 | 100% |
| B 구조 | 창고·배정 정책 | 10 | 0 | 0 | 100% |
| C 공용설비 | 브라우저·로깅 | 5 | 0 | 4 | 56% |
| D 세대외벽 | Domain shell (8도메인×11방) | 10 | 4 | 74 | ~11% |
| E~I | 내장·통합·검사·운영 | 0 | 0 | — | 0% |
