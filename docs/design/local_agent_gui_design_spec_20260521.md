# Haehan AI Local Agent — GUI 디자인 스펙 (제품 등급)

문서 종류: **디자인 설계서** (구현 전 승인용)
대상: `HaehanAI-Agent.exe --gui` 진입점
스타일: **VS Code / JetBrains 사이드바 4탭 + 레벨 1 (제품용)**
HEAD: `b4faa00`

---

## 1. 디자인 원칙

1. **명확성 우선** — 사용자가 "지금 무엇이 일어나고 있는가" 를 0.5초 안에 파악.
2. **상태가 가장 큰 정보** — 상단 status bar + 사이드바 dot + 우측 카드 모두 동일 상태 source.
3. **PII 안전 시각화** — agent_id 마스킹, registration_code show='●', device_token 절대 미노출.
4. **모션은 의미 전달용** — 펄스/페이드는 *상태 변화* 의 신호. 장식용 애니메이션 금지.
5. **키보드 우선** — Ctrl+R 재등록 / F1 진단 / Esc 종료 / Tab 포커스 이동.

---

## 2. 디자인 토큰

### 2.1 컬러 (Dark — 기본)

| 토큰 | hex | 용도 |
|------|-----|------|
| `bg.canvas` | `#0B0D11` | 윈도우 배경 (가장 어두움) |
| `bg.panel` | `#11141A` | 사이드바 |
| `bg.surface` | `#161A22` | 메인 영역 |
| `bg.card` | `#1C2129` | 카드/입력 |
| `bg.card-hover` | `#222936` | 카드 hover |
| `bg.elevated` | `#252B36` | 메뉴/팝업 |
| `border.subtle` | `#22272F` | 카드 보더 |
| `border.default` | `#2D333D` | 입력 보더 |
| `border.focus` | `#6366F1` | 포커스 링 |
| `fg.default` | `#E6E9EF` | 본문 |
| `fg.muted` | `#9AA3B2` | 라벨 |
| `fg.subtle` | `#6B7484` | 캡션 |
| `fg.faint` | `#4A5160` | 비활성 |
| `accent.500` | `#6366F1` | primary 버튼 |
| `accent.400` | `#818CF8` | hover |
| `accent.600` | `#4F46E5` | pressed |
| `success` | `#10B981` | 연결됨/heartbeat |
| `success.bg` | `#0E2B1F` | 성공 카드 배경 |
| `warning` | `#F59E0B` | 재연결/대기 |
| `warning.bg` | `#2B1F0A` | |
| `danger` | `#EF4444` | 인증 실패 |
| `danger.bg` | `#2B1212` | |
| `info` | `#3B82F6` | 진단/로그 |

### 2.2 타이포그래피 (8pt 베이스라인)

| 토큰 | font / size / weight | 용도 |
|------|----------------------|------|
| `display` | Segoe UI 22 / Semibold | 헤더 브랜드 |
| `title` | Segoe UI 16 / Semibold | 페이지 제목 |
| `subtitle` | Segoe UI 13 / Semibold | 카드 헤더 |
| `body` | Segoe UI 12 / Regular | 본문 |
| `label` | Segoe UI 11 / Medium | 입력 라벨 |
| `caption` | Segoe UI 10 / Regular | 보조 설명 |
| `mono` | Consolas 12 / Regular | agent_id, URL, log |
| `mono-strong` | Consolas 13 / Semibold | 상태 텍스트 |

### 2.3 스페이싱 (8px grid)

- `space.1` = 4px (인라인)
- `space.2` = 8px (요소 간 좁은 간격)
- `space.3` = 12px (라벨↔입력)
- `space.4` = 16px (카드 내부 패딩)
- `space.5` = 20px (카드 ↔ 카드)
- `space.6` = 24px (섹션 간)
- `space.8` = 32px (페이지 가장자리)

### 2.4 모서리 / 그림자

- `radius.sm` = 6px (입력)
- `radius.md` = 8px (버튼)
- `radius.lg` = 12px (카드)
- `radius.xl` = 16px (모달)
- shadow: customtkinter 한계상 그림자 불가 → 보더 + 톤 차이로 깊이감

### 2.5 모션

- `motion.fast` = 120ms (hover)
- `motion.base` = 200ms (focus, state transition)
- `motion.slow` = 400ms (page transition)
- `motion.pulse` = 1600ms (heartbeat dot — opacity 0.4→1.0→0.4)
- easing = ease-out (감속) 기본

