# HAEHAN_DESKTOP_RELEASE_BASELINE_01

본 문서는 HaehanAI Desktop 데스크탑 단일 실행 파일의 정식 릴리즈 기준점을 고정한다.
이후 모든 빌드/배포/디버깅은 본 baseline 을 출발점으로 한다.

작성일: 2026-05-22
근거 커밋: c8faa5f (build(haehan): HAEHAN_SINGLE_EXE_BUILD_01 — rewire Desktop exe entrypoint and smoke)

---

## 1. 정식 실행 경로 (OFFICIAL)

| 항목 | 값 |
|---|---|
| 산출물 디렉터리 | `dist/HaehanAI-Desktop/` |
| 정식 실행 파일 | `dist/HaehanAI-Desktop/HaehanAI-Desktop.exe` |
| PyInstaller spec | `HaehanAI-Desktop.spec` |
| PyInstaller entrypoint 모듈 | `build/webview_launcher.py` |
| 실제 main 함수 | `desktop.main_launcher.main` |
| 빌드 로그 | `data/logs/build_haehan_desktop.log` |
| exe SHA-256 (baseline) | `943c60f2c5c52bcf33154246b36e8c08d03ae350a15afee1ffdb8147584cf29e` |
| 총 산출물 용량 | 724 MB / 3942 files |
| exe 크기 | 약 19.2 MB |
| version 출력 | `HaehanAI 0.2.0-launcher-foundation` |

### 1.1 부팅 흐름
```
HaehanAI-Desktop.exe
  → build/webview_launcher.py
  → desktop.main_launcher.main()
      → parse_mode()      # --tray (default) / --admin / --diagnostics / --version / --reset-lock
      → check_consent_hook() → run_consent_flow() if needed   # decline → rc=4
      → acquire_lock()    # 단일 인스턴스
      → run_tray_mode()  | run_admin_mode(explicit_role=HAEHAN_ROLE env)
      → graceful_shutdown_hook()
```

### 1.2 환경 변수 (운영 인터페이스)
| 이름 | 의미 | 동작 |
|---|---|---|
| `HAEHAN_SKIP_GUI` | `1`/`true` 시 tkinter consent / tray GUI 미기동 | CI/smoke 전용 |
| `HAEHAN_ROLE` | `admin` 또는 `owner` 면 `--admin` 진입 허용, 그 외는 차단 | rc=0 / rc=2 |

---

## 2. Legacy / 금지 경로

다음 항목은 본 baseline 이후 **운영/배포/CI 어디서도 사용하지 않는다.**
실수로 발견 시 즉시 정리 대상.

| 항목 | 상태 | 비고 |
|---|---|---|
| `dist/HaehanAI-Agent/` | **삭제됨** (재생성 금지) | 구 PyInstaller 산출물 — 정식 exe 와 혼동 위험 |
| `dist/HaehanAI-Agent-*.zip` | 새로 만들지 않음 | |
| `HaehanAI-Agent.spec` | **legacy spec** | 빌드 금지. 정식은 `HaehanAI-Desktop.spec` 만. |
| `desktop/electron/` | **삭제됨** | 구 Electron 런타임. 본 repo 에서 운영 안 함. |
| `desktop/webview_app.py` | **legacy source 보존, 직접 실행 금지** | PyQt6 WebEngine 기반 구 진입점 — main_launcher 흐름과 무관. |
| `desktop/webview_app_pywebview.py::main()` 직접 호출 | **금지** | `_check_consent` 만 main_launcher 가 import 해서 재사용. main() 자체는 더 이상 entry 가 아님. |
| `desktop/ui_dist_backup_*` | 만들지 않음 | UI 산출물 백업 폴더. ui_dist 만 정식. |

---

## 3. Smoke 기준 결과 (baseline)

빌드 직후 `dist/HaehanAI-Desktop/HaehanAI-Desktop.exe` 에 대해 수행된 smoke. 본 결과를 회귀 기준으로 한다.

| 시나리오 | env | 명령 | 기대 rc | 실측 rc |
|---|---|---|---|---|
| 버전 출력 | — | `--version` | 0 | 0 |
| 진단 + secret 마스킹 | `HAEHAN_SKIP_GUI=1` | `--diagnostics` | 0 | 0 |
| consent 없음 차단 | `HAEHAN_SKIP_GUI=1` | `--tray` | **4** | **4** |
| consent 동의 후 진입 | `HAEHAN_SKIP_GUI=1` + `dist/HaehanAI-Desktop/data/consent.json` agreed=true | `--tray` | 0 | 0 |
| admin role=any 차단 | `HAEHAN_SKIP_GUI=1 HAEHAN_ROLE=any` | `--admin` | 2 | 2 |
| admin role=user 차단 | `HAEHAN_SKIP_GUI=1 HAEHAN_ROLE=user` | `--admin` | 2 | 2 |
| admin role=viewer 차단 | `HAEHAN_SKIP_GUI=1 HAEHAN_ROLE=viewer` | `--admin` | 2 | 2 |
| admin role=admin 허용 | `HAEHAN_SKIP_GUI=1 HAEHAN_ROLE=admin` | `--admin` | 0 | 0 |
| admin role=owner 허용 | `HAEHAN_SKIP_GUI=1 HAEHAN_ROLE=owner` | `--admin` | 0 | 0 |
| 잔류 프로세스 | — | smoke 종료 후 | 0개 | 0개 |
| CDP 데몬 유지 | — | smoke 종료 후 | ≥3 | 6 |

`--diagnostics` 응답 내 secret 검사:
- `device_token` / `registration_code` / `password` / `api_key` / `bearer` / `cookie` / `authorization` 원문 출현 = **0건**
- 노출 가능 식별자는 마스킹된 형태로만: `agent_id_masked: la-xxx***yyyy`, `server.url_redacted`, `server.ws_url_redacted`

---

## 4. 회귀 기준

다음이 모두 PASS 여야 baseline 이 유효:

- `pytest tests/test_haehan_*.py` → **281 passed** 이상 (현재 baseline 기준)
- `python scripts/ops/audit_haehan_single_exe_build.py` → PASS
- `python scripts/ops/audit_haehan_consent_dialog.py` → PASS
- `python scripts/ops/audit_haehan_whoami_route.py` → PASS
- `python scripts/ops/audit_haehan_admin_mode_webview_lazy_load.py` → PASS
- `python scripts/ops/audit_haehan_tray_registration_merge.py` → PASS
- `python scripts/ops/audit_haehan_desktop_release_baseline.py` → PASS

---

## 5. 보호 항목 (수정 금지 — baseline 보존 조건)

- `desktop/tray_app.py`
- `desktop/user_settings.py`
- `desktop/webview_app.py` (legacy source 보존 — 삭제 금지)
- `git stash@{0}` (pre-whoami-route-session-leftover)
- `dist/HaehanAI-Desktop-20260521.zip` (이전 패키지 보존)

CDP 운영 인프라(`scripts/browser/cdp/cdp_daemon.py`, `scripts/entry/cdp_cli.py popup-monitor`, `scripts/chrome_ui_monitor.py`, `chrome.exe --remote-debugging-port=9222`) 는 본 baseline 작업 범위 밖이며 종료/조작 금지.
