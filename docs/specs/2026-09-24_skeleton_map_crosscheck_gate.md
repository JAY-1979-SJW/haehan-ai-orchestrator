# 지도↔골격 대조 의무화 설계 (결함 #34 후속, 2026-09-24)

## 목적
사용자 지시: "지도와 골격을 맞대 보는 장치를 설계상으로 해서 무조건 하게".
지금 9번 대조(verify_change)는 **누가 돌릴 때만** 실행된다. 이를 **돌리지 않으면 커밋·병합이 안 되는** 구조로 바꾼다.

용어: **지도** = 코드맵(`data/code_map/map.json`, 실제 파일·연결) / **골격** = 분류 정본(`configs/module_registry.json` 층·역할·도메인 + `configs/module_boundaries` 선언 모듈).

## 원칙
1. 골격은 **git 에 커밋된 코드 파일**만 담는다(미추적 임시 파일 제외) — 깨끗한 폴더에서 재도 같은 결과.
2. 파일을 **추가·삭제·이동**하는 커밋은 **같은 커밋에서** 골격도 갱신해야 한다. 안 하면 커밋 차단.
3. 사람(AI)이 손으로 맞출 필요 없게 **자동 동기화 명령** 제공 — 차단 메시지가 그 명령을 알려준다.
4. 병합 전 전체 대조(verify_change 9항목 포함)는 **병합 스크립트가 강제** — PASS 기록 없이 master 로 못 들어간다.
5. 기존 부채는 기준선, 신규만 FAIL. 우회는 사유 trailer 로만, 감사로 집계.

## 구성 (3겹)

| 겹 | 언제 | 무엇을 | 속도 | 막는 곳 |
|---|---|---|---|---|
| ① 커밋 게이트 `skeleton_gate.py` | 모든 커밋 | 스테이지된 A/D/R 코드 파일 ↔ 스테이지된 정본 키 일치, 정본 전체 ↔ 추적 파일 일치, 선언 모듈 경로 존재, 금지 import(스테이지 파일) | 1초 내외(지도 빌드 없음) | pre-commit (차단) |
| ② 동기화 도구 `registry_sync.py --fix` | 게이트 FAIL 시 | 새 파일 → classify 규칙으로 분류 추가 / 삭제 파일 → 제거 / 이동 → 값 유지한 채 키 변경 / 미추적 항목 제거. overrides(사람 확정값)도 키 이동 | 수 초 | — (고치는 도구) |
| ③ 병합 게이트 `merge_stage.py <branch>` | master 병합 | `verify_change --base master --head <branch>` 실행 → PASS 일 때만 `merge --ff-only` + `verified/<branch>` 태그(검증표) | 약 15분 | 병합 절차 자체 |

①만으로 "정본 누락·유령 항목"은 원천 차단. 층간 위반·순환·지도 기반 대조는 지도 빌드가 필요해 ③에서.

## ① 커밋 게이트 판정 규칙
- A(추가) `.py/.ts/.tsx/.js/.mjs` → 스테이지된 정본에 키 있어야 함
- D(삭제) → 정본에서 키 없어야 함
- R(이동) → 옛 키 없음 + 새 키 있음(값은 옛 값 유지 권장, 층 달라지면 경고)
- 정본 전체 키 ⊆ 추적 파일(스테이지 반영), 추적 코드 파일 ⊆ 정본 → 어긋나면 FAIL
- 선언 모듈(module_boundaries) 경로가 없으면 FAIL
- 금지 import: 스테이지된 파일에서 새로 생긴 것만 FAIL(기존 1건은 기준선)
- 우회: 커밋 메시지 trailer `Skip-Skeleton-Gate: <사유>` (사유 없으면 무시) — 감사 집계
- FAIL 메시지 끝: `python tools/code_map/registry_sync.py --fix && git add configs/module_registry.json`

## 기존 부채 정리 (시공 1단계에 포함)
- 정본의 미추적 파일 36개 제거(작업폴더 임시·미커밋 제품 파일) → 해당 파일이 커밋될 때 ①이 등록을 요구
- 선언 모듈 portable_install(6)·desktop_runtime(1) 의 없는 경로 → 삭제된 기능이므로 선언에서 제거
- 금지 import 1건(google/youtube/search_analyze → youtube/research) → 기준선 등록(별도 수정)
- 목표: 정리 후 ① 전체 검사 0건에서 시작

## 드라이런 (2026-09-24 실측)
- 정본 2,433 / 추적 코드 파일 기준 누락 0, 유령 0, **미추적 포함 36**
- 최근 30커밋에 ①을 적용했다면 **8커밋 차단**(py 추가·삭제·이동 후 정본 미갱신: e8f23c72, 4cfa1c09, d331b910, 8dafbf3a(29파일), 5c536a3d, d4a4421d(19), 5973ebd2(62), 48a4aa4b(12))
  → 대량 정리 커밋이 골격을 방치해 온 것이 36건 불일치의 원인

## 검증 (깨뜨리기)
①: 새 .py 추가+정본 미갱신 → FAIL / `--fix` 후 → PASS / 파일 삭제+정본 유지 → FAIL / 이동 → FAIL→fix→PASS / 선언 경로 없음 → FAIL / trailer 우회 → PASS+감사 기록 / 2회 실행 동일.
③: 고장 브랜치 → 병합 거부 / 정상 → ff 병합+태그.

## 영향
- 신규: tools/code_map/skeleton_gate.py, registry_sync.py, tools/merge_stage.py, 테스트 tests/test_skeleton_gate.py
- 수정: .githooks/pre-commit.orig(① 호출 1줄 — 추적 정본 + install_git_hooks.py 반영), configs/module_registry.json(부채 정리), 선언 모듈 설정, 공용 스킬 verify-change(설치 대상에 포함)
- API·DB·보안 영향 없음. CLAUDE.md 는 사용자 확인 후 "게이트 실행 의무" 절에 1줄 추가 제안.

## 롤백
훅 1줄 제거 또는 태그 `pre-skeleton-gate`.