---

## 3. 정보 아키텍처

### 3.1 윈도우 구조 (820 × 620, 최소 720×560)

```
┌──────────────────────────────────────────────────────────────┐
│  ▣  Haehan AI · Local Agent              v0.1.0   ─  □  ✕   │ ← Title bar (32px)
├──────────┬───────────────────────────────────────────────────┤
│  Logo    │                                                   │
│          │                                                   │
│  ⌂ Dash  │           ACTIVE PAGE CONTENT                     │
│  ◆ Reg   │           (48px 내부 패딩)                         │
│  ▦ Logs  │                                                   │
│  ⚙ Set   │                                                   │
│          │                                                   │
│  ─────   │                                                   │
│          │                                                   │
│  ⓘ Help  │                                                   │
├──────────┴───────────────────────────────────────────────────┤
│  ● HEARTBEAT_OK · agent la-612***5dd3 · last 12:34:56  v0.1.0│ ← Status bar (28px)
└──────────────────────────────────────────────────────────────┘
   72px           나머지
```

### 3.2 사이드바 (72px wide, fixed)

| 아이콘 | 페이지 | 단축키 |
|--------|--------|--------|
| ⌂ | Dashboard | Ctrl+1 |
| ◆ | Registration | Ctrl+2 |
| ▦ | Logs | Ctrl+3 |
| ⚙ | Settings | Ctrl+4 |
| ⓘ | Help / About | F1 |

- 활성 페이지: accent.500 좌측 4px 세로 바 + 아이콘 색 fg.default
- 비활성: 아이콘 색 fg.subtle, hover 시 fg.default + bg.card-hover
- 아이콘은 unicode glyph (이모지 금지 — 시스템 폰트 차이 회피)

### 3.3 상태 바 (하단 28px)

좌측 → 우측:
- 상태 도트 (펄스 애니메이션 — CONNECTING/RECONNECTING 시)
- 상태 텍스트 (한글 라벨)
- 구분점 `·`
- agent 마스킹 ID (mono)
- 구분점
- last heartbeat 시각 (mono)
- (우측 끝) 버전 + 서명 상태 (`unsigned` warning 색)

---

## 4. 페이지별 와이어프레임

### 4.1 Dashboard (기본 페이지)

```
┌────────────────────────────────────────────────────────────┐
│  Dashboard                                                 │
│  ─────────────                                             │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  ● HEARTBEAT_OK                                      │  │ ← 상태 카드 (대형)
│  │  ─────────────                                       │  │   bg = success.bg
│  │                                                      │  │   글자 색 = success
│  │  agent_id        la-612***5dd3        (mono 13)      │  │
│  │  last heartbeat  2026-05-21 12:34:56  (mono 12)      │  │
│  │  reconnect       0                                   │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                            │
│  ┌────────────────────────────┐  ┌──────────────────────┐  │
│  │  Heartbeat                 │  │  Network             │  │
│  │  ─────────                 │  │  ───────             │  │
│  │  ▁▂▃▅▆▇█▇▆▅▃▂▁▂▃▅▆▇█▇▆▅▃   │  │  proxy   none        │  │
│  │  (sparkline 최근 60초)     │  │  rtt     124 ms      │  │
│  │  60s · 12 heartbeats       │  │  uptime  00:24:17    │  │
│  └────────────────────────────┘  └──────────────────────┘  │
│                                                            │
│  Quick actions                                             │
│  [ 재연결 ]  [ 진단 보기 ]  [ 재등록 ]                      │
└────────────────────────────────────────────────────────────┘
```

빈 상태 (미등록):
- 상태 카드: bg.card, "● 미등록 — 등록코드로 시작하세요"
- 우측 sparkline 자리에: 안내 카드 "관리자에게 등록코드를 요청한 뒤 Registration 탭에서 입력하세요"
- Quick actions 비활성 → "Registration 으로 이동" 단일 버튼

### 4.2 Registration

