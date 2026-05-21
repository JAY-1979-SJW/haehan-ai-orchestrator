# Haehan AI Local Agent — 사용자 설치 가이드

대상: Python 설치 없이 Windows PC 에서 `HaehanAI-Agent.exe` 를 받아 사용하려는 사용자.

## 1. 설치 (압축 해제)

1. 관리자에게 `HaehanAI-Agent.zip` (약 80MB) 을 전달 받습니다.
2. 임의 폴더에 압축 해제. 예:
   ```
   C:\Program Files\HaehanAI-Agent\
   ```
   (관리자 권한 폴더가 아니어도 됩니다. 사용자 폴더면 더 안전.)
3. 해제하면 다음 구조:
   ```
   HaehanAI-Agent\
   ├── HaehanAI-Agent.exe
   └── _internal\          ← 실행에 필요한 런타임 (건드리지 마세요)
   ```

## 2. 환경 변수 설정 (필수)

WebSocket 활성화 + 서버 주소:
```cmd
setx HAEHAN_AGENT_WS_ENABLED true
setx HAEHAN_AGENT_SERVER https://haehan-ai.kr/orchestrator
```

또는 일시적으로 (현재 cmd 세션만):
```cmd
set HAEHAN_AGENT_WS_ENABLED=true
set HAEHAN_AGENT_SERVER=https://haehan-ai.kr/orchestrator
```

## 3. 첫 등록 (관리자 발급 코드 사용)

1. 관리자에게 **registration_code** 1개를 요청. (1회용, 10분 TTL)
2. 받은 코드를 환경변수에 설정 후 등록 실행:
   ```cmd
   set HAEHAN_AGENT_CODE=<관리자가 알려준 코드>
   HaehanAI-Agent.exe --register
   ```
3. 성공 시 출력:
   ```
   등록 성공: agent_id=la-xxx***yyy
   ```
   - `agent_id` 일부가 마스킹되어 표시됩니다.
   - **device_token 은 Windows Credential Manager 에 자동 저장**되어 디스크에 평문으로 남지 않습니다.

4. 전체 `agent_id` 가 필요하면 관리자가 서버에서 확인할 수 있습니다.

## 4. 재실행 (이후 자동 연결)

전체 agent_id 를 확인했다면 (예: `la-612b17d65dd3`):
```cmd
HaehanAI-Agent.exe --agent-id la-612b17d65dd3
```

자동으로:
1. Windows Credential Manager 에서 device_token 로드
2. wss 연결 → auth_ok 수신
3. heartbeat 시작 (30~60초 주기)

연결 성공 로그:
```
WebSocket 연결 시도 | url=wss://haehan-ai.kr/orchestrator/...
WebSocket auth_ok (agent_id=la-612b17d65dd3)
```

종료하려면 `Ctrl+C`.

## 5. 진단 (문제 발생 시)

```cmd
HaehanAI-Agent.exe --diagnostics
```

출력 예시:
```
── 로컬 에이전트 연결 상태 ──
서버: https://haehan-ai.kr/orchestrator
WS  : wss://haehan-ai.kr/orchestrator/api/v1/local-agents/ws
agent_id: la-612***5dd3
상태: NOT_REGISTERED / CONNECTED / AUTH_FAILED / ...
마지막 heartbeat: 2026-05-21T...
마지막 오류: AUTH_FAILED_4401 / SERVER_NOT_REACHABLE / ...
안내: <한글 안내 문구>
조치:
  - <할 일 1>
  - <할 일 2>
```

## 6. 의존성 자가 검사

설치 직후 또는 문제 발생 시:
```cmd
HaehanAI-Agent.exe --self-test
```

OK 응답이면 의존성/저장소/URL/diagnostics 모두 정상.

## 7. 오류별 사용자 조치

| 오류 코드 | 의미 | 조치 |
|----------|------|------|
| `AUTH_FAILED_4401` | 장치 인증 실패. device_token 변경/폐기됨 | 데스크앱 **재등록** 필요 (`--reset` → `--register`) |
| `REG_CODE_EXPIRED` | 등록코드 TTL 만료 (10분 초과) | 관리자에게 **새 코드** 요청 |
| `REG_CODE_INVALID` | 잘못된 코드 입력 | 코드 다시 확인 후 재입력 |
| `REG_CODE_ALREADY_USED` | 코드 재사용 시도 (1회용) | 새 코드 요청 |
| `SERVER_NOT_REACHABLE` | 서버 접속 실패 | `HAEHAN_AGENT_SERVER` URL 확인, 인터넷 확인 |
| `NETWORK_BLOCKED_PROXY` | 회사 프록시/방화벽 의심 | 회사 IT 에 wss 차단 여부 문의 |
| `HEARTBEAT_LOST` | heartbeat 응답 없음 | 자동 재연결 진행. 5분 이상 지속 시 진단 실행 |
| `TOKEN_NOT_STORED` | Credential Manager 에 token 없음 | `--register` 로 재등록 |
| `AUTH_TIMEOUT` | 서버 응답 시간 초과 | 잠시 후 재시도 |

## 8. 재등록 방법 (token 폐기 후)

```cmd
HaehanAI-Agent.exe --reset --agent-id la-612b17d65dd3
# → Credential Manager 에서 token 삭제

# 새 코드로 재등록
set HAEHAN_AGENT_CODE=<새 코드>
HaehanAI-Agent.exe --register
```

## 9. SmartScreen / 백신 경고 안내

본 빌드는 **코드 서명되지 않았습니다**. Windows SmartScreen 또는 일부 백신이 경고할 수 있습니다.

대응:
- SmartScreen: "추가 정보" → "실행" 클릭
- 백신 경고: 관리자에게 sha256 확인 요청
  - 정식 빌드 sha256 은 `data/inspection/local_agent_installer_package/checksums.json` 에서 확인 가능
- 백신 false positive 의심 시 관리자에게 보고

## 10. 자주 묻는 질문

**Q. Python 이 설치되어 있어야 하나요?**
A. 아니요. `HaehanAI-Agent.exe` 와 `_internal/` 폴더만 있으면 Python 없이 실행됩니다.

**Q. 폴더를 다른 위치로 옮겨도 되나요?**
A. 네. `HaehanAI-Agent.exe` 와 `_internal/` 폴더를 **함께** 옮기세요.

**Q. device_token 이 어디에 저장되나요?**
A. **Windows Credential Manager** (제어판 → 자격 증명 관리자 → 일반 자격 증명) 에 `haehan-agent` 라는 이름으로 저장됩니다. 평문 파일로 디스크에 남지 않습니다.

**Q. 다른 사용자 계정으로 token 을 공유할 수 있나요?**
A. 불가능합니다. Credential Manager 는 Windows 사용자별로 격리됩니다. 다른 계정에서 사용하려면 그 계정에서 재등록하세요.

**Q. 같은 PC 에서 여러 agent 를 운영할 수 있나요?**
A. 네. 각 agent 마다 별도의 `--agent-id` 로 실행하면 Credential Manager 에 각각 저장됩니다.

## 11. 알려진 제한

- macOS / Linux 빌드: 미제공 (별도 공정 예정)
- GUI 트레이 아이콘: 미제공 (CLI only)
- 자동 업데이트: 미제공 (관리자가 신규 zip 배포)
- 코드 서명: 미적용 (SmartScreen 경고 가능)
