# 홈택스 로컬 에이전트 작업 큐 — 대표님 무실행 구조 (F-4G-3Y)

> **상태**: 설계/조사 문서 (코드 변경 없음)
> **선행**: [F-4G-3X 전략 문서](./hometax_automation_strategy.md), F-4G-3B (post-login smoke runner), F-4G-3E (warmup/retry), TAX-API-1L (live API 검증 PASS)
> **본 단계의 의도**: 대표님이 터미널/CLI/JSON 파일을 직접 다루지 않도록, 기존 로컬 에이전트 작업 큐 인프라에 홈택스 post-login observe 작업 타입을 끼워 넣는 *최소 침습 설계*.

---

## 1. 결론 요약

### 1.1 한 줄 결론

홈택스 post-login observe 흐름은 새 큐를 만들지 않고 **기존 Stage 1/2 로컬 에이전트 큐**(`/api/v1/local-agents/...`) 위에 새 action 한 개 (`hometax_post_login_observe`) 만 등록하는 것으로 충분하다.

### 1.2 대표님 입장의 흐름

1. Claude 가 “홈택스에서 X 자료를 보겠습니다” 라고 작업을 만든다.
2. 대표님 PC 의 visible Chromium 이 자동으로 떠서 홈택스 메인을 연다.
3. 대표님은 **로그인/인증서/보안프로그램만** 직접 처리한다. 콘솔/CLI 도, JSON 파일 경로도 손대지 않는다.
4. 인증 완료 후 observer 가 자동으로 한 번 read-only 캡처 + plan 빌드 → 서버 업로드.
5. Claude 가 작업 ID 로 결과를 직접 조회해 판정한다.

### 1.3 본 단계의 산출물 (이 문서)

- 코드 수정은 하지 않는다.
- 본 문서가 끝나면 다음 4개의 작은 구현 단계 (F-4G-3Y-a/b/c/d) 로 분할된 지시문이 준비된다.

---

## 2. 배경

- **TAX-API-1 / TAX-API-1L** 은 사업자 상태조회/진위확인을 공식 공공데이터 API 로 자동화하는 데 성공했다. 이 경로는 인증 자체가 “API 키” 한 가지뿐이라 자동화가 자연스러웠다.
- **TAX-API-2A** (거래처 일괄검증) 는 본 단계에서 보류한다 — 거래처 리스크 기능 확장이 아니라, 홈택스 자동화의 “대표님 무실행” 흐름을 먼저 굳힌다.
- 홈택스 화면 자체는 인증서/보안프로그램이 필요해 자동화의 마지막 폴백으로만 둔다 (전략 문서 9.1 의 4순위). 단, 이 폴백조차도 **대표님이 직접 명령을 칠 필요는 없어야** 한다.

---

## 3. 기존 구조 정리

### 3.1 두 큐 구조가 병존

이 저장소에는 로컬 에이전트 큐가 두 갈래 있다.

| 갈래                                          | 위치                                                            | 통신     | 주요 액션                          | 본 작업 적합도 |
| --------------------------------------------- | --------------------------------------------------------------- | -------- | ----------------------------------- | -------------- |
| **Stage 1/2** (서버 ⟷ 로컬 에이전트 큐)       | `local_agent/`, `ai_orchestrator/local_agent_router.py`         | WS + 폴링 | ping, open_url, capture_screenshot, observe_public_browser_page, … | ✅ 적합        |
| **B안 3/4단계** (로컬 에이전트 폴링)           | `agent/`                                                        | HTTP 폴링 | Excel/CAD COM 위주                  | ❌ 부적합       |

본 단계의 대상은 **Stage 1/2** 갈래다. 이유:

- 홈택스 observe 코드 (`browser_manual_handoff.py`, `site_adapters/hometax.py`, `controlled_site_executor.py`) 가 이미 `local_agent/` 패키지 안에 있다.
- 기존 액션 `observe_public_browser_page`, `open_local_browser_probe` 와 동일한 정책/스캐폴딩 위에 얹을 수 있다.
- 라우터/registry/risk 매핑/감사 로그 인프라가 이미 완비되어 있다.

