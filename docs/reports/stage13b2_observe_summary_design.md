# Stage 13B-2 observe_summary design

## 1. 목적

controlled browser observe (`open_url_readonly`) 결과를 안전하게 구조화 저장/표시하기 위한
`observe_summary` 필드 설계.

현재 `result_summary` 는 1줄 문자열(최대 500자)이라 `final_url` / `title` /
`status_category` / `pages_observed_count` / `error_category` 등을 안전하게 구조화
표시하기 어렵다. 이번 단계는 설계/감사 문서만 작성한다. 코드·API·DB 수정은 없다.

---

## 2. 현재 구조

| 항목 | 현재 상태 | 한계 |
|---|---|---|
| `result_summary` | `LocalAgentTask.result_summary: str = ""` (최대 500자). `apply_result()` 에서 WS agent 보고 요약 문자열을 저장. 서버 즉시 완료 액션은 `_initial_result_summary()` 가 고정 문자열을 반환. | 구조화 필드 없음. `final_url` / `status_category` / `pages_observed_count` 등을 파싱·표시하려면 문자열 분해가 필요해 불안정. |
| task detail API | `GET /api/v1/local-agents/{agent_id}/tasks/{task_id}` → `LocalAgentTask.to_safe()`. `result_summary`, `error_summary`, 타임스탬프, 승인·취소 필드 포함. `observe_summary` 구조화 필드 부재. | observe 전용 구조화 데이터 없음. |
| admin-web task detail | Stage 13B-1에서 `LocalAgentTaskDetail` 확장 + read-only 모달 추가. `result_summary` 1줄 표시만 가능. | `url_category` / `status_category` / `pages_observed_count` 등 개별 표시 불가. |
| `browser_reader` result dict | `open_url_readonly()` 반환: `ok`, `url`, `current_url`, `title`, `html_truncated`, `login_required_hint`, `login_reason`, `modal_candidates`, `page_structure`, `summary`. | 이 dict는 local_agent 프로세스 in-memory 반환값. orchestrator로 전달 경로 없음. WS result 메시지의 `summary` 문자열만 `result_summary` 로 저장됨. |
| `browser_open_*` audit | 7종 이벤트를 `~/.haehan_agent/audit.jsonl` 에 기록. `browser_open_observed` 에 `pages_observed_count` / `title_len` / `login_required_hint` / `modal_candidates_count` / `html_truncated` 포함. | PC local 파일에만 존재. orchestrator·admin-web 에서 조회 불가. |

핵심 갭:
- `browser_reader.open_url_readonly()` 결과의 구조화 필드가 orchestrator task 에 저장되지 않는다.
- audit JSONL 은 PC local 에만 있어 admin-web 에서 직접 접근 불가.

---

## 3. observe_summary 후보 필드

| 필드 | 분류 | 표시 여부 | sanitize 기준 | 비고 |
|---|---|---:|---|---|
| `target_kind` | STORE_AND_DISPLAY | ✅ | 불필요 | `"about_blank"` / `"internal_test"` / `"external"` enum. 외부 접속이 허용되면 `"external"` 추가. |
| `url_category` | STORE_AND_DISPLAY | ✅ | 불필요 | `_categorize_url()` 결과 그대로: `about_blank` / `internal_test` / `public_https` / `public_http` 등. |
| `final_url_sanitized` | STORE_AND_DISPLAY | ✅ | **필수** | `about:blank` 또는 internal_test allowlist 통과 host:port+path 만 저장. 외부 URL이면 `url_category` 만 저장, 이 필드는 `null`. query/fragment 원문 절대 포함 금지. |
| `title` | STORE_AND_DISPLAY | ✅ | 길이 제한 ≤300 | `browser_reader` 결과 `title[:300]`. 민감값 없음 (title 에 token 등이 포함되는 경우 외부 URL allowlist 단계에서 차단). |
| `title_len` | STORE_AND_DISPLAY | ✅ | 불필요 | 정수. `len(title)`. |
| `status_category` | STORE_AND_DISPLAY | ✅ | 불필요 | `"ok"` / `"blocked"` / `"failed"` enum. |
| `pages_observed_count` | STORE_AND_DISPLAY | ✅ | 불필요 | 정수. 현재 항상 1. |
| `error_category` | STORE_AND_DISPLAY | ✅ | 필요 | `BROWSER_DEPENDENCY_MISSING` / `URL_SCHEME_BLOCKED` / `URL_PRIVATE_BLOCKED` 등 enum 코드만. 자유 문자열(reason) 포함 금지. |
| `blocked_reason` | STORE_AND_DISPLAY | ✅ | 필요 | `PASSWORD_INPUT_PRESENT` / `FINAL_URL_NOT_IN_ALLOWLIST` 등 enum 코드만. `analyze_internal_page_safety` 반환값 직접 사용. |
| `login_required_hint` | STORE_AND_DISPLAY | ✅ | 불필요 | bool. |
| `modal_candidates_count` | STORE_AND_DISPLAY | ✅ | 불필요 | 정수. `len(modal_candidates)`. 후보 text/reason 목록은 저장하지 않음. |
| `html_truncated` | STORE_AND_DISPLAY | ✅ | 불필요 | bool. |
| `page_structure_counts` | STORE_AND_DISPLAY | ✅ | 불필요 | `{headings, links, buttons, inputs, forms, tables}` 정수 dict. 실제 텍스트/href는 포함하지 않음. |
| `audit_event_count` | STORE_ONLY | ⛔ 보류 | 불필요 | 정수. PC local audit JSONL 이벤트 수. orchestrator 보고 채널(13C+) 도입 후 의미가 생김. 현재는 저장·표시 보류. |
| `observed_at` | STORE_AND_DISPLAY | ✅ | 불필요 | ISO timestamp. `browser_open_completed` 이벤트 시각 기준. |

