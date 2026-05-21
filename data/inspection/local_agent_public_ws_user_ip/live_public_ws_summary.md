# Live Public WS — from user IP

server: `https://haehan-ai.kr/orchestrator`
ws: `wss://***.kr/orchestrator/api/v1/local-agents/ws`

## 00_regcode_loaded
```
{
  "ok": true,
  "len": 14,
  "redacted": true
}
```
## 01_register_with_code
```
{
  "status": 200,
  "ok": true,
  "agent_id_masked": "la-e***e52a",
  "device_token_hash": "4420d3b52f833fe7",
  "error": ""
}
```
## 02_ws_auth_ok
```
{
  "steps": [
    "ws_open",
    "auth_sent",
    "auth_ok",
    "hb_0_heartbeat_ack",
    "hb_1_heartbeat_ack"
  ],
  "ok": true,
  "auth_response_type": "auth_ok"
}
```
## 03_reconnect_same_token
```
{
  "steps": [
    "ws_open",
    "auth_sent",
    "auth_ok",
    "hb_0_heartbeat_ack"
  ],
  "ok": true,
  "auth_response_type": "auth_ok"
}
```
## 04_bad_token
```
{
  "steps": [
    "ws_open",
    "auth_sent"
  ],
  "ok": false,
  "error": "received 4401 (private use); then sent 4401 (private use)"
}
```
## 05_admin_endpoints_from_allowed_ip
```
{
  "list_status": 404,
  "issue_status": 200,
  "note": "이 IP 는 allowlist 멤버라 admin 접근 성공 가능. 외부 IP 차단은 nginx config 검증으로 보장 (deploy audit)."
}
```
## 06_user_diagnostics
```
{
  "connected_block": "── 로컬 에이전트 연결 상태 ──\n서버: https://haehan-ai.kr/orchestrator\nWS  : wss://haehan-ai.kr/orchestrator/api/v1/local-agents/ws\nagent_id: la-edc***e52a\n상태: CONNECTED\n마지막 heartbeat: 2026-05-21T11:56:09+09:00\n마지막 오류: -",
  "auth_failed_block": "── 로컬 에이전트 연결 상태 ──\n서버: https://haehan-ai.kr/orchestrator\nWS  : wss://haehan-ai.kr/orchestrator/api/v1/local-agents/ws\nagent_id: la-edc***e52a\n상태: AUTH_FAILED\n마지막 heartbeat: -\n마지막 오류: AUTH_FAILED_4401\n안내: 장치 인증 실패(4401). device_token 이 변경되었거나 폐기됐을 수 있습니다. 데스크앱 재등록을 진행하세요.\n조치:\n  - 데스크앱을 재등록(새 registration_code 발급 → 입력)하세요."
}
```