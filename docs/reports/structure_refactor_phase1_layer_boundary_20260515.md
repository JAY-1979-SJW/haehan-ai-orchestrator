# Structure Refactor Phase 1 - Layer Boundary Baseline - 2026-05-15

## 1. 시작 기준

- branch: master
- 시작 HEAD: 2573ecf2a46028d628b362a1a717cff84434b060
- server status: clean

## 2. 감사 전 결과

| 항목 | 결과 |
|---|---|
| 전체 파일 수 | 3500 |
| issues | 805 |
| warnings | 798 |
| import cycles | 0 |
| UNKNOWN layer | 745 (실제 코드베이스: 6, .claude/ 내부: 739) |
| P0 위반 (ERROR/BLOCK) | 0 |
| FAT_SITE_ROUTER | 1 (scripts/hiworks/router.py) |
| ROOT_PY_SCRIPT | 24 |

## 3. 위반 분류

| 위치 | 위반 유형 | 등급 | 조치 |
|---|---|---|---|
| .claude/ (739건) | UNKNOWN_LAYER | FALSE_POSITIVE | EXCLUDED_DIRS에 .claude 추가로 해소 |
| services/file_map_executor/ (6건) | UNKNOWN_LAYER | P2_AUDIT_RULE_FIX | services/ → L8 규칙 추가로 해소 |
| scripts/hiworks/router.py | FAT_SITE_ROUTER | P1 | tracked_residuals 등록, Phase 2 처리 |
| root *.py 24건 | ROOT_PY_SCRIPT | P3 | tracked_residuals 등록, Phase 3 처리 |
| (없음) | P0_LAYER_BLOCKER | P0 | 0건 확인 |

## 4. 수정 파일

| 파일 | 변경 내용 | 이유 |
|---|---|---|
| scripts/ops/codebase_layer_audit.py | EXCLUDED_DIRS에 `.claude` 추가 | .claude/ 739건 UNKNOWN 오탐 제거 |
| scripts/ops/codebase_layer_audit.py | `services/` → L8 분류 규칙 추가 | services/file_map_executor/ UNKNOWN 해소 |
| configs/codebase_layer_audit.json | max_unknown_layer_files 900→20 | 임계값 실제 기준 반영 |
| configs/codebase_layer_audit.json | FAT_SITE_ROUTER/ROOT_PY_SCRIPT tracked_residuals 등록 | Phase 2/3 추적 |
| configs/codebase_layer_audit.json | .claude/ 및 services/ resolved_residuals 등록 | 이번 단계 해소 기록 |
| docs/reports/structure_refactor_phase1_layer_boundary_20260515.md | 이 보고서 | 감사 결과 문서화 |

## 5. 감사 후 결과

| 항목 | 이전 | 이후 | 판정 |
|---|---:|---:|---|
| 전체 파일 수 | 3500 | 1929 (.claude 제외) | ✓ |
| UNKNOWN layer | 745 | 0 | PASS ✓ |
| import cycles | 0 | 0 | PASS ✓ |
| P0 위반 | 0 | 0 | PASS ✓ |
| issues | 805 | 60 | 개선 ✓ |
| warnings | 798 | 53 | 개선 ✓ |
| max_unknown threshold | 900 | 20 | 강화 ✓ |

## 6. 영향 범위

- API response key 변경: 없음
- DB/schema 변경: 없음
- 권한 변경: 없음
- 서버 재시작: 없음
- 배포: 없음
- HOLD 파일 stage: 없음 (close_2_more.py, eum_docs.py 제외)

## 7. 남은 P1/P3 항목

| 항목 | 등급 | 다음 단계 |
|---|---|---|
| FAT_SITE_ROUTER (hiworks/router.py) | P1 | Phase 2: router 책임 분리 |
| ROOT_PY_SCRIPT 24건 | P3 | Phase 3: root 파일 정리 |

## 8. 다음 단계 권장

```
STRUCTURE_REFACTOR_PHASE2_ROUTER_SERVICE_SPLIT_01
```

Phase 2 목표: scripts/hiworks/router.py FAT_SITE_ROUTER 분리 및
router/service/core 책임 분리 최소 수정.