```
┌────────────────────────────────────────────────────────────┐
│  Registration                                              │
│  ─────────────                                             │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  ▸ Server                                            │  │ ← collapsible 섹션
│  │     서버 URL                                         │  │
│  │     ┌────────────────────────────────────────────┐   │  │
│  │     │ https://haehan-ai.kr/orchestrator          │   │  │
│  │     └────────────────────────────────────────────┘   │  │
│  │     caption: WebSocket: wss://.../local-agents/ws    │  │
│  │                                                      │  │
│  │  ▸ Registration code                                 │  │
│  │     관리자에게 발급받은 1회용 코드 · 10분 유효        │  │
│  │     ┌────────────────────────────────────────────┐   │  │
│  │     │  ● ● ● ● ● ● ● ● ● ● ● ● ● ●               │   │  │
│  │     └────────────────────────────────────────────┘   │  │
│  │     [ ☐ 입력 보이기 ]                                │  │
│  │                                                      │  │
│  │  ▸ Device info  (자동 수집)                          │  │
│  │     host           DESKTOP-XXXX                      │  │
│  │     os             Windows 11                        │  │
│  │     version        0.1.0                             │  │
│  │                                                      │  │
│  │                       ┌─────────────────────────┐    │  │
│  │                       │   Register →            │    │  │
│  │                       └─────────────────────────┘    │  │
│  │                       accent.500 primary 버튼        │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                            │
│  caption.subtle: device_token · registration_code 원문은   │
│                  화면·로그·보고서에 노출되지 않습니다.       │
└────────────────────────────────────────────────────────────┘
```

상태 별 동작:
- **로딩 중** (register 진행): 버튼 → "등록 중…" + 회전 spinner (PIL 동적 이미지)
- **성공**: toast 상단 슬라이드 인 "등록 성공: la-xxx***yyy" 3초 후 사라짐 + Dashboard 로 전환
- **실패**: 코드 입력 보더 → danger 색 + 캡션 위치에 오류 메시지 (한글)

### 4.3 Logs

```
┌────────────────────────────────────────────────────────────┐
│  Logs                                                      │
│  ────                                                      │
│                                                            │
│  Filter: [ All ▾ ] [ INFO ▾ ]      [ Clear ] [ Export ]    │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 12:34:56  INFO   register-with-code 호출 시작        │  │ ← mono 11
│  │ 12:34:57  INFO   register 성공 · agent_id la-612*** │  │   bg.card
│  │ 12:34:58  INFO   WebSocket 연결 시도                 │  │   tail -100
│  │ 12:34:58  INFO   auth_ok                             │  │
│  │ 12:35:28  INFO   heartbeat_ack                       │  │   상태별 색:
│  │ 12:35:58  INFO   heartbeat_ack                       │  │   INFO  fg.muted
│  │ 12:36:28  WARN   reconnect attempt 1                 │  │   WARN  warning
│  │ ...                                                  │  │   ERR   danger
│  │                                                      │  │
│  │  [ 자동 스크롤 ☑ ]                                   │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                            │
│  caption: device_token / registration_code 는 자동 redact  │
└────────────────────────────────────────────────────────────┘
```

- 메모리 ring buffer 1000 라인 (앞쪽 drop)
- 정규식 redact 1차 통과: `device_token=...` / `registration_code=...` / `token: ...`
- Export: JSON Lines (redact 적용된 사본만)

### 4.4 Settings

```
┌────────────────────────────────────────────────────────────┐
│  Settings                                                  │
│  ────────                                                  │
│                                                            │
│  ▸ 서버                                                    │
│      서버 URL                                              │
│      [ https://haehan-ai.kr/orchestrator           ]       │
│      WebSocket 자동 활성  ☑                                 │
│      heartbeat 주기 (초)  [ 30 ]                            │
│                                                            │
│  ▸ 외관                                                    │
│      테마           ◉ Dark    ○ Light    ○ System          │
│      포커스 크기    ◉ 보통    ○ 큼       ○ 더 큼            │
│                                                            │
│  ▸ 토큰 저장소                                              │
│      backend          WinVaultKeyring (available)          │
│      [ 토큰 삭제 — 재등록 필요 ]   ← danger ghost button    │
│                                                            │
│  ▸ 정보                                                    │
│      버전          0.1.0                                   │
│      sha256        72b59edb...d3e8  [ 복사 ]                │
│      서명          unsigned (코드 서명 OUT_OF_SCOPE)        │
│      라이센스      MIT                                     │
│      [ 도움말 보기 ]                                        │
└────────────────────────────────────────────────────────────┘
```

