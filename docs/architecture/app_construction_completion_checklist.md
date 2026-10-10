# App Construction Completion Checklist (공정별 완료 체크리스트)

작성일: 2026-05-15  
작업 ID: APP_CONSTRUCTION_SCHEDULE_DOCUMENTATION_01  
상태: LOCKED

---

## 사용법

각 Phase 완료 선언 전 아래 체크리스트를 100% 충족해야 한다.  
체크 항목에 ✅ / ❌ 기입 후 감사 스크립트로 자동 검증.

---

## Phase A — 기초 공사 체크리스트 ✅ 완료

- [x] `tools/repo_gates/codebase_layer_audit.py` 존재 및 실행 가능
- [x] `tools/quality/quality_gate.py` 존재 및 실행 가능
- [x] `docs/architecture/governance_gate_matrix.md` 존재
- [x] `docs/architecture/layer_policy.md` 존재
- [x] `docs/architecture/storage_audit_evidence_model.md` 존재
- [x] layer audit: FORBIDDEN_IMPORT=0
- [x] layer audit: SECURITY_PATTERN=0
- [x] layer audit: CIRCULAR_IMPORT=0
- [x] quality gate: errors=0
- [x] quality gate: warnings=0

**완료 선언 조건:** 위 10개 항목 전체 ✅

---

## Phase B — 구조 공사 체크리스트 ✅ 완료

- [x] `docs/architecture/domain_room_allocation_rule.md` 존재
- [x] `docs/architecture/domain_units/gabia_room_allocation.md` 존재
- [x] `docs/architecture/domain_units/g2b_room_allocation.md` 존재
- [x] `docs/architecture/domain_units/common_domain_room_allocation.md` 존재
- [x] `docs/architecture/shared_facility_allocation.md` 존재
- [x] `docs/architecture/shared_warehouse_model.md` 존재
- [x] `docs/architecture/domain_warehouse_allocation.md` 존재
- [x] `docs/architecture/storage_boundary_policy.md` 존재
- [x] `docs/architecture/shared_warehouse_manifest.json` 존재 및 parse 가능
- [x] `data/drafts/.gitkeep` 존재
- [x] `data/approvals/.gitkeep` 존재
- [x] `data/execution_plans/.gitkeep` 존재
- [x] `data/evidence/.gitkeep` 존재
- [x] `data/artifacts/.gitkeep` 존재
- [x] `data/uploads/.gitkeep` 존재
- [x] `tools/audits/app/audit_domain_room_allocation.py` 63/63 PASS
- [x] `tools/audits/app/audit_shared_warehouse_policy.py` 75/75 PASS
- [x] `tests/test_domain_room_allocation.py` 69/69 PASS
- [x] `tests/test_shared_warehouse_policy.py` 65/65 PASS
- [x] `tests/test_shared_warehouse_physical_skeleton.py` 33/33 PASS
- [x] session_policy=BLOCKED, data/sessions 봉인 유지

**완료 선언 조건:** 위 21개 항목 전체 ✅

---

## Phase C — 공용 설비 체크리스트 🔨 부분 완료

- [x] `cdp_client.py` goto/click/type/paste-image 명령 구현
- [x] `popup_watcher.py` MutationObserver 기반 팝업 감지 구현
- [x] `navigator.py` goto + wait-login 통합 진입점 구현
- [x] `data/logs/app.log` 기록 확인
- [x] `data/cdp.db` 기록 확인
- [ ] Action Registry (`core/action_registry.py`) 구현
- [ ] Approval Gate 구현
- [ ] Workflow Queue 구현
- [ ] Local Agent Gateway 구현
- [ ] Notification Center 구현
- [ ] 공용 설비 통합 테스트 PASS

**완료 선언 조건:** 위 11개 항목 전체 ✅

---

## Phase D — 세대 외벽 체크리스트 ⬜ 진행 중

각 도메인 유닛별 완료 조건 (8개 도메인 × 체크리스트):

### D-1. 공통 필수 항목 (도메인별 반복)

- [ ] `scripts/{domain}/router.py` 존재
- [ ] `scripts/{domain}/profile.py` 존재
- [ ] `scripts/{domain}/gates.py` 존재
- [ ] `scripts/{domain}/validators.py` 존재
- [ ] router는 HTTP 라우팅만 (업무 로직 금지)
- [ ] ROUTER_THINNESS 게이트 PASS
- [ ] SERVER_BROWSER_GUARD 게이트 PASS
- [ ] cross-domain import 없음
- [ ] 도메인별 테스트 PASS
- [ ] 도메인 규약집(docs) 존재

### D-2. 도메인별 현황

| 도메인 | router | profile | gates | validators | tests | 규약집 |
|--------|--------|---------|-------|------------|-------|--------|
| gabia | 🔨 | ⬜ | ⬜ | ⬜ | 부분 | ✅ |
| hiworks | 🔨 | ⬜ | ⬜ | ⬜ | ⬜ | ✅ |
| g2b | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ✅ |
| eum | 부분 | ⬜ | ⬜ | ⬜ | ⬜ | ✅ |
| google | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ✅ |
| youtube | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ✅ |
| cad | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ✅ |
| hwpx | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ✅ |

**완료 선언 조건:** 8개 도메인 전체 D-1 체크리스트 ✅

---

## Phase E — 세대 내장 체크리스트 ⬜

- [ ] 각 도메인 `usecase.py` 존재
- [ ] 각 도메인 `adapter.py` 존재
- [ ] 각 도메인 `workflow.py` 존재
- [ ] evidence 자동 생성 (`data/evidence/{domain}/{task_id}/`)
- [ ] audit log 자동 기록
- [ ] 각 도메인 E2E 시나리오 PASS

---

## Phase F — 통합 배선 체크리스트 ⬜

- [ ] 도메인 간 요청이 공용 시설(Action Registry) 경유
- [ ] Approval Gate 연동
- [ ] FORBIDDEN_IMPORT=0 유지 (cross-domain import 없음)
- [ ] Workflow Queue 통합 PASS

---

## Phase G — 준공 검사 체크리스트 ⬜

- [ ] 전체 게이트 PASS (FORBIDDEN=0, SECURITY=0, CIRCULAR=0)
- [ ] E2E 시나리오 커버리지 ≥ 80%
- [ ] 보안 감사 완료 (session BLOCKED 확인)
- [ ] 성능 측정 완료

---

## Phase H — 입주 준비 체크리스트 ⬜

- [ ] 서버 배포 완료 (docker compose up)
- [ ] 운영 모니터링 대시보드 가동
- [ ] 사용자 가이드 작성
- [ ] 열쇠 전달 (접속 계정 확인)

---

## Phase I — 운영·유지보수 체크리스트 ⬜

- [ ] 주 1회 감사 스크립트 자동 실행
- [ ] 장애 감지 → 알림 → 대응 체계 가동
- [ ] 하자 보수 프로세스 정의
