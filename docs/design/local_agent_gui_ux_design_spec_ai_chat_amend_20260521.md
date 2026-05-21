# HaehanAI-Agent.exe — GUI UX 설계 보정 (AI Chat 반영)

- 공정: **AGENT_GUI_UX_DESIGN_SPEC_AI_CHAT_AMEND_01**
- 기존 설계: `local_agent_gui_ux_design_spec_20260521.md` (HEAD 27d6ede)
- HEAD: `27d6ede`
- 종류: **설계 보정 문서 (코드 변경 없음)**
- 다음 구현 공정명:
  - **`AGENT_AI_CHAT_API_CLIENT_01`** (AI API 클라이언트 구현)
  - **`AGENT_GUI_CHAT_IMPLEMENTATION_01`** (Chat UI 구현 + 기존 GUI 보정)

---

## 1. 보정 사유

직전 설계 (`AGENT_GUI_UX_DESIGN_SPEC_01`) 의 권장안은 **D. wizard + tray only**.
이 권장은 *"단순 연결 에이전트"* 가정 하에 적절했지만, **AI API 연동이 요구되면 사용자가 대화할 채팅창이 필수**.

### 1.1 기존 가정 (보정 전)
- 사용자는 등록 1회 후 트레이만 본다
- 진단은 가끔
- 윈도우는 wizard 시점에만 잠시 등장

### 1.2 새 요구 (보정 후)
- 사용자가 **AI 와 대화**한다 (질문/지시/응답)
- AI 가 로컬에이전트에게 작업을 위임할 수 있음 → 사용자는 **승인/상태**를 본다
- 진단/연결 상태도 여전히 필요

### 1.3 결론
- **wizard + tray only 는 불충분**
- **윈도우가 평소에도 열려 있을 수 있는 구조 필요** (트레이로 최소화하되 풀스크린은 아님)
- **Chat 중심 + Status / Diagnostics 보조 탭** 구조로 보정

---

## 2. 사용자 목적 재정의

| 단계 | 보정 전 | 보정 후 |
|------|---------|---------|
| 등록 | 1회 wizard | 동일 |
| 평상시 | 트레이만 본다 | **Chat 창을 열어 AI 와 대화** |
| 작업 위임 | (해당 없음) | AI 가 위임 → 사용자가 **승인/상태** 확인 |
| 진단 | 가끔 (트레이 메뉴) | 가끔 (탭 또는 트레이 메뉴) |

→ **Chat 이 주 사용 면. Status / Diagnostics 는 보조.**

---

## 3. GUI 구조 재비교

### 3.1 A. wizard + tray only (보정 전 권장 D)
| 차원 | 평가 |
|------|------|
| AI 채팅 입력 | ✗ 윈도우 없음 → 대화 불가 |
| 작업 승인 표시 | ✗ |
| 본 요구사항 | **부적합** |

### 3.2 B. wizard + tray + Chat 단일창 (1탭, 채팅만)
| 차원 | 평가 |
|------|------|
| AI 채팅 | ✓✓ 채팅 중심 |
| Status | △ 채팅창 상단 띠로 압축 |
| Diagnostics | △ 메뉴 dialog 또는 채팅창 안 sub-panel |
| 구현 단순 | ✓ 단일창 1탭 |
| 정보 밀도 | △ 상태/진단이 보조로 묻힘 |
| **총평** | 채팅 중심엔 OK 하나 진단 접근성 낮음 |

### 3.3 C. wizard + tray + 3탭 미니창 (Chat / Status / Diagnostics) ⭐ 권장
| 차원 | 평가 |
|------|------|
| AI 채팅 | ✓✓ Chat 탭이 default |
| Status | ✓✓ 별도 탭, 명확 |
| Diagnostics | ✓ 별도 탭, 한 화면 |
| 정보 밀도 | ✓ 각 탭 단일 책임 |
| 학습 비용 | ✓ 3탭 — 인지 부담 적음 |
| 운영자 중복 | ✓ 채팅/진단은 사용자 책임, 통계/관리는 React |
| **총평** | **AI 채팅 + 진단/상태가 모두 필요한 본 요구에 정확** |

### 3.4 D. React desktop/ui 와 통합
| 차원 | 평가 |
|------|------|
| 코드 공유 | ✓✓ |
| 라인 잠금 | ✗ desktop/ui 수정 금지 정책 위반 |
| 운영자/사용자 혼재 | ✗ Persona 혼란 |
| 본 라인 | **금지** |

