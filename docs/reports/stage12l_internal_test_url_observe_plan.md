# Stage 12L internal test URL observe plan

## 1. 목적

`about:blank` 다음 단계로, 내부 테스트 URL controlled open/observe 의
허용 범위와 차단 조건을 사전 정의한다. 이 문서는 설계만 수행하며,
실제 내부 서버 기동/브라우저 실행/HTTP 요청은 전혀 하지 않는다.

기 구현 컨텍스트:
- `local_agent/web_reader.py::validate_url_for_readonly_open` — 기본은 `localhost`/사설 IP를 `URL_HOST_BLOCKED` 로 차단. `allow_private_network=True` opt-in 시에만 통과.
- `local_agent/browser_reader.py::open_url_readonly` — `allow_private_network` / `allow_about_blank` 두 opt-in 게이트 존재.
- `_categorize_url()` — audit에 외부 host 누출 방지용 카테고리 분류.
- `browser_open_*` audit event 7종 wiring 완료 (Stage 12J).

---

## 2. 현재 기준

| 항목 | 상태 | 판정 |
|---|---|---|
| about:blank actual smoke | 완료 (Stage 12I-B / 12J 회귀) | PASS |
| browser_open audit | 7종 wiring 완료 (Stage 12J) | PASS |
| `allow_private_network` opt-in | 코드 존재, 미사용 | 사용 대기 |
| 외부 URL | 금지 | PASS |
| 내부 테스트 URL | 미실행 | **계획 대상** |

origin/master 최신: `3c50d58`

---

## 3. 허용 URL 후보

| 항목 | 허용 여부 | 기준 |
|---|---:|---|
| `localhost` | 조건부 허용 | `allow_private_network=True` + 명시 포트 + 명시 path + read-only fixture page 한정 |
| `127.0.0.1` | 조건부 허용 | 동일 조건 (IPv4 loopback) |
| `[::1]` (IPv6 loopback) | 보류 | 12M에서 별도 결정 |
| `0.0.0.0` | **금지** | 모호한 binding, allowlist 회피 위험 |
| 사설망 (10/8, 172.16/12, 192.168/16) | **금지** | 같은 네트워크의 다른 서비스로 오접근 위험 |
| `*.local` (mDNS) | **금지** | 호스트 이름 충돌·로컬 네트워크 노출 |
| 공인 IP / 외부 도메인 | **금지** | 12L 범위 외 |
| 운영 서비스 URL (`*.haehan.*` 등) | **금지** | 운영 데이터 노출 위험 |
| 로그인/인증 페이지 | **금지** | password/cookie 위험 |
| 인증 필요 페이지 | **금지** | 토큰/세션 노출 위험 |
| POST/form 페이지 | **금지** | mutation 위험 |
| 파일 업로드/다운로드 페이지 | **금지** | 디스크 변경 위험 |
| 개인정보/민감정보 표시 페이지 | **금지** | 본문 노출 위험 |

---

## 4. allowlist 기준

| 기준 | 값 |
|---|---|
| scheme | `http` only (`https` 는 내부 self-signed 허용 안 함, 별도 검토) |
| host | `localhost` 또는 `127.0.0.1` (정확 일치, 와일드카드 금지) |
| port | 명시된 단일 테스트 포트만 (예: `9 ​**​ ` — 12M에서 확정). 포트 미지정 호출 금지 |
| path | `/__haehan_test__/readonly` 또는 동등한 read-only fixture 경로만 (prefix 매칭, `..` 등 정상화 필요) |
| query | 비어 있어야 함. `?token=...`, `?session=...`, `?password=...`, `?key=...` 등은 즉시 BLOCK |
| fragment | 무시 (미보존, 미로깅) |
| 매칭 방식 | exact host:port + prefix path. 하나라도 불일치 시 BLOCK |
| allowlist 정의 위치 | 12M 단계에서 별도 모듈 (예: `local_agent/internal_url_allowlist.py`) 또는 fixture 상수로 도입. 운영 yaml 정책 파일 변경 금지 |

---

## 5. 차단 패턴

