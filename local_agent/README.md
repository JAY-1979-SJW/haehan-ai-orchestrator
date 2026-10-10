# haehan-ai 로컬 에이전트 (Stage 1)

Windows PC 에서 실행되는 사용자 설치형 에이전트.
서버 오케스트레이터(`ai_orchestrator`) 와 연결되어 read-only 안전 작업만 수행한다.

> 본 1단계는 폴링 모드 데모. WebSocket 양방향 푸시는 2단계에서 활성화.

---

## 핵심 원칙

- **사용자 설치/실행 기반**: 서비스 자동 등록·자동 시작 금지. 사용자가 직접 실행, Ctrl+C 로 즉시 종료.
- **read-only 우선**: 1단계에서 자동 실행되는 액션은 부수 효과 없는 작업만.
- **파일 수정/삭제/전송 금지**: `delete_file` / `upload_file` / `modify_file` / `execute_shell` 액션은 등록 자체를 하지 않는다.
- **위험 작업은 텔레그램 승인 게이트 재사용**: `capture_screenshot` (high) 은 서버 측 `issue_token_for_dev_reg` 로 승인 대기.
- **무단 원격제어 금지**: 본 에이전트가 등록한 PC 외에는 서버가 어떤 PC 도 제어하지 않는다.

---

## 디렉터리 구조

```
local_agent/
├── agent.py             # 메인 엔트리 (--register, --ping)
├── config.py            # 서버 URL / 화이트리스트 / 토큰 보관 경로
├── actions.py           # ping / system_info / open_url / list_files_readonly …
├── websocket_client.py  # 2단계 WS 스텁 (현재 비활성)
├── audit.py             # 로컬 감사 로그 (PC 보관)
└── README.md
```

---

## 지원 액션 (Stage 1)

| action | risk_level | 1단계 동작 |
|--------|------------|-----------|
| `ping` | low | 서버 자동 완료 (pong) |
| `system_info` | low | 서버 자동 완료 (OS/host) |
| `list_allowed_apps` | low | 서버 자동 완료 (앱 목록 + 실행 가능 여부) |
| `open_url` | low | 큐잉 → 에이전트가 `webbrowser.open` (http/https 만) |
| `list_files_readonly` | medium | 큐잉 → 사전 화이트리스트 디렉터리만 나열 |
| `capture_screenshot` | high | 승인 토큰 발행, **승인 후에도 1단계에서는 미구현** (NOT_IMPLEMENTED_STAGE1) |

### 명시적 거절 (등록조차 안 됨)

`delete_file`, `upload_file`, `modify_file`, `execute_shell` — 호출 시
서버에서 `400 UNKNOWN_ACTION`, 에이전트 측 `actions.execute_action` 에서도
`ACTION_FORBIDDEN` 으로 즉시 차단.

---

## 허용 앱 (Allowed Apps)

`browser`, `excel`, `hwp`, `cad` 만 `ALLOWED_APPS` 화이트리스트에 등록.
1단계에서는 **`browser` (open_url) 만 실제 실행 가능**.
나머지 앱은 `list_allowed_apps` 응답에 `executable_stage1: false` 로 표시되며
실제 실행 액션은 등록되어 있지 않다.

---

## 실행

### 1) 서버에 신규 에이전트 등록

```powershell
python -m core.agent_runtime.agent --register --user <orchestrator_user> --password <pwd>
```

응답에 표시되는 `device_token` 은 **1회만** 노출된다.
`%USERPROFILE%\.haehan_agent\device_token` 에 자동 저장되며, Windows ACL 로
사용자 전용 권한을 주는 것을 권장한다.

### 2) 로컬 ping (서버 호출 없음, 셀프 테스트)

```powershell
python -m core.agent_runtime.agent --ping
```

---

## 환경 변수

| 변수 | 기본값 | 의미 |
|------|--------|------|
| `HAEHAN_AGENT_SERVER` | `http://127.0.0.1:8400` | 서버 base URL |
| `HAEHAN_AGENT_WS_ENABLED` | `false` | WebSocket 활성화 (2단계) |
| `HAEHAN_AGENT_POLL_SEC` | `10` | 폴링 주기 |
| `HAEHAN_AGENT_PUBLIC_DIR` | `~/Documents/haehan-public` | list_files_readonly 화이트리스트 |
| `HAEHAN_AGENT_AUDIT` | `~/.haehan_agent/audit.jsonl` | 로컬 감사 로그 |
| `HAEHAN_AGENT_AUDIT_FALLBACK` | `logs/local_agent_audit.jsonl` or temp fallback | primary 감사 로그 쓰기 실패 시 대체 감사 로그 |
| `HAEHAN_AGENT_TOKEN` | `~/.haehan_agent/device_token` | device_token 보관 위치 |
| `HAEHAN_AGENT_USER` / `HAEHAN_AGENT_PASSWORD` | (없음) | 서버 Basic auth |

---

## 보안 체크리스트

- [ ] `device_token` 원문은 메모리 외 저장하지 않거나, 사용자 홈 보호 디렉터리에만 저장
- [ ] 로컬 감사 로그(`audit.jsonl`) 에는 password / token / cookie / secret 키가 자동 제거된 후 기록됨
- [ ] `open_url` 은 `http://` / `https://` 만 허용, `file://` / `javascript:` / `data:` 는 차단
- [ ] `list_files_readonly` 는 `READ_ONLY_DIRS` 화이트리스트 외부 접근 시 `DIR_NOT_ALLOWED` 거절
- [ ] WebSocket 은 2단계까지 비활성, `WebSocketDisabled` 예외로 강제 차단
- [ ] 백그라운드 / 자동 시작 / 트레이 은폐 실행 미지원 — 사용자가 항상 종료할 수 있어야 한다
