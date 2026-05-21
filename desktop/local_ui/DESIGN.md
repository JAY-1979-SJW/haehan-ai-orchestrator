# Haehan AI 데스크탑 앱 UI 설계서 v2

> 기준: 사내 표준 디자인 시스템(`00.디자인시스템`) + Claude 데스크탑 UX 패턴  
> 작성일: 2026-05-19

---

## 1. 시스템 전체 구조

데스크탑 앱은 단순 화면이 아니라 **서버 ↔ 로컬 에이전트 ↔ AI 브라우저** 전체를 사용자가 한 곳에서 확인·제어하는 통합 허브입니다.

```
┌──────────────────────────────────────────────────────────────┐
│                    서버 (포트 8000)                            │
│  FastAPI · AI Planner · Task Queue · Approval Gate           │
│  WebSocket /ws/desktop  →  Push (task / result / browser)    │
└──────────────────┬───────────────────────────────────────────┘
                   │ WebSocket (자동 재연결)
┌──────────────────▼───────────────────────────────────────────┐
│           로컬 서버 (포트 8765)  desktop/local_server.py       │
│  정적 파일 서빙 · UI 브로커 · 메뉴 설정 저장                   │
│  WebSocket /ws/ui  ↔  UI 클라이언트(app.js)                   │
└──────┬───────────────────────────────┬────────────────────────┘
       │ WebSocket                     │ WS Push (browser_status)
┌──────▼──────┐               ┌────────▼──────────────┐
│  로컬 UI    │               │  AI 브라우저 (CDP)     │
│  index.html │               │  백그라운드 · 화면 없음 │
│  style.css  │               │  결과 → 채팅창 보고    │
│  app.js     │               └───────────────────────┘
└──────▲──────┘
┌──────┴──────┐
│  PyQt6      │  webview_app.py
│  WebEngine  │  http://127.0.0.1:8765
└─────────────┘
```

### 데이터 흐름

| 방향 | 경로 | 내용 |
|------|------|------|
| 서버 → 앱 | WS Push | task, result(AI 답변), browser_status |
| 앱 → 서버 | WS Send | chat(메시지), approve, reject |
| AI브라우저 → 앱 | WS Push | browser_status (URL/포트/상태), screenshot |

---

## 2. 디자인 원칙

| # | 원칙 | 설명 |
|---|------|------|
| 1 | 채팅 우선 | 첫 화면 = 채팅. AI 결과는 모두 채팅창으로 보고 |
| 2 | 허브 구조 | 사이드바로 전체 기능 전환. 패널 교체 방식 |
| 3 | 최소 클릭 | 자주 쓰는 기능은 2클릭 이내 접근 |
| 4 | 역할 기반 노출 | admin/owner 전용 메뉴는 일반 사용자에게 미노출 |
| 5 | 읽기 전용 MVP | 조회·채팅·승인만. 실행·결제·배포 버튼 없음 |
| 6 | 표준 색상 | 사내 디자인 시스템 토큰 준수 (navy/orange) |

---

## 3. 색상 토큰

표준 디자인 시스템(`tokens/colors.ts`) 기준으로 매핑합니다.

```css
:root {
  --bg:         #0F1117;               /* 앱 최외곽 다크 */
  --surface:    #1E2D4A;               /* 사이드바 = navyBase */
  --surface2:   #253661;               /* hover = navyHover */
  --surface3:   #1E293B;               /* 카드·패널 = navySurface */
  --accent:     #F97316;               /* primaryOrange — CTA, active */
  --accent2:    #EA580C;               /* hover */
  --accent-bg:  rgba(249,115,22,.12);
  --accent-bdr: rgba(249,115,22,.30);
  --text:       #E2E8F0;
  --text-sub:   #94A3B8;
  --text-dim:   #4A5568;
  --green:      #059669;
  --red:        #DC2626;
  --yellow:     #D97706;
  --border:     #2A3A5C;
  --radius:     8px;
  --trans:      0.2s cubic-bezier(.4,0,.2,1);
  font-family:  'Pretendard', -apple-system, 'Segoe UI', sans-serif;
}
```

---

## 4. 전체 레이아웃

```
#app  (flex, height:100vh)
├── .sidebar  240px  ← navy 배경, 접으면 56px
└── #main     flex:1
    └── #panels
        └── .panel.active  (한 번에 하나만)
```

---

## 5. 사이드바 구조

### 5-1. 전체 구성

