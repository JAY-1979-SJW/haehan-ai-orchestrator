# Stage 12N internal test URL actual smoke report

## 1. 승인 확인

- 승인 문구: `Stage 12N 내부 테스트 URL 실제 smoke 승인`
- 승인 여부: **확인됨** (대표님이 직접 메시지로 명시)

---

## 2. 목적

내부 테스트 URL controlled open/observe 의 첫 실제 smoke.  
임시 localhost HTTP 서버에서 정적 read-only fixture page 1개를 GET 으로 관찰하고,
allowlist gate / page safety / audit event 7종 wiring 의 end-to-end 동작을 검증한다.

---

## 3. 사전 검증

| 항목 | 결과 |
|---|---|
| HEAD | `d5644a5` (= origin/master) |
| working tree | clean |
| noexec smoke | Total 39 / PASS 37 / WARN 2 / FAIL 0 → **WARN exit 0** |
| allowlist fixture (`tests/test_internal_test_url_allowlist_fixture.py`) | **88 passed** |
| browser fixture (`tests/test_browser_open_observe_fixture.py`) | **48 passed, 1 skipped** |
| approval fixture (`tests/test_local_agent_approval_fixture.py`) | **28 passed** |
| 합계 | **164 passed, 1 skipped, 0 failed** |
| py_compile | OK (`internal_test_allowlist.py`, `browser_reader.py`, `web_reader.py`) |

---

## 4. fixture 서버

| 항목 | 결과 |
|---|---|
| bind host | `127.0.0.1` (loopback only, 외부 인터페이스 미바인드) |
| port | `39876` (단일 임시 포트) |
| path | `/__haehan_test__/readonly` (그 외 path 는 404) |
| HTTP method | GET 만 처리, POST 는 405 Method Not Allowed 명시 차단 |
| HTML 본문 | 정적 — `<title>haehan internal test readonly</title>`, `<h1>` 1개, `<p>` 1개, `<ul><li>` 2개. **form/input/button/textarea/file/contenteditable/external script/img/link/meta refresh 모두 부재** |
| token/session/password/key query | 없음 |
| 서버 기동 방식 | Python `http.server.HTTPServer` + `threading.Thread(daemon=True)` 으로 인라인 one-off (임시 파일 미저장) |
| 서버 종료 여부 | `httpd.shutdown()` + `server_close()` + `thread.join()` → **`SERVER_THREAD_ALIVE: False`** 확인 |

---

## 5. 실제 smoke 결과

| 항목 | 값 |
|---|---|
| 실행 URL | `http://127.0.0.1:39876/__haehan_test__/readonly` |
| 사전 게이트 (`validate_internal_test_url`) | `ok=True`, `url_category="internal_test"`, `allowlist_name="internal_test_default"` |
| `open_url_readonly` opt-in | `allow_private_network=True`, `timeout_ms=10000` |
| final_url (`current_url`) | `http://127.0.0.1:39876/__haehan_test__/readonly` (allowlist 내부) |
| title | `haehan internal test readonly` |
| status_category | OK (`result["ok"] == True`) |
| pages_observed_count | 1 |
| page_structure counts | `{headings:1, links:0, buttons:0, inputs:0, forms:0, tables:0}` |
| html_truncated | False |
| login_required_hint | False |
| modal_candidates | 0 |
| error_category | 없음 |
| timestamp | `2026-04-29T00:35:45.591272+00:00` |
| 사후 안전성 (`analyze_internal_page_safety`) | `safe=True`, `blocked_reason=None` (final_url allowlist 재확인 통과) |

---

## 6. audit event

| event | 기록 여부 |
|---|---|
| `browser_open_requested` | ✅ |
| `browser_open_dry_run_checked` | ✅ |
| `browser_open_started` | ✅ |
| `browser_open_observed` | ✅ |
| `browser_open_completed` | ✅ |
| `browser_open_blocked` | 해당 없음 (의도적 미발생) |
| `browser_open_failed` | 해당 없음 (의도적 미발생) |

audit payload 민감 키 누출: `AUDIT_LEAK: none` — `cookie / session / token / password / authorization / localstorage / sessionstorage / html / content` 키 모두 부재.

기록 위치: `~/.haehan_agent/audit.jsonl` (repo 외부 경로, git 영향 없음).

---

## 7. 안전 조건 준수

| 조건 | 결과 |
|---|---|
| 외부 URL 접근 없음 | PASS — 127.0.0.1 만 호출, DNS 미사용 |
| 운영 서비스 접근 없음 | PASS |
| HTTP POST 없음 | PASS — handler 도 POST 405 거절, 호출도 GET 1회 |
| screenshot 없음 | PASS |
| DOM 입력/클릭 없음 | PASS (`browser_reader._open_and_read` 는 goto/title/url/content 만 호출) |
| cookie/session/storage 접근 없음 | PASS — `cookies` / `evaluate` / `storage_state` 미호출, 결과 dict 키 부재 |
| password value 접근 없음 | PASS — fixture 페이지에 password input 자체 부재 |
| Authorization header 노출 없음 | PASS |
| secret 출력 없음 | PASS |
| 서버 접속 없음 (외부) | PASS |
| docker 실행 없음 | PASS |
| 다른 앱 접근 없음 | PASS |
| fixture 서버 종료 확인 | PASS (`SERVER_THREAD_ALIVE: False`) |
| working tree 잔여물 | **없음** (`git status --short` empty, 임시 파일 미저장) |

---

## 8. 다음 단계 제안

권장 다음 단계:

**Stage 12O — internal_test_allowlist 를 `browser_reader.open_url_readonly` 에 정식 wiring**
- 현재는 호출자가 `validate_internal_test_url` 를 사전 호출해야 함
- `open_url_readonly` 에 `internal_test_port: int | None = None` opt-in 파라미터 추가 검토
- 또는 12O를 controlled browser 마감 보고로 종결

---

## 9. 최종 판정

**PASS**

- 승인 문구 확인 ✅
- 사전 검증 164 passed / 0 failed
- 내부 테스트 URL 1개만 실행 (`http://127.0.0.1:39876/__haehan_test__/readonly`)
- allowlist 통과, final_url allowlist 내부, 사후 안전성 safe
- HTTP GET 관찰만 수행 (POST/screenshot/입력/클릭 없음)
- audit 성공 경로 5종 기록, 민감 키 누출 0
- fixture 서버 정상 종료, working tree clean
