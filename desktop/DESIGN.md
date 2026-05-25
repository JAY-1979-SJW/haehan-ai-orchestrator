# Haehan AI 데스크 앱 — 통합 설계서

작성일: 2026-05-19  
기준: 현재 구현 코드 역공학 + 웹 서비스 직접 탐색

---

## 1. 앱 개요

Haehan AI 데스크 앱은 Windows PC에서 AI 오케스트레이터 시스템을 조작·모니터링하는 관리자용 데스크탑 애플리케이션이다.

**MVP 범위 잠금 (2026-05-18 확정):** 조회/보기 전용. 실행·승인 DRY_RUN 해제·결제 버튼 절대 노출 금지.

---

## 2. 아키텍처 구조

```
┌─────────────────────────────────────────────────────────────┐
│  로컬 PC (Windows)                                           │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  HaehanAI Desktop launcher (desktop/main_launcher.py) │   │
│  │  창 크기: 기본 1000×720, 최소 720×520                  │   │
│  │  http://127.0.0.1:8765 로드                           │   │
│  └─────────────────────┬────────────────────────────────┘   │
│                        │ HTTP/WS                            │
│  ┌─────────────────────▼────────────────────────────────┐   │
│  │  FastAPI 로컬 서버  (desktop/local_server.py)          │   │
│  │  포트: 8765                                           │   │
│  │                                                      │   │
│  │  WS  /ws/ui          ← UI 클라이언트 다중 연결         │   │
│  │  GET /proxy/admin/*  ← autowork 역방향 프록시          │   │
│  │  GET /              ← ui_dist/ 정적 서빙 (SPA)        │   │
│  └─────────────────────┬────────────────────────────────┘   │
│                        │ WS 재연결 루프 (5초)               │
└────────────────────────┼────────────────────────────────────┘
                         │ wss://api.haehan-ai.kr/ws/desktop
                         │ (현재 미연결 — nginx /ws/desktop 미설정)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  원격 서버 haehan-mcp (Ubuntu / 1.201.176.236)               │
│  FastAPI  포트 8000                                          │
│  - /ws/desktop    Push WebSocket (미설정)                    │
│  - /orchestrator/api/v1/  REST API                          │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  admin-web  autowork.haehan-ai.kr  (haehan-webdb 서버)       │
│  Next.js / nginx 서빙                                        │
│  X-Frame-Options: SAMEORIGIN  →  프록시로 우회               │
│                                                             │
│  /                  관리 대시보드                             │
│  /ops               운영 현황                                │
│  /local-agents      로컬 에이전트 관리                        │
│  /browser-approvals 브라우저 승인                            │
│  /file-map          AI 파일 지도                             │
│  /cad               AI CAD 워크스페이스                      │
│  /external-tasks    외부 웹 업무 현황                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 파일 구조

```
desktop/
├── main_launcher.py      통합 데스크톱 진입점
├── local_server.py       L8   FastAPI 로컬 서버 (8765)
├── user_settings.py      L8   사용자 메뉴 설정 저장/로드
├── audit_desktop.py      L11  상시 감사 스크립트
├── DESIGN.md                  본 설계서
├── WEB_DESIGN.md              웹 서비스 설계서
├── settings/                  사용자별 메뉴 설정 JSON
│   └── {user_id}.json
├── ui/                   L9   React/Vite 소스
│   ├── src/
│   │   ├── App.tsx             루트 컴포넌트, 패널 라우팅
│   │   ├── store/appStore.ts   Zustand 전역 상태
│   │   ├── lib/ws.ts           WsClient (연결/재연결)
│   │   ├── lib/utils.ts        공통 유틸
│   │   └── components/
│   │       ├── Sidebar.tsx           좌측 사이드바
│   │       ├── ChatPanel.tsx         대화 패널
│   │       ├── MenuDrawer.tsx        메뉴 편집 Drawer
│   │       ├── IframePanel.tsx       admin-web 임베드
│   │       └── panels/
│   │           ├── PanelShell.tsx    패널 공통 레이아웃
│   │           └── Panels.tsx        모든 패널 export
│   ├── package.json
│   └── vite.config.ts
└── ui_dist/              빌드 결과 (정적 서빙 대상)
    ├── index.html
    └── assets/
        ├── index-*.js   (~252KB)
        └── index-*.css  (~24KB)