---

## 5. 컴포넌트 카탈로그

### 5.1 Button

| 변형 | 배경 | 글자 | 보더 | 용도 |
|------|------|------|------|------|
| Primary | accent.500 → 400 hover → 600 pressed | white | none | 등록, 저장 |
| Secondary | bg.card → card-hover | fg.default | border.default | 진단 보기 |
| Ghost | transparent → bg.card-hover | fg.muted | border.subtle | 보조 |
| Danger | transparent → danger.bg | danger | border subtle | 토큰 삭제 |
| Success | success → 0EA372 | white | none | 연결 시작 |

높이 36px, 가로 padding 16px, radius 8px.
focus: border.focus 2px outer ring.

### 5.2 Input (text / password)

- 높이 38px, padding 12px, radius 6px
- bg.card, border.default, font body
- placeholder: fg.subtle
- focus: border = border.focus + 2px ring
- error: border = danger + caption danger 색
- password: show='●' (별표 대신 검은 점)

### 5.3 Card

- bg.card, border border.subtle, radius 12px
- 헤더 (subtitle, fg.default) + 본문 (body)
- 패딩 16px / 헤더-본문 간격 12px
- hover: card-hover (action 가능 카드만)

### 5.4 Status pill / badge

- 높이 24px, 가로 padding 10px, radius 12px
- 좌측 dot (8px) + 한글 라벨
- 색 매핑은 §2.1 의 상태 색

### 5.5 Section accordion

- 좌측 ▸ / ▾ 삼각형 (12px)
- 헤더 클릭 → expand/collapse with 200ms ease
- 펼친 상태가 기본

### 5.6 Toast (상단 슬라이드)

- 우상단 24px 떨어진 위치에서 등장
- 너비 360px, height 64px
- bg.elevated, border subtle, radius 12px
- 좌측 icon (성공/오류/정보), 본문, 닫기 X
- 3초 후 자동 fade-out

### 5.7 Spinner

- PIL 로 12px 원호 그림
- after(80ms) 마다 회전 30도
- 버튼 내부에 사용 시 좌측 텍스트 마진 8px

### 5.8 Sparkline

- PIL 로 64×16 SVG-like polyline
- 최근 60개 데이터 포인트
- 색 accent.500, 채우기 accent with alpha 0.2

---

## 6. 상태 다이어그램 (시각화 매핑)

| 상태 | 사이드바 dot | 상태 카드 색 | 상태 바 텍스트 | 모션 |
|------|--------------|--------------|----------------|------|
| NOT_REGISTERED | fg.faint | bg.card / fg.muted | "● 미등록" | — |
| CONNECTING | warning | warning.bg | "● 연결 중…" | pulse 1600ms |
| AUTHENTICATING | warning | warning.bg | "● 인증 중…" | pulse 800ms (빠르게) |
| CONNECTED | success | success.bg | "● 연결됨" | — |
| HEARTBEAT_OK | success | success.bg | "● 정상" | dot subtle pulse 4s |
| DISCONNECTED | fg.subtle | bg.card | "● 끊김" | — |
| AUTH_FAILED | danger | danger.bg | "● 인증 실패 — 재등록 필요" | dot quick blink x3 |
| RECONNECTING | warning | warning.bg | "● 재연결 중…" | pulse 1600ms |
| SERVER_UNREACHABLE | danger | danger.bg | "● 서버 접속 실패" | — |

---

## 7. 키보드 / 접근성

| 키 | 동작 |
|----|------|
| `Ctrl+1..4` | 페이지 전환 |
| `Ctrl+R` | 재등록 (token 삭제 + Registration 탭) |
| `Ctrl+L` | Logs 탭 |
| `Ctrl+,` | Settings |
| `F1` | 도움말 |
| `Esc` | 모달 닫기 / 종료 확인 |
| `Tab / Shift+Tab` | 포커스 이동 |
| `Enter` | 활성 버튼 / 폼 제출 |

포커스 링: 2px border.focus + 1px 보조 ring (총 3px 시각).
모든 인터랙티브 요소는 focus 표시 필수.

---

## 8. 마이크로 카피 (한글)

