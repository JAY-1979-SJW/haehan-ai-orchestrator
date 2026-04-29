# Stage 13A observe/audit UI design

## 1. 목적

Stage 12 controlled browser observe 1차 라인이 마감되어, admin-web 운영자가
observe 결과와 `browser_open_*` audit event 를 안전하게 확인할 수 있는 UI 를 설계한다.

이 단계는 설계만 수행한다. 코드/UI 구현/서버 반영/실행은 12N 외엔 없다.

origin/master 최신: `65482e1` (Stage 12O closeout)

---

## 2. 현재 저장/조회 구조

read-only 감사 결과:

| 항목 | 현재 위치 | admin-web 조회 가능 여부 | 비고 |
|---|---|---:|---|
| observe result (`open_url_readonly` 반환 dict) | local-agent 프로세스 in-memory dict (반환값) | **간접** — `result_summary` 필드로 task에 요약 저장 시에만 노출 | HTML 본문 / page_structure 전체는 admin-web 미노출 (의도적) |
| task state | orchestrator (`local_agent_registry`) + JSONL persist | **가능** — `GET /local-agents/{agent_id}/tasks/{task_id}` (admin-web `LocalAgentTaskDetail`) | `result_summary`, `error_summary`, `failure_reason`, `status` 노출 |
| `browser_open_*` audit (Stage 12J) | `local_agent.audit.log_local_event` → **`~/.haehan_agent/audit.jsonl`** (PC local, repo 외부) | **불가** — 현재 orchestrator 로 전송 경로 없음 | 7종 이벤트는 PC 디스크에만 존재 |
| approval audit (`APPROVAL_*`, `LOCAL_AGENT_TASK_*`) | `ai_orchestrator.audit_logger.log_event` → orchestrator audit JSONL | **간접** — admin-web 전용 audit 조회 API 미존재. 운영자가 서버 파일 직접 봐야 함 | task detail에는 일부 timestamp 만 반영 |

핵심 갭:
- `browser_open_*` 7종 audit 은 **PC local 파일에만 존재** — admin-web 가시성 0.
- observe result 는 `result_summary` 문자열로만 흘러들어옴 — 구조화 필드 (counts/login_hint/title_len/url_category) 는 손실.

---

## 3. 표시 가능 데이터

| 필드 | 표시 여부 | sanitize 필요 여부 | 비고 |
|---|---:|---:|---|
| `task_id` | ✅ | 불필요 | 기존 노출 |
| `agent_id` | ✅ | 불필요 | 기존 노출 |
| `status` | ✅ | 불필요 | 기존 enum (queued/completed/failed/...) |
| `action` | ✅ | 불필요 | 기존 노출 (`web_open_url_readonly` 등) |
| `target_kind` | ✅ (신규) | 필요 | `internal_test` / `about_blank` 카테고리만 |
| `url_category` | ✅ (신규) | 필요 | `_categorize_url` 결과 그대로 |
| `final_url` | **조건부** | **필수** | `about_blank` 또는 internal allowlist 매칭 시에만 host:port+path. 외부면 카테고리만 |
| `title` | ✅ | 길이 제한(≤300) 유지 | 기존 `result_summary` 안에 일부 포함 가능 |
| `status_category` | ✅ (신규) | 불필요 | `ok` / `blocked` / `failed` |
| `pages_observed_count` | ✅ (신규) | 불필요 | 정수 |
| `error_category` | ✅ (신규) | 필요 | `BROWSER_DEPENDENCY_MISSING`, `URL_*_BLOCKED` 등 코드만 |
| `blocked_reason` | ✅ (신규) | 필요 | `PASSWORD_INPUT_PRESENT` 등 enum 코드만 |
| `risk_level` | ✅ | 불필요 | 기존 노출 |
| `dry_run` | ✅ (신규) | 불필요 | bool |
| `audit_event_count` | ✅ (신규) | 불필요 | 7종 중 발생 개수 |
| `created_at` / `completed_at` | ✅ | 불필요 | 기존 노출 |
| `approval status` | ✅ | 불필요 | 기존 노출 (`approved_at`, `rejected_at`) |

---

## 4. 표시 금지 데이터

| 필드/데이터 | 금지 사유 |
|---|---|
| cookie / set-cookie / session | secret 노출 위험. PC local 에서도 미수집, admin-web에서는 절대 표시 금지 |
| Authorization header | 토큰 누출 위험 |
| password / hidden input value | 자격증명 노출 |
| localStorage / sessionStorage | 클라이언트 secret |
| HTML/body 전체 | 개인정보·본문 노출 (현재도 미노출 유지) |
| query / fragment 원문 | `?token=…` 등 secret 위험. 카테고리만 표시 |
| 외부 URL host/path/query 원문 | 정찰/추적 위험. 외부 URL 은 `url_category` 만 표시 |
| 디바이스 토큰 / agent device_token | 등록 응답 1회 외 절대 표시 금지 |
| audit JSONL raw viewer | 민감 키 직접 노출 위험. 구조화된 필드만 노출 |

---

## 5. UI 위치 후보

