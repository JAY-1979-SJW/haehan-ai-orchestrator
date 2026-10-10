# HAEHAN_SINGLE_EXE_MODE_CONSOLIDATION_SPEC_01

**공정명**: HAEHAN_SINGLE_EXE_MODE_CONSOLIDATION_SPEC_01
**작성일**: 2026-05-22
**시작 HEAD**: e9a549a
**종류**: 설계 문서 (코드 변경 없음)
**다음 구현 공정**: HAEHAN_SINGLE_EXE_LAUNCHER_FOUNDATION_01

---

## 1. 결정 배경

현재 두 개의 독립 exe로 분리 운영 중:

- `HaehanAI-Agent.exe` — Persona A (일반 사용자) 트레이 에이전트
- `HaehanAI-Desktop.exe` — Persona B (관리자) pywebview React UI

이 분리 구조의 문제:

| 영역 | 분리 비용 |
|------|-----------|
| 빌드 산출물 | 2개 spec / 2개 build script / 2개 dist 폴더 |
| 등록 흐름 | register / device_token / heartbeat 코드 2벌 중복 |
| WS 서버 | local_agent와 desktop/local_server 각자 운영 |
| 로그 / 동의 / keyring | 각자 구현 — 갱신 시 2곳 수정 |
| 사용자 혼란 | "둘 다 설치?" — 설치/배포 매뉴얼 2벌 |
| 보안 표면 | 2개 surface — redaction 정책 동기화 부담 |

**결정**: A안 통합 — 단일 exe `HaehanAI.exe` 로 합친다. 단, 즉시 폐기 금지. 설계 → 단계별 흡수 → deprecated → cleanup 순서.

---

## 2. 두 앱 기능 맵

### 2.1 현재 `local_agent/` (HaehanAI-Agent.exe)

| 모듈 | 역할 | 통합 처분 |
|------|------|-----------|
| `agent.py` | 메인 엔트리, 등록/heartbeat | **흡수** — HaehanAI.exe Tray Mode 코어 |
| `gui_app.py` | 4탭 GUI (Dashboard/Reg/Logs/Settings) | **흡수 + 단순화** — wizard 3-step 로 |
| `gui_tray.py` | 시스템 트레이 아이콘/메뉴 | **흡수** — Tray Mode 진입점 |
| `gui_state.py` | 상태 머신 (NOT_REG / CONNECTING / HEARTBEAT_OK 등) | **흡수** — 단일 source 유지 |
| `gui_icons.py` | PIL 아이콘/sparkline | **흡수** — sparkline 제거, dot만 유지 |
| `gui_log_buffer.py` | 1000-line ring buffer | **폐기** — 통합 로깅으로 대체 |
| `registration_client.py` | register-with-code | **흡수** — 단일 등록 모듈 |
| `token_store.py` | Credential Manager keyring | **흡수** — 단일 token store |
| `connection_diagnostics.py` | 진단 텍스트 생성 (redact 포함) | **흡수** — Tray 진단 다이얼로그 |
| `websocket_client.py` | 서버 WS heartbeat | **흡수** — local_server에서 호출 |
| `ai_chat_client.py` / `openai_chat_client.py` / `server_proxy_chat_client.py` | AI 채팅 클라이언트 | **흡수** — Admin Mode React UI에서 호출 |
| `ai_chat_adapter.py` / `ai_chat_models.py` | 채팅 어댑터/모델 | **흡수** |
| `gui_chat_state.py` | 채팅 상태 (CTk) | **폐기** — React Admin UI가 대체 |
| `openai_key_store.py` | OpenAI dev key (test mode only) | **흡수** |
| `desktop_launcher.py` | --self-test / --diagnostics CLI | **흡수** — CLI 인터페이스 단일화 |
| `desktop_config.py` | 서버 URL / WS URL 설정 | **흡수** |
| `actions.py` | ping/system_info/open_url 등 read-only | **흡수** |
| `audit.py` | 로컬 감사 로그 | **흡수** |
| `redaction.py` | secret/token redact | **흡수** |
| `browser_*.py` (15개) | CDP 브라우저 자동화 | **흡수** — Admin Mode에서 사용 |
| `user_present_*.py` | 사용자 현존 감지 / WS adapter | **흡수** |
| `cad_adapter.py` | CAD bridge | **흡수** |
| `site_mapper.py` / `web_reader.py` / `file_scanner.py` | 사이트맵/리더 | **흡수** |