```
┌────────────────────────────────┐
│  🔷 Haehan AI         [◀]      │  ← 로고 + 접기 버튼
├────────────────────────────────┤
│  [+  새 대화          ]        │  ← 항상 표시 (collapsed 시 [+] 아이콘만)
├────────────────────────────────┤
│  ── AI 대화 ──                  │  섹션 레이블
│  💬  대화                  ●   │  ← 기본 active, ● = 현재 위치
│  📋  작업 큐            [3]    │  ← 수신 태스크 배지
│  ✅  승인 대기          [1]    │  ← 승인 필요 배지
├────────────────────────────────┤
│  ── 업무 조회 ──                │
│  📰  뉴스                      │
│  🏗️  EUM 단말기    [admin]     │
├────────────────────────────────┤
│  ── 시스템 ──      [admin]     │
│  🌐  브라우저 상태              │
│  📸  스크린샷      (기본 OFF)   │
│  📊  로그                      │
├────────────────────────────────┤
│  [H]  사용자명  역할  [···]    │  ← 사용자 버튼 (클릭 → 팝오버)
│  ●  연결됨                     │  ← 연결 상태 (클릭 → 재연결)
└────────────────────────────────┘
```

### 5-2. 사이드바 하단 — 핵심 UX 설계

**문제**: 사용자 아바타 클릭 = 메뉴 편집 드로어는 직관적이지 않음.  
아바타는 보통 프로필/계정을 의미합니다.

**해결**: 사용자 버튼 클릭 시 **인라인 팝오버** 표시

```
클릭 전                      클릭 후 (팝오버)
┌──────────────────────┐     ┌──────────────────────┐
│ [H] 사용자  User [···]│  → │ ⚙️  설정              │
│ ●  연결됨            │     │ ☰   메뉴 편집         │
└──────────────────────┘     └──────────────────────┘
```

| 팝오버 항목 | 동작 |
|------------|------|
| ⚙️ 설정 | settings 패널로 이동 |
| ☰ 메뉴 편집 | 우측 드로어 열기 |

**설정 메뉴를 nav에서 제거**: 설정은 팝오버로만 접근 → nav 중복 제거, 공간 절약

**연결 상태**: 클릭하면 재연결 시도 (끊김 시 피드백 제공)

### 5-3. collapsed 상태 (56px)

```
┌──────┐
│  🔷  │  로고 (클릭 → 펼치기)
├──────┤
│  +   │  새 대화
├──────┤
│  💬  │  대화       ← active 시 orange dot
│  📋  │  작업 큐    ← [N] 배지
│  ✅  │  승인 대기  ← [N] 배지
│  📰  │  뉴스
│  🏗️  │  EUM
│  🌐  │  브라우저
│  📊  │  로그
├──────┤
│  [H] │  사용자 (클릭 → 팝오버)
│  ●   │  연결 상태
└──────┘
```

- 텍스트·섹션 레이블 숨김, 아이콘만 표시
- 툴팁(title 속성)으로 항목명 제공
- 설정 항목은 팝오버에서만 접근 → collapsed에서도 사용자 버튼으로 접근 가능

---

## 6. 메뉴 항목 정의

### 6-1. 항목 상세

| ID | 레이블 | 아이콘 | 섹션 | 최소 역할 | 기본 표시 | 배지 |
|----|--------|--------|------|-----------|-----------|------|
| `chat` | 대화 | 💬 | AI 대화 | any | ✅ | — |
| `task_queue` | 작업 큐 | 📋 | AI 대화 | any | ✅ | 수신 태스크 수 |
| `approval` | 승인 대기 | ✅ | AI 대화 | any | ✅ | 승인 대기 수 |
| `news` | 뉴스 | 📰 | 업무 조회 | any | ✅ | — |
| `eum` | EUM 단말기 | 🏗️ | 업무 조회 | admin | ✅ | — |
| `browser` | 브라우저 상태 | 🌐 | 시스템 | admin | ✅ | — |
| `screenshot` | 스크린샷 | 📸 | 시스템 | admin | ❌ | — |
| `logs` | 로그 | 📊 | 시스템 | admin | ✅ | — |

> ⚠️ `settings`는 nav 항목에서 제거 — 하단 사용자 팝오버로만 접근

### 6-2. 역할별 노출

| 역할 | 표시 항목 |
|------|-----------|
| `any` | 대화, 작업 큐, 승인 대기, 뉴스 |
| `admin` | any + EUM, 브라우저 상태, 스크린샷, 로그 |
| `owner` | admin 동일 |

### 6-3. 메뉴 커스터마이징 (드로어)