| 상황 | 문구 |
|------|------|
| 미등록 안내 | "등록코드로 시작하세요 — 관리자가 발급한 1회용 코드를 받아 Registration 탭에서 입력합니다." |
| 등록 성공 | "등록 성공 · {agent_id_masked}" |
| 등록 실패 (코드 잘못) | "등록코드가 유효하지 않습니다. 코드를 다시 확인하세요." |
| 등록 실패 (만료) | "등록코드가 만료되었습니다. 관리자에게 새 코드를 요청하세요." |
| 등록 실패 (서버) | "서버에 접속할 수 없습니다. 서버 URL과 네트워크를 확인하세요." |
| 4401 | "장치 인증 실패. device_token 이 폐기되었을 수 있습니다. 재등록하세요." |
| token 삭제 확인 | "저장된 device_token 을 삭제합니다. 이후 재등록이 필요합니다. 계속할까요?" |

---

## 9. PII 안전 정책 (디자인 레벨 강제)

1. **device_token** 은 UI 어디에도 표시되지 않는다. 백그라운드 변수에서만 사용 후 폐기.
2. **registration_code** 입력은 `show='●'` + "입력 보이기" 토글 한정. 토글 OFF가 기본.
3. **agent_id** 는 어디서나 `la-xxx***yyy` 마스킹. Logs 탭도 마스킹.
4. **URL 의 query string** 에 token / device_token / registration_code / auth / session 등 키가 있으면 `[REDACTED]` 치환 후 표시.
5. **Logs export** 시 동일 redact 1차 적용.
6. **Toast 의 본문** 에 token / code 노출 금지 — 마스킹된 식별자만.

---

## 10. 구현 의존성

| 추가 | 용도 | 필수 / 옵션 |
|------|------|------------|
| `customtkinter 5.2+` | dark mode + radius + button | 필수 |
| `pystray 0.19+` | 시스템 트레이 | 필수 |
| `Pillow 12+` | 아이콘 / sparkline / spinner | 필수 |
| `tkfontawesome` 또는 unicode | 사이드바 아이콘 | unicode 선택 (의존성 ↓) |

**결정**: unicode glyph 사용 (의존성 추가 회피). 아이콘은 ⌂ ◆ ▦ ⚙ ⓘ 등 시스템 폰트 호환 문자만.

PyInstaller hidden imports 추가:
- 기존: `tkinter / pystray / PIL / customtkinter` 유지
- 추가 불필요

---

## 11. 빌드 / 검증 계획

1. `gui_app.py` 전면 재작성 (사이드바 + 4탭 + 페이지 모듈화)
2. `gui_state.py` — 변경 없음 (기존 상태 머신 그대로 사용)
3. `gui_tray.py` — 변경 최소화 (메뉴 항목 4탭과 동기화)
4. `gui_icons.py` 신규 — PIL 로 아이콘 / spinner / sparkline 생성
5. `gui_log_buffer.py` 신규 — 1000-line ring buffer + redact
6. 단위 테스트 추가:
   - 페이지 라우팅 (Ctrl+1..4)
   - log redact 패턴
   - toast 자동 사라짐
   - sparkline 데이터 → 이미지 변환
   - 빈 상태 / 오류 상태 UI 트리거
7. PyInstaller 재빌드 + 6초 launch smoke
8. 회귀 — 기존 24+17+25+17 = 83 PASS 유지

---

## 12. 적용 시 산출물

- `local_agent/gui_app.py` (전면 재작성)
- `core/agent_runtime/gui/gui_icons.py` (신규)
- `core/agent_runtime/gui/gui_log_buffer.py` (신규)
- `local_agent/gui_tray.py` (메뉴 4탭 동기화)
- `tests/test_local_agent_gui_pages.py` (신규 12+ 테스트)
- `docs/design/local_agent_gui_design_spec_20260521.md` (본 문서)
- 빌드 후 `dist/HaehanAI-Agent/HaehanAI-Agent.exe` — sha256 갱신

**dist 산출물 git commit 제외** (.gitignore 적용 유지).

---

## 13. 다음 단계

본 스펙 승인되면:
1. `gui_icons.py` (PIL 아이콘) 먼저 작성
2. `gui_log_buffer.py` (redact) 작성
3. `gui_app.py` 사이드바 + 4페이지 구현
4. 테스트 + 빌드 + launch smoke
5. 커밋

승인 부탁드립니다. 또는 수정 의견 (특정 페이지 레이아웃 / 컬러 / 단축키) 알려주시면 반영 후 구현.