### 3.2 활용할 핵심 부품

- **서버측**
  - `ai_orchestrator/local_agent_router.py` — `/api/v1/local-agents/...` 엔드포인트 (등록/조회/큐/WS).
  - `ai_orchestrator/local_agent_registry.py`
    - `ACTION_RISK` (액션 → low/medium/high)
    - `AUTO_EXECUTE_VIA_AGENT` (에이전트로 push 가능한 액션 화이트리스트)
    - `_SENSITIVE_KEYS` (`password/token/cookie/secret …` 자동 strip)
    - `LocalAgentTask` 데이터 모델 (status: queued/delivered/running/completed/failed)
- **로컬 에이전트측**
  - `local_agent/actions.py`
    - `_ACTIONS` 딕셔너리 dispatch (line 1274)
    - `execute_action()` (line 1301) — `FORBIDDEN_ACTIONS` / `UNKNOWN_ACTION` 가드
  - `local_agent/browser_manual_handoff.py::observe_after_user_ready(...)`
  - `local_agent/site_adapters/hometax.py::build_hometax_controlled_action_plan(...)`
  - `local_agent/websocket_client.py` — Stage 2 WS 클라이언트 (high risk 미구현 거절 패턴 등)
- **CLI smoke runner (참조 구현)**
  - `scripts/run_hometax_post_login_smoke.py` — 본 단계에서 큐로 옮길 `build_result_payload()` / `render_markdown()` 의 origin.

---

## 4. 새 action 정의: `hometax_post_login_observe`

### 4.1 action 이름

```
hometax_post_login_observe
```

(점 `.` 대신 underscore — 기존 액션 명명 컨벤션과 정합)

### 4.2 risk_level

```
medium
```

이유:

- visible Chromium 띄우기 + 사용자 인증 트리거 → 단순 read-only `open_url` 보다는 위험.
- 그러나 자동 클릭/입력/쿠키/스토리지 접근은 코드 단에서 차단되어 있어 (`browser_manual_handoff` 정책) `capture_screenshot` 류 high 리스크와 같은 수준은 아님.
- 작업 생성 권한은 `local_agent_router` 의 기존 정책상 admin/owner 만 가능 — 무자격자가 생성할 수 없음.
- `medium` 이면 별도 승인 토큰 단계 없이 바로 `queued → delivered → running → completed` 흐름.

### 4.3 입력 (params)

`scripts/run_hometax_post_login_smoke.py` 의 CLI 옵션 셋과 동등하다:

| 키                              | 타입   | 기본값                              | 비고 |
| ------------------------------- | ------ | ----------------------------------- | ---- |
| `target_url`                    | str    | `https://www.hometax.go.kr/`        | http(s) 화이트리스트만 |
| `user_ready_seconds`            | int    | 120                                 | 0~180 |
| `dwell_after_capture_seconds`   | int    | 10                                  | 0~30 |
| `max_text_chars`                | int    | 10_000                              | 200~50_000 |
| `warmup_url`                    | str?   | `https://example.com/`              | F-4G-3E. `null`/빈문자열이면 disable |
| `goto_retries`                  | int    | 2                                   | 1~5 |
| `goto_retry_delay_seconds`      | float  | 1.5                                 | 0~10 |
| `goto_timeout_ms`               | int    | 90_000                              | 1000~180_000 |

### 4.4 출력 (result)

`scripts/run_hometax_post_login_smoke.py::build_result_payload()` 가 만드는 dict 와 동일한 구조:

