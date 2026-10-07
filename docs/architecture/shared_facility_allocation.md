# 공용시설 배정표 (Shared Facility Allocation)

고정일: 2026-05-15  
작업 ID: APP_FOUNDATION_DOMAIN_ROOM_ALLOCATION_01  
상태: LOCKED

---

## 1. Action Registry (행동 등록소)

**담당 책임:** 모든 사이트 행동(action)의 등록, 조회, 검색  
**파일:** `scripts/site_engine/registry.py`

| 항목 | 내용 |
|------|------|
| 접근 가능 | 모든 Domain Unit (읽기 전용), site_engine 내부 |
| 금지된 접근 | Domain Unit에서 registry를 통하지 않고 직접 action 실행 |
| 저장 위치 | 메모리 레지스트리 (DB 없음) |
| gate/test 위치 | `tests/test_action_*.py`, `tests/test_site_engine_registry.py` |
| 감사로그 | 등록/호출 이벤트 기록 |

---

## 2. Approval Gate (승인 게이트)

**담당 책임:** 사용자 승인 요청, 승인 기록, 승인 상태 관리  
**파일:** `scripts/site_engine/execution_gate.py`, `scripts/site_engine/site_types.py`

| 항목 | 내용 |
|------|------|
| 접근 가능 | 모든 Domain Unit (승인 요청만), site_engine, local_agent |
| 금지된 접근 | Domain Unit에서 승인 우회, 승인 없이 EXECUTING 전이 |
| 저장 위치 | `data/approvals/` (승인자/시각/범위/유효기간 기록) |
| gate/test 위치 | `tests/test_browser_approval_*.py`, `tests/test_site_engine_execution_gate.py` |
| 감사로그 | 모든 승인/거부 이벤트 기록 (who/when/what/result) |

---

## 3. Permission Model (권한 모델)

**담당 책임:** 역할별 허용 행동 정의, gate decision 분류  
**파일:** `scripts/site_engine/site_types.py` (GateDecision), `docs/architecture/permission_approval_model.md`

| 항목 | 내용 |
|------|------|
| 접근 가능 | 모든 Domain Unit (읽기 전용) |
| 금지된 접근 | Domain Unit에서 GateDecision 임의 변경 |
| 저장 위치 | 코드 상수 (변경 시 테스트 FAIL) |
| gate/test 위치 | `tests/test_app_foundation_governance.py` |
| 감사로그 | 정책 변경 시 감사 필요 |

---

## 4. Workflow / Task Queue (작업흐름 / 태스크 큐)

**담당 책임:** 16개 워크플로우 상태 관리, 상태 전이, 큐 처리  
**파일:** `scripts/site_engine/workflow_runner.py`, `scripts/hiworks/workflows.py` 등

| 항목 | 내용 |
|------|------|
| 접근 가능 | 모든 Domain Unit (상태 전이 요청), site_engine |
| 금지된 접근 | 승인 없이 DRAFT_CREATED→EXECUTING 전이, USER_DIRECT→EXECUTING 전이 |
| 저장 위치 | `data/tasks/` (task 상태 기록) |
| gate/test 위치 | `tests/test_site_engine_workflow_runner.py` |
| 감사로그 | 모든 상태 전이에 who/when/what/result 기록 |

---

## 5. Local Agent Gateway (로컬 에이전트 게이트웨이)

**담당 책임:** 로컬 PC 작업 라우팅, 로컬-서버 브리지  
**파일:** `scripts/local_agent/router.py`, `scripts/local_agent/` 전체

| 항목 | 내용 |
|------|------|
| 접근 가능 | LOCAL_AGENT_REQUIRED 결정을 받은 모든 Domain Unit |
| 금지된 접근 | 서버 사이드에서 직접 외부 사이트 브라우저 실행 |
| 저장 위치 | 로컬 PC (서버 DB 없음) |
| gate/test 위치 | `tests/test_local_agent_*.py` |
| 감사로그 | 로컬 작업 시작/완료/실패 기록 |

---

## 6. Browser Execution Gateway (브라우저 실행 게이트웨이)

**담당 책임:** 브라우저 자동화 실행 조율, SERVER_BROWSER_GUARD 적용  
**파일:** `scripts/site_engine/execution_gate.py`, `scripts/site_engine/ai_orchestrator.connectors.g2b/`

| 항목 | 내용 |
|------|------|
| 접근 가능 | LOCAL_AGENT_REQUIRED, SERVER_BROWSER_ALLOWED (비금지 사이트만) |
| 금지된 접근 | 금지 사이트(gabia/g2b/hiworks/eum/nts/customs)로 서버 사이드 브라우저 |
| 저장 위치 | 세션 없음, 스냅샷만 `data/manual_visits/` |
| gate/test 위치 | `tests/test_app_foundation_p1_gates.py`, `tests/test_site_engine_execution_gate.py` |
| 감사로그 | 브라우저 실행/종료/결과 기록 |