### 2.2 현재 `desktop/` (HaehanAI-Desktop.exe)

| 모듈 | 역할 | 통합 처분 |
|------|------|-----------|
| `webview_app_pywebview.py` | 메인 엔트리, pywebview + 서버 | **유지 + 확장** — HaehanAI.exe 통합 진입점 |
| `local_server.py` | FastAPI 8765 / WS /ws/ui | **유지** — Admin Mode 백엔드 + Tray Mode heartbeat 통합 |
| `tray_app.py` | (별도 트레이 시도) | **폐기** — local_agent.gui_tray 흡수본으로 대체 |
| `webview_app.py` | (구 Electron/Edge 시도) | **폐기** — pywebview 단일화 |
| `app_config.py` | LOCAL_HOST/PORT/URL | **유지** |
| `audit_desktop.py` | desktop 자체 audit | **유지** |
| `cad_bridge_*.py` | CAD bridge proxy/runner | **유지** |
| `electron/` | (실험 디렉터리) | **폐기 후보 — 별도 cleanup** |
| `local_agent_service.py` | (신규) local_agent 통합 어댑터 | **유지 — 통합 진입점 후보** |
| `remote_access.py` | 원격 접속 토큰 검증 | **유지** |
| `status_provider.py` | 상태 조회 | **유지** |
| `user_settings.py` | 메뉴/설정 영속화 | **유지** |
| `ui/` (React 소스) | shadcn + Tailwind admin UI | **유지** — Admin Mode 전용 |
| `ui_dist/` (React 빌드물) | vite 산출물 | **유지** |

### 2.3 중복 기능 (제거 대상)

| 기능 | 현재 위치 | 통합 후 단일 위치 |
|------|-----------|------------------|
| 등록 (register-with-code) | `core.agent_runtime.connection.registration_client` + `desktop.local_server._handle_register` | **core.agent_runtime.connection.registration_client** (서버는 호출만) |
| device_token 저장 | `core.agent_runtime.connection.token_store` + `desktop` keyring 별도 | **core.agent_runtime.connection.token_store** |
| 서버 WS heartbeat | `core.agent_runtime.connection.websocket_client` + `desktop.local_server._connect_to_server_ws` | **core.agent_runtime.connection.websocket_client** (desktop에서 spawn) |
| 트레이 아이콘 | `local_agent.gui_tray` + `desktop.tray_app` | **local_agent.gui_tray** |
| 로그 redaction | `core.agent_runtime.common.redaction` + `desktop` ad-hoc | **core.agent_runtime.common.redaction** |
| 진단 텍스트 | `core.agent_runtime.connection.connection_diagnostics` + `desktop` 패널 | **core.agent_runtime.connection.connection_diagnostics** |

### 2.4 유지 (각 라인 고유)

| 라인 | 고유 기능 |
|------|-----------|
| local_agent | actions.py(read-only), audit.py, openai_key_store(test only) |
| desktop | React UI / FastAPI 라우터 / CAD bridge / pywebview |

---

## 3. 최종 단일 exe 목표 구조

```
HaehanAI.exe (PyInstaller onefolder)
│
├── build/main_launcher.py (신규) — 진입점
│     ├── consent 확인
│     ├── token 로드
│     ├── mode 분기 (Tray / Admin / CLI)
│     └── lifecycle 관리
│
├── local_agent/ (흡수 — 내부 라이브러리)
│     ├── registration_client (등록)
│     ├── token_store (keyring)
│     ├── websocket_client (서버 heartbeat)
│     ├── gui_tray (트레이)
│     ├── gui_state (상태 머신)
│     ├── connection_diagnostics (진단)
│     ├── redaction (secret 가림)
│     ├── actions (read-only 액션)
│     ├── browser_* (CDP 자동화)
│     ├── ai_chat_client / openai_chat_client / server_proxy_chat_client
│     └── ...
│
├── desktop/ (Admin Mode 전용)
│     ├── webview_app_pywebview (Admin 진입)
│     ├── local_server (FastAPI 8765)
│     ├── ui_dist (React 빌드물)
│     ├── cad_bridge_* (CAD bridge)
│     ├── remote_access (원격 토큰)
│     └── ...
│
└── shared/
      ├── logging_setup
      └── consent_store
```