```

---

## 4. 메뉴 구조 (4개 섹션, 14개 항목)

| 섹션 | ID | 라벨 | 아이콘 | 역할 | 기본 표시 | 패널 |
|------|----|------|--------|------|----------|------|
| AI 대화 | chat | 대화 | 💬 | any | O | ChatPanel |
| AI 대화 | task_queue | 작업 큐 | 📋 | any | O | TaskQueuePanel |
| AI 대화 | approval | 승인 대기 | ✅ | any | O | ApprovalPanel |
| 업무 조회 | news | 뉴스 | 📰 | any | O | NewsPanel |
| 업무 조회 | eum | EUM 단말기 | 🏗️ | admin | O | EumPanel |
| 관리 웹 | admin_dashboard | 관리 대시보드 | 🖥️ | admin | O | IframePanel(/) |
| 관리 웹 | admin_ops | 운영 현황 | 📊 | admin | O | IframePanel(/ops) |
| 관리 웹 | admin_approvals | 브라우저 승인 | 🔐 | admin | O | IframePanel(/browser-approvals) |
| 관리 웹 | admin_agents | 로컬 에이전트 | 🤖 | admin | O | IframePanel(/local-agents) |
| 관리 웹 | admin_filemap | 파일맵 | 🗂️ | admin | X | IframePanel(/file-map) |
| 관리 웹 | admin_cad | CAD | 📐 | admin | X | IframePanel(/cad) |
| 시스템 | browser | 브라우저 상태 | 🌐 | admin | O | BrowserPanel |
| 시스템 | screenshot | 스크린샷 | 📸 | admin | X | ScreenshotPanel |
| 시스템 | logs | 로그 | 📋 | admin | O | LogsPanel |

**IframePanel 프록시 경로:**
```
http://127.0.0.1:8765/proxy/admin/{path}
→ https://autowork.haehan-ai.kr/{path}  (X-Frame-Options 제거 후 전달)
```

---

## 5. 디자인 시스템 토큰

| 토큰 | 값 | 용도 |
|------|-----|------|
| 브랜드 오렌지 | `#F97316` | 상단 액센트 라인, 로고, 활성 메뉴, 배지 |
| 배경 메인 | `#F5F7FA` | 앱 전체 배경 |
| 배경 사이드바 | `#F0F2F5` | 사이드바 |
| 배경 카드 | `#FFFFFF` | 활성 메뉴, 버튼, 팝오버 |
| 경계선 | `#E5E7EB` | 사이드바·버튼·구분선 |
| 텍스트 강조 | `#111827` | 주요 텍스트 |
| 텍스트 보조 | `#6B7280` | 비활성 메뉴 |
| 텍스트 희미 | `#9CA3AF` | 섹션 레이블 |
| 성공 | `#059669` | 연결됨 (초록) |
| 경고 | `#D97706` | 연결 중 (앰버 스피너) |
| 오류 | `#DC2626` | 연결 끊김 (빨강) |

**폰트:** Pretendard (CDN), 시스템 폴백  
**사이드바 너비:** 펼침 224px / 접힘 56px  
**상단 액센트 라인:** 4px 오렌지 (필수 디자인 요소)

---

## 6. WebSocket 메시지 스펙

### UI → 로컬서버 (action)
```json
{ "action": "load_menu",  "user_id": "...", "role": "..." }
{ "action": "save_menu",  "user_id": "...", "items": [...] }
{ "action": "chat",       "text": "..." }
{ "action": "approve",    "task_id": "..." }
{ "action": "reject",     "task_id": "..." }
```

