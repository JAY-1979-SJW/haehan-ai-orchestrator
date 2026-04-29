# Stage 12M internal test URL allowlist fixture report

## 1. 목적

Stage 12L 정책 문서를 코드로 고정한다.  
내부 테스트 URL controlled open/observe 의 allowlist (host/port/path/query/fragment/risky-keyword/path-traversal)
와 페이지 안전성 검사 (password/file input, form POST, textarea, contenteditable,
final_url escape) 를 fixture 로 검증한다.

실제 HTTP/브라우저/local-agent/서버는 실행하지 않는다.

---

## 2. 수정 파일

| 파일 | 수정 내용 | 판정 |
|---|---|---|
| `local_agent/internal_test_allowlist.py` | **신규** — `validate_internal_test_url()`, `analyze_internal_page_safety()`, 정책 상수 | PASS |
| `tests/test_internal_test_url_allowlist_fixture.py` | **신규** — 88 tests / 12 클래스 | PASS |
| `docs/reports/stage12m_internal_test_url_allowlist_fixture_report.md` | 신규 보고서 | PASS |
| `local_agent/browser_reader.py` / `web_reader.py` | 변경 없음 (기본 동작 무변경 — 호출자 명시 사용 시에만 동작) | PASS |
| approval / admin-web / policy yaml / package.json | 변경 없음 | PASS |

---

## 3. allowlist 기준

| 기준 | 값 | 판정 |
|---|---|---|
| scheme | `http` only | PASS |
| host | `localhost` 또는 `127.0.0.1` (`ALLOWED_HOSTS` frozenset, exact 매칭) | PASS |
| port | 호출자가 지정한 단일 정수 포트 (인자 `allowed_port`, 누락/wrong/0 모두 BLOCK) | PASS |
| path | `/__haehan_test__/readonly` prefix만 (기본값, 호출자 변경 가능) | PASS |
| query | 빈 문자열만 통과 (`URL_QUERY_BLOCKED`) | PASS |
| fragment | 빈 문자열만 통과 (`URL_FRAGMENT_BLOCKED`) | PASS |
| allow_private_network | 호출자 책임 — 본 게이트는 host=localhost/127.0.0.1 강제로 사실상 동등한 효과 | PASS |
| IPv6 `[::1]` | **BLOCK 유지** (12L에서 보류로 명시, 12N 이후 별도 결정) | PASS |

---

## 4. 허용 URL fixture

| URL | 기대 | 결과 |
|---|---|---|
| `http://localhost:9876/__haehan_test__/readonly` | ALLOW | PASS |
| `http://127.0.0.1:9876/__haehan_test__/readonly` | ALLOW | PASS |
| `http://localhost:9876/__haehan_test__/readonly/page1.html` | ALLOW (subpath) | PASS |

---

## 5. 차단 URL fixture

| URL/패턴 | 기대 | 결과 |
|---|---|---|
| port 누락 (`http://localhost{PFX}`) | URL_PORT_BLOCKED | PASS |
| wrong port (80/8080/3000/5000/9877) | URL_PORT_BLOCKED | PASS |
| wrong path (`/`, `/other`, `/__haehan_test__`, `/__haehan_test__/write`) | URL_PATH_BLOCKED | PASS |
| query (`?token=…`, `?session=…`, `?password=…`, `?key=…`, `?x=1`) | URL_QUERY_BLOCKED | PASS |
| fragment (`#frag`) | URL_FRAGMENT_BLOCKED | PASS |
| path traversal (`/..`, `/../admin`, `/sub/../../etc`, `%2e%2e/`, `%2e./`, `.%2e/`) | URL_PATH_TRAVERSAL | PASS |
| `0.0.0.0` | URL_HOST_BLOCKED | PASS |
| RFC1918 (192.168/16, 10/8, 172.16/12, 169.254/16) | URL_HOST_BLOCKED | PASS |
| `*.local` (`test.local`, `service.local`) | URL_HOST_BLOCKED | PASS |
| `[::1]` IPv6 loopback | URL_HOST_BLOCKED | PASS |
| 외부 도메인 (`example.com`) | URL_HOST_BLOCKED | PASS |
| 운영 도메인 (`haehan-ai.kr`) | URL_HOST_BLOCKED | PASS |
| 위험 scheme (`https`, `file`, `javascript`, `data`, `ftp`, `ssh`) | URL_SCHEME_BLOCKED 등 | PASS |
| `about:blank` (12I 게이트 영역 — internal_test 게이트는 허용 안 함) | URL_*_BLOCKED | PASS |
| 위험 경로 키워드 18종 (login/signin/sign-in/auth/oauth/sso/payment/checkout/order/delete/remove/withdraw/cancel/admin/role/permission/grant/revoke) | URL_RISKY_KEYWORD | PASS |