### 분류 요약

| 분류 | 필드 |
|---|---|
| STORE_AND_DISPLAY | `target_kind`, `url_category`, `final_url_sanitized`, `title`, `title_len`, `status_category`, `pages_observed_count`, `error_category`, `blocked_reason`, `login_required_hint`, `modal_candidates_count`, `html_truncated`, `page_structure_counts`, `observed_at` |
| STORE_ONLY | `audit_event_count` (13C+ 이후 검토) |
| DISPLAY_DERIVED | 없음 (필요 시 `status_category` + `error_category` 조합 표시) |
| DO_NOT_STORE | `current_url` 원문(외부 URL), `modal_candidates` text/reason 목록, `page_structure` 전체, HTML 원문, `login_reason` 세부, `summary` 자유 문자열 |
| DO_NOT_DISPLAY | `audit_event_count` (현재 단계 보류), `page_structure` 원본 dict 전체, modal_candidates 목록 |

---

## 4. 저장 금지/표시 금지 데이터

| 데이터 | 저장 | 표시 | 사유 |
|---|---:|---:|---|
| cookie/session/token | 금지 | 금지 | secret 노출. browser_reader 에서도 미수집. |
| Authorization | 금지 | 금지 | 토큰 누출 위험 |
| password / hidden input value | 금지 | 금지 | 자격증명. `analyze_html_structure` 가 드롭. |
| localStorage/sessionStorage | 금지 | 금지 | 클라이언트 secret. browser_reader 에서 미수집. |
| HTML/body 전체 | 금지 | 금지 | 개인정보·본문 노출. `page_structure` counts 만 허용. |
| query/fragment 원문 | 금지 | 금지 | `?token=…` 등 secret 위험. |
| 외부 URL host/path/query 원문 | 금지 | 금지 | 정찰·추적 위험. `url_category` 만 허용. |
| headers (HTTP 응답 헤더) | 금지 | 금지 | set-cookie 등 민감 헤더 포함 가능. |
| hidden input value | 금지 | 금지 | 자격증명 포함 가능. |
| modal_candidates 텍스트/reason 목록 | 금지 | 금지 | 본문 텍스트 노출 가능. count만 허용. |
| login_reason 세부 목록 | 금지 | 금지 | keyword 목록이 본문 일부를 암시. bool hint 만 허용. |
| `audit.jsonl` raw | 금지 | 금지 | PC local 파일. orchestrator 직접 접근 금지. |

---

## 5. 저장 위치 후보

| 안 | 위치 | 장점 | 단점 | 추천 여부 |
|---|---|---|---|---|
| **A** | `LocalAgentTask` 에 `observe_summary: dict \| None = None` optional 필드 추가. `apply_result()` 또는 WS result 처리 시 local_agent 가 구조화 dict 를 함께 보고 → 저장. | 기존 task detail API(`to_safe()`) 자연 확장. `LocalAgentTaskDetail` 타입에 optional 필드 추가만 하면 됨. 기존 클라이언트 호환(새 필드 무시). | WS result 메시지 schema 확장(local_agent → orchestrator `result` 메시지에 `observe_summary` 추가), `apply_result()` 파라미터 추가 필요. `task_states.jsonl`/`_STORE_PATH` serialization 검토 필요(`asdict` 사용). | **권장** |
| B | `result_summary` 문자열에 compact JSON embed. | orchestrator backend 변경 없음. | UI에서 JSON parse 필요 → 취약. `result_summary` 500자 한계. 비표준. **비권장.** | 비권장 |
| C | 별도 `observe_results` store + 전용 API. | 확장성 좋음. observe 전용 조회 가능. | 현재 단계에는 과함. 신규 router/store/type 다수 추가. 13C+ 이후 검토. | 보류 |

**권장: A안.** `LocalAgentTask.observe_summary: dict | None = None` 추가가 가장 작은 변경이며 기존 호환성을 유지한다.