### 3.5 비교 매트릭스

| 항목 | A wizard+tray | B Chat단일 | C **3탭** | D React통합 |
|------|---------------|------------|----------|--------------|
| AI 채팅 적합 | ✗ | ✓✓ | ✓✓ | ✓ |
| Status 명확 | ✓ tray | △ 압축 | ✓✓ | ✓ |
| Diagnostics 접근성 | ✓ dialog | △ sub-panel | ✓✓ | ✓ |
| 구현 난이도 | 낮음 (보정전) | 중간 | 중간 | 높음 |
| 정책 준수 (desktop/ui 미수정) | ✓ | ✓ | ✓ | **✗** |
| 권장 순위 | 4 | 3 | **1** | 5 |

---

## 4. 최종 권장 보정안 = C. wizard + tray + 3탭 미니창

### 4.1 구조 요약
```
┌─ Wizard (첫 실행, 1회) ───────────────────────────┐
│  Step 1 서버 URL → Step 2 등록코드 → Step 3 완료   │
│  Step 3 [시작하기] 누르면 → 메인 윈도우 (3탭) 열림 │
└────────────────────────────────────────────────────┘

┌─ 메인 윈도우 (3탭 미니창, 평소 사용) ──────────────┐
│  [ Chat ] [ Status ] [ Diagnostics ]              │
│  ──────                                           │
│  (탭별 내용)                                       │
│  하단 상태 바 (● 정상 · agent la-xxx***yyy · v0.1) │
└────────────────────────────────────────────────────┘

┌─ Tray (윈도우 최소화 시 상주) ─────────────────────┐
│  ● 연결 상태 (비활성)                              │
│  ───                                              │
│  열기                                              │
│  Chat 열기                                         │
│  상태 보기                                         │
│  진단                                              │
│  ───                                              │
│  재등록                                            │
│  종료                                              │
└────────────────────────────────────────────────────┘
```

### 4.2 창 크기
- 메인 윈도우: **720 × 600** (Chat 위주 → 세로 충분)
- Wizard 다이얼로그: **560 × 480** (기존 유지)
- 재등록 확인: **400 × 200** (기존 유지)

### 4.3 기본 동작
- 메인 윈도우 [X] 닫기 → **최소화 → 트레이로 이동** (실제 종료는 트레이 [종료] 또는 Esc 2회)
- 트레이 [열기] / [Chat 열기] → 메인 윈도우 복원 + 해당 탭 활성

---

## 5. Chat 탭 설계

### 5.1 화면 와이어
```
┌─────────────────────────────────────────────────┐
│  [ Chat ★ ] [ Status ] [ Diagnostics ]          │
├─────────────────────────────────────────────────┤
│                                                 │
│  ┌─ 메시지 목록 (스크롤) ──────────────────┐    │
│  │  AI      안녕하세요. 무엇을 도와드릴까요? │    │
│  │  ───                                     │    │
│  │  나      오늘 일정 알려줘                 │    │
│  │  ───                                     │    │
│  │  AI      네, 오늘 일정은 다음과 같습니다.│    │
│  │          - 09:00 ...                     │    │
│  │  ───                                     │    │
│  │  [작업 위임] 파일을 검색하려고 합니다.    │    │
│  │          [ 승인 ] [ 거절 ]                │    │
│  └────────────────────────────────────────┘    │
│                                                 │
│  ┌─ 입력 ─────────────────────────────────┐    │
│  │ 메시지를 입력하세요…                    │    │
│  └────────────────────────────────────────┘    │
│  [ 전송 ]  (Enter 전송, Shift+Enter 줄바꿈)     │
│                                                 │
│  ⚠ 민감정보(비밀번호/주민번호) 입력 금지        │
└─────────────────────────────────────────────────┘
하단: ● 정상 · la-xxx***yyy · v0.1.0
```

### 5.2 필수 요소
- 메시지 목록 (사용자 / AI / 시스템 [작업 위임 카드] 3종)
- 사용자 입력창 (multiline)
- 전송 버튼 + 단축키 (Enter 전송, Shift+Enter 줄바꿈)
- AI 응답 표시 (`AI` 라벨 + 텍스트)
- 작업 위임 카드 (AI 가 로컬에이전트에게 작업 요청 시) — [승인] / [거절]
- 연결 안 됨 시 입력창 비활성화 + 안내 "연결이 끊겼습니다. 재연결을 기다리거나 [재연결] 클릭"
- 민감정보 입력 경고 배너 (정적 텍스트)

