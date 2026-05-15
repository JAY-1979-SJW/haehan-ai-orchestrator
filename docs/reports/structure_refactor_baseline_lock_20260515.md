# Structure Refactor Baseline Lock - 2026-05-15

## 1. 기준선

- branch: master
- local HEAD: 444d6fbeae0a25ef2bd317c964d4a92807b0d0bb
- origin HEAD: 444d6fbeae0a25ef2bd317c964d4a92807b0d0bb
- server HEAD: 444d6fbeae0a25ef2bd317c964d4a92807b0d0bb
- server status: clean
- modified: 0
- deleted: 0
- untracked: 2건 (close_2_more.py, eum_docs.py — HOLD)
- staged: 없음

## 2. 완료된 정리 작업

- COMMIT_GROUP_A docs
- CAD compose 운영 변경 승격
- COMMIT_GROUP_B ops/audit/quality gate
- COMMIT_GROUP_D local-agent/API contract
- COMMIT_GROUP_C site modules
  - EUM
  - Hiworks
  - Naver
  - Smartstore
  - Google
  - Youtube
- ADMIN_WEB_TSCONFIG_SPLIT
- COMMIT_GROUP_E admin-web UI/PWA
- MISSED_GROUP_1 core/security/router
- MISSED_GROUP_2 CDP/browser runtime
- MISSED_GROUP_3 browser session/popup
- MISSED_GROUP_4 site infra/form/explorer
- MISSED_GROUP_5 security/session tests closeout
- MISSED_GROUP_6 ops/config/index
- BLOCKER_FIX deleted imports
- ARCHIVE_COMMIT_GROUP
- DOCS_REFERENCE_UPDATE_GROUP
- PROBE_OPS_TEST_CLOSEOUT
- TEST_RELOCATION_PLAN

## 3. 남은 HOLD

| 파일 | 상태 | 처리 방침 |
|---|---|---|
| close_2_more.py | untracked HOLD | 사용자 확인 후 처리 |
| eum_docs.py | untracked HOLD | EUM 자동화 참고 가이드, 사용자 확인 후 처리 |

## 4. 구조 리팩터링 착수 판정

- BLOCK_REFACTORING: 0
- UNKNOWN: 0
- local/origin/server: 일치
- server status: clean
- 판정: PASS

## 5. 구조 리팩터링 본작업 원칙

- 기능 변경 금지
- API 응답 key 변경 금지
- DB schema 변경 금지
- 운영 경로 변경 금지
- 권한 변경 금지
- 삭제 금지
- 파일 이동은 명시된 리팩터링 대상만 수행
- 각 단계는 테스트/quality gate/서버 ff-only 동기화 후 마감
- close_2_more.py, eum_docs.py는 stage 금지

## 6. 다음 단계 권장

1. 구조 리팩터링 Phase 1: layer boundary / import 정리
2. 구조 리팩터링 Phase 2: router/service/core 책임 분리
3. 구조 리팩터링 Phase 3: persistence/audit facade 정리
4. 구조 리팩터링 Phase 4: smoke/e2e/quality gate 최종 고정