| 패턴 | 차단 사유 |
|---|---|
| password input (`<input type="password">`) | 자격증명 입력 페이지 — 본문/value 노출 위험 |
| login / signin / auth / oauth / sso 경로 | 자격증명 흐름 진입 자체 차단 |
| `<form method="post">` | mutation 트리거 가능 |
| `<button type="submit">` / submit input | 의도치 않은 POST 가능 |
| `<input type="file">` | 파일 업로드 표면 |
| `contenteditable` / `<textarea>` | 사용자 입력 표면 |
| payment / checkout / order / pay 경로 | 결제 mutation |
| delete / remove / withdraw / cancel 경로 | 파괴적 mutation |
| admin / role / permission / grant / revoke 경로 | 권한 변경 |
| `document.cookie` / `localStorage` / `sessionStorage` 접근 코드 패턴 | secret 추출 표면 |
| `<meta http-equiv="refresh">` 또는 JS navigation | allowlist 밖 이동 위험 |
| navigation 결과 `final_url` 이 allowlist 밖 | 즉시 close + `browser_open_blocked` |

---

## 6. 수집 가능/금지 데이터

| 구분 | 항목 | 판정 |
|---|---|---|
| 허용 | `final_url` (allowlist에 매칭되는 경우에 한해 audit에 path까지 노출 가능) | PASS |
| 허용 | `title` (≤300자) | PASS |
| 허용 | `page_structure.counts` (headings/links/buttons/forms/inputs/tables) | PASS |
| 허용 | `status_category`, `pages_observed_count`, `error_category`, `timestamp`, `audit_event_id` | PASS |
| 금지 | HTML/body 전체 | BLOCK (현행 `open_url_readonly` 결과에 본문 부재 유지) |
| 금지 | cookie / session / token | BLOCK |
| 금지 | Authorization header | BLOCK |
| 금지 | localStorage / sessionStorage | BLOCK |
| 금지 | hidden input value (`<input type="hidden">`) | BLOCK (`_NO_VALUE_INPUT_TYPES` 유지) |
| 금지 | password value | BLOCK |
| 금지 | 개인정보 본문 | BLOCK (본문 자체 미수집으로 자동 차단) |

---

## 7. audit 기준

기존 `browser_open_*` 7종을 그대로 사용한다. 추가 payload 는 최소화한다.

| event | 사용 여부 | payload 기준 |
|---|---:|---|
| `browser_open_requested` | ✅ | `url_category="internal_test"`, `allowlist_name`, `allow_private_network=true`, `dry_run` |
| `browser_open_dry_run_checked` | ✅ | 동일 + `validation_ok` |
| `browser_open_started` | ✅ | 동일 (실 fetch 직전) |
| `browser_open_observed` | ✅ | `pages_observed_count`, `title_len`, `login_required_hint`, `modal_candidates_count`, `html_truncated` (본문 미포함 유지) |
| `browser_open_completed` | ✅ | `status_category="ok"` |
| `browser_open_blocked` | ✅ | `error_code`, `blocked_reason` (예: `OUTSIDE_ALLOWLIST`, `LOGIN_PAGE_DETECTED`, `FORM_POST_DETECTED`) |
| `browser_open_failed` | ✅ | `error_code` (예: `BROWSER_OPEN_FAILED`, `INTERNAL_SERVER_DOWN`) |

**금지 payload 필드**:
- url 원문은 host:port + path만 기록. `query` / `fragment` / `Authorization` / `cookie` / `token` 는 절대 기록 금지.
- query 가 비어 있어야 통과하므로 audit 에서도 query 부재 보장.
- `_categorize_url` 에 `internal_test_loopback` 카테고리 추가 검토 (12M에서 결정).

---

## 8. 다음 단계

1. **Stage 12M** — 내부 테스트 URL allowlist/fixture 검증
   - allowlist 모듈 또는 fixture 상수 도입
   - fixture 테스트로 host/port/path/query/scheme 매트릭스 검증
   - login/form/file/payment/admin 패턴 차단 검증
   - audit payload 에 query/cookie/token 미노출 검증
   - 실제 내부 서버 기동 없이 fake page + monkeypatch 만 사용
2. **Stage 12N** — 내부 테스트 URL 실제 smoke
   - read-only fixture page 1회 실 open
   - audit event 5종 성공경로 + 안전 필드 회귀
   - 별도 대표님 승인 게이트 통과 후

---

## 9. 금지 작업 준수 확인

- 코드 수정: 없음
- 테스트 수정: 없음
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

## 10. 최종 판정

**PASS**

설계 문서로서 내부 테스트 URL 허용/차단/allowlist/audit 기준을 명시하였다.
실제 코드/fixture 도입은 12M, 실 smoke 는 12N 단계의 별도 승인 게이트 통과 후 진행한다.