A안 구체 흐름:
1. local_agent `browser_reader.open_url_readonly()` 결과에서 안전 필드만 추출 → `observe_summary` dict 구성 (sanitize 후).
2. local_agent WS result 메시지에 `observe_summary` 키 추가 (`summary` 와 별도).
3. orchestrator `_handle_result()` 에서 `apply_result()` 호출 시 `observe_summary` 전달.
4. `LocalAgentTask.observe_summary` 에 저장.
5. `to_safe()` 응답에 `observe_summary` 포함 → admin-web `LocalAgentTaskDetail` 확장.

---

## 6. API 영향

| 항목 | 변경 필요 여부 | 기준 |
|---|---:|---|
| task detail API (`GET …/tasks/{task_id}`) | 필요 — `to_safe()` 에 `observe_summary` optional 추가 | 기존 클라이언트는 새 필드를 무시하므로 하위 호환 유지 |
| task list API (`GET …/tasks`) | **불필요** | `to_list_safe()` 에는 observe_summary 추가하지 않음 (목록은 요약만) |
| `LocalAgentTaskDetail` 타입 (admin-web) | 필요 — `observe_summary?: ObserveSummary \| null` 추가 | TypeScript interface 확장만 |
| admin-web task detail 렌더링 | 필요 — read-only 섹션 추가 | `observe_summary` 존재 시만 표시 |
| raw audit JSONL 노출 | **불가/금지** | PC local 파일. 현재도 admin-web 접근 없음. 13C+ 검토. |
| WS result 메시지 schema | 필요 — `observe_summary` 키 추가 | local_agent 측 변경 필요 |

---

## 7. Stage 13B-3 구현 제안

최소 구현 범위:
- `LocalAgentTask` 에 `observe_summary: dict | None = None` 필드 추가
- `apply_result()` 에 `observe_summary: dict | None = None` 파라미터 추가
- WS result 핸들러 `_handle_result()` 에서 `observe_summary` 수신·전달
- local_agent `browser_reader.open_url_readonly()` 결과에서 안전 필드만 추출하는 `_build_observe_summary()` helper 추가
- local_agent WS result 보고 시 `observe_summary` 포함
- admin-web `LocalAgentTaskDetail` 에 `observe_summary?: ObserveSummary | null` 추가
- admin-web task detail 모달에 observe 섹션 read-only 표시
- fixture tests 추가 (observe_summary 구조, sanitize, WS 흐름)

변경 대상:
- `ai_orchestrator/local_agent_registry.py` — `LocalAgentTask.observe_summary`, `apply_result()`
- `ai_orchestrator/local_agent_router.py` — `_handle_result()` WS 핸들러
- `local_agent/browser_reader.py` — `_build_observe_summary()` helper
- `local_agent/actions.py` 또는 WS 보고 모듈 — result 메시지에 `observe_summary` 추가
- `admin-web/src/types/local-agent.ts` — `ObserveSummary` interface, `LocalAgentTaskDetail` 확장
- `admin-web/src/app/local-agents/LocalAgentsClient.tsx` — observe 섹션 렌더링
- `tests/` — observe_summary fixture 추가

변경 금지:
- 외부 URL observe 실행 — 여전히 금지
- `task_states.jsonl` schema 변경 없음 (field 추가만, 기존 JSONL 재생 호환 유지)
- raw audit JSONL 노출 금지
- 새 실행 버튼 추가 금지
- 민감 필드(query 원문/외부 URL host/cookie/token 등) observe_summary 포함 금지

검증:
- fixture test: `_build_observe_summary()` sanitize 검증 (query 원문 포함 안 됨, external URL은 `final_url_sanitized=null`)
- fixture test: WS result → `apply_result()` → `observe_summary` 저장 흐름
- `npm run lint` / `npm run typecheck` (admin-web)
- `python scripts/check_local_agent_noexec_smoke.py`
- token_id / cookie / sessionStorage grep 0건 확인

---

## 8. 금지 작업 준수 확인

- 코드 수정: 없음
- 테스트 수정: 없음
- API 수정: 없음
- DB/schema 수정: 없음
- 서버 접속: 없음
- docker 실행: 없음
- local-agent 실행: 없음
- 브라우저 실행: 없음
- 실제 HTTP 요청: 없음
- 외부 URL: 없음
- 다른 앱 접근: 없음
- secret 출력: 없음

---

## 9. 최종 판정

**PASS**

`browser_reader.open_url_readonly()` 반환 dict 의 안전 필드를 `observe_summary: dict | None`
으로 구조화 저장하는 A안을 권장한다. 기존 task detail API·admin-web 타입의 optional 확장만
필요하며 하위 호환을 유지한다. 저장/표시 금지 데이터(query 원문, 외부 URL host,
cookie/token/HTML 전체 등) 기준이 명확히 정의되었다. 실제 구현은 Stage 13B-3에서 진행한다.