### 5.3 상태별 동작
| 연결 상태 | 입력창 | 전송 버튼 | 배너 |
|-----------|--------|-----------|------|
| HEARTBEAT_OK / CONNECTED | 활성 | 활성 | "● 정상 — AI 와 대화 가능" |
| CONNECTING / RECONNECTING | 비활성 (placeholder "연결 중…") | 비활성 | "● 연결 중…" |
| AUTH_FAILED | 비활성 | 비활성 | "● 인증 실패. [재등록]" |
| SERVER_UNREACHABLE | 비활성 | 비활성 | "● 서버 접속 실패. [재시도]" |
| NOT_REGISTERED | 입력 자체 숨김 | — | "등록이 필요합니다. [등록]" |

### 5.4 작업 위임 카드 (AI → 로컬에이전트)
- AI 가 사용자에게 "다음 작업을 진행할까요?" 카드를 띄움
- 표시: 작업 종류 / 위험도 (low / medium / high) / 영향 범위 요약
- 버튼: [승인] (높은 위험 시 다시 한번 확인 dialog) / [거절]
- **실제 작업 실행은 본 공정 OUT_OF_SCOPE** — UI 만 정의

### 5.5 보안 / PII
- **device_token / registration_code 절대 화면 표시 0**
- **agent_id 는 마스킹** (status 표시 / 메시지 메타에서도)
- **대화 로그 디스크 저장 = OFF 기본** (메모리만, 종료 시 폐기)
- **저장 기능 (Later)** — 사용자 명시 토글 + 위치 안내 + 저장 시 redact 1차
- 사용자 입력에 token-like 문자열 감지 시 경고 ("토큰처럼 보이는 값이 포함됨. 전송할까요?")
- AI 응답 텍스트도 redact 통과 후 표시 (혹시 모를 echo back 방지)

### 5.6 마이크로 카피
| 상황 | 문구 |
|------|------|
| 첫 진입 | "안녕하세요. 무엇을 도와드릴까요?" |
| 빈 입력 전송 | (전송 버튼 비활성) |
| 연결 끊김 입력 | "연결이 끊겼습니다. 재연결을 기다리세요." |
| 민감정보 의심 | "토큰/비밀번호처럼 보이는 값이 포함되어 있습니다. 그래도 전송하시겠어요?" |
| 작업 위임 (low) | "다음 작업을 진행할까요? — {요약}" + [승인][거절] |
| 작업 위임 (high) | 추가 확인 dialog "정말 실행하시겠어요? 영향 범위: {scope}" |

---

## 6. Status 탭 설계

### 6.1 화면 와이어
```
┌─────────────────────────────────────────────────┐
│  [ Chat ] [ Status ★ ] [ Diagnostics ]          │
├─────────────────────────────────────────────────┤
│                                                 │
│     ● 정상                                       │
│                                                 │
│   agent_id          la-9bc***22df                │
│   서버              https://haehan-ai.kr/...     │
│   WS                wss://haehan-ai.kr/...       │
│   마지막 heartbeat  2026-05-21 14:23:01         │
│   재연결 횟수       0                            │
│                                                 │
│   [ 재연결 ]    [ 재등록 ]                       │
│                                                 │
└─────────────────────────────────────────────────┘
```

### 6.2 필수 표시
- 현재 연결 상태 (한글 라벨 + 색 dot)
- agent_id 마스킹
- server_url (query 자동 redact)
- ws_url (정규화된 형태)
- 마지막 heartbeat ISO
- 재연결 횟수 (운영 신호)

### 6.3 버튼
- **재연결**: 현재 WS 닫고 즉시 재시도
- **재등록**: §7 (재등록 확인 dialog)

---

## 7. Diagnostics 탭 설계

