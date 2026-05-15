# Local Agent On-Demand Controller 보고서 (2026-05-15)

## 단계: LOCAL_AGENT_ON_DEMAND_CONTROLLER_01

## 생성 파일

| 파일 | 유형 | 내용 |
|------|------|------|
| scripts/local_agent/controller.py | 신규 | start/status/stop/cleanup |
| scripts/local_agent/status_store.py | 신규 | 상태 파일/lock 읽기쓰기 |
| scripts/local_agent/process_guard.py | 신규 | stale 감지, dry_run cleanup |
| scripts/local_agent/README.md | 신규 | 운영 가이드 |
| docs/architecture/local_agent_on_demand_controller.md | 신규 | 정책 문서 |
| tests/test_local_agent_on_demand_controller.py | 신규 | 18개 테스트 |
| docs/reports/local_agent_on_demand_controller_20260515.md | 신규 | 본 보고서 |

## 운영 정책

| 항목 | 정책 |
|------|------|
| 상시 데몬 | 금지 |
| AI on/off | 작업 단위 start/stop |
| 승인 조건 | LOCAL_AGENT_REQUIRED / APPROVAL_REQUIRED |
| BLOCKED | start 거부 |
| USER_DIRECT_REQUIRED | start 거부 |
| 승인 만료 | start 거부 |
| idle timeout | 기본 1800초 |
| stale cleanup | dry_run=True 기본 |
| session/cookie/token | 기록/접근 금지 |
| 서버 사이드 브라우저 | 금지 |

## 테스트/게이트

- local_agent 테스트: 18 passed ✅
- P1/warehouse/room/governance/site_engine: 222 passed ✅
- layer audit: 10 passed ✅
- quality gate: errors=0, warnings=0 ✅

## 판정: PASS
