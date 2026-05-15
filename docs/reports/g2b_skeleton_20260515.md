# G2B 세대 골격 생성 보고서 (2026-05-15)

## 단계: SITE_ENGINE_PHASE_G_G2B_SKELETON_01

## 생성 파일

| 파일 | 유형 | 내용 |
|------|------|------|
| scripts/g2b/profile.py | 신규 | G2B 사이트 프로필 및 action 분류 정책 |
| scripts/g2b/gates.py | 신규 | 실행 판단 게이트 함수 집합 |
| scripts/g2b/validators.py | 신규 | 페이로드 검증기 |
| scripts/g2b/router.py | 보완 | skeleton 명령(status/gate/analysis-draft/submit-draft) 추가 |
| scripts/g2b/README.md | 신규 | 세대 운영 가이드 |
| tests/test_g2b_site_engine_skeleton.py | 신규 | 골격 검증 33개 테스트 |

## G2B 세대 구조 (9개 하위 집)

| 집 | gate 정책 |
|----|-----------|
| public-notice | READ_ONLY_ALLOWED |
| notice-detail | READ_ONLY_ALLOWED |
| attachment-download | LOCAL_AGENT_REQUIRED |
| openapi-collector | READ_ONLY_ALLOWED (별도 경계 유지) |
| login-restricted | LOCAL_AGENT_REQUIRED |
| bid-analysis | DRAFT_ALLOWED |
| bid-submit | USER_DIRECT_REQUIRED |
| e-sign | BLOCKED |
| evidence-report | READ_ONLY_ALLOWED |

## 테스트 결과

- G2B 신규 skeleton: 33 passed
- 공정표/warehouse/room/governance/P1: 287 passed
- site_engine: 149 passed
- Gabia: 52 passed
- layer audit pytest: 10 passed
- quality gate: errors=0, warnings=0

## 안전 확인

- 실제 G2B 접속: 없음
- 실제 로그인: 없음
- 실제 투찰: 없음
- 실제 전자서명: 없음
- OpenAPI collector 변경: 없음
- DB/schema 변경: 없음
- data/sessions 접근: 없음
- secret/env 출력: 없음
- 삭제/권한 변경: 없음
- 서버 재시작/배포: 없음
- HOLD stage: 없음

## 판정: PASS
