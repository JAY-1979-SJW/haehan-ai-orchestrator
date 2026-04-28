# Stage 12E approval fixture report

## 1. 목적

실제 local-agent 실행 없이 approval 상태 전이와 안전 조건을 fixture 기반으로 검증한다.  
대상: `ai_orchestrator/approval.py`, `ai_orchestrator/task_state.py`, `ai_orchestrator/policy.py`

---

## 2. 수정 파일

| 파일 | 수정 내용 | 판정 |
|---|---|---|
| `tests/test_local_agent_approval_fixture.py` | 신규 — 28개 fixture 테스트 | PASS |
| `docs/reports/stage12e_approval_fixture_report.md` | 신규 — 이 보고서 | PASS |
| `ai_orchestrator/approval.py` | 변경 없음 | PASS |
| `ai_orchestrator/local_agent_router.py` | 변경 없음 | PASS |
| `admin-web/` | 변경 없음 | PASS |
| `package.json` / lockfile | 변경 없음 | PASS |

---

## 3. 테스트 항목

| 항목 | 검증 방식 | 판정 |
|---|---|---|
| waiting_approval approve | `_seed_token(status="issued")` → `approve_token()` → status == "approved" | PASS |
| waiting_approval reject | `_seed_token(status="issued")` → `reject_token()` → status == "rejected" | PASS |
| invalid token_id 차단 | 존재하지 않는 uuid → `approve_token()` → status == "not_found" | PASS |
| token 재사용 차단 | `status="approved"` 토큰 재시도 → status == "already_used" | PASS |
| 권한 부족 차단 | role="viewer" / "unknown_role" → status == "forbidden" | PASS |
| critical 정책 유지 | `policy.evaluate_request()` → `result.allowed is False` + blocked_reasons에 "critical" 포함 | PASS |
| audit 기록 | `approve_token()` / `reject_token()` 후 tmp JSONL 파일에 `token_approved` / `token_rejected` 이벤트 기록 확인 | PASS |
| 실제 action 미실행 | `subprocess.run`, `subprocess.Popen`, `os.system` 패치 후 실행 여부 확인 — 0건 | PASS |

**테스트 총계: 28개 / PASS 28개 / FAIL 0개**

---

## 4. 12D WARN 처리

| 항목 | 처리 | 판정 |
|---|---|---|
| `audit` marker in `approval.py` | **B안 — 선택 WARN 유지.** `approval.py`는 `_append_event`(자체 JSONL)만 사용. 감사 이벤트(`log_event`)는 `local_agent_router.py` 레이어에서 호출. "audit" 문자열이 없어도 감사는 실제 동작 중. 검사 기준 약화 없이 WARN 유지. | WARN (선택) |
| `preview` marker in `local_agent_router.py` | **B안 — 선택 WARN 유지.** 라우터에는 `dry_run` 키워드만 존재하며 `preview` 단어는 미구현 또는 미사용 marker. 위험 차단 기능과 무관하므로 검사 기준 유지, WARN 허용. | WARN (선택) |

스크립트(`check_local_agent_noexec_smoke.py`) 변경 없음.

---

## 5. 검증 결과

| 명령 | 결과 |
|---|---|
| `python scripts/check_local_agent_noexec_smoke.py` | Total: 39  PASS: 37  WARN: 2  FAIL: 0  →  **WARN exit 0** |
| `python -m py_compile scripts/check_local_agent_noexec_smoke.py` | **OK** |
| `pytest tests/test_local_agent_approval_fixture.py -v` | **28 passed in 0.24s** |
| git diff 범위 | `tests/test_local_agent_approval_fixture.py`, `docs/reports/stage12e_approval_fixture_report.md` 만 변경 |

---

## 6. 한계

- 실제 approve/reject HTTP POST는 수행하지 않음
- 실제 capture/cancel POST는 수행하지 않음
- 실제 local-agent와 브라우저는 실행하지 않음
- 이 테스트는 상태 전이/정책 fixture 검증이며 E2E 대체가 아님
- `_load_store` / `_load` 를 no-op 패치하여 파일 기반 재생 로직은 테스트 범위 외
- rate limit 은 `clear_rate_store()` 로 초기화하여 각 테스트 독립 실행 보장

---

## 7. 다음 단계 제안

권장 다음 단계:

- **Stage 12F: approval UI 서버 반영 후 마감 보고**  
  Stage 12B/12C에서 추가된 approve/reject UI를 운영 서버에 배포하고 Stage 12 전체 클로즈아웃 보고서 작성.

또는

- **Stage 12F: local-agent controlled browser open/observe dry-run 설계**  
  실제 브라우저 제어 없이 dry-run 관찰 시나리오 설계.

---

## 8. 금지 작업 준수 확인

- 서버 접속: **없음**
- docker 실행: **없음**
- local-agent 실행: **없음**
- 브라우저 실행: **없음**
- 실제 POST: **없음**
- DB 접속: **없음**
- 다른 앱 접근: **없음**
- secret 출력: **없음**