- 사용자 팝오버 → **☰ 메뉴 편집** → 우측 드로어 슬라이드인
- 항목 **ON/OFF** 토글 (역할 범위 내)
- 드래그로 **순서** 변경
- `desktop/settings/{user_id}.json` 영속 저장
- 역할 필터는 서버 강제 — 클라이언트 우회 불가

### 6-4. `user_settings.py` 수정 필요

`section` 필드 추가 + `settings` 항목 제거:

```python
ALL_MENU_ITEMS = [
  {"id":"chat",       "label":"대화",         "icon":"💬", "section":"AI 대화",   "min_role":"any",   "default":True},
  {"id":"task_queue", "label":"작업 큐",       "icon":"📋", "section":"AI 대화",   "min_role":"any",   "default":True},
  {"id":"approval",   "label":"승인 대기",     "icon":"✅", "section":"AI 대화",   "min_role":"any",   "default":True},
  {"id":"news",       "label":"뉴스",          "icon":"📰", "section":"업무 조회", "min_role":"any",   "default":True},
  {"id":"eum",        "label":"EUM 단말기",    "icon":"🏗️", "section":"업무 조회", "min_role":"admin", "default":True},
  {"id":"browser",    "label":"브라우저 상태", "icon":"🌐", "section":"시스템",    "min_role":"admin", "default":True},
  {"id":"screenshot", "label":"스크린샷",      "icon":"📸", "section":"시스템",    "min_role":"admin", "default":False},
  {"id":"logs",       "label":"로그",          "icon":"📊", "section":"시스템",    "min_role":"admin", "default":True},
  # settings는 팝오버로 접근 — nav에서 제외
]
```

---

## 7. 채팅 패널 UX

### 7-1. 두 가지 상태

```
[초기 상태 — 입력창 중앙]          [대화 중 — 입력창 하단]

         Haehan AI                ┌────────────────────┐
      AI에게 질문하세요            │ 🤖 안녕하세요       │
                                  │ 👤 뉴스 요약해줘    │
  ┌─────────────────────────┐     │ 🤖 오늘 주요 뉴스…  │
  │ 메시지 입력…      [전송] │     ├────────────────────┤
  └─────────────────────────┘     │ 메시지 입력… [전송] │
  Enter전송 · Shift+Enter줄바꿈   └────────────────────┘

  [📰 오늘 뉴스] [🏗️ EUM] [🌐 브라우저]
```

### 7-2. 상태 전환 규칙

| 이벤트 | 동작 |
|--------|------|
| 첫 메시지 전송 | `#panel-chat`에 `.has-messages` 추가 → 입력창 하단 고정 |
| [+ 새 대화] 클릭 | `.has-messages` 제거 → 초기 상태 복원 |
| 시스템 메시지 수신 | `appendSystem()` → 자동으로 has-messages 전환 |

### 7-3. HTML 구조

```html
<div id="panel-chat" class="panel active">

  <!-- 메시지 영역 (초기: 숨김 / 대화중: flex:1) -->
  <div id="chat-scroll">
    <div id="chat-messages"></div>
  </div>

  <!-- 하단 영역 (초기: 화면 중앙 / 대화중: 하단 고정) -->
  <div id="chat-foot">

    <!-- 환영 블록 (대화 시작 후 사라짐) -->
    <div id="chat-welcome">
      <div class="welcome-logo">…SVG…</div>
      <div class="welcome-title">Haehan AI</div>
      <div class="welcome-sub">AI에게 지시하거나 질문하세요</div>
    </div>

    <!-- 입력창 (항상 존재, 위치만 변함) -->
    <div id="input-wrap">
      <div id="input-box">
        <textarea id="chat-input" rows="1" placeholder="메시지 입력…"></textarea>
        <button id="btn-send" class="btn-send" disabled>…</button>
      </div>
      <div class="input-hint">Enter 전송 · Shift+Enter 줄바꿈</div>
    </div>

    <!-- 퀵칩 (대화 시작 후 사라짐) -->
    <div id="chat-chips">
      <button class="chip" onclick="App.quickSend('오늘 뉴스 요약해줘')">📰 오늘 뉴스</button>
      <button class="chip" onclick="App.quickSend('EUM 단말기 현황 확인해줘')">🏗️ EUM 현황</button>
      <button class="chip" onclick="App.quickSend('브라우저 상태 확인해줘')">🌐 브라우저 상태</button>
    </div>

  </div>
</div>
```

### 7-4. CSS 상태 전환