| 안 | 위치 | 장점 | 단점 | 추천 여부 |
|---|---|---|---|---|
| **A** | 기존 `/local-agents` task detail 모달/펼침에 "observe 결과" 영역 추가 | 신규 route 없음, 기존 task→detail 동선 재사용, 구현 가장 작음 | task 단위로만 보임 (전체 audit 타임라인 없음) | **권장** |
| B | `/local-agents/observe-results` 신규 route | observe 전용 리스트 가능 | 신규 nav/route, API 신규 필요, 구현 큼 | 보류 (13C 이후) |
| C | `/audit` 신규 route (전체 감사 로그) | 통합 감사 동선 | audit 종류가 너무 광범위, 13A 범위 초과, raw viewer 위험 | 비권장 |

판단 기준 만족도:
- **최소 구현** → A
- **기존 API 재사용 가능성** → A (`GET /local-agents/{agent_id}/tasks/{task_id}` 응답 확장 또는 `result_summary` 활용)
- **운영자 사용성** → A (task 흐름과 자연스럽게 연결)
- **위험 정보 노출 최소화** → A/B 동등 (정책상 동일)
- **향후 확장성** → A 시작 후 13C 에서 B 로 확장 가능

---

## 6. 추천 구현 범위

**추천안: A안 + 최소 데이터**

최소 구현 (Stage 13B-1 한정):
- 기존 `LocalAgentTaskDetail` 응답을 그대로 사용 (서버 변경 없음)
- admin-web 의 task detail 표시 영역에 다음 read-only 필드 추가:
  - `action`, `risk_level`, `status` (기존)
  - `result_summary` 를 1줄 텍스트로 그대로 표시 (현재 화면에 이미 있을 수 있음 — 강조만)
  - `error_summary`, `failure_reason` (있을 때만)
  - `approved_at` / `approved_by` / `rejected_at` / `reject_reason` (기존)
- 신규 API 호출 없음. 신규 권한 없음.

이번 단계(13A)에서 **하지 않을 것**:
- 외부 URL 실행
- 새로운 실행 버튼
- approve/reject 정책 변경
- secret/raw log viewer
- 브라우저 실행
- `~/.haehan_agent/audit.jsonl` 직접 노출 (PC local 파일이라 admin-web 접근 불가, 노출하면 안 됨)

후속(13C+)에서 검토:
- orchestrator 측에 `browser_open_*` audit 보고 채널 추가 (PC local → orchestrator 요약 보고)
- 해당 데이터가 도착한 뒤에야 observe-results 전용 list/audit timeline UI 의미가 생김

---

## 7. API 필요성

| API | 필요 여부 | 이유 |
|---|---:|---|
| observe results list | **불필요 (13B-1 기준)** | 기존 task 리스트로 충분. observe 전용 분리 시 13C 이후 |
| observe result detail | **불필요** | 기존 `GET /local-agents/{agent_id}/tasks/{task_id}` 의 `LocalAgentTaskDetail` 재사용 |
| audit events list | **불필요 (13B-1 기준)** | 현재 `browser_open_*` 가 PC local 에만 존재 — orchestrator 보고 채널 도입(13C+) 후 검토 |
| task detail 확장 | **불필요 (13B-1)** / 검토 (13B-2) | 현재 필드로 최소 표시 가능. 구조화 표시가 필요해지면 13B-2 에서 `observe_summary: {url_category, status_category, pages_observed_count, ...}` 옵션 필드 추가 검토 |

원칙:
- admin-web 에서 PC local 파일 직접 read 금지
- admin-web 에서 secret 파일/JSONL raw 접근 금지
- 모든 데이터는 orchestrator API 경유

---

## 8. Stage 13B 제안

다음 중 하나로 제안한다.

- **Stage 13B-1**: API 없이 기존 task data 만으로 `/local-agents` task detail 영역 read-only 보강
  - 가장 작은 구현. 신규 권한/API 없음. 회귀 위험 최소.
- Stage 13B-2: `LocalAgentTaskDetail` 에 `observe_summary` 옵션 필드 추가 (orchestrator API + admin-web type 동시 변경)
- Stage 13B-3: `browser_open_*` audit 을 orchestrator 로 보고하는 채널 + audit list API + admin-web timeline (큰 작업)

**권장: 13B-1 부터.**
- 기존 admin-web UI 일관성 유지
- 백엔드 변경 없음 → 회귀 거의 없음
- 13B-2/13B-3 은 운영자가 13B-1 사용해 보고 진짜 필요한 필드를 식별한 뒤 진행

---

## 9. 금지 작업 준수 확인

- 코드 수정: 없음
- 테스트 수정: 없음
- 서버 접속: 없음
- docker 실행: 없음
- local-agent 실행: 없음
- 브라우저 실행: 없음
- 실제 HTTP 요청: 없음
- 외부 URL: 없음
- 다른 앱 접근: 없음
- secret 출력: 없음

---

## 10. 최종 판정

**PASS**

설계 문서로서 현재 저장/조회 갭(`~/.haehan_agent/audit.jsonl` 의 admin-web 미가시), 표시 가능/금지 데이터, UI 위치(A안 권장), 최소 구현 범위(13B-1)를 명시했다.
실제 UI 구현은 13B-1 단계에서 별도 진행한다.
