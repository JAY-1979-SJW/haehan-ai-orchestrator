# Stage 12I-A about:blank policy gate report

## 1. 목적

Stage 12G 정책에서 `about:blank`을 controlled browser open 첫 후보로 정의했으나,
Stage 12H fixture 테스트에서 현재 `validate_url_for_readonly_open` 가
`about:blank`을 `URL_SCHEME_BLOCKED` 로 보수 차단함을 확인했다.

이번 단계에서는 호출자가 `allow_about_blank=True` 를 **명시할 때만** 정확히
`about:blank` 문자열을 read-only 관찰 후보로 통과시키는 opt-in 게이트를 추가한다.
기본 동작은 변경하지 않는다.

---

## 2. 기존 문제

| 항목 | 기존 상태 | 판정 |
|---|---|---|
| `about:blank` | `URL_SCHEME_BLOCKED` (12G 정책과 불일치) | 보정 필요 |
| 위험 scheme (file/javascript/data/ftp/ssh) | 차단 | 유지 |
| 외부 URL | URL validation 통과(첫 실행 정책상 호출자 책임) | 유지 |

---

## 3. 수정 파일

| 파일 | 수정 내용 | 판정 |
|---|---|---|
| `local_agent/web_reader.py` | `validate_url_for_readonly_open` 에 `allow_about_blank: bool = False` opt-in 파라미터 추가. True 일 때만 `strip().lower() == "about:blank"` 정확 일치 통과 | PASS |
| `local_agent/browser_reader.py` | `open_url_readonly` 에 동일 파라미터 추가, validate 호출에 전달 | PASS |
| `tests/test_browser_open_observe_fixture.py` | about:blank opt-in 정확 일치 + about:* 변종 차단 fixture 추가 (총 11개 신규) | PASS |
| `docs/reports/stage12ia_about_blank_policy_gate_report.md` | 신규 — 이 보고서 | PASS |
| approval/admin-web/policy yaml | 변경 없음 | PASS |

---

## 4. 정책 게이트

| URL | opt-in 미사용 | `allow_about_blank=True` | 판정 |
|---|---|---|---|
| `about:blank` | BLOCK (`URL_SCHEME_BLOCKED`) | **ALLOW** (`scheme="about"`, `about_blank=True`) | PASS |
| `About:Blank` / `ABOUT:BLANK` / `  about:blank  ` | BLOCK | ALLOW (case-insensitive + strip) | PASS |
| `about:srcdoc` | BLOCK | BLOCK | PASS |
| `about:config` | BLOCK | BLOCK | PASS |
| `about:newtab` | BLOCK | BLOCK | PASS |
| `about:blank?x=1`, `about:blank#frag`, `about:blank/extra`, `about:blanket`, `about: blank` | BLOCK | BLOCK | PASS |
| `file://...` | BLOCK | BLOCK | PASS |
| `javascript:...` | BLOCK | BLOCK | PASS |
| `data:...` | BLOCK | BLOCK | PASS |
| `ftp://...`, `ssh://...` | BLOCK | BLOCK | PASS |
| `http://localhost/`, `http://127.0.0.1/`, private IP | BLOCK (`URL_HOST_BLOCKED`) | BLOCK | PASS |
| `https://example.com/` (외부) | URL validation 통과 (첫 실행 정책상 호출자/정책 레이어 책임) | 동일 | PASS (분리) |

---

## 5. 안전 조건 유지

| 조건 | 결과 |
|---|---|
| 외부 URL 허용 확장 없음 | PASS — about:blank 외 게이트는 변경 없음 |
| 위험 scheme 허용 없음 | PASS — file/javascript/data/ftp/ssh 모두 BLOCK 유지 |
| medium/high/critical 완화 없음 | PASS — `policy.evaluate_request` 미수정 |
| approval 정책 완화 없음 | PASS — `approval.py` 미수정 |
| cookie/session/storage 차단 유지 | PASS — `_RaiseOnAccess` fixture 통과 |
| login/password 감지 유지 | PASS — `login_required_hint` fixture 통과 |
| POST성 동작 차단 유지 | PASS — `browser_reader` 소스에 `.click/.fill/.press/.evaluate/.add_cookies/.set_cookie/.storage_state/.accept_downloads` 부재 회귀 방어 |
| 실제 browser/local-agent 실행 없음 | PASS — fake factory만 사용, subprocess/playwright 실 호출 0건 |

---

## 6. 검증 결과

| 명령 | 결과 |
|---|---|
| `python scripts/check_local_agent_noexec_smoke.py` | Total 39 / PASS 37 / WARN 2 / FAIL 0 → **WARN exit 0** |
| `python -m py_compile local_agent/web_reader.py local_agent/browser_reader.py tests/test_browser_open_observe_fixture.py` | **OK** |
| `pytest tests/test_browser_open_observe_fixture.py -v` | **41 passed, 1 skipped, 0 failed** |
| `pytest tests/test_local_agent_approval_fixture.py -q` | **28 passed** (회귀 없음) |
| git diff 범위 | `local_agent/web_reader.py`, `local_agent/browser_reader.py`, `tests/test_browser_open_observe_fixture.py`, `docs/reports/stage12ia_about_blank_policy_gate_report.md` 4파일만 |

---

## 7. 다음 단계 제안

권장 다음 단계:

**Stage 12I-B — about:blank controlled open/observe 실제 smoke 지시문 작성**
- 사전 조건:
  - 호출자(action layer) 가 `allow_about_blank=True` 를 명시적으로 전달하도록 wiring
  - audit event 7종 (`browser_open_requested` … `browser_open_failed`) 도입
  - dry_run 기본값 True 강제 가드
- 실행 범위:
  - `about:blank` 1회 open → title/url 관찰 → close
  - 결과에 cookie/session/token 부재 재확인
- **단, 대표님 승인 후 실제 실행**

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