### 3.1 lifecycle (lifecycle 그림)

```
HaehanAI.exe 실행
  │
  ├─[1] consent 확인 ─ 미동의 → 동의 창 → 거부 시 종료
  │
  ├─[2] token 로드 (keyring)
  │
  ├─[3] mode 분기
  │     │
  │     ├─ [no arg] → Tray Mode (기본)
  │     │             │
  │     │             ├─ 미등록 → wizard 3-step → 등록 완료 후 트레이
  │     │             └─ 등록됨 → 바로 트레이
  │     │
  │     ├─ [--admin] → Admin Mode (즉시 pywebview)
  │     │
  │     └─ [--self-test / --diagnostics / --reset] → CLI Mode
  │
  ├─[4] local_server 8765 기동 (Tray/Admin 공통)
  │
  ├─[5] heartbeat 시작 (websocket_client → wss 서버)
  │
  └─[6] Tray 표시
        │
        └─ 트레이 메뉴: 진단 / 재등록 / [관리화면 열기] / autostart / 종료
              │
              └─ "관리화면 열기" 클릭 (admin/owner role만 노출)
                    │
                    └─ pywebview 창 lazy load
                          │
                          └─ React UI → /ws/ui 연결
                                ├─ browser/screenshot/blog/cafe/mail
                                ├─ CAD bridge
                                ├─ AI 채팅 (proxy)
                                └─ 작업큐 / 승인 / 로그
```

---

## 4. 모드 분기 정의

### 4.1 Tray Mode (기본)

| 속성 | 값 |
|------|-----|
| 진입 | `HaehanAI.exe` (인자 없음) |
| 창 | 없음 — 트레이 아이콘만 |
| 미등록 시 | wizard 3-step 자동 표시 |
| 등록됨 시 | 바로 트레이 상주 |
| 트레이 메뉴 | 상태 / 진단 / 재등록 / 관리화면 / 자동시작 / 종료 |
| 백엔드 | local_server (8765) + WS heartbeat |
| 사용자 | Persona A (일반) — role=any |

### 4.2 Admin Mode

| 속성 | 값 |
|------|-----|
| 진입 | `HaehanAI.exe --admin` OR 트레이 → [관리화면 열기] |
| 창 | pywebview 네이티브 창 (1200×800) |
| 권한 | role ∈ {admin, owner} 만 진입 가능 |
| role 확인 | local_server `/api/v1/whoami` 호출 → role 반환 |
| 백엔드 | 같은 local_server 재사용 (8765) |
| UI | React (`desktop/ui_dist`) — 모든 기존 패널 |
| 창 닫기 | local_server는 유지 — Tray Mode로 복귀 |

### 4.3 CLI Mode

| 진입 | 동작 |
|------|------|
| `--self-test` | 부팅 검증 후 즉시 종료 |
| `--diagnostics` | 진단 텍스트 stdout 출력 |
| `--register CODE` | 등록 1회 후 종료 |
| `--reset` | token 삭제 (재등록 필요) |
| `--agent-id` | 마스킹 agent_id 출력 |

> CLI Mode는 트레이/GUI 표시 없이 stdout만 사용. 자동화/스크립트 친화.

---

## 5. role guard 정책

### 5.1 role 결정

| 출처 | 우선순위 |
|------|---------|
| `localStorage.user_role` (React) | 1 |
| `local_server /api/v1/whoami` 응답 | 2 |
| 서버 등록 시 부여된 role | 3 (백엔드) |
| 기본값 | `any` (일반 사용자) |

