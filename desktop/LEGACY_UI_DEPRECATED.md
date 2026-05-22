# Legacy UI — 제거 완료

공정: HAEHAN-DESKTOP-LEGACY-UI-REMOVAL-01
완료일: 2026-05-23

## 제거 완료 파일

| 파일 | 상태 |
|------|------|
| `tray_app.py` | **제거 완료** |
| `webview_app.py` | **제거 완료** |
| `webview_app_pywebview.py` | **제거 완료** |
| `desktop/ui/` (React/Vite SPA, 35개 파일) | **제거 완료** |

## 이전 공유 로직

| 원본 위치 | 이전 위치 | 내용 |
|-----------|-----------|------|
| `webview_app_pywebview._check_consent` | `desktop/consent.py` | 사용자 정보 제공 동의 로직 |

## new_shell 기본화

- `app_config.py` `ACTIVE_SHELL_URL` 기본값: 항상 `{LOCAL_URL}/app-new`
- `HAEHAN_DESKTOP_UI` 환경변수는 호환성 유지 목적으로 남겨두나 legacy 값은 무시
- `main_launcher.py` 는 `desktop.consent.check_consent` 사용

## 보존 파일 (도구/엔진)

아래 파일은 도구/엔진으로 보존 필수.

- `local_server.py` — 모든 API endpoint 호스트 (포트 8765)
- `local_agent_service.py` — MCP + Anthropic SDK 에이전트
- `main_launcher.py` — 통합 진입점
- `tray_runtime.py` — 등록/heartbeat 통합
- `admin_webview.py` — Admin Mode role guard
- `cad_bridge_runner/registry/proxy.py` — CAD bridge 계층
- `task_receiver.py`, `status_provider.py`, `remote_access.py`
- `user_settings.py`, `app_config.py`, `local_runner.py`, `audit_desktop.py`
- `consent.py` — 사용자 동의 공유 모듈 (신규, webview_app_pywebview 에서 이전)

## 보존 API endpoint

| Endpoint | 상태 |
|----------|------|
| `GET /health` | ✅ 보존 |
| `GET/POST /agent/status` | ✅ 보존 |
| `GET/POST /agent/register` | ✅ 보존 |
| `GET/POST /local-agent/health` | ✅ 보존 |
| `GET/POST /local-agent/preflight` | ✅ 보존 |
| `GET/POST /local-agent/run` | ✅ 보존 |
| `GET/POST /cad/bridge/status` | ✅ 보존 |
| `GET/POST /cad/bridge/start` | ✅ 보존 |
| `GET/POST /cad/bridge/stop` | ✅ 보존 |
| `GET/POST /cad/bridge/restart` | ✅ 보존 |
| `GET/POST /cad/bridge/proxy` | ✅ 보존 |
| `GET /api/v1/whoami` | ✅ 보존 |
| `GET /logs` | ✅ 보존 |
| `WebSocket /ws/ui` | ✅ 보존 |
| `GET /app-new` | ✅ new_shell 전용 신규 |

## 신규 shell

`desktop/ui_new/` — 서버 사이드 HTML 렌더링 방식.
도구/엔진 API를 내부 함수로 직접 호출 (HTTP 재진입 없음).
WebView URL: `http://127.0.0.1:8765/app-new`

## 다음 공정 (후속)

- HAEHAN-DESKTOP-PACKAGED-APP-NEW-SHELL-SMOKE-01 — exe 패키징 후 /app-new 동작 검증
- HAEHAN-DESKTOP-INSTALLER-BUILD-SMOKE-01 — 인스톨러 빌드 및 설치 smoke