### 7.1 화면 와이어
```
┌─────────────────────────────────────────────────┐
│  [ Chat ] [ Status ] [ Diagnostics ★ ]          │
├─────────────────────────────────────────────────┤
│                                                 │
│   ┌─ 진단 (마스킹 적용) ─────────────────────┐ │
│   │ 상태               ● 정상                  │ │
│   │ agent_id           la-9bc***22df          │ │
│   │ 서버               https://...             │ │
│   │ WS                 wss://...               │ │
│   │ 마지막 heartbeat   2026-05-21 14:23:01    │ │
│   │ 재연결 횟수        0                       │ │
│   │ 마지막 오류        —                        │ │
│   │                                            │ │
│   │ 조치:                                      │ │
│   │   — (오류 없음)                             │ │
│   └────────────────────────────────────────────┘ │
│                                                 │
│   [ 복사 ]    [ 재등록 ]                          │
│                                                 │
│   ⓘ device_token / registration_code 원문은     │
│      어디에도 노출되지 않습니다.                 │
└─────────────────────────────────────────────────┘
```

### 7.2 데이터 source
- `connection_diagnostics.build_diagnostics(...)` + `render_user_block(...)` 그대로 사용
- 오류 코드별 한글 안내 → `connection_diagnostics.explain_error(code)`

### 7.3 [복사]
- 클립보드에 텍스트 (마스킹된 본문만)
- agent_id raw / token / code 절대 미포함

### 7.4 OUT_OF_SCOPE (MVP)
- 로그 export (JSON Lines)
- 메시지 history download
- 시스템 정보 자동 수집

---

## 8. Wizard 설계 (유지)

직전 설계서 §5.1~5.3 의 **3 step wizard 그대로 유지**.

보정 사항:
- Step 3 **[시작하기]** 누르면 메인 윈도우 (3탭) 열리고 **Chat 탭 활성**.
- Step 3 의 autostart 토글 유지.

---

## 9. Tray 메뉴 (보정)

```
┌──────────────────────────┐
│ ● 정상                    │ ← 상태 표시 (비활성)
├──────────────────────────┤
│ 열기                      │ ← 메인 윈도우 복원 (마지막 탭)
│ Chat 열기                 │ ← Chat 탭 활성으로 복원
│ 상태 보기                 │ ← Status 탭 활성으로 복원
│ 진단                      │ ← Diagnostics 탭 활성으로 복원
├──────────────────────────┤
│ Windows 시작 시 자동실행   │ ← 토글
├──────────────────────────┤
│ 재등록                    │ ← 확인 dialog
│ 종료                      │ ← 즉시 종료
└──────────────────────────┘
```

차이점 (vs 직전 설계):
- 직전: 트레이만 → 윈도우 없음
- 보정: 트레이 + 메인 윈도우 (최소화 시 트레이 상주)
- 메뉴 항목 [Chat 열기 / 상태 보기 / 진단] 추가 — 탭 직접 진입

---

## 10. AI API 연동 범위 분리

본 설계서는 **UI 만** 정의.

| 단계 | 공정 |
|------|------|
| AI API 클라이언트 (요청/응답/스트림/오류 처리) | `AGENT_AI_CHAT_API_CLIENT_01` (별도) |
| Chat UI 구현 + 기존 GUI 보정 | `AGENT_GUI_CHAT_IMPLEMENTATION_01` (별도) |
| 작업 위임 카드 → 실제 실행 흐름 | `AGENT_AI_TASK_DELEGATION_01` (별도, 더 후) |

### 10.1 API 추상 정의 (UI 가 의존하는 인터페이스만)
```
AiChatClient (UI 가 import 하는 protocol):
  - send_user_message(text: str, session_id: str) -> StreamIterator | str
  - receive_event() -> AiChatEvent (message | task_delegation | error)
  - cancel() -> None
```
*실제 구현은 별도 공정. UI 는 mock 으로 먼저 개발 가능.*

### 10.2 작업 위임 데이터
```
TaskDelegationCard:
  - id: str
  - kind: str (search_file / open_url / read_doc / ...)
  - risk: "low" | "medium" | "high"
  - summary_kr: str
  - scope_kr: str
```
*실제 task 실행 시 server 의 local_agent_router → device_token 인증 흐름 재사용.*

---

## 11. MVP / Later / 하지 않을 항목 (재정의)

### 11.1 MVP (이번 보정 후 다음 구현)
1. wizard 3 step 유지
2. 메인 윈도우 (3탭) 신규
3. Chat 탭 UI (메시지 목록 / 입력 / 전송 / Enter 처리)
4. Status 탭 UI
5. Diagnostics 탭 UI (기존 render_user_block 재사용)
6. tray 메뉴 보정 (탭 직접 진입 항목 추가)
7. 연결 상태 기반 입력 활성/비활성 자동 제어
8. redaction (device_token / registration_code / agent_id 마스킹)
9. CLI 모드 회귀 유지