```jsonc
{
  "target_url": "...",
  "observer": { /* observe_after_user_ready 결과 전체 */ },
  "plan":     { /* build_hometax_controlled_action_plan 결과 전체 */ },
  "summary": {
    "success": true,
    "page_state": "authenticated",
    "manual_action_required": false,
    "safe_read_candidates_count": 12,
    "download_candidates_count":  3,
    "blocked_candidates_count":   5,
    "warmup_attempted": true,
    "warmup_success":   true,
    "goto_attempts_used": 1,
    /* ... */
  },
  "verdict": "PASS" /* PASS/WARN/FAIL */
}
```

**감사 로그 / 결과 페이로드에 들어가지 않는 것** (지금도 그렇고, 본 단계 이후에도):

- 쿠키 / `storage_state` / `localStorage` / `sessionStorage`
- HTML 원문 / input value / textarea value
- 사용자 ID/PW/인증서 비밀번호/OTP/간편인증 값
- visible browser 에서 쓰인 사용자 환경/프로필 식별자

---

## 5. 흐름

### 5.1 시퀀스

```
┌──────────┐                                           ┌────────────┐
│  Claude  │                                           │ Local Agent │
│  /User   │                                           │ (대표님 PC) │
└────┬─────┘                                           └─────┬──────┘
     │  (1) POST /api/v1/local-agents/{id}/tasks             │
     │      action="hometax_post_login_observe"              │
     │      params={target_url, user_ready_seconds, …}       │
     ▼                                                        │
┌─────────────────────────────────┐                           │
│ ai_orchestrator                 │                           │
│ local_agent_router              │                           │
│  - 입력 검증 / risk 판정 medium │                           │
│  - _strip_sensitive(params)     │                           │
│  - LocalAgentTask 생성          │                           │
│    status=queued                │                           │
└─────────┬───────────────────────┘                           │
          │ (2) WS push 또는 폴링 응답                         │
          └────────────────────────────────────────►──────────┤
                                                              │
                                                              │ (3) status=delivered
                                                              │     status=running
                                                              │
                                                              ▼
                                              ┌─────────────────────────────┐
                                              │ local_agent.actions         │
                                              │ action_hometax_post_login_  │
                                              │ observe(params)             │
                                              │  - validate URL/params      │
                                              │  - FORBIDDEN_ENV guard      │
                                              │  - observe_after_user_ready │
                                              │    (visible chromium,       │
                                              │     N초 대기, 한 번 캡처)    │
                                              │  - build_hometax_           │
                                              │    controlled_action_plan   │
                                              │  - build_result_payload     │
                                              └────────┬────────────────────┘
                                                       │
                                                       │ (4) 사용자가 화면에서
                                                       │     로그인/인증서/보안프로그램
                                                       │     처리 (AI 미접촉)
                                                       │
                                                       ▼
                                              ┌─────────────────────────────┐
                                              │ result dict (no secrets)    │
                                              └────────┬────────────────────┘
                                                       │ (5) WS result 또는 POST result
                                                       ▼
┌─────────────────────────────────┐
│ ai_orchestrator                 │
│ local_agent_registry            │
│  apply_result(...)              │
│  - status=completed/failed      │
│  - audit log (no secrets)       │
└─────────┬───────────────────────┘
          │ (6) GET /api/v1/local-agents/{id}/tasks/{tid}
          ▼
┌──────────┐
│  Claude  │  결과 dict 직접 조회 → verdict 판정 / 다음 단계 결정
└──────────┘
```

### 5.2 상태 전이

```
queued ──(WS push / polling claim)──► delivered ──► running ──► completed
                                                            ╰──► failed
```

`waiting_approval` 단계는 본 액션에서는 발생하지 않는다 (medium).

### 5.3 인증 대기 시간 안에 사용자가 도달하지 못한 경우

- `observe_after_user_ready(user_ready_seconds=N)` 가 N초 sleep 후 한 번 캡처.
- 캡처 결과의 `page_state` 가 `login_required` / `authenticated` 어느 쪽인지 보고 verdict 결정.
- `login_required` 로 끝나면 `summary.verdict = "WARN"` + 이후 작업 재생성 가능.
- 본 단계에서는 “장시간 대기 후 자동 만료” 만 다룬다 — 무한 대기 모드는 없다.

---

## 6. 데이터 모델 변경

### 6.1 서버측 (`local_agent_registry.py`)

- `ACTION_RISK` 에 한 줄 추가:
  ```python
  "hometax_post_login_observe": "medium",
  ```
- `AUTO_EXECUTE_VIA_AGENT` 에 한 줄 추가:
  ```python
  "hometax_post_login_observe",
  ```

`LocalAgentTask` 자체의 필드 변경은 **없음**. `params` / `result` 는 dict 이므로 새 키를 받아도 데이터 모델은 그대로.

### 6.2 로컬 에이전트측 (`local_agent/actions.py`)

- 새 함수 `action_hometax_post_login_observe(params)` 추가.
- `_ACTIONS` 딕셔너리에 한 줄 등록:
  ```python
  "hometax_post_login_observe": action_hometax_post_login_observe,
  ```

`_FORBIDDEN_ACTIONS`, `execute_action()` 의 dispatch 흐름 변경 **없음**.

### 6.3 라우터 (`local_agent_router.py`)

차단 리스트(line 122 부근의 `observe_public_browser_page` 류)는 그대로 둔다. 본 신규 액션은 차단 리스트가 아닌 `AUTO_EXECUTE_VIA_AGENT` 화이트리스트로 들어간다.

작업 생성 엔드포인트:
```
POST /api/v1/local-agents/{agent_id}/tasks
Body: { "action": "hometax_post_login_observe", "params": { ... } }
```
→ admin/owner 만 가능 (기존 권한 정책 그대로).

---

## 7. 보안 정책 유지 (체크리스트)

본 액션에서도 다음은 **절대 추가하지 않는다**:

- [ ] `page.click` / `page.fill` / `page.type` / `page.press`
- [ ] `page.keyboard.*` / `page.mouse.*`
- [ ] `page.set_input_files` / `page.select_option`
- [ ] 폼 `submit` / 파일 다운로드 / 보안프로그램 자동 설치
- [ ] ID / PW / 인증서 비밀번호 / OTP / 간편인증 값 입력
- [ ] `cookies` / `storage_state` / `localStorage` / `sessionStorage` 접근
- [ ] input value / textarea value 수집
- [ ] `--remote-debugging-port` / `--headless` / 사용자 기존 프로필 / `storage_state` 로드

위 정책은 모두 `browser_manual_handoff.observe_after_user_ready` 가 이미 강제하고 있다. 본 액션은 그 함수를 그대로 호출하므로 보강 코드는 필요 없고, 다만 “호출 전에 params 의 forbidden 키가 들어왔는지” 만 한 번 더 검사한다 (registry 의 `_strip_sensitive` 와 이중 방어).

신규 환경변수 / secret 도입 **없음**:

- 본 액션은 어떤 비밀값도 읽지 않는다.
- `service_key` / `device_token` / `bearer token` 은 서버측 큐 인프라가 기존대로 처리한다 (registry 가 SHA-256 으로만 저장).

---

## 8. 최소 코드 수정 범위

본 단계에서는 **코드 수정 없음**. 다음 4개의 작은 단계로 분할:

### 8.1 F-4G-3Y-a — 서버측 액션 등록 (서버만)

- `ai_orchestrator/local_agent_registry.py` `ACTION_RISK` 에 `"hometax_post_login_observe": "medium"` 추가.
- `AUTO_EXECUTE_VIA_AGENT` 에 동일 액션 추가.
- 단위 테스트:
  - 미등록 액션 → `UNKNOWN_ACTION` 그대로.
  - 신규 액션 risk 매핑 / 화이트리스트 멤버십.
- 영향 범위: server-side only. 로컬 에이전트 코드 미변경.

### 8.2 F-4G-3Y-b — 로컬 에이전트측 핸들러 구현