### 5.2 guard 위치

| 보호 대상 | 위치 | 동작 |
|----------|------|------|
| 트레이 [관리화면 열기] 메뉴 항목 | `gui_tray.py` 메뉴 빌더 | role ∉ {admin,owner} → 항목 숨김 |
| `--admin` CLI 옵션 | `main_launcher.py` | role 미확인/부족 → 오류 + 즉시 종료 |
| pywebview 진입 (직접 URL) | `local_server` 미들웨어 | role 헤더 누락/부족 → 401 |
| `/ws/ui` admin 액션 (browser_start, cafe_write 등) | `local_server._handle_ui_message` | role 검사 → 부족 시 거절 |
| React UI 사이드바 admin 메뉴 | `appStore.menuItems` `min_role` | 클라이언트 필터 (보조) |

### 5.3 local-only bypass 금지

- 127.0.0.1 라고 해서 role 무시 금지
- 같은 PC라도 role 없으면 admin 액션 거절
- 미들웨어 fallback 정책 명시

---

## 6. lifecycle 정책

### 6.1 실행

1. 로그 setup (`data/logs/haehan_app.log`, RotatingFileHandler 5MB×3)
2. consent.json 확인 — 미동의 시 tkinter 동의 창 (수집/이용목적/보유기간)
3. keyring에서 device_token 로드
4. mode 분기 (§4)
5. local_server (8765) 백그라운드 thread 기동
6. websocket_client 시작 (등록된 경우만)
7. 트레이 표시 (Tray/Admin 공통)

### 6.2 관리화면 열기

- local_server가 이미 떠 있으면 재사용 (재기동 안 함)
- pywebview 창 lazy load — 첫 호출 시에만 webview import
- 창 닫기 = 창만 hide(), 서버는 유지
- 다시 [관리화면 열기] = 같은 창 재표시 또는 새 창

### 6.3 종료

- 트레이 [종료] → local_server 종료 + websocket_client 종료 + 트레이 제거
- 본 프로세스가 띄운 자식만 종료 (외부 chrome cdp_daemon 등 보존)
- pywebview 창만 닫는 것은 "종료" 아님 — 트레이 [종료] 명시적 필요

### 6.4 충돌 처리

| 상황 | 대응 |
|------|------|
| 다른 HaehanAI.exe 이미 실행 중 | 단일 인스턴스 락 (`%LOCALAPPDATA%\HaehanAI\app.lock`) — 새 인스턴스는 기존에게 신호 보내고 종료 |
| 8765 포트 이미 점유 | 우선 `/health` 핑 → 200이면 재사용, 아니면 오류 |
| CDP 9222 이미 점유 | 외부 chrome 신호 → 그대로 사용 (cdp_daemon 신규 기동 안 함) |

---

## 7. build policy

### 7.1 최종 빌드 (목표)

- **파일명**: `HaehanAI.exe` (또는 호환성 위해 `HaehanAI-Desktop.exe` 유지 가능)
- **포맷**: PyInstaller onefolder (우선) / onefile (옵션)
- **포함**:
  - playwright + driver (강제 포함)
  - React `ui_dist`
  - `local_agent` 전체 모듈
  - `desktop` 전체 모듈
  - pythonnet / clr (pywebview winforms)
  - uvicorn / fastapi / starlette / anyio / h11 (collect_all)
- **제외**:
  - pytest / pytest_asyncio
  - 개발용 도구
- **크기 목표**: ≤ 30MB onefolder

### 7.2 spec 통합

| 현재 | 통합 후 |
|------|---------|
| `HaehanAI-Agent.spec` | **deprecated 표기 — 폐기 후보** |
| `HaehanAI-Desktop.spec` | `HaehanAI.spec` 으로 rename 후 단일 사용 |
| `scripts/build_desktop_agent_windows.py` | **deprecated** |
| `scripts/build_desktop_windows.py` (있다면) | `scripts/build_haehan.py` 신규로 단일화 |