### 11.2 Later (별도 공정)
- 실제 AI API 연동 (`AGENT_AI_CHAT_API_CLIENT_01`)
- 작업 위임 실행 흐름 (`AGENT_AI_TASK_DELEGATION_01`)
- 대화 저장 (사용자 명시 토글)
- 파일 첨부
- 음성 입력
- 명령 승인 흐름 강화 (high risk 추가 확인)
- 메시지 검색
- 다국어
- Diagnostics 로그 export

### 11.3 하지 않을 항목 (본 라인 영구 제외)
- 운영자 admin 패널 / task 관리 dashboard
- React `desktop/ui` 통합 또는 임베드
- 상세 통계 / 그래프
- 다른 사용자의 agent 모니터링
- 서버측 task router 변경
- desktop/ui_dist 수정

---

## 12. 구현 가이드 (다음 공정에 전달)

### 12.1 `AGENT_AI_CHAT_API_CLIENT_01` (먼저)
- `local_agent/ai_chat_client.py` 신규
- protocol: send / receive_event / cancel
- 초기에는 mock backend → 이후 server proxy 또는 직접 API
- 단위 테스트: send / receive / error 경로
- token / code redact 통과 후 전송 (보내기 전 redact 1차)

### 12.2 `AGENT_GUI_CHAT_IMPLEMENTATION_01` (다음)
- `gui_app.py` 보정:
  - 윈도우 크기 720×600
  - 3탭 CTkTabview 또는 자체 탭 구성
  - Chat 탭 — `gui_chat_panel.py` 분리 (재사용성)
  - Status 탭 — 기존 코드 재사용
  - Diagnostics 탭 — render_user_block 재사용
- `gui_tray.py` 보정 — 메뉴 항목 추가 (탭 직접 진입)
- `gui_chat_state.py` 신규 — 메시지 목록 / 입력 상태 (gui_state.GuiController 와 분리)
- 단위 테스트 16+ (탭 라우팅, 입력 활성/비활성, redact, 작업 위임 카드 표시)

### 12.3 회귀 보장
- CLI (--self-test / --diagnostics / --register / --agent-id / --reset) 0 회귀
- gui_state 단위 테스트 100% 유지
- token leak 검사 동일 또는 강화

---

## 13. desktop/ui (React 운영자 앱) 미수정

본 설계 보정도 **`HaehanAI-Agent.exe` 라인 한정**.

- `desktop/ui/*` — 절대 수정 안 함
- `desktop/ui_dist/*` — 절대 수정 안 함
- React / Vite / Tailwind / shadcn — 건드리지 않음
- 운영자 UI 와 통합 시 별도 공정 `REACT_GUI_AGENT_INTEGRATION_01`

---

## 14. 보안 / PII UX (재확인)

직전 설계서 §8 정책 **그대로 유지** + 채팅 관련 추가:

### 14.1 채팅 추가 항목
- **대화 로그 디스크 저장 기본 OFF** (메모리만)
- 사용자 입력에 token-like 패턴 감지 → 경고 prompt (취소 가능)
- AI 응답도 redact 통과 후 표시
- 작업 위임 카드의 `kind / scope_kr / summary_kr` 는 마스킹된 식별자만 사용
- **세션 id 는 random uuid** (agent_id 와 무관)

### 14.2 절대 금지
- 사용자 입력 / AI 응답 / 작업 위임 페이로드에 raw token / code / cookie 노출 0
- 대화 history 자동 외부 전송 0
- 마이크 / 화면 캡처 자동 권한 요청 0 (Later 명시 토글 시점에만)

---

## 15. 결정 / 승인 요청

본 보정 설계서 승인 시:
- 다음 공정 1 = **`AGENT_AI_CHAT_API_CLIENT_01`** (mock 부터)
- 다음 공정 2 = **`AGENT_GUI_CHAT_IMPLEMENTATION_01`** (3탭 미니창 구현)
- 작업 위임 실행은 한참 후 별도 공정

승인 의견:
- (a) 권장 C (3탭 미니창) 그대로 진행
- (b) 차선 B (단일창 1탭) 로 변경
- (c) 일부 수정 (탭 명칭 / 위치 / 키 단축키 / 작업 위임 위치)
- (d) 보류