---

## 6. 페이지 차단 패턴 fixture

| 패턴 | 기대 | 결과 |
|---|---|---|
| password input (`<input type="password">`) | PASSWORD_INPUT_PRESENT | PASS |
| login/auth path | URL_RISKY_KEYWORD (URL 단계에서 차단) | PASS |
| form POST (`<form method="post">`) | FORM_POST_PRESENT | PASS |
| form GET (`<form method="get">`, password 없음) | safe | PASS |
| form with has_password=True | PASSWORD_INPUT_PRESENT | PASS |
| file input (`<input type="file">`) | FILE_INPUT_PRESENT | PASS |
| `<textarea>` | TEXTAREA_PRESENT | PASS |
| `contenteditable=` 포함 HTML | CONTENTEDITABLE_PRESENT | PASS |
| payment/delete/admin path | URL_RISKY_KEYWORD (URL 단계) | PASS |
| allowlist 밖 final_url (`https://example.com/x`, `192.168.0.1`, wrong port, query 포함) | FINAL_URL_OUTSIDE_ALLOWLIST | PASS |

---

## 7. audit payload 안전성

| 항목 | 결과 | 판정 |
|---|---|---|
| query/fragment 미기록 | validate 결과 dict 키에 `query`/`fragment` 부재 | PASS |
| cookie/session/token 미기록 | 결과 dict 키에 부재 (`test_validate_result_does_not_include_query_or_fragment`) | PASS |
| Authorization 미기록 | 부재 | PASS |
| password/storage/html/body 미기록 | 부재 | PASS |
| BLOCK 응답에 secret 원문 미노출 | `?token=SECRETVAL` 입력 시 결과 어디에도 `SECRETVAL` 부재 (`test_block_result_does_not_include_url_original`) | PASS |
| `url_category="internal_test"` 기록 | PASS | PASS |
| `allowlist_name="internal_test_default"` 기록 | PASS | PASS |
| `blocked_reason` 키 노출 (페이지 안전성) | `analyze_internal_page_safety` 가 사유 반환 (PASSWORD_INPUT_PRESENT 등) | PASS |

---

## 8. 검증 결과

| 명령 | 결과 |
|---|---|
| `python scripts/check_local_agent_noexec_smoke.py` | Total 39 / PASS 37 / WARN 2 / FAIL 0 → **WARN exit 0** |
| `python -m py_compile local_agent/{internal_test_allowlist,browser_reader,web_reader}.py tests/{test_internal_test_url_allowlist_fixture,test_browser_open_observe_fixture}.py` | **OK** |
| `pytest tests/test_internal_test_url_allowlist_fixture.py -v` | **88 passed in 0.15s** |
| `pytest tests/test_browser_open_observe_fixture.py` | **48 passed, 1 skipped** (12J 회귀, 변동 없음) |
| `pytest tests/test_local_agent_approval_fixture.py` | **28 passed** (회귀 없음) |
| git diff 범위 | `local_agent/internal_test_allowlist.py`, `tests/test_internal_test_url_allowlist_fixture.py`, `docs/reports/stage12m_internal_test_url_allowlist_fixture_report.md` 3파일만 |

---

## 9. 다음 단계 제안

권장 다음 단계:

**Stage 12N — 내부 테스트 URL 실제 smoke 지시문 작성**
- 사전 조건:
  - 내부 read-only fixture page 준비 (정적 HTML, mutation 요소 부재)
  - allowed_port / allowed_path 확정
  - `browser_reader.open_url_readonly` 에 `internal_test_allowlist` wiring 옵션 추가
  - audit event 7종 + `url_category="internal_test"` 기록 확인 경로
- 실행 범위:
  - 사전 fixture 통과 확인 → 1회 open → audit 5종 success path 확인
- **단, 대표님 별도 승인 후 실행**

---

## 10. 금지 작업 준수 확인

- 서버 접속: 없음
- docker 실행: 없음
- local-agent 실행: 없음
- 브라우저 실행: 없음
- 실제 HTTP 요청: 없음
- 실제 POST: 없음
- 외부 URL: 없음
- 다른 앱 접근: 없음
- secret 출력: 없음

---

## 11. 최종 판정

**PASS**

내부 테스트 URL controlled observe 의 정책 게이트(11종 BLOCK 사유)와
페이지 안전성 검사(6종 BLOCK 사유)가 코드로 고정되었으며, 88개 fixture 로
검증되었다. 기본 동작은 무변경(호출자 명시 사용 시에만 활성)으로 기존
about:blank / 일반 URL 경로에 회귀 없음.
