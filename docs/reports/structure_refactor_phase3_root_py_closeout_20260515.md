# Structure Refactor Phase 3 Root Python Closeout
**날짜**: 2026-05-15
**HEAD**: 6fff4c8 (ROOT_FLASK_LEGACY_RESIDUAL_LOCK_01 완료 기준)

---

## 1. 기준선

- HEAD: `6fff4c8`
- local/origin/server 일치: YES
- server status: clean
- modified: 0
- deleted: 0
- untracked HOLD: close_2_more.py, eum_docs.py

---

## 2. 완료한 Phase 3 정리

| 단계 | 작업 | commit |
|---|---|---|
| BLOCK_FIX_01 | CUsers...Hancom root draft → git index 제거 | `407d5f9` |
| ROOT_PROBE_OUTSIDE_REPO_EXEC_01 | run_local_agent_windows.py, tmp_policy_check.py, Hancom draft → repo 밖 백업 이동 | `baf785f` |
| ROOT_FLASK_RESIDUAL_STATUS_FIX_01 | tracked_residuals status "tracked" → "accepted" 수정 | `1e1e04b` |
| ROOT_TEST_RELOCATION_COMMIT_01 | test_blog_agent.py, test_browser_state.py, test_wait_login.py → tests/integration/manual/ | `d40e8c0` |
| ROOT_OPS_TOOL_RELOCATION_COMMIT_01 | check_audit.py → scripts/ops/check_audit.py | `1c56e32` |
| GENERIC_SITE_AUTOMATION_ARCHITECTURE_LOCK_01 | 범용 site_engine 설계 문서 고정 | `484f00b` |
| ROOT_ARCHIVE_EUM_COMMIT_01 | EUM standalone scripts 13건 → scripts/archive/eum_legacy/ | `6fff4c8` |

---

## 3. Active Flask root modules 유지 판정

| 파일군 | 유지 이유 | 후속 단계 |
|---|---|---|
| app.py | systemd ai-orchestrator-dashboard/monitor 서비스 ExecStart 진입점 | Flask→FastAPI migration 이후 이관 |
| dashboard.py, monitor.py | app.py에서 직접 참조되는 Flask 서비스 모듈 | 동일 |
| executor.py, models.py, policy_engine.py, risk_assessor.py | 핵심 업무 로직 — 현재 active | 동일 |
| approval_manager.py, whitelist_executor.py | 승인/실행 정책 | 동일 |
| telegram_notifier.py, logger.py, audit_logger.py | 알림/로깅 공통 모듈 | 동일 |
| task_store.py, logging_utils.py, security_utils.py | 저장소/보안 공통 | 동일 |
| inbox_router.py, tasks_router.py, webhooks_router.py | Flask route 정의 | 동일 |
| log_analyzer.py, inbox_store.py | 로그/수신함 분석 | 동일 |
| candidate_store.py, candidate_to_task.py, email_classifier.py | 후보 처리 파이프라인 | 동일 |
| email_task_approval.py, email_task_executor.py, email_task_store.py | 이메일 태스크 처리 | 동일 |
| hiworks_mail_reader.py, kakaowork_reader.py, message_classifier.py | 메시지 수신/분류 | 동일 |

**총 29건. 현재 운영 중인 systemd 서비스가 app.py를 직접 참조하므로 이 단계에서는 이동하지 않는다.**

---

## 4. HOLD

| 파일 | 상태 | 처리 방침 |
|---|---|---|
| close_2_more.py | untracked HOLD | 사용자 확인 후 처리 (내용 미확인) |
| eum_docs.py | untracked HOLD | EUM 참고 가이드, 사용자 확인 후 처리 |

---

## 5. 감사 결과 (Phase 3 완료 기준)

| 항목 | 값 | 판단 |
|---|---|---|
| BLOCK_REFACTORING | 0 | PASS |
| UNKNOWN | 0 | PASS |
| import cycle | 0 | PASS |
| consistency | ok | PASS |
| ROOT_PY_SCRIPT residual | accepted (Phase 3 CLOSED 명시) | PASS |
| FAT_SITE_ROUTER residual | accepted | PASS |
| root issues | 39건 (전체 WARN, 모두 Flask active module) | WARN 유지 |

---

## 6. root .py 정리 요약 (Phase 3 완료 기준)

| 분류 | 파일 수 | 처리 결과 |
|---|---|---|
| Hancom draft (오염 파일) | 1 | git index 제거 + repo 밖 이동 |
| probe/temp (외부 repo 이동) | 2 | repo 밖 백업 이동 |
| manual test 이관 | 3 | tests/integration/manual/ |
| ops 도구 이관 | 1 | scripts/ops/ |
| EUM legacy archive | 13 | scripts/archive/eum_legacy/ |
| Flask active root module | 29 | 유지 (서비스 진입점) |
| HOLD | 2 | 사용자 확인 대기 |

---

## 7. 다음 단계

```text
1. SITE_ENGINE_PHASE_B_INIT_01
   - scripts/site_engine/ 디렉터리 신설
   - profiles.py (SiteProfile), registry.py, audit.py 초안
   - 기존 site_registry.py 보존하며 wrapper 구조 전환

2. SITE_ENGINE_PHASE_C_EXECUTION_GATE_01
   - execution_gate.py 공통화
   - gate.py + 사이트별 gates.py 통합

3. SITE_ENGINE_PHASE_D_BROWSER_FORM_RESOLVER_01
   - form_resolver.py, adapters/browser.py 공통화
   - cdp_client 추상화, 사이트별 CDP 직접 호출 제거
```

**Flask→FastAPI 마이그레이션 완료 후 Flask active root module 29건 이관 별도 진행.**
