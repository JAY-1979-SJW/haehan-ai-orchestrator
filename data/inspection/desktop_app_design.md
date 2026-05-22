# HaehanAI Desktop 앱 설계서 v1.0
**작성일**: 2026-05-21  
**대상**: HaehanAI-Desktop.exe (PyInstaller onefolder)

---

## 1. 전체 구조

```
HaehanAI-Desktop.exe
  └── webview_app_pywebview.py (진입점)
        ├── [Step 1] 동의 확인 — data/consent.json 없으면 동의 창 표시
        ├── [Step 2] 로그 설정 — data/logs/desktop_app.log + 서버 전송
        ├── [Step 3] 서버 기동 — desktop.local_server (FastAPI 8765)
        └── [Step 4] pywebview 창 — http://127.0.0.1:8765

desktop/local_server.py (FastAPI 8765)
  ├── /ws/ui     — React UI WebSocket
  ├── /health    — 헬스체크
  └── static     — desktop/ui_dist

scripts/ops/audit_desktop_app_watchdog.py
  └── 60초 간격 상시 감사 — 서버·CDP·WS·playwright
```

---

## 2. 단계별 검증 항목

| 단계 | 항목 | 검증 방법 | 판정 기준 |
|------|------|-----------|-----------|
| S1 | spec 모듈 번들 | _internal에 uvicorn/fastapi/starlette/anyio 존재 | 폴더/zip 확인 |
| S2 | 로그 파일 생성 | exe 실행 후 data/logs/desktop_app.log 생성 | 파일 존재 + 내용 확인 |
| S3 | 서버 기동 | /health 200 응답 | HTTP 200 |
| S4 | WS 연결 | /ws/ui 접속 + browser_status 수신 | ok=True |
| S5 | CDP 연결 | playwright connect_over_cdp | contexts>=1 |
| S6 | 동의 창 | 최초 실행 시 동의 창 표시 | consent.json 생성 |
| S7 | 로그 서버 전송 | ERROR 로그 → 서버 /api/v1/logs | HTTP 200 |
| S8 | 스크린샷 | /ws/ui → screenshot → PNG | ok=True, bytes>0 |
| S9 | 네이버 메일 | CDP → mail.naver.com 접속 | 메일함 로드 |
| S10 | 감사 스크립트 | watchdog --once PASS | verdict=PASS |

---

## 3. 수정 사항 목록

### 3-1. spec 수정 (완료)
- excludes에서 anyio 제거
- collect_submodules(uvicorn/fastapi/starlette/anyio) 추가
- h11, sniffio, exceptiongroup, httptools hiddenimports 추가

### 3-2. 로그 경로 수정 (미완)
- exe 실행 시 `__file__` → `sys.executable` 기준으로 경로 변경
- `data/logs/desktop_app.log` exe 옆 디렉터리에 생성

### 3-3. 로그 서버 전송 (미완)
- ERROR 이상 로그 → HTTP POST → 로컬서버 /api/log 또는 외부 서버

### 3-4. 동의 창 (미완)
- 최초 실행 시 tkinter 동의 창 표시
- 동의 시 data/consent.json 저장
- 거부 시 앱 종료

---

## 4. 파일 위치

| 파일 | 역할 |
|------|------|
| `desktop/webview_app_pywebview.py` | 앱 진입점, 로그/동의/서버/webview |
| `desktop/local_server.py` | FastAPI 서버, WS 핸들러 |
| `HaehanAI-Desktop.spec` | PyInstaller 빌드 설정 |
| `scripts/ops/audit_desktop_app_watchdog.py` | 상시 감사 |
| `data/logs/desktop_app.log` | 앱 로그 |
| `data/consent.json` | 동의 기록 |