```css
/* 초기: chat-foot이 화면 중앙을 차지 */
#panel-chat { display: flex; flex-direction: column; }
#chat-scroll { flex: 0; height: 0; overflow: hidden; transition: flex 0.35s ease; }
#chat-foot   { flex: 1; display: flex; flex-direction: column;
               align-items: center; justify-content: center;
               max-width: 680px; margin: 0 auto; padding: 0 24px; width: 100%; }

/* 대화 중: 스크롤 영역 확장, 입력창 하단 고정 */
#panel-chat.has-messages #chat-scroll { flex: 1; height: auto; overflow-y: auto; }
#panel-chat.has-messages #chat-foot  { flex: 0 0 auto; max-width: 100%;
                                       border-top: 1px solid var(--border); padding: 12px 24px 16px; }
#panel-chat.has-messages #chat-welcome { display: none; }
#panel-chat.has-messages #chat-chips   { display: none; }
```

---

## 8. 패널별 콘텐츠

### 공통 구조
```
.panel-inner (padding 28px 32px, overflow-y:auto)
├── .panel-head
│   ├── .panel-icon   이모지 24px
│   ├── .panel-title  17px bold
│   └── .panel-desc   12px text-sub
└── 콘텐츠
```

### 8-1. 작업 큐 (`task_queue`)
- **데이터**: 서버 WS Push `type:"task"` → `task_receiver.py` 분류
- **역할**: 서버에서 내려온 **모든 태스크** 현황 모니터링
- **콘텐츠**:
  ```
  ┌─────────────────────────────────────┐
  │ [MEDIUM]  hiworks / login            │  risk badge + action_type
  │ 실행 위치: 로컬 에이전트             │  execution_location
  │ 상태: 수신 대기   2026-05-19 14:32  │  status + 시간
  └─────────────────────────────────────┘
  ```
- **MVP**: 조회 전용. 버튼 없음.

### 8-2. 승인 대기 (`approval`)
- **역할**: 작업 큐 중 `approval_required: true`인 것만 별도 표시
- **이유**: 사용자가 즉시 행동해야 하는 항목 → 분리해서 집중

> ⚠️ 현재 설계 문제: "채팅 인라인 처리" 안내만 있으면 패널이 의미 없음.  
> **수정 방향**: 승인 패널에서 직접 approve/reject 처리

```
┌─────────────────────────────────────┐
│ ✅ 승인 대기   1건                   │
├─────────────────────────────────────┤
│ [HIGH]  naver_cafe / post           │
│ 네이버 카페 게시글 발행 요청          │
│ 2026-05-19 14:30                   │
│          [✅ 승인]    [❌ 거부]      │
└─────────────────────────────────────┘
```

### 8-3. 뉴스 (`news`)
- **단기**: 퀵팁 ("대화창에서 '오늘 뉴스 요약해줘' 라고 말씀하세요")
- **중기**: 뉴스 카드 직접 표시 (`/external/naver/news-main` API)

### 8-4. EUM 단말기 (`eum`) — admin
- **단기**: 퀵팁 ("대화창에서 'EUM 현황 확인해' 라고 말씀하세요")
- **중기**: 22대 단말기 현황 카드 표시 (`data/eum_all_devices_complete.json`)

### 8-5. 브라우저 상태 (`browser`) — admin
- **데이터**: WS Push `type:"browser_status"`
- **콘텐츠**:
  ```
  CDP 포트   9222
  현재 URL   https://eum.cw.or.kr/…
  작업 상태  실행 중 / 대기
  ```

### 8-6. 스크린샷 (`screenshot`) — admin, 기본 OFF
- 썸네일 그리드. WS Push 수신 시 자동 추가.

### 8-7. 로그 (`logs`) — admin
- 시간 / 레벨(INFO·WARN·ERROR) / 메시지 목록

### 8-8. 설정 (`settings`) — 팝오버에서 접근, 독립 패널 유지
```
서버 주소    [ws://localhost:8000/ws/desktop  ]
사용자 이름  [이름                            ]
역할         [User ▼]
             [저장]
```
저장 시 → localStorage 갱신 + 사이드바 사용자 영역 즉시 반영

---

## 9. 메시지 렌더링

| type | role | 렌더 |
|------|------|------|
| `chat` | user | orange 말풍선, 우측, max-width 80% |
| `chat` | assistant | 텍스트만, 좌측, max-width 88% |
| `system` | — | 소형 회색, 중앙 정렬 |
| `task` | — | task-card (승인 패널과 채팅 인라인 양쪽) |
| `browser_status` | — | 브라우저 패널 status-card 업데이트 |

