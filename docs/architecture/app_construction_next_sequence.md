# App Construction Next Sequence (다음 공정 순서)

작성일: 2026-05-15  
작업 ID: APP_CONSTRUCTION_SCHEDULE_DOCUMENTATION_01  
상태: LOCKED

---

## 현재 위치

Phase A (기초) ✅ → Phase B (구조) ✅ → Phase C 부분 ✅ → **Phase D 진행 중**

---

## 다음 즉시 실행 순서

### 1단계: G2B 세대 외벽 골격 (Priority: HIGH)

```
APP_DOMAIN_G2B_SHELL_01
```

- `scripts/g2b/site_profile.py` — 공사번호·입찰구분·기관코드 프로필
- `scripts/g2b/gates.py` — 투찰/전자서명 BLOCKED 게이트
- `scripts/g2b/validators.py` — 공고번호 형식 검증
- 테스트 `tests/test_g2b_shell.py`
- ROUTER_THINNESS, SERVER_BROWSER_GUARD 게이트 PASS

### 2단계: Eum 세대 외벽 보강 (Priority: HIGH)

```
APP_DOMAIN_EUM_SHELL_REINFORCE_01
```

- `scripts/eum/profile.py` — 단말기 임대 프로필 (22개 현장)
- `scripts/eum/gates.py` — 자동 실행 게이트
- `scripts/eum/validators.py` — 단말기번호·공사번호 형식 검증
- 기존 `eum_extract_all_devices.py`, `eum_business_dashboard.py` 보존

### 3단계: Gabia DNS 세대 내장 (Priority: MEDIUM)

```
APP_DOMAIN_GABIA_DNS_INTERIOR_01
```

- `scripts/gabia/dns_assist.py` — DNS 조회 보조 (router 연결)
- USER_DIRECT_REQUIRED 게이트 적용
- evidence 자동 생성 (`data/evidence/gabia/{task_id}/`)

### 4단계: CAD / HWPX 세대 외벽 (Priority: MEDIUM)

```
APP_DOMAIN_CAD_HWPX_SHELL_01
```

- `scripts/cad/router.py`, `scripts/cad/profile.py`
- `scripts/hwpx/router.py`, `scripts/hwpx/profile.py`
- L10 레이어 (Local PC App) 배치

### 5단계: 공용 설비 Phase C 완성 (Priority: MEDIUM)

```
APP_SHARED_FACILITY_ACTION_REGISTRY_01
```

- `core/action_registry.py` — Action Registry 구현
- `core/approval_gate.py` — Approval Gate 구현
- 공용 설비 통합 테스트

---

## 각 단계 공통 DoD

1. 신규 파일은 정해진 레이어 위치에만 작성
2. 기존 구현 재사용, 중복 구현 금지
3. FORBIDDEN_IMPORT=0, SECURITY_PATTERN=0 유지
4. quality gate errors=0, warnings=0 유지
5. 테스트 PASS 후 커밋 → push → server pull
6. HOLD 파일 (close_2_more.py, eum_docs.py) stage 금지

---

## 장기 로드맵

| 단계 | 공정 | 예상 작업 수 |
|------|------|-------------|
| 즉시 | Phase D 완성 (8개 도메인 shell) | 5~8개 작업 |
| 단기 | Phase E 완성 (내장 구현) | 8~12개 작업 |
| 중기 | Phase F 통합 배선 | 3~5개 작업 |
| 장기 | Phase G~I (검사·입주·운영) | 3~5개 작업 |

---

## 참조

- `docs/architecture/app_construction_master_schedule.md` — 전체 공정표
- `docs/architecture/app_construction_as_built_matrix.md` — 현재 시공 현황
- `docs/architecture/app_construction_completion_checklist.md` — 완료 체크리스트
- `docs/reports/app_construction_punch_list_20260515.md` — 미처리 항목