### 7.3 deprecated 표기 (이번 공정엔 삭제 X)

각 deprecated 파일 상단에 주석 추가 (별도 후속 공정):

```python
# DEPRECATED: HAEHAN_SINGLE_EXE_MODE_CONSOLIDATION_SPEC_01 이후 단일 빌드로 통합됨.
# 본 spec/script는 HAEHAN_AGENT_EXE_DEPRECATION_01 공정에서 삭제 예정.
```

---

## 8. 보안 정책

### 8.1 절대선

1. `device_token` 원문 UI/log/report 출력 **금지**
2. `registration_code` 입력 후 변수 폐기 (`code = ""` 명시)
3. OpenAI API key는 **production client에 미존재** — server proxy 경유
4. dev key (`openai_key_store`)는 test mode에서만 사용
5. admin UI는 role guard 통과 후에만 노출
6. Chrome profile cookie / set-cookie 헤더 원문 출력 금지
7. 로그/리포트 redaction 필수 (`core.agent_runtime.common.redaction`)

### 8.2 redaction 패턴 (통합 source = `core.agent_runtime.common.redaction`)

- `device_token=...` → `[REDACTED]`
- `registration_code=...` → `[REDACTED]`
- `bearer <token>` → `bearer [REDACTED]`
- URL query에서 `token / authorization / session / api_key / bearer` → `[REDACTED]`
- agent_id → `la-xxx***yyy` 마스킹

### 8.3 admin surface 분리

- Tray Mode에서 noop으로 만들 admin 액션:
  - `browser_start` / `cafe_write` / `blog_write` / `cad_*` / 작업큐 / 승인
  - 클라이언트 메뉴 숨김 + 서버 role 검사 양쪽
- local_server 미들웨어:
  - `/ws/ui` 메시지 핸들러 진입 시 `role` 필드 검사
  - 부족 시 `{ ok: false, error: "권한 부족" }` 응답

### 8.4 단일 인스턴스 안전성

