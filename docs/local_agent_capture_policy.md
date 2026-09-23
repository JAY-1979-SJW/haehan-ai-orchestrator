# 로컬 에이전트 — 화면 캡처 운영 정책

본 문서는 **로컬 에이전트 `capture_screenshot`** 기능의 운영 반영 전·후
고정 정책을 정의한다. 코드 구현은 별도 파일에서 이루어지지만, **운영상
허용되는 동작의 경계**는 본 문서가 단일 근거(single source of truth)가 된다.

관련 구현 문서:
- [로컬 에이전트 아키텍처](./local_agent_architecture.md)
- [웹 자동화 표준](./web_automation_standard.md)

---

## 1. 기능 목적

관리자가 사용자 로컬 PC(본인이 직접 설치·실행한 `local_agent`)에서
**승인된 1회 한정의 화면 캡처**를 원격으로 요청할 수 있게 한다.

본 기능은 다음 두 가지 요구를 동시에 만족해야 한다.

- 운영자/관리자는 원격지에서 화면 상태를 “한 번” 확인할 수 있어야 한다
- 사용자(PC 소유자)는 언제든 이를 감지·거절·종료할 수 있어야 한다

따라서 아래 고정 정책이 예외 없이 적용된다.

> **실제 화면 캡처는 승인 후 로컬 PC에서 1회만 실행되며, 서버에는
> 이미지가 업로드되지 않는다.**

> **반복 캡처, 스트리밍, 상시 감시, 서버 이미지 업로드 기능은 현재
> 정책상 금지한다.**

---

## 2. dry-run과 실제 1회 요청의 차이

| 구분 | dry-run (사전 점검) | 실제 1회 캡처 |
|------|---------------------|----------------|
| 관리자 UI 버튼 | `화면 캡처 사전 점검` (파란색) | `실제 1회 화면 캡처 요청` (빨간색) |
| API body | `{"dry_run": true,  "reason": "ui_dry_run_check"}` | `{"dry_run": false, "reason": "ui_capture_once_request"}` |
| 브라우저 확인창 | 없음 | `window.confirm()` 통과 필수 |
| 로컬 PC 실행 | **실제 캡처 실행되지 않음** (경로/권한 사전 점검만) | 승인 후 1회만 실행 |
| 이미지 생성 | 없음 | 로컬 PC 한정, 서버 비전송 |
| 승인 게이트 | 텔레그램 승인 필요 | 텔레그램 승인 필요 |
| 횟수 제한 | 건별 독립 | **1회 = 1 요청** (연속/반복 불가) |

dry-run의 존재 이유: 실제 캡처 시점에 권한/경로 오류로 실패해 운영자가
재시도하는 악순환을 막는다. 사전 점검 자체도 승인 게이트를 거친다.

---

## 3. 승인 흐름

```
[관리자 UI]
   │  ① 버튼 클릭 (dry-run 또는 실제 1회)
   │     └─ 실제 1회 경로는 window.confirm 통과 필수
   ▼
[서버 /api/v1/local-agents/{id}/capture-screenshot]
   │  ② waiting_approval 상태로만 생성 (즉시 실행 금지)
   │     └─ 감사 로그: LOCAL_AGENT_TASK_WAITING_APPROVAL
   ▼
[텔레그램 승인 게이트]
   │  ③ 승인자는 텔레그램에서 [승인]/[거절] 클릭
   │     └─ 거절/만료 → rejected, WS 전달 없음
   ▼
[WebSocket → 로컬 에이전트]
   │  ④ 승인된 1회 작업만 에이전트에 전달
   ▼
[로컬 PC]
   │  ⑤ 1회 실행 → 결과 요약만 서버에 보고
   │     └─ 이미지 바이너리는 서버로 전송되지 않음
   ▼
[감사 로그]
   └─ LOCAL_AGENT_TASK_COMPLETED (원문 경로/파일명 제외)
```

핵심 불변식:
- ②와 ④ 사이에 **승인 게이트(③)** 가 없으면 ④는 발생하지 않는다
- ④는 승인된 단일 `task_id`에 대해서만 발생한다 (재사용·재승인 금지)

---

## 4. 서버 미업로드 정책

- 캡처된 이미지 바이너리는 **서버 어느 저장소에도 기록되지 않는다**
  (FS, DB, 오브젝트 스토리지, 로그 모두 포함).
- 서버는 **결과 요약 텍스트**(성공 여부, 에러 코드, 타임스탬프)만 수신한다.
- 에이전트가 실수로 파일을 포함해 응답을 보내더라도 서버는 이를
  저장·전파하지 않는다. 라우터는 요약 필드 외 본문을 수용하지 않는다.

