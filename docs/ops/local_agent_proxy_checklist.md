# 로컬 에이전트 WebSocket nginx/프록시 체크리스트

`/api/v1/local-agents/ws` 가 서버 앞단 nginx/리버스 프록시를 통과하도록 설정 확인.

## 1. nginx site 설정

```nginx
location /api/v1/local-agents/ws {
    proxy_pass http://app_backend;       # upstream
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 600s;          # heartbeat 주기보다 크게
    proxy_send_timeout 600s;
}
```

핵심 헤더:
- `proxy_http_version 1.1`
- `Upgrade $http_upgrade`
- `Connection "upgrade"`

이 셋이 빠지면 클라이언트가 `4401` 받기 전에 핸드셰이크 실패.

## 2. HTTPS / wss

- 서버가 HTTPS 면 클라이언트는 **반드시 `wss://`** 사용.
- self-signed 인증서는 데스크앱 측 SSL 검증 우회 코드 금지 — 정상 인증서 발급 후 사용.

## 3. 타임아웃

- 클라이언트 heartbeat 주기 (예: 30~60s) < `proxy_read_timeout` (600s 권장)
- 너무 짧으면 idle 시 ws 가 끊긴다.

## 4. 경로/라우팅

- 서버 라우트: `/api/v1/local-agents/ws`
- nginx location 이 위 경로와 정확히 일치하는지 확인.
- 다른 location 이 더 specific 하지 않은지 (가장 긴 prefix 매칭 우선).

## 5. 방화벽/보안 그룹

- 클라우드 보안 그룹/방화벽에서 인바운드 443 (HTTPS+WSS) 허용.
- WAF/CDN 사용 시 WebSocket 통과 옵션 켜기 (Cloudflare: "WebSockets ON").

## 6. 디버깅

클라이언트 4401 시:
1. `device_token` 폐기/변경 → 재등록 필요 (사용자에게 `AUTH_FAILED_4401` 안내)
2. 서버 로그: `local_agent_router.py` 의 `_authenticate_agent` 결과 확인.

서버 도달 자체 실패 시 (TCP/TLS 단계):
1. `curl -I https://<server>/api/v1/local-agents/diagnostics` 로 도달성 확인.
2. nginx `error.log` 의 `upstream` 줄 확인.
3. 클라이언트 측 `connection_diagnostics.normalize_ws_url(server_base_url)` 결과 확인.

WebSocket 핸드셰이크 실패 (HTTP 200 받았는데 ws 안 됨):
- `Upgrade/Connection` 헤더 누락 — 위 1번 항목 재확인.

## 7. 운영 점검 명령

```bash
# 1) 서버 진단 endpoint 도달
curl -sS https://<server>/api/v1/local-agents/diagnostics | head

# 2) WebSocket 핸드셰이크 시뮬레이션 (websocat 등)
websocat -v wss://<server>/api/v1/local-agents/ws

# 3) 등록코드 발급 (서버 관리 콘솔에서 진행)
# 4) 데스크앱에서 등록코드 입력 후 register-with-code 성공 확인
# 5) 데스크앱 ws 자동 재연결 확인 (네트워크 끊었다 다시 연결)
```

## 8. 절대 금지

- `proxy_pass` 에 `http://` 만 두고 HTTPS 종단 안 하면서 클라이언트에 `ws://` 강요
- `Upgrade` 헤더를 임의 값으로 덮어쓰기
- 인증서 검증 우회 (`-k`/`insecure` 옵션 데스크앱 빌드에 박지 말 것)
- 로그에 `Authorization` / `device_token` / `X-API-Key` 헤더 원문 출력