- app lock 파일 path는 사용자 home 하위 (`%LOCALAPPDATA%\HaehanAI\`)
- 락 PID는 절대 secret 아님 — 노출 무방
- 락 파일 손상/stale 시 자동 복구 (PID 검사 후)

---

## 9. 위험 분석

| 위험 | 영향 | 완화 |
|------|------|------|
| **exe 크기 증가** (12→22MB) | 다운로드 시간 ↑, SmartScreen 표면 변화 | onefolder 유지, lazy load (webview), code signing 후속 |
| **playwright 번들 의존** | exe 크기 + 보안 검사 표면 | 강제 포함 — 외부 PC 의존성 제거 (사용자 승인 완료) |
| **admin surface 노출 위험** | role guard 누락 시 일반 사용자도 browser_start 가능 | 5중 guard (트레이 메뉴 / CLI / 미들웨어 / WS 핸들러 / 클라이언트) |
| **role guard 누락** | 코드 추가 시 새 액션에 role 체크 빠뜨림 | `_require_role()` 데코레이터 단일화 + 회귀 테스트 |
| **local_server port 충돌** | 8765가 다른 앱에 점유됨 | `/health` 핑 → 재사용, fallback 포트 (`8766`) 옵션 |
| **기존 Agent.exe 사용자 migration** | 이미 설치한 사용자 어떻게 옮기나 | 두 exe 공존 — Agent.exe는 deprecated 메시지만 표시, 강제 마이그레이션 안 함 |
| **두 exe 공존 기간의 token 충돌** | 같은 keyring 키 사용 시 동시 갱신 충돌 | 같은 키 사용 — Last Write Wins, 안전 (race는 register 1회만) |
| **문서 혼란** | 사용자가 "어느 걸 설치?" | 통합 후 단일 README, Agent.exe 페이지에 통합 안내 배너 |
| **PyInstaller 빌드 시간 증가** | playwright + 모든 collect_all → 15분+ | 캐시 활용, 변경 최소화 |
| **단일 인스턴스 락 stale** | exe crash 후 락 파일 잔존 | PID 검사 + stale 자동 정리 |

---

## 10. 단계별 구현 계획

| # | 공정명 | 범위 | 산출물 |
|---|--------|------|--------|
| 1 | **HAEHAN_SINGLE_EXE_MODE_CONSOLIDATION_SPEC_01** | 본 설계서 (현재 공정) | docs/design/*.md + audit + test |
| 2 | HAEHAN_SINGLE_EXE_LAUNCHER_FOUNDATION_01 | `build/main_launcher.py` 신규 — consent/token/mode 분기 골격 | launcher + 단위 테스트 |
| 3 | HAEHAN_TRAY_REGISTRATION_MERGE_01 | local_agent.gui_tray + registration_client 흡수 — Tray Mode 단순화 (wizard 3-step) | 통합 gui_app slim + 등록 흐름 |
| 4 | HAEHAN_ADMIN_MODE_WEBVIEW_LAZY_LOAD_01 | pywebview lazy load + role guard 5중 적용 | webview + role 미들웨어 + 테스트 |
| 5 | HAEHAN_SINGLE_EXE_BUILD_01 | `HaehanAI.spec` 단일화 + PyInstaller 재빌드 + smoke | spec + build script + smoke audit |
| 6 | HAEHAN_AGENT_EXE_DEPRECATION_01 | Agent.exe / Agent.spec / agent build script에 DEPRECATED 표기 + README 통합 안내 | 주석 + 문서 |
| 7 | HAEHAN_SINGLE_EXE_USER_FIELD_TEST_01 | 외부 PC 5대 설치/등록/admin 진입 테스트 | 결과 리포트 |
| 후속 | HAEHAN_AGENT_EXE_CLEANUP_01 | deprecated 파일 실제 삭제 (별도 공정, 본 설계 외) | 파일 제거 + git rm |

### 본 공정 (#1)의 완료 조건

- [x] 설계 문서 작성 (`docs/design/HAEHAN_SINGLE_EXE_MODE_CONSOLIDATION_SPEC_01.md`)
- [x] 두 앱 기능 맵 (§2)
- [x] 단일 exe 목표 구조 (§3)
- [x] Tray/Admin/CLI 모드 정의 (§4)
- [x] role guard 5중 정책 (§5)
- [x] lifecycle 정책 (§6)
- [x] build policy (§7)
- [x] 보안 정책 (§8)
- [x] 위험 분석 (§9)
- [x] 단계별 구현 계획 (§10)
- [x] audit 스크립트 (`tools/audits/agent/audit_haehan_single_exe_mode_consolidation_spec.py`)
- [x] 테스트 (`tests/test_haehan_single_exe_mode_consolidation_spec.py`)

---

## 11. OUT_OF_SCOPE (본 공정에서 하지 않음)

- ❌ 즉시 Agent.exe 삭제
- ❌ Agent.spec / build script 삭제
- ❌ 실제 통합 코드 작성
- ❌ PyInstaller 재빌드
- ❌ React UI 대규모 수정
- ❌ 서버 배포
- ❌ code signing
- ❌ auto update
- ❌ field test 실행 (계획만)

---

## 12. 즉시 삭제 금지 명시

본 설계서는 **설계만** 수행한다. 다음은 별도 cleanup 공정 (HAEHAN_AGENT_EXE_CLEANUP_01)에서 처리:

- `local_agent/gui_app.py` 4탭 코드 정리
- `core/agent_runtime/gui/gui_log_buffer.py` 제거
- `HaehanAI-Agent.spec` 삭제
- `scripts/build_desktop_agent_windows.py` 삭제
- `core/agent_runtime/gui/gui_chat_state.py` (CTk) 제거
- Agent.exe 설치 문서 archive 이동

본 공정에서는 위 항목 **분류만** 한다 (§2 통합 처분 표).

---

## 13. 다음 공정

본 설계서 승인 시 다음 공정으로 진행:

**HAEHAN_SINGLE_EXE_LAUNCHER_FOUNDATION_01** — `build/main_launcher.py` 신규 + consent/token/mode 분기 골격 + 단위 테스트.