따라서 서버 측 장애나 침해가 발생해도 로컬 PC의 화면 이미지가 함께
유출되는 경로는 존재하지 않는다.

---

## 5. 금지 기능 목록 (영구 금지)

| # | 기능 | 사유 |
|---|------|------|
| 1 | 반복 캡처 (N분 간격) | 승인 게이트 우회, 상시 감시로 변질 |
| 2 | 스트리밍 / 실시간 화면 전송 | 대역폭·프라이버시 위험, 승인 게이트 무력화 |
| 3 | 상시 감시 / 자동 트리거 | 사용자 동의 없는 지속 관찰 |
| 4 | 서버 이미지 업로드 / 저장 | 유출 경로 제거 |
| 5 | 이미지 다운로드 UI | 서버 미업로드 원칙과 직접 충돌 |
| 6 | 다중 에이전트 일괄 캡처 | 승인 게이트 우회·확산 위험 |
| 7 | 사전 승인 / 재사용 토큰 | 1회성 원칙 위배 |
| 8 | 백그라운드 / 자동 실행 | 사용자 제어권 상실 |

이 목록의 어느 항목이라도 기능 요구사항으로 재등장하면 본 정책 문서를
먼저 갱신하고 별도 검토·결재를 받아야 한다. 코드 변경이 먼저 진행돼서는
안 된다.

---

## 6. 민감정보 미노출 원칙

다음 값은 관리자 UI HTML, API 응답, 텔레그램 메시지, 감사 로그 원문
어디에도 노출되지 않는다.

- `approval_token`, `device_token`, `token_hash` 원문
- 승인 토큰 ID (`token_id`) — 감사 로그에는 **해시·alias**만 허용
- `LOCAL_AGENT_SCREENSHOT_DIR` 등 환경 변수 원문
- `screenshot_file`, `screenshot_path`, 파일명(`.png` 포함)
- 로컬 PC 경로(`C:/Users/…`, `/home/…`, `.haehan_agent/…`)

UI 측 DOM 삽입은 모두 `textContent`로만 이루어지며 innerHTML 경로가
없도록 유지한다.

---

## 7. 감사 로그 기준

| 이벤트 | 기록 내용 | 기록 금지 |
|--------|-----------|-----------|
| `LOCAL_AGENT_TASK_QUEUED` | task_id, agent_id, action, requested_by, dry_run | 승인 토큰 원문 |
| `LOCAL_AGENT_TASK_WAITING_APPROVAL` | task_id, token_id **해시**, requested_by | token_id 원문, 경로, 파일명 |
| `LOCAL_AGENT_TASK_COMPLETED` | task_id, 결과 요약(성공/에러 코드) | 이미지 바이너리, 파일명, 로컬 경로 |
| `LOCAL_AGENT_TASK_REJECTED` | task_id, 사유(denied/expired/unknown_action) | 토큰 원문 |

감사 로그 재스캔 테스트는 본 문서 §8·§9 의 게이트 테스트에 포함된다.

---

## 8. 운영 반영 전 필수 게이트 테스트

운영 반영 직전(= 배포 PR 머지 직전) 아래 10개 테스트는 **모두 PASS**
상태여야 한다.

- `ai_orchestrator/tests/test_admin_ui_capture_screenshot.py`
- `ai_orchestrator/tests/test_capture_screenshot_request_api.py`
- `ai_orchestrator/tests/test_capture_screenshot_telegram.py`
- `ai_orchestrator/tests/test_capture_screenshot_approval.py`
- `ai_orchestrator/tests/test_capture_screenshot_dry_run.py`
- `ai_orchestrator/tests/test_local_agent.py`
- `ai_orchestrator/tests/test_local_agent_ws.py`
- `ai_orchestrator/tests/test_auth_enforcement.py`
- `ai_orchestrator/tests/test_telegram_webhook.py`
- `ai_orchestrator/tests/test_telegram_callback.py`

단일 명령으로 실행:

```bash
pytest ai_orchestrator/tests/test_admin_ui_capture_screenshot.py \
  ai_orchestrator/tests/test_capture_screenshot_request_api.py \
  ai_orchestrator/tests/test_capture_screenshot_telegram.py \
  ai_orchestrator/tests/test_capture_screenshot_approval.py \
  ai_orchestrator/tests/test_capture_screenshot_dry_run.py \
  ai_orchestrator/tests/test_local_agent.py \
  ai_orchestrator/tests/test_local_agent_ws.py \
  ai_orchestrator/tests/test_auth_enforcement.py \
  ai_orchestrator/tests/test_telegram_webhook.py \
  ai_orchestrator/tests/test_telegram_callback.py
```

전체 스위트의 pre-existing 실패(본 기능과 무관)는 본 게이트와 별개이며
본 단계에서 수정하지 않는다.

---

## 9. 금지 문자열 재스캔 게이트

운영 반영 전 **관리자 UI HTML 응답 / capture API 응답 / 텔레그램 발송
메시지 / 감사 로그 라인**에 아래 문자열이 한 번도 등장하지 않는지 재스캔한다.

```
approval_token
device_token
token_hash
LOCAL_AGENT_SCREENSHOT_DIR
screenshot_file
screenshot_path
.png
.haehan_agent
C:/Users/
/home/
```

정책:
- **관리자 UI HTML**: 위 문자열 중 어느 것도 응답 본문에 포함 금지
- **API 응답**: JSON 키/값 어디에도 포함 금지
- **텔레그램 메시지**: 승인 요청/결과 알림 본문에 포함 금지
- **감사 로그**: 토큰 원문·로컬 경로·이미지 파일명 포함 금지
  (해시/alias/요약만 기록)

본 재스캔은 `test_admin_ui_capture_screenshot.py`의 `_FORBIDDEN_UI_STRINGS`
및 관련 응답 검증 테스트가 자동 수행한다. 문서상 별도 수동 재스캔이
필요한 경우 위 목록을 기준으로 `grep -R` 한 뒤 신규 매칭이 없는지 확인한다.

※ 구현 설명 주석(코드/문서 내부 설명 텍스트)에 단어로 등장하는 경우는
허용된다. 본 게이트는 **런타임 응답 본문**이 대상이다.

---

## 10. 관리자 UI 주의 문구 (고정)

`ai_orchestrator/routers/admin_ui_router.py`의 HTML 에는 다음 의미가 유지되어야
한다(문구 단위 수정은 허용, 의미 변경은 불가).

- 상단 안내: dry-run 버튼과 실제 요청 버튼의 구분 명시
- 실제 1회 버튼 옆 경고선:
  `※ 실제 1회 캡처는 승인 후 로컬 PC에서 1회만 실행됩니다. 서버에는 이미지가 업로드되지 않습니다.`
- `window.confirm` 문구:
  `승인 후 로컬 PC에서 1회 화면 캡처가 실행됩니다. 서버에는 이미지가 업로드되지 않습니다. 계속하시겠습니까?`
- 성공 응답 안내(실제 1회 경로):
  `승인 후 로컬 PC에서 1회 실행되며 서버에는 이미지가 업로드되지 않습니다.`

JS 로직, 승인 로직, API 로직은 본 문서의 범위가 아니며 수정 불가.

---

## 11. 운영자 주의사항

- 실제 1회 요청은 텔레그램 승인을 **반드시** 거친다. 승인 지연 시
  사용자에게 직접 알리는 것보다 요청을 취소(또는 거절 대기)하는 편이
  안전하다.
- 한 명의 운영자가 연속으로 실제 1회 요청을 발급하는 패턴이 감지되면
  이는 반복 캡처 회피 우회 시도로 간주한다. 감사 로그를 통해 빈도를
  모니터링한다.
- 캡처 결과는 서버에 저장되지 않으므로 **사후 재확인이 불가하다**.
  필요 시 사용자에게 직접 이미지 공유를 요청한다.
- dry-run에서 성공했다고 해서 실제 1회 캡처가 무조건 성공한다고
  가정해서는 안 된다(권한·잠금화면 등 타이밍 이슈).

---

## 12. 장애 / 오작동 시 대응 원칙

| 상황 | 대응 |
|------|------|
| 승인 게이트 없이 실행된 의심 사례 | 즉시 `/api/v1/local-agents` 전체 비활성, 감사 로그 보존, 재현 조사 |
| 텔레그램 승인 장애(발송 실패) | 실제 1회 경로를 **비활성**까지 허용 — 무승인 실행은 절대 안 됨 |
| 이미지가 서버로 전송된 흔적 발견 | 본 정책 위반으로 배포 즉시 롤백, 이미지 즉시 삭제 |
| 금지 문자열 응답 노출 발견 | UI/API 해당 라우터 비활성 → 수정 → §8/§9 재검증 후 재배포 |
| 반복 캡처 기능 요구 유입 | 본 문서 §5 를 근거로 거절, 별도 결재 없이 구현 금지 |
| 로컬 에이전트 프로세스 응답 없음 | 사용자가 Ctrl+C 로 종료 가능, 서버 측 재시도는 하지 않는다 |

---

## 13. 변경 관리

본 문서의 §5(금지 기능), §6(민감정보 미노출), §7(감사 로그 기준)의
정책 문구 변경은 **보안 리뷰 + 별도 결재**가 선행되어야 한다. 코드
변경이 본 문서보다 먼저 머지되어서는 안 된다.

최초 작성: 2026-04-24