### 로컬서버 → UI (type, broadcast)
```json
{ "type": "menu",         "items": [...] }
{ "type": "menu_saved",   "ok": true }
{ "type": "chat",         "role": "assistant|user|system", "text": "...", "ts": 0 }
{ "type": "system",       "text": "🟢 서버 연결됨" }
{ "type": "task",         "task_id": "...", "action_type": "...", "risk_level": "low|medium|high",
                          "needs_approval": false, "execution_location": "...", "ts": 0 }
{ "type": "browser_status", "port": "...", "url": "...", "state": "...", "active": true }
```

---

## 7. 프록시 동작 원리

```
데스크 앱 (127.0.0.1:8765)
  iframe src="http://127.0.0.1:8765/proxy/admin/ops"
    ↓
  local_server.py  GET /proxy/admin/{path}
    ↓  httpx.AsyncClient
  https://autowork.haehan-ai.kr/ops
    ↓  응답 헤더에서 제거:
       X-Frame-Options
       Content-Security-Policy
       Content-Encoding
       Transfer-Encoding
    ↓
  브라우저에 전달 → iframe 정상 표시
```

---

## 8. 실행 방법

### 사전 요건
```
Python 3.10+
PyQt6, PyQt6-WebEngine
uvicorn, fastapi, websockets, httpx
Node.js 18+  (UI 빌드 시)
```

### UI 빌드 (코드 변경 시)
```bash
cd desktop/ui
npm install
npm run build
# → desktop/ui_dist/ 갱신
```

### 앱 실행
```bash
# 프로젝트 루트에서
python -m desktop.main_launcher
```

### 감사 스크립트 실행
```bash
python -m desktop.audit_desktop           # 1회 감사
python -m desktop.audit_desktop --watch   # 60초 주기 상시 감사
python -m desktop.audit_desktop --dry     # dry-run
```

---

## 9. 감사 스크립트 (audit_desktop.py) 항목

| 감사 항목 | PASS 조건 | FAIL 조건 |
|----------|----------|----------|
| 포트 8765 LISTENING | TCP 연결 성공 | 연결 거부 |
| index.html 서빙 | 'Haehan AI' 타이틀 포함 | HTTP 오류 또는 타이틀 없음 |
| ui_dist 빌드 | assets/*.js, *.css 존재 | 파일 없음 (빌드 필요) |
| 프록시 X-Frame-Options 제거 | 헤더 없음 + HTML 응답 | 헤더 존재 또는 502 |
| app.log 최신성 | 1시간 내 갱신 | 파일 없음 (WARN) |
| WebSocket 메뉴 | 4개 섹션 14개 항목 | 연결 실패 |
| 메뉴 section 필드 | 전 항목 section 있음 | 누락 항목 |

---

## 10. 미완료 / 보류 항목

| 항목 | 원인 | 처리 방법 |
|------|------|----------|
| 원격 WS 미연결 | KINX 보안그룹 SSH 차단 / nginx /ws/desktop 미설정 | 보안그룹 IP 추가 후 nginx 설정 |
| api.haehan-ai.kr 404 | nginx 라우팅 미설정 | 원격 서버 접속 후 nginx 설정 추가 |
| 인증/로그인 플로우 없음 | MVP 미포함 | 2차 MVP 예정 |
| NewsPanel 데이터 미연결 | 서버 연결 필요 | 원격 WS 연결 후 자동 해결 |
| EumPanel 데이터 미연결 | 서버 연결 필요 | 원격 WS 연결 후 자동 해결 |
| LogsPanel 데이터 없음 | API 미구현 | local_server에 /logs 엔드포인트 추가 필요 |
| 승인/거부 버튼 | MVP 잠금 (2026-05-18) | 2차 MVP에서 활성화 |

---

## 11. 운영 보안 정책

1. secret/token/password/env 값 출력·로깅 금지
2. 운영 DB write/schema 변경 승인 없이 금지
3. 투찰·전자서명·송금·결제 자동 실행 금지
4. 쿠키·session 추출 금지
5. 승인 토큰 30분 TTL — 만료 후 자동 거부
6. `safe_to_execute` 항상 false — 승인과 무관하게 실행 차단
