# 외부 사용자 PC Field Test 런북

대상: 빌드 머신과 다른 Windows PC + 다른 네트워크에서 `HaehanAI-Agent.zip` 을 받아 실행하는 외부 테스터.
출력: `user_field_test_report_external.json` 작성 후 회신.

## 1. 준비

- 다운로드: 관리자가 전달하는 `HaehanAI-Agent.zip` (≈84MB)
- sha256 비교:
  ```powershell
  Get-FileHash HaehanAI-Agent.zip -Algorithm SHA256
  # 기대: C69039EB562CF03AFE8C12FB47A542E03B60EFE8DD92E221B61128D248E419FB
  ```
- 압축 해제: 임의 폴더 (예: `C:\Tools\HaehanAI-Agent\`)

## 2. SmartScreen / 백신 응답 기록

`HaehanAI-Agent.exe` 첫 실행 시 다음 중 하나가 발생할 수 있음:

| 시나리오 | 응답 | 보고서 기록 |
|----------|------|------------|
| SmartScreen 표시 | "추가 정보 → 실행" | `smartscreen_warning_observed: true` |
| Windows Defender 차단 | 격리 / 삭제 | `antivirus_block_observed: true` + 백신 명/규칙명 |
| 3rd-party 백신 알림 | 사용자 결정 | 백신 이름 / 알림 내용 |
| 조용히 실행 | 정상 | `false` 기록 |

## 3. 검증 명령 (PowerShell 권장 — 한글 깨짐 회피)

```powershell
cd C:\Tools\HaehanAI-Agent

# 3-1) self-test
.\HaehanAI-Agent.exe --self-test

# 3-2) diagnostics
.\HaehanAI-Agent.exe --diagnostics

# 3-3) 환경변수
$env:HAEHAN_AGENT_WS_ENABLED = "true"
$env:HAEHAN_AGENT_SERVER     = "https://haehan-ai.kr/orchestrator"

# 3-4) 등록 (관리자에게 받은 1회용 코드)
$env:HAEHAN_AGENT_CODE = "여기에-코드-붙여넣기"
.\HaehanAI-Agent.exe --register
# → "등록 성공: agent_id=la-xxx***yyy" 기대

# 3-5) 재실행 자동 연결 (관리자가 알려준 풀 agent_id)
.\HaehanAI-Agent.exe --agent-id la-xxxxxxxxxxxx
# → "WebSocket auth_ok" 로그 기대

# 3-6) GUI 모드
.\HaehanAI-Agent.exe --gui

# 3-7) 오류 안내 확인 — 잘못된 agent_id
.\HaehanAI-Agent.exe --agent-id la-nonexistent-x
# → TOKEN_NOT_STORED + 재등록 안내 기대
```

## 4. 외부 IP 차단 확인 (admin endpoint)

외부 IP 에서 다음 호출이 **403** 또는 **거부** 되어야 함 (admin 보호):

```powershell
# admin agent 목록 — 외부 IP 차단 기대
Invoke-WebRequest -Uri "https://haehan-ai.kr/orchestrator/api/v1/local-agents/registration-codes" -Method GET
# 기대: 403 or connection refused
```

만약 200 응답 + JSON 받으면 → **FAIL_ADMIN_ENDPOINT_PUBLIC** 즉시 보고.

## 5. 보고서 작성

다음 형식으로 `user_field_test_report_external.json` 작성 후 회신:

```json
{
  "tester_pc": {
    "os": "Windows 11 / 10",
    "ip_in_allowlist": false,
    "network_type": "home / office / hotspot",
    "python_installed": false
  },
  "artifacts_verified": {
    "zip_sha256_match": true,
    "exe_sha256_match": true
  },
  "13_steps": {
    "01_extract": true,
    "02_self_test_rc": 0,
    "03_diagnostics_rc": 0,
    "04_gui_launch": true,
    "05_register_status": 200,
    "06_token_stored_credential_manager": true,
    "07_wss_auth_ok": true,
    "08_heartbeat_ack_observed": true,
    "09_reexecute_auto_reconnect": true,
    "10_token_not_stored_message_shown": true,
    "11_register_no_env_handled": true,
    "12_smartscreen_warning_observed": "true / false",
    "13_admin_endpoint_blocked_external": true
  },
  "feedback_freeform": "사용 편의성, 메시지 명확성, 한글 표시 등",
  "leaks_observed": [],
  "antivirus_info": {
    "smartscreen": "...",
    "defender": "...",
    "third_party": "..."
  }
}
```

## 6. 금지

- registration_code 원문을 회신에 포함하지 마세요
- device_token 값을 어디에도 적지 마세요
- 스크린샷 첨부 시 token / agent_id 풀버전이 보이는지 확인 후 마스킹

## 7. 회신

- 메일 또는 PR 댓글로 `user_field_test_report_external.json` 첨부
- 차단/오류 발생 시 sha256 + 환경 정보 함께