- `local_agent/actions.py` 에 `action_hometax_post_login_observe(params)` 추가.
  - 입력 검증: target_url 화이트리스트, 정수/실수 범위 클립.
  - forbidden env / forbidden params 가드 (cookie/session/token 등 무조건 거절).
  - `from .browser_manual_handoff import observe_after_user_ready`
  - `from .site_adapters.hometax import build_hometax_controlled_action_plan`
  - `build_result_payload()` 와 동등한 평탄화 (smoke runner 와 같은 dict 구조 반환).
- `_ACTIONS` 등록.
- 단위 테스트 (browser 미실행 mock 으로):
  - 정상 paths / verdict 분류 / forbidden params 거절 / forbidden env 거절.
  - 결과 dict 에 cookies/storage_state/HTML 원문 키가 절대 들어가지 않는지.

### 8.3 F-4G-3Y-c — 사용자 알림 (선택, 작은 부가)

- visible Chromium 이 떠도 대표님이 못 보면 의미 없으니, 작업 시작 시점에 “홈택스 인증 진행해 주십시오” 알림 한 번.
- 옵션 (다음 단계에서 결정):
  - (a) `winsound` 알림음 + `print()` 콘솔 메시지 (가장 작음)
  - (b) `ctypes` 로 Windows MessageBox (modal — 비추천)
  - (c) `plyer` / `win10toast` 등 가벼운 의존성 추가 (토스트)
  - (d) 기존 `local_agent/audit.py` 와 통합된 알림 (있다면)
- 본 단계에서는 (a) 가 가장 단순. 의존성 0.
- 본 단계는 모든 OS 에서 fail-safe — 알림 실패해도 작업 진행은 막지 않는다.

### 8.4 F-4G-3Y-d — 운영 검증 (smoke)

- 대표님 PC + 서버에서 한 번의 무실행 체인 점검:
  - `POST /api/v1/local-agents/{agent_id}/tasks` → queued
  - 로컬 에이전트가 Stage 1/2 흐름으로 자동 claim → visible Chromium → 대표님 인증 → result 업로드
  - `GET /api/v1/local-agents/{agent_id}/tasks/{task_id}` → status=completed, summary 로 verdict 확인
- Claude 가 결과를 직접 조회하므로 대표님 손이 필요 없음.
- 검증 후 결과 JSON/MD 는 운영 결정 — 평소엔 서버 DB 만, 필요 시 사람이 보기 좋도록 markdown export.

---

## 9. 다음 구현 단계 지시문 (요약 버전)

각 단계는 **별도 commit**, push 금지, 직렬 진행.

### F-4G-3Y-a (서버측 등록)

> `ai_orchestrator/local_agent_registry.py` 의 `ACTION_RISK` 와
> `AUTO_EXECUTE_VIA_AGENT` 에 `hometax_post_login_observe` 를 medium 으로
> 추가한다. 라우터/엔드포인트 변경 없음. 신규 단위 테스트:
>
> - 액션이 ACTION_RISK 에 medium 으로 등록됨
> - AUTO_EXECUTE_VIA_AGENT 멤버십
> - 미등록 다른 액션은 여전히 UNKNOWN_ACTION
> - capture_screenshot 등 기존 액션의 risk 변경 없음
>
> live 호출 / 브라우저 실행은 본 단계 범위 아님.

### F-4G-3Y-b (로컬 에이전트 핸들러)

> `local_agent/actions.py` 에 `action_hometax_post_login_observe(params)` 추가.
> 내부에서 `browser_manual_handoff.observe_after_user_ready(...)` 와
> `site_adapters.hometax.build_hometax_controlled_action_plan(...)` 호출.
> 결과 dict 는 `scripts/run_hometax_post_login_smoke.py::build_result_payload`
> 와 동등 구조. `_ACTIONS` 에 등록. 단위 테스트는 browser_factory 를 mock
> 으로 주입해 실제 Chromium 없이 PASS/WARN/FAIL 분기 검증.
>
> 보안 회귀 테스트:
>
> - params 의 cookie/session/token 키가 들어오면 거절
> - 결과 dict 에 cookies/storage_state/raw HTML 키가 절대 없음
> - FORBIDDEN_ENV (`GOOGLE_PASSWORD` 등) 가 set 된 환경에서는 즉시 실패

