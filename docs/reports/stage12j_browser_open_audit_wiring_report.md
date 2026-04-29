# Stage 12J browser_open audit wiring report

## 1. 목적

Stage 12I-B 보고서에서 WARN으로 분류된 항목(`browser_open_*` audit event 7종이
실제 controlled smoke 경로에 wiring되지 않음)을 보완한다.

`local_agent/audit.py` 의 기존 `log_local_event()` (민감 키 자동 strip)을 재사용해
`open_url_readonly` 호출 흐름의 7종 이벤트를 기록하고, fixture + 실제 about:blank
smoke 로 회귀 검증한다.

---

## 2. 수정 파일

| 파일 | 수정 내용 | 판정 |
|---|---|---|
| `local_agent/browser_reader.py` | 7종 audit event wiring + `_categorize_url()` 헬퍼 추가. URL 원문은 `about:blank` 인 경우에만 audit 에 노출 | PASS |
| `tests/test_browser_open_observe_fixture.py` | autouse fixture로 audit 캡처 + `TestAuditWiring` 7개 신규 케이스 | PASS |
| `docs/reports/stage12j_browser_open_audit_wiring_report.md` | 신규 보고서 | PASS |
| `local_agent/audit.py` | 변경 없음 (기존 헬퍼 재사용) | PASS |
| `local_agent/web_reader.py` | 변경 없음 | PASS |
| approval / admin-web / policy yaml / package.json | 변경 없음 | PASS |

---

## 3. audit event wiring

| event | 발생 조건 | fixture 검증 | 실제 smoke 검증 |
|---|---|:---:|:---:|
| `browser_open_requested` | 호출 진입 직후 | ✅ | ✅ |
| `browser_open_dry_run_checked` | URL/`allow_about_blank` 게이트 통과 검사 직후 | ✅ | ✅ |
| `browser_open_started` | playwright factory 확보 후 실제 page open 직전 | ✅ | ✅ |
| `browser_open_observed` | title/url/html 수집 후 (counts·login_hint 메타만) | ✅ | ✅ |
| `browser_open_completed` | 정상 반환 직전 | ✅ | ✅ |
| `browser_open_blocked` | URL validation 실패 시 (예: `URL_SCHEME_BLOCKED`, opt-in 없는 about:blank) | ✅ | n/a (의도적 미발생) |
| `browser_open_failed` | factory/page 예외 또는 `BROWSER_DEPENDENCY_MISSING` | ✅ | n/a (의도적 미발생) |

성공 경로(5종)는 실제 about:blank smoke에서 순서대로 기록되었고, 차단/실패 2종은
fixture 케이스(`test_url_scheme_blocked_emits_blocked`, `test_about_blank_without_optin_emits_blocked`,
`test_factory_exception_emits_failed`)에서 정상 발화 확인.

---

## 4. audit payload 안전성

| 금지 필드 | 기록 여부 | 판정 |
|---|:---:|---|
| cookie / cookies | 없음 | PASS — `browser_reader` 가 audit payload 에 cookie 키 부재. `audit._strip_sensitive` 도 추가 방어 |
| session / session_token | 없음 | PASS |
| token / access_token / refresh_token | 없음 | PASS |
| Authorization / auth | 없음 | PASS |
| password / passwd / pwd | 없음 | PASS |
| localStorage / sessionStorage | 없음 | PASS |
| page content / html | 없음 | PASS — `browser_open_observed` 는 `title_len`, `pages_observed_count`, `modal_candidates_count`, `html_truncated`, `login_required_hint` 만 기록 (본문 미포함) |
| 외부 URL 호스트/경로/쿼리 | 없음 | PASS — `_categorize_url` 로 카테고리화 (`public_https` 등). `url` 키는 `about:blank` 일 때만 추가 |

`test_external_url_audit_does_not_log_full_url` 에서 `example.com`, `secret-path`,
`key=abc` 가 audit 어디에도 부재함을 검증.

---

## 5. about:blank 실제 smoke 회귀

| 항목 | 결과 |
|---|---|
| 실행 URL | `about:blank` |
| final_url (`current_url`) | `about:blank` |
| title | `""` (blank page 정상) |
| status_category | OK (`result["ok"] == True`) |
| pages_observed_count | 1 |
| error_category | 없음 |
| audit event 기록 | 5종 (`browser_open_requested` → `dry_run_checked` → `started` → `observed` → `completed`) 순서대로 기록 |
| audit url_category | `about_blank` |
| audit url 노출 | `about:blank` 만 (외부 호스트 미노출) |
| audit 민감 키 누출 | none |
| timestamp | 2026-04-29T00:02:32.186154+00:00 |
| secret 출력 | 없음 |

실행 방식: 인라인 `python -c '...'` one-off (파일 미저장) — `local_agent.audit.log_local_event` 를
`patch.object` 로 캡처하면서 동시에 원본 호출도 위임 → 디스크에도 정상 기록 (`~/.haehan_agent/audit.jsonl`,
repo 외부 경로) 후 캡처 데이터로 검증.

---

## 6. 안전 조건 유지

| 조건 | 결과 |
|---|---|
| about:blank exact match 유지 | PASS |
| about:* 전체 허용 없음 | PASS (about:srcdoc/config/blank?x=1/blanket 등 모두 BLOCK 유지) |
| 위험 scheme 차단 유지 | PASS (file/javascript/data/ftp/ssh) |
| 외부 URL 접근 없음 | PASS (실제 smoke 는 about:blank 1회만) |
| HTTP/POST 없음 | PASS |
| screenshot 없음 | PASS |
| DOM 입력/클릭 없음 | PASS (`browser_reader` 소스 회귀 방어 유지) |
| cookie/session/storage 접근 없음 | PASS (`_RaiseOnAccess` fixture 통과) |
| 다른 앱 접근 없음 | PASS |

---

## 7. 검증 결과

| 명령 | 결과 |
|---|---|
| `python scripts/check_local_agent_noexec_smoke.py` | Total 39 / PASS 37 / WARN 2 / FAIL 0 → **WARN exit 0** |
| `python -m py_compile local_agent/{browser_reader,web_reader,audit}.py tests/test_browser_open_observe_fixture.py` | **OK** |
| `pytest tests/test_browser_open_observe_fixture.py` | **48 passed, 1 skipped, 0 failed** (12H 41 + 12J 7 신규) |
| `pytest tests/test_local_agent_approval_fixture.py` | **28 passed** (회귀 없음) |
| actual about:blank smoke | **PASS** (5종 audit + 안전 필드만 기록) |
| git diff 범위 | `local_agent/browser_reader.py`, `tests/test_browser_open_observe_fixture.py`, `docs/reports/stage12j_browser_open_audit_wiring_report.md` 3파일만 |

---

## 8. 다음 단계 제안

권장 다음 단계:

**Stage 12K — local-agent browser open/observe closeout**
- 12A~12J 마감 보고서
- audit event 카탈로그를 `audit_logger.EVENT_TYPES` 와 통합 검토 (현재는 local_agent 자체 audit)
- 또는 12K: 내부 테스트 URL controlled open/observe 계획(외부 사이트는 여전히 금지)

---

## 9. 금지 작업 준수 확인

- 서버 접속: 없음
- docker 실행: 없음
- 외부 URL: 없음
- HTTP/POST: 없음
- screenshot: 없음
- DOM 입력/클릭: 없음
- cookie/session/storage: 없음
- 다른 앱 접근: 없음
- secret 출력: 없음
