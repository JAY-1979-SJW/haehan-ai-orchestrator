# Stage 12H browser open/observe fixture report

## 1. 목적

Stage 12G에서 정의한 controlled browser open/observe 정책을 실제 실행 전 fixture 테스트로 고정한다.  
실제 Playwright/Chrome/local-agent/HTTP는 일절 실행하지 않으며, fake page object와
monkeypatch만 사용한다.

---

## 2. 수정 파일

| 파일 | 수정 내용 | 판정 |
|---|---|---|
| `tests/test_browser_open_observe_fixture.py` | 신규 — 31 tests (30 passed / 1 skipped / 0 failed) | PASS |
| `docs/reports/stage12h_browser_open_observe_fixture_report.md` | 신규 — 이 보고서 | PASS |
| `local_agent/*` (구현 코드) | 변경 없음 | PASS |
| `ai_orchestrator/*` (정책) | 변경 없음 | PASS |
| `admin-web/*` | 변경 없음 | PASS |
| `package.json` / lockfile | 변경 없음 | PASS |

---

## 3. 테스트 항목

| 항목 | 검증 방식 | 판정 |
|---|---|---|
| about:blank 허용 | `validate_url_for_readonly_open("about:blank")` 결과 — 현재는 보수적으로 `URL_SCHEME_BLOCKED`. 12I에서 별도 정책 게이트 신설 후 명시적 허용 예정. | PASS (보수 차단) |
| 외부 URL 차단 | `validate_url_for_readonly_open("https://example.com/")`는 통과 — 외부 차단은 정책 레이어 책임. URL validation 자체는 공개 http(s) 호스트 허용함을 명시 | PASS (분리 확인) |
| file/javascript/data URL 차단 | parametrize 6 패턴 → 모두 `URL_SCHEME_BLOCKED` 또는 `URL_NO_HOST` | PASS |
| `action_open_url` 위험 스킴 차단 | `webbrowser.open` mock → 호출 0건, `URL_SCHEME_NOT_ALLOWED` | PASS |
| medium/high/critical 차단 | URL 자체 검증 layer엔 risk 게이트 없음 — 12E에서 `policy.evaluate_request` critical 차단 검증 완료. 12H 범위 외(설계 분리) | 기 검증 (12E) |
| 승인 없는 dry_run=false 차단 | approval 토큰 발급/검증은 12E fixture(`test_local_agent_approval_fixture.py`)에서 검증 완료. 12H 범위 외 | 기 검증 (12E) |
| title/url 관찰 허용 | FakePage(title/url/html) → `result["title"]`, `result["current_url"]` 안전 필드만 노출 | PASS |
| cookie/session/storage 접근 차단 | FakePage/FakeContext의 `cookies`, `evaluate`, `storage_state`, `add_cookies` 속성을 `_RaiseOnAccess`로 설정 — 호출되면 즉시 AssertionError. 정상 종료 = forbidden API 미호출 | PASS |
| login/password 감지 차단 | password input HTML → `login_required_hint=True`, `login_reason=["password_input_detected"]` | PASS |
| password/hidden value 미수집 | "SECRET-PASSWORD-123", "HIDDEN-TOKEN-XYZ" 가 결과 직렬화에 부재 | PASS |
| POST 가능성 차단 | `inspect.getsource(browser_reader)`에 `.click(`, `.fill(`, `.press(`, `.evaluate(`, `.add_cookies(`, `.set_cookie(`, `.storage_state(`, `.accept_downloads` 부재 (정책 회귀 방어) | PASS |
| audit 불가 시 차단 | audit gate는 정책 레이어 책임. 12I에서 audit event 7종 적용 시 검증 예정 | 12I 예정 |
| 실제 browser/local-agent 실행 없음 | subprocess.run/Popen/os.system 패치 후 호출 0건. fake factory로 실제 playwright import 회피. dependency 미설치 시 `BROWSER_DEPENDENCY_MISSING` 반환(skipped — 환경에 playwright 설치됨) | PASS |

**테스트 총계: 31 / passed 30 / skipped 1 / failed 0**

---

## 4. 수집/금지 데이터 확인

| 구분 | 항목 | 판정 |
|---|---|---|
| 허용 | `final_url` (`current_url` ≤500자) | PASS — 결과 dict에 포함 |
| 허용 | `title` (≤300자) | PASS |
| 허용 | `status_category` (`html_truncated`, `login_required_hint` 등 메타 필드) | PASS |
| 금지 | cookie / session / token | PASS — 결과 직렬화 검증, 모듈 소스 검증 |
| 금지 | localStorage / sessionStorage | PASS — 결과 dict 키 부재 |
| 금지 | password value | PASS — `_NO_VALUE_INPUT_TYPES` + 직렬화 부재 검증 |
| 금지 | Authorization header | PASS — 결과 직렬화 검증 |

---

## 5. 검증 결과

| 명령 | 결과 |
|---|---|
| `python scripts/check_local_agent_noexec_smoke.py` | Total 39 / PASS 37 / WARN 2 / FAIL 0 → **WARN exit 0** |
| `python -m py_compile scripts/check_local_agent_noexec_smoke.py` | **OK** |
| `pytest tests/test_browser_open_observe_fixture.py -v` | **30 passed, 1 skipped in 0.11s** |
| git diff 범위 | `tests/test_browser_open_observe_fixture.py`, `docs/reports/stage12h_browser_open_observe_fixture_report.md` 만 변경 |

---

## 6. 한계

- 실제 브라우저는 실행하지 않음 (Playwright/Chromium 미기동)
- 실제 local-agent 프로세스는 실행하지 않음
- 실제 HTTP 요청은 수행하지 않음 (fake page는 `goto()` no-op, `content()` 정적 HTML)
- 실제 about:blank smoke는 다음 Stage 12I에서 별도 승인 후 수행
- audit event 7종(`browser_open_*`)은 아직 코드에 미존재 — 12I에서 실 호출 경로 추가 시 fixture 보강 예정
- risk gate / dry_run 토큰 게이트는 12E에서 별도 검증 완료, 12H는 URL/observation 레이어에 한정

---

## 7. 다음 단계 제안

권장 다음 단계:

**Stage 12I — about:blank controlled open/observe 실제 smoke**
- 사전 조건:
  - 12G 정책 게이트(allowlist에 `about:blank` 명시) 코드 반영
  - audit event 7종 (`browser_open_requested` … `browser_open_failed`) 도입
  - dry_run 기본값 True 강제 가드
- 실행 범위:
  - `about:blank` 1회 open → title/url 관찰 → close
  - audit event 7종 기록 확인
  - 결과에 cookie/session/token 부재 재확인
- **단, 대표님 승인 후 진행**

---

## 8. 금지 작업 준수 확인

- 서버 접속: 없음
- docker 실행: 없음
- local-agent 실행: 없음
- 브라우저 실행: 없음
- 실제 HTTP 요청: 없음
- 실제 POST: 없음
- 다른 앱 접근: 없음
- secret 출력: 없음

---

## 9. 최종 판정

**PASS**

controlled browser open/observe 정책의 URL/관찰/민감값 레이어가 fixture로 고정되었다.
risk/approval 게이트는 12E, audit event 7종은 12I 단계에서 보강 예정이다.