---

## 7. Evidence Store (증거 저장소)

**담당 책임:** 업무 수행 증거 파일 보존 (read-only 원칙)  
**파일:** `data/evidence/` 또는 `data/{domain}/evidence/`

| 항목 | 내용 |
|------|------|
| 접근 가능 | 모든 Domain Unit (쓰기: 증거 저장만) / 조회: read-only |
| 금지된 접근 | 증거 삭제, 원본 수정 |
| 저장 위치 | `data/evidence/`, `data/{domain}/evidence/` |
| gate/test 위치 | `tests/test_server_action_evidence_store_20260509.py` |
| 감사로그 | 저장 이벤트 기록 |

---

## 8. Report Store (리포트 저장소)

**담당 책임:** 운영 리포트, 분석 결과물 저장  
**파일:** `data/reports/`, `docs/reports/`

| 항목 | 내용 |
|------|------|
| 접근 가능 | 모든 Domain Unit (쓰기: 리포트 저장) |
| 금지된 접근 | 리포트 원본 삭제 |
| 저장 위치 | `data/reports/{domain}/` |
| gate/test 위치 | 감사 스크립트 |
| 감사로그 | 생성 이벤트 기록 |

---

## 9. Audit Log (감사 로그)

**담당 책임:** 모든 작업 이벤트 실시간 기록  
**파일:** `data/logs/app.log`, `data/cdp.db`

| 항목 | 내용 |
|------|------|
| 접근 가능 | 모든 레이어 (쓰기), 운영자 (읽기) |
| 금지된 접근 | 감사 로그 삭제, 위조 |
| 저장 위치 | `data/logs/app.log` (RotatingFileHandler), `data/cdp.db` |
| gate/test 위치 | `tests/test_realtime_audit.py` |
| 감사로그 | 자기 자신이 감사 로그 |

---

## 10. Admin Ops Center (운영 관리 센터)

**담당 책임:** layer audit, quality gate, governance audit 실행  
**파일:** `scripts/ops/` 전체

| 항목 | 내용 |
|------|------|
| 접근 가능 | 운영자 (CI/CD), 관리자 |
| 금지된 접근 | Domain Unit에서 직접 audit 스크립트 호출 (역방향 금지) |
| 저장 위치 | `data/codebase_layer_audit_latest.json`, `data/app_foundation_governance_audit_latest.json` |
| gate/test 위치 | `tests/test_codebase_layer_audit.py`, `tests/test_app_foundation_governance.py` |
| 감사로그 | 게이트 실행 결과 기록 |

---

## 11. Notification Center (알림 센터)

**담당 책임:** 사용자 알림 발송 (Telegram, Kakao, 메일)  
**파일:** `scripts/kakao/`, 알림 관련 스크립트

| 항목 | 내용 |
|------|------|
| 접근 가능 | Workflow 레이어 (알림 요청), 운영자 |
| 금지된 접근 | Domain Unit에서 직접 알림 발송 (Notification Center 경유 의무) |
| 저장 위치 | `data/notifications/` |
| gate/test 위치 | `tests/test_telegram_notifier.py`, `tests/test_kakao_webhooks.py` |
| 감사로그 | 발송 이벤트 기록 |

---

## 12. 공용시설 현황 요약

| 공용시설 | 파일 | 현황 | 감사로그 |
|---------|------|------|---------|
| Action Registry | `scripts/site_engine/registry.py` | ✅ | ✅ |
| Approval Gate | `scripts/site_engine/execution_gate.py` | ✅ | ✅ |
| Permission Model | `scripts/site_engine/site_types.py` | ✅ | ✅ |
| Workflow/Task Queue | `scripts/site_engine/workflow_runner.py` | ✅ | 부분 |
| Local Agent Gateway | `scripts/local_agent/router.py` | ✅ | 부분 |
| Browser Execution Gateway | `scripts/site_engine/ai_orchestrator.connectors.g2b/` | ✅ | ✅ |
| Evidence Store | `data/evidence/` | ❌ (미정) | ❌ |
| Report Store | `data/reports/` | 부분 | ❌ |
| Audit Log | `data/logs/app.log`, `data/cdp.db` | ✅ | ✅ |
| Admin Ops Center | `scripts/ops/` | ✅ | ✅ |
| Notification Center | `scripts/kakao/` | 부분 | 부분 |
