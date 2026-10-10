# HAEHAN_DESKTOP_USER_RUN_BASELINE_01

본 문서는 정식 HaehanAI Desktop exe 가 **실제 사용자 실행** 기준으로 어떤 동작/응답을 보이는지를 고정한다.
이후 설치/배포/업데이트 공정은 본 baseline 의 동작을 회귀 기준으로 사용한다.

작성일: 2026-05-22
근거 smoke 공정: HAEHAN_DESKTOP_USER_RUN_SMOKE_01
근거 빌드 baseline: [HAEHAN_DESKTOP_RELEASE_BASELINE_01](./HAEHAN_DESKTOP_RELEASE_BASELINE_01.md)

---

## 1. 정식 exe 식별자

| 항목 | 값 |
|---|---|
| 경로 | `dist/HaehanAI-Desktop/HaehanAI-Desktop.exe` |
| SHA-256 | `943c60f2c5c52bcf33154246b36e8c08d03ae350a15afee1ffdb8147584cf29e` |
| version | `HaehanAI 0.2.0-launcher-foundation` |
| entrypoint | `desktop.main_launcher.main` (via `build/webview_launcher.py`) |

---

## 2. 실행 전 프로세스 상태 (사전 조건)

| 대상 | 기대 | 측정 |
|---|---|---|
| `HaehanAI-Desktop.exe` | 미실행 | 미실행 ✅ |
| `HaehanAI-Agent.exe` | 미실행 | 미실행 ✅ |
| Electron 프로세스 | 미실행 | 미실행 ✅ |
| CDP 운영 프로세스 (`cdp_daemon` / `popup_monitor` / `chrome_ui_monitor`) | 유지 | 6 ✅ |

다중 앱 충돌(레거시 Agent / Electron / 신규 Desktop 이 동시에 떠서 연결이 꼬이는 현상)이 발생하지 않도록 위 사전 조건이 보장되어야 한다.

---

## 3. Consent Smoke 결과

| 시나리오 | env | 명령 | 기대 rc | 실측 rc |
|---|---|---|---|---|
| consent 없음 차단 | `HAEHAN_SKIP_GUI=1` | `--tray` | rc=4 | rc=4 ✅ |
| consent agreed=true 진입 | `HAEHAN_SKIP_GUI=1` | `--tray` | 0 | 0 ✅ |
| 재실행 시 재요구 없음 | `HAEHAN_SKIP_GUI=1` | `--tray` (2회차) | 0 | 0, `agreed_at` 보존 ✅ |

consent.json 스키마(허용 키): `agreed`, `agreed_at`, `version`, `scope` 만 — secret/token 류 키 0건.

---

## 4. Admin Role Guard 결과

| HAEHAN_ROLE | 기대 | 실측 rc |
|---|---|---|
| `any` | 차단 (rc=2) | 2 ✅ |
| `user` | 차단 (rc=2) | 2 ✅ |
| `viewer` | 차단 (rc=2) | 2 ✅ |
| `admin` | 허용 (rc=0) | 0 ✅ |
| `owner` | 허용 (rc=0) | 0 ✅ |

env 미설정 시 (HAEHAN_ROLE unset) → 로컬 server 미기동 상태에서 `api_error` → rc=2 (차단). 즉 **명시적 admin 권한이 있어야만 admin 모드 진입**.

---

## 5. Diagnostics Secret Masking 결과

`HAEHAN_SKIP_GUI=1 HaehanAI-Desktop.exe --diagnostics` 결과 검증:

| 항목 | 측정 |
|---|---|
| `agent_id_masked` | `la-xxx***yyyy` 형식 마스킹 ✅ |
| `server.url_redacted` | 도메인만 노출 (`https://haehan-ai.kr/orchestrator`) ✅ |
| `server.ws_url_redacted` | 도메인만 노출 (`wss://haehan-ai.kr/orchestrator/api/v1/local-agents/ws`) ✅ |
| `token.present` | bool 만 (원문 미노출) ✅ |
| secret 패턴 (`device_token`/`registration_code`/`password`/`api_key`/`bearer`/`cookie`/`authorization`) 의 실제 값 | **0건** ✅ |

---

## 6. 종료 후 잔류/유지

| 대상 | 기대 | 측정 |
|---|---|---|
| `HaehanAI-Desktop.exe` 프로세스 | 잔류 없음 | 없음 (NO-RESIDUAL) ✅ |
| CDP 운영 프로세스 | 유지 | 6 ✅ |

---

## 7. Legacy 경로 부재

baseline 시점 기준 다음 경로가 부재함을 사용자 실행 기준으로도 재확인:

- `dist/HaehanAI-Agent/` — absent ✅
- `desktop/electron/` — absent ✅
- `desktop/ui_dist_backup_*` — absent ✅

---

## 8. 회귀 기준 (테스트/감리)

| 항목 | 결과 |
|---|---|
| `pytest tests/test_haehan_*.py` | **290 passed**, 2 warnings ✅ |
| `audit_haehan_single_exe_build` | PASS ✅ |
| `audit_haehan_consent_dialog` | PASS ✅ |
| `audit_haehan_whoami_route` | PASS ✅ |
| `audit_haehan_admin_mode_webview_lazy_load` | PASS ✅ |
| `audit_haehan_tray_registration_merge` | PASS ✅ |
| `audit_haehan_desktop_release_baseline` | PASS ✅ |
| `audit_haehan_legacy_entrypoint_guard` | PASS ✅ |

---

## 9. 보호 항목 (수정 금지 — baseline 보존 조건)

- `desktop/tray_app.py`
- `desktop/user_settings.py`
- `desktop/webview_app.py` (legacy source 보존 — 삭제 금지)
- `git stash@{0}` (pre-whoami-route-session-leftover)
- `dist/HaehanAI-Desktop-20260521.zip` (이전 패키지 보존)
- CDP 운영 인프라 (`scripts/browser/cdp/cdp_daemon.py` / `scripts/entry/cdp_cli.py popup-monitor` / `scripts/chrome_ui_monitor.py` / `chrome.exe --remote-debugging-port=9222`)

---

## 10. 사용자 실행 표준 절차 (요약)

1. 사전 확인: 위 §2 사전 조건 충족.
2. 실행: `dist/HaehanAI-Desktop/HaehanAI-Desktop.exe` 만 실행. **다른 spec 빌드 산출물 / Electron / Agent / `python -m desktop.webview_app` 직접 실행은 금지.**
3. 최초 1회 consent 동의 → 이후 자동 통과.
4. Admin 모드는 운영자 권한(`HAEHAN_ROLE=admin` 또는 `owner`) 이 있어야 진입.
5. 종료 후 잔류 프로세스 없음을 확인.
6. CDP 데몬은 별도 라이프사이클 — 본 앱이 건드리지 않음.
