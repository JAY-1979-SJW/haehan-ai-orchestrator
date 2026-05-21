# Haehan AI Local Agent — Installer Package

대상: 사용자 PC에 Python 설치 없이 실행 가능한 데스크앱 에이전트.
운영 서버: `https://haehan-ai.kr/orchestrator`

## 1. 패키징 방식

| 항목 | 결정 |
|------|------|
| 도구 | **PyInstaller** (Windows) |
| 모드 | **onefolder** (one-file 은 백신 오탐 위험) |
| 엔트리 | `local_agent.desktop_launcher:main` |
| 산출 | `dist/HaehanAI-Agent/HaehanAI-Agent.exe` |
| 의존성 | `websockets`, `keyring`, `local_agent.*` |

## 2. 사용자 최초 실행 흐름

```
1) 사용자: HaehanAI-Agent.exe 다운로드 (관리자 배포)
2) 관리자: 사용자에게 registration_code 1회용 발급 (TTL 10분)
3) 사용자: cmd 또는 PowerShell 에서 환경변수 설정 + 등록 실행
     set HAEHAN_AGENT_CODE=<code>
     HaehanAI-Agent.exe --register
4) 앱: register-with-code 호출 → agent_id + device_token 수신
5) 앱: device_token 을 Windows Credential Manager (keyring) 에 저장
        (불가 시 %APPDATA%\HaehanAI\local_agent\... 평문 fallback — 옵트인)
6) 사용자: HaehanAI-Agent.exe --agent-id <agent_id> 로 연결
```

## 3. 재실행 (자동 연결)

```
HaehanAI-Agent.exe --agent-id la-xxxxxxxxxxxx
```

내부 동작:
- token_store.load_device_token() → device_token 로드
- websocket_client.connect(agent_id, device_token) → wss 연결
- heartbeat 시작

## 4. 진단/오류 메시지

`HaehanAI-Agent.exe --diagnostics` 실행 시:
- 서버 URL, WS URL
- token_store backend (Windows Credential Manager / plaintext fallback / 없음)
- 현재 연결 상태
- 마지막 오류 코드별 사용자 안내 (한글)

오류 코드 → 사용자 안내 (connection_diagnostics):
| code | 안내 |
|------|------|
| AUTH_FAILED_4401 | 데스크앱 재등록 |
| REG_CODE_EXPIRED | 새 등록코드 요청 |
| REG_CODE_INVALID | 코드 입력 확인 |
| REG_CODE_ALREADY_USED | 새 등록코드 요청 |
| SERVER_NOT_REACHABLE | 서버 URL/네트워크 확인 |
| NETWORK_BLOCKED_PROXY | 회사 프록시/방화벽 확인 |
| HEARTBEAT_LOST | 자동 재연결 진행 |
| TOKEN_NOT_STORED | 데스크앱 재등록 |
| AUTH_TIMEOUT | 서버 응답 시간 초과 — 재시도 |

## 5. self-test

`HaehanAI-Agent.exe --self-test` :
- 핵심 의존성 import 가능?
- token_store backend 가용 여부
- ws URL normalize round-trip
- diagnostics render 가 token leak 없이 작동

미설치/빌드 환경에서도 의존성 sanity check.

## 6. token 저장 정책

우선순위:
1. **Windows Credential Manager** (keyring 라이브러리 자동 detect)
2. **평문 파일 fallback** — `~/.haehan_agent/tokens/<server>_<agent_id>.token`
   - 명시적 `allow_plaintext_fallback=True` 옵트인 필요
   - 권한 제한 (POSIX 0600), Windows는 user-only

device_token 원문은:
- 로그 출력 금지
- build report 미저장
- diagnostics는 sha256[:16] hash 만

## 7. 빌드 명령

```bash
# 의존성 설치 (개발/빌드 머신만)
pip install pyinstaller websockets keyring

# 빌드 (one-folder, 기본)
python -m scripts.build_desktop_agent_windows

# 빌드 (one-file, 백신 위험 인지하고)
python -m scripts.build_desktop_agent_windows --onefile

# 깨끗이 다시 빌드
python -m scripts.build_desktop_agent_windows --clean
```

산출:
- `dist/HaehanAI-Agent/` (onefolder) 또는 `dist/HaehanAI-Agent.exe` (onefile)
- `data/inspection/local_agent_installer_package/build_report.json`
- `data/inspection/local_agent_installer_package/checksums.json`

**dist/ 는 git commit 대상 아님** (.gitignore 또는 quality_gate 가드).

## 8. 보안 체크리스트

- [ ] device_token 원문 빌드 산출물에 없음 (sha256 검증)
- [ ] registration_code 원문 미저장
- [ ] PyInstaller 산출 .exe 에 SECRET 환경변수 미포함
- [ ] keyring backend 가 Null/Fail 이 아닌지 확인 (Windows: WinVaultKeyring 기대)
- [ ] 코드 서명: 본 공정 OUT_OF_SCOPE (별도 공정 `CODE_SIGNING_01`)
- [ ] 자동 업데이트: 본 공정 OUT_OF_SCOPE

## 9. 알려진 제한

- macOS .dmg / Linux deb: OUT_OF_SCOPE (별도 공정)
- Code Signing: OUT_OF_SCOPE → 백신/SmartScreen 경고 가능성
- Auto-update: OUT_OF_SCOPE → 신규 버전 배포는 수동
- GUI (트레이 아이콘/창): 본 공정은 CLI 우선. tray_app.py 는 개발 전용으로 분리.

## 10. 다음 공정 후보

1. **`CODE_SIGNING_01`** — 코드 서명 인증서 적용
2. **`AGENT_GUI_TRAY_01`** — 시스템 트레이 아이콘 + 사용자 진단 GUI
3. **`AUTO_UPDATE_01`** — 자동 업데이트 메커니즘
4. **`MAC_LINUX_BUILD_01`** — .dmg / .deb 빌드