---

## 10. 사이드바 하단 상세 설계

```
┌──────────────────────────────────┐
│ [H]  사용자명   역할   [···]     │  ← 클릭 시 팝오버
├──────────────────────────────────┤
│  ●  연결됨                       │  ← 클릭 시 재연결 시도
└──────────────────────────────────┘
```

### 사용자 팝오버 (클릭 시 사이드바 위에 표시)

```
┌──────────────────┐
│ ⚙️  설정          │  → settings 패널 이동
│ ☰   메뉴 편집    │  → 드로어 열기
└──────────────────┘
```

### 연결 상태 인터랙션

| 상태 | 표시 | 클릭 동작 |
|------|------|-----------|
| 연결됨 | 🟢 연결됨 | 없음 |
| 연결 중 | 🟡 연결 중… | 없음 |
| 연결 끊김 | 🔴 연결 끊김 | 재연결 시도 |

### collapsed (56px) 하단

```
│ [H] │  아바타 클릭 → 팝오버
│  ●  │  연결 dot (색으로 상태 표현)
```

---

## 11. DOM ID 전체 목록

| ID | 위치 | JS 역할 |
|----|------|---------|
| `panel-chat` | HTML | `.has-messages` 토글 |
| `chat-scroll` | 채팅 | scrollTop 제어 |
| `chat-messages` | 채팅 | 메시지 DOM 추가 |
| `chat-welcome` | 채팅 | 환영 블록 숨김/표시 |
| `chat-chips` | 채팅 | 퀵칩 숨김/표시 |
| `chat-foot` | 채팅 | 입력창 컨테이너 |
| `chat-input` | 채팅 | textarea |
| `btn-send` | 채팅 | 전송 버튼 |
| `sidebar` | 사이드바 | `.collapsed` 토글 |
| `sidebar-nav` | 사이드바 | nav-item 렌더 |
| `btn-collapse` | 사이드바 | 접기 |
| `btn-expand` | 메인 | 펼치기 |
| `btn-new-chat` | 사이드바 | 새 대화 초기화 |
| `btn-user` | 사이드바 하단 | 팝오버 열기/닫기 |
| `user-popover` | 사이드바 하단 | 팝오버 컨테이너 |
| `btn-goto-settings` | 팝오버 | settings 패널 이동 |
| `btn-edit-menu` | 팝오버 | 드로어 열기 |
| `menu-drawer-overlay` | 전역 | 드로어 배경 |
| `menu-drawer` | 전역 | 드로어 패널 |
| `drawer-list` | 드로어 | 항목 목록 |
| `conn-dot` | 사이드바 하단 | 상태 dot |
| `conn-text` | 사이드바 하단 | 상태 텍스트 |
| `conn-retry` | 사이드바 하단 | 재연결 버튼 (끊김 시만) |
| `user-name` | 사이드바 하단 | 사용자 이름 |
| `user-role` | 사이드바 하단 | 역할 |
| `sb-avatar` | 사이드바 하단 | 이니셜 아바타 |
| `bs-port` | 브라우저 패널 | CDP 포트 |
| `bs-url` | 브라우저 패널 | 현재 URL |
| `bs-state` | 브라우저 패널 | 작업 상태 |

---

## 12. 구현 순서

| 순서 | 작업 | 파일 |
|------|------|------|
| 1 | `user_settings.py` — `section` 추가, `settings` 항목 제거 | `desktop/user_settings.py` |
| 2 | `index.html` — 채팅 패널 재구조 (chat-foot 패턴), 사용자 팝오버 HTML | `index.html` |
| 3 | `style.css` — navy/orange 토큰, has-messages 전환, 팝오버 스타일 | `style.css` |
| 4 | `app.js` — has-messages 토글, 팝오버 열기/닫기, 재연결 버튼, 섹션 렌더 | `app.js` |
| 5 | `index.html` — Pretendard 폰트 로드 | `index.html` |

---

## 13. UX 검토 이력

| 버전 | 변경 내용 |
|------|-----------|
| v1 | 초안 — 사이드바 기본 구조, 채팅 중앙→하단 전환 |
| v2 | 사용자 아바타 → 팝오버로 변경 (설정+메뉴 편집 통합) |
| v2 | 설정 nav 항목 제거 → 팝오버 전용 접근 |
| v2 | 승인 대기 패널에 직접 approve/reject 처리 추가 |
| v2 | 연결 끊김 시 재연결 클릭 기능 추가 |
| v2 | collapsed 상태에서도 새 대화·팝오버 접근 보장 |
