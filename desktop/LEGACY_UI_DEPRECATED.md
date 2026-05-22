# Legacy UI — Deprecated

공정: HAEHAN-DESKTOP-NEW-SHELL-PHASE1-API-SEPARATION-01
확정일: 2026-05-23

## 폐기 대상 파일

아래 파일은 레거시 UI/App-Shell로 분류되어 폐기 예정이다.
신규 코드에서 이 파일들에 대한 의존 추가 금지.

| 파일 | 분류 | 대체 방향 |
|------|------|---------|
| `tray_app.py` | 레거시 pystray 트레이 | `tray_runtime.py`로 통합 |
| `webview_app.py` | PyQt6 WebEngine 창 | `main_launcher.py` → 신규 shell |
| `webview_app_pywebview.py` | pywebview 창 (구 Desktop.exe) | `main_launcher.py` → 신규 shell |
| `desktop/ui/` | 기존 React/Vite SPA (28개 패널) | `desktop/ui_new/` 신규 shell |

## 보존 파일 (도구/엔진)

아래 파일은 도구/엔진으로 보존 필수.

- `local_server.py` — 모든 API endpoint 호스트 (포트 8765)
- `local_agent_service.py` — MCP + Anthropic SDK 에이전트
- `main_launcher.py` — 통합 진입점 (신규 shell 진입점으로 전환 예정)
- `tray_runtime.py` — 등록/heartbeat 통합
- `admin_webview.py` — Admin Mode role guard
- `cad_bridge_runner/registry/proxy.py` — CAD bridge 계층
- `task_receiver.py`, `status_provider.py`, `remote_access.py`
- `user_settings.py`, `app_config.py`, `local_runner.py`, `audit_desktop.py`

## 삭제 예정 순서

1. 신규 `desktop/ui_new/` shell smoke PASS 확인
2. `tray_app.py`, `webview_app.py`, `webview_app_pywebview.py` 제거
3. `desktop/ui/` 제거
4. 관련 테스트 정리

## 신규 shell 진입점

`desktop/ui_new/` — 기존 React SPA와 독립적인 신규 shell.
도구/엔진 API만 호출하며, 실행 버튼은 Phase 2 smoke 이후 연결.