### F-4G-3Y-c (사용자 알림, 선택)

> 작업 시작 시점에 “홈택스 인증 진행해 주십시오” 알림 한 번. 1차 PoC 는
> `winsound.MessageBeep()` + `print()` 만. 의존성 추가 금지. 알림 실패는
> 작업 진행을 막지 않는다.

### F-4G-3Y-d (운영 무실행 검증)

> 대표님 PC 에 로컬 에이전트가 띄워져 있는 상태에서, Claude 가 작업 1건을
> POST 로 생성한다. 로컬 에이전트가 자동 claim → visible Chromium → 대표님
> 인증 → result 업로드 → Claude 가 GET 으로 결과 조회. 대표님은 명령 1줄도
> 치지 않는다 (인증 외).
>
> 본 단계에서 확인:
>
> - status=completed
> - summary.verdict ∈ {PASS, WARN}
> - audit log 에 cookies/storage_state/raw HTML 미기록
> - F-4G-3Y-a/b 의 코드 변경이 운영 환경에서 정합

---

## 10. 본 단계의 PASS / WARN / FAIL 자가 판정

### PASS 조건

- [x] 기존 큐 인프라 (Stage 1/2) 위에 얹히는 최소 침습 설계임을 명시.
- [x] 새 action 한 개 (`hometax_post_login_observe`) 만 등록한다.
- [x] 흐름 안에 “대표님이 콘솔/CLI 를 친다” 단계가 없다.
- [x] 보안 정책(`browser_manual_handoff` 가 이미 강제) 을 그대로 상속, 신규 비밀값/secret 도입 없음.
- [x] 다음 4개 구현 단계 (F-4G-3Y-a/b/c/d) 가 명확하게 분리되었다.

### WARN

- [ ] OS 알림(F-4G-3Y-c) 의 구체 방식은 본 문서에서 결정하지 않았다 — 다음 단계에서 (a)/(b)/(c)/(d) 중 선택.
- [ ] 인증 완료 자동 감지(폴링형 page_state 변화) 는 본 단계 범위 밖. 단순 N초 sleep 만 사용.

### FAIL — 모두 회피됨

- [x] 자동 클릭/입력/쿠키/스토리지 접근을 추가하지 않는다.
- [x] AI 의 인증값 자동 입력/저장을 도입하지 않는다.
- [x] 대표님 수동 명령 실행 전제를 유지하지 않는다.
- [x] 새 큐 인프라를 만들지 않는다 (기존 Stage 1/2 큐 재사용).
- [x] TAX-API-2A 거래처 일괄검증을 본 흐름에 끼워 넣지 않는다.

따라서 본 설계 문서의 자가 판정은 **PASS (with WARN)** 이다.

---

## 부록 A. 본 단계가 끝난 뒤 “대표님 무실행” 의 최종 검증

다음 모두를 만족하면 F-4G-3Y 시리즈가 종결된다.

1. 대표님은 `python -m local_agent.agent` 또는 동등한 1회성 PC 측 등록 외에는 어떤 명령도 손으로 치지 않는다 (한 번 띄우면 상시 실행).
2. 대표님은 결과 JSON/MD 의 경로를 모르고도 일이 진행된다.
3. Claude 는 작업 ID 만으로 결과를 조회해 다음 단계를 결정할 수 있다.
4. 인증값 / 쿠키 / 스토리지 / HTML 원문이 어떤 로그/응답에도 남지 않는다.
5. F-4G-3X 전략 문서의 4순위(폴백 로컬 브라우저)가 “대표님 손이 필요한 마지막 자료” 한정으로만 발동한다.
