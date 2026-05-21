# Local Desktop Agent — Live Connection Smoke
- generated_at: 2026-05-21T11:21:15+0900

## A_server_head
```
{
  "step": "A_server_head",
  "remote_head": "a9b4fe33158a716d",
  "ssh_head": "a9b4fe33158a716d",
  "local_head": "d5828a9d5806c5c3",
  "server_matches_local": false
}
```
## B_containers
```
{
  "step": "B_containers",
  "ssh_ok": true,
  "containers": [
    "haehan-ai-orchestrator-admin-web\tUp 2 days",
    "haehan-ai-orchestrator-api\tUp 2 days (healthy)",
    "haehan-ai-orchestrator-file-map-executor\tUp 8 days (healthy)",
    "haehan-ai-orchestrator-browser-worker\tUp 8 days (healthy)",
    "nginx\tUp 8 days",
    "gongmu-nginx\tUp 12 days"
  ]
}
```
## C_nginx_ws
```
{
  "step": "C_nginx_ws",
  "ssh_ok": true,
  "has_proxy_http_version_11": true,
  "has_upgrade_header": true,
  "has_connection_upgrade": true,
  "has_proxy_read_timeout": true,
  "has_ip_allowlist": true,
  "uses_orchestrator_prefix": true,
  "upstream_target": true,
  "snippet": "    # /orchestrator/api/v1/local-agents/ws -> WebSocket (local-agent WS, Stage G2B-WS-1)\n    location /orchestrator/api/v1/local-agents/ws {\n        allow 220.79.246.190;\n        allow 127.0.0.1;\n        allow 172.18.0.1;\n        deny  all;\n\n        proxy_pass         http://haehan-ai-orchestrator-api:8400/api/v1/local-agents/ws;\n        proxy_http_version 1.1;\n        proxy_set_header   Upgrade           $http_upgrade;\n        proxy_set_header   Connection        \"upgrade\";\n        proxy_set_header   Host              $host;\n        proxy_set_header   X-Real-IP         $remote_addr;\n        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;\n        proxy_set_header   X-Forwarded-Proto $scheme;\n        proxy_read_timeout    3600s;\n        proxy_send_timeout    3600s;\n    }\n"
}
```
## D_inprocess_e2e
```
{
  "step": "D_inprocess_e2e",
  "issue_consume_ok": true,
  "register_ok": true,
  "token_not_stored_raw": true,
  "auth_ok": true,
  "bad_token_4401_ok": true,
  "set_connected_ok": true,
  "heartbeat_ok": true,
  "reconnect_ok": true
}
```
## E_url_normalize
```
{
  "step": "E_url_normalize",
  "cases": [
    {
      "input": "https://api.haehan.ai",
      "expected": "wss://api.haehan.ai/api/v1/local-agents/ws",
      "actual": "wss://api.haehan.ai/api/v1/local-agents/ws",
      "ok": true
    },
    {
      "input": "https://api.haehan.ai/orchestrator",
      "expected": "wss://api.haehan.ai/orchestrator/api/v1/local-agents/ws",
      "actual": "wss://api.haehan.ai/orchestrator/api/v1/local-agents/ws",
      "ok": true
    },
    {
      "input": "http://localhost:8400",
      "expected": "ws://localhost:8400/api/v1/local-agents/ws",
      "actual": "ws://localhost:8400/api/v1/local-agents/ws",
      "ok": true
    }
  ],
  "all_ok": true
}
```
## F_token_leak
```
{
  "step": "F_token_leak",
  "secret_in_output": false,
  "raw_agent_id_in_output": false,
  "leak_keywords_block": [
    "token",
    "device_token"
  ],
  "leak_keywords_one": [
    "token",
    "device_token"
  ],
  "pass": true
}
```