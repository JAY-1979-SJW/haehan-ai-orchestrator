# 로컬 에이전트 IP allowlist 정책

문서 종류: **정책 결정서** (실 운영 변경 전 승인 입력용)
대상: `haehan-ai-orchestrator` 운영 nginx + local agent endpoint
HEAD: `90ee926`

## 1. 현재 정책 (확정 — 2026-05-21 SSH 조회)

| location | allow | 비고 |
|----------|-------|------|
| `/orchestrator/admin-web/` | 220.79.246.190, 127.0.0.1, 172.18.0.1 | 관리자 UI |
| `/orchestrator/` | 동일 IP 3개 | 대시보드 (5050) |
| `/orchestrator/api/v1/local-agents/ws` | 동일 IP 3개 | WebSocket |
| `/orchestrator/api/` | 동일 IP 3개 | 전체 API |

→ **전체 `/orchestrator` 가 동일한 IP 3개로 보호**. 일반 사용자 데스크앱은 어느 IP 에서도 접속 불가.

## 2. 현재 차단되는 사용자 시나리오

- 사용자가 회사/집/현장/카페 등 임의 IP 에서 데스크앱 실행
- registration_code 입력 → POST `/orchestrator/api/v1/local-agents/register-with-code` 호출
- nginx 가 `deny all` 적용 → 403 반환 (또는 connection refused)
- 데스크앱 측 에러: "서버 접속 실패 / 인증 실패" — 사용자는 원인 식별 어려움

→ 결국 **관리자가 직접 대표님 IP(220.79.246.190) 에서만 데스크앱을 실행할 수 있는 상태**.

## 3. 비교안 A / B / C / D

### A안 — 현재 allowlist 유지
- **장점**: 보안 강함. nginx 단계에서 모든 외부 차단.
- **단점**: 일반 사용자 데스크앱 연결 불가 = 제품 자체가 외부 사용 불가능.
- **권장**: ❌ (현 상태 그대로). 내부 운영자 전용일 때만 허용.

### B안 — local-agents 전체 allowlist 해제
- **장점**: 사용자 연결 가장 쉬움.
- **단점**: `/registration-codes` 발급 endpoint 까지 노출 → 외부 공격자가 임의로 등록코드 발급 시도 가능.
        agent 목록, task 생성/승인/취소 등 admin 까지 노출.
- **권장**: ❌ 비추천. 보안 갭 큼.

### C안 — 사용자 연결에 필요한 최소 endpoint만 공개 ⭐ **단기 권장**
공개:
- `POST /orchestrator/api/v1/local-agents/register-with-code` (registration_code 1회용 검증 + agent 등록)
- `WS /orchestrator/api/v1/local-agents/ws` (device_token auth)

보호 유지 (allowlist 그대로):
- `POST /orchestrator/api/v1/local-agents/registration-codes` (코드 발급 — admin 전용)
- `GET /orchestrator/api/v1/local-agents` (agent 목록)
- `POST /orchestrator/api/v1/local-agents/{id}/tasks` (task 생성)
- 모든 admin/owner 관리 endpoint
- `/orchestrator/admin-web/`, `/orchestrator/` (대시보드)

보안 보완:
- registration_code 1회용 + TTL (이미 적용됨)
- device_token auth + bad token 4401 (이미 적용됨)
- token/secret 로그 redaction (이미 적용됨 — `connection_diagnostics`)
- 추가: register-with-code 에 IP 당 분당 rate limit (예: `limit_req_zone`)
- 추가: WS auth 실패 IP 카운터 (서버측 audit_log)

### D안 — 별도 public agent gateway 경로 신설 ⭐ **중장기 권장**
새 경로:
- `POST /public/local-agent/register` (register-with-code 대응)
- `WS /public/local-agent/ws` (device_token auth)

내부 admin 은 `/orchestrator/api/` 그대로 allowlist 유지.

- **장점**: 제품 구조가 명확. 외부 노출/내부 관리가 URL 레벨에서 완전 분리.
- **단점**: 클라이언트 코드(`websocket_client.py`, `registration_client.py`)의 `/api/v1/local-agents/` 경로를 `/public/local-agent/` 로 변경해야 하며,
            기존 사용자(있다면) 마이그레이션 필요.

## 4. 권장안

- **단기 (즉시 적용 가능)**: **C안**
  - nginx config 만 추가/변경, 클라이언트 코드 변경 불필요
  - 보안 위험 최소화 (1회용 code + device_token + 4401)
- **중장기 (제품 정식 출시 시점)**: **D안**
  - URL 분리로 운영 정책이 명확해짐
  - admin API 와 public agent API 가 완전히 다른 location → 실수 노출 방지

본 공정은 **C안 nginx 변경 계획서까지 작성**하고, 실제 nginx reload 는 별도 승인 공정에서 수행.

## 5. 공개 허용 후보 (C안)

| Method | Path | 보안 layer |
|--------|------|-----------|
| POST | `/orchestrator/api/v1/local-agents/register-with-code` | registration_code 1회용 + TTL |
| WS | `/orchestrator/api/v1/local-agents/ws` | first frame `auth(agent_id, device_token)` 필수 / 10s timeout / 4401 close |

## 6. allowlist 유지 (C안)

| Method | Path | 사유 |
|--------|------|-----|
| POST | `/orchestrator/api/v1/local-agents/registration-codes` | admin 만 코드 발급 |
| GET | `/orchestrator/api/v1/local-agents/registration-codes` | 발급 이력 조회 |
| DELETE | `/orchestrator/api/v1/local-agents/registration-codes/{id}` | code revoke |
| GET | `/orchestrator/api/v1/local-agents` | agent 목록 |
| GET | `/orchestrator/api/v1/local-agents/diagnostics` | 진단 메타 |
| POST | `/orchestrator/api/v1/local-agents/{id}/tasks` | task 생성 |
| POST | `/orchestrator/api/v1/local-agents/{id}/tasks/{id}/approve` | 승인 |
| POST | `/orchestrator/api/v1/local-agents/{id}/tasks/{id}/reject` | 거절 |
| POST | `/orchestrator/api/v1/local-agents/{id}/tasks/{id}/cancel` | 취소 |
| POST | `/orchestrator/api/v1/local-agents/{id}/cleanup` | cleanup |
| 그 외 `/orchestrator/api/` 전체 | 〃 | admin only |
| `/orchestrator/admin-web/`, `/orchestrator/` | 〃 | UI |

## 7. 보안 보완책 (C안 시행 시 추가 필수)

1. **rate limit (register-with-code)**: `limit_req_zone` 으로 IP 당 분당 10회 제한
2. **rate limit (ws auth fail)**: 서버측 audit_log 에 4401 발생 시 IP+agent_id 카운트, 임계치 초과 시 차단 후보 기록
3. **registration_code TTL 단축 검토**: 현재 기본 TTL (현 코드 확인 필요) — 사용자 등록 흐름 시간 (예: 10분) 만 허용
4. **registration_code 1회 사용 강제** (이미 적용됨 — `consume_code` 이중 호출 거부)
5. **device_token SHA-256 hash 만 저장** (이미 적용됨 — `register_agent` 의 `token_hash`)
6. **로그 redaction**: `connection_diagnostics._strip_secrets_from_url` 적용 확인 (`device_token / registration_code / token / authorization` 등 redact)
7. **TLS only**: 클라이언트 측 `wss://` 강제 (HTTP 평문 차단)
8. **WAF/CDN 우회 차단**: Cloudflare 등 사용 시 직접 origin 접속 방지

## 8. nginx 변경 계획 (C안 dry-run)

기존 단일 location 을 **분리**:

```nginx
# (신규) register-with-code 만 공개 — 1회용 code 자체가 보안 layer
location = /orchestrator/api/v1/local-agents/register-with-code {
    # allow all 명시적 — 다른 IP allow/deny 없음
    limit_req zone=la_register burst=20 nodelay;   # rate limit (사전 정의)

    proxy_pass         http://haehan-ai-orchestrator-api:8400/api/v1/local-agents/register-with-code;
    proxy_http_version 1.1;
    proxy_set_header   Host              $host;
    proxy_set_header   X-Real-IP         $remote_addr;
    proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header   X-Forwarded-Proto $scheme;
    proxy_connect_timeout 10s;
    proxy_read_timeout    15s;
    proxy_send_timeout    15s;
}

# (변경) ws — IP allowlist 제거, device_token auth 가 보안 layer
location = /orchestrator/api/v1/local-agents/ws {
    # allow all 명시적 (IP allowlist 제거)
    # 보호: 클라이언트 첫 메시지 auth(agent_id, device_token) 필수, 10s timeout, 실패 시 4401 close

    proxy_pass         http://haehan-ai-orchestrator-api:8400/api/v1/local-agents/ws;
    proxy_http_version 1.1;
    proxy_set_header   Upgrade           $http_upgrade;
    proxy_set_header   Connection        "upgrade";
    proxy_set_header   Host              $host;
    proxy_set_header   X-Real-IP         $remote_addr;
    proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header   X-Forwarded-Proto $scheme;
    proxy_read_timeout    3600s;
    proxy_send_timeout    3600s;
}

# (유지) 그 외 모든 /orchestrator/api/v1/local-agents/* 는 allowlist 유지
location /orchestrator/api/v1/local-agents/ {
    allow 220.79.246.190;
    allow 127.0.0.1;
    allow 172.18.0.1;
    deny  all;

    proxy_pass         http://haehan-ai-orchestrator-api:8400/api/v1/local-agents/;
    # ... (기존과 동일)
}
```

추가: `limit_req_zone` (http 블록):
```nginx
limit_req_zone $binary_remote_addr zone=la_register:10m rate=10r/m;
```

**중요**: nginx 의 `location` 우선순위 — 정확한 일치 (`location =`) 가 prefix 보다 우선. 따라서 위 순서로 두면 `register-with-code` 와 `ws` 는 공개, 나머지 `/local-agents/*` 는 allowlist 적용됨.

## 9. rollback 계획

1. **백업 보관**:
   ```bash
   ssh haehan-app "docker exec nginx cat /etc/nginx/conf.d/default.conf > /tmp/default.conf.before-public-local-agent.$(date +%Y%m%d-%H%M%S).bak"
   ```
2. **롤백 트리거 조건**:
   - 외부 공격 트래픽 급증 (`limit_req` 로그 임계 초과)
   - 정상 사용자 인증 실패율 비정상 (예: 4401 비율 20% 이상)
   - 알 수 없는 IP 의 ws 연결 시도가 분당 100건 이상
3. **롤백 절차** (한 줄 명령):
   ```bash
   ssh haehan-app "docker cp /tmp/default.conf.before-public-local-agent.<timestamp>.bak nginx:/etc/nginx/conf.d/default.conf && docker exec nginx nginx -s reload"
   ```
4. **롤백 후 확인**:
   - `docker exec nginx nginx -t` (config 검증)
   - `/orchestrator/api/v1/local-agents/ws` 외부 IP 접속 → 403/deny 확인
   - 내부 IP (220.79.246.190) 접속 정상 확인

## 10. live smoke (적용 후 별도 공정)

C안 적용 후 검증해야 할 항목 (별도 공정 `LIVE_PUBLIC_WS_FROM_USER_IP_01`):

| 단계 | 기대 |
|------|------|
| 외부 IP 에서 `POST /register-with-code` (valid code) | 200 + device_token |
| 외부 IP 에서 `POST /register-with-code` (invalid code) | 400/404 |
| 외부 IP 에서 동일 IP 분당 11회 호출 | 429 (rate limit) |
| 외부 IP 에서 `WS /ws` + auth(valid token) | auth_ok |
| 외부 IP 에서 `WS /ws` + auth(bad token) | 4401 close |
| 외부 IP 에서 `WS /ws` + 10초간 auth 미전송 | 4401 close |
| 외부 IP 에서 `POST /registration-codes` (발급 시도) | 403 (allowlist 보호) |
| 외부 IP 에서 `GET /local-agents` (목록 조회 시도) | 403 |
| 내부 IP 에서 admin 모든 endpoint | 정상 |

## 11. 보안 체크리스트

- [ ] registration_code 발급 endpoint 는 public 후보에 포함되지 않음 ✓
- [ ] device_token auth 없는 public ws 존재하지 않음 (auth 필수) ✓
- [ ] registration_code TTL 유효 ✓
- [ ] registration_code 1회용 ✓
- [ ] device_token 원문 서버 저장 금지 ✓ (SHA-256 hash 만)
- [ ] WS 4401 즉시 종료 ✓
- [ ] token/secret 로그 출력 금지 ✓ (`connection_diagnostics._strip_secrets_from_url` 강화)
- [ ] rate limit (register-with-code) 설정 (적용 시 검증)
- [ ] TLS only (wss) 강제
- [ ] rollback 백업 보관

## 12. 본 공정 결정 (요약)

- ✅ **권장안 = C안** (단기 즉시 적용 가능, 보안 위험 최소)
- ✅ 중장기는 D안 — 별도 공정 `PUBLIC_AGENT_GATEWAY_SCAFFOLD_01` 으로 분리
- ❌ 실제 nginx 변경은 **본 공정에서 수행하지 않음** — 별도 승인 공정 `IP_ALLOWLIST_RELAX_DEPLOY_01` 에서 수행
- ❌ allowlist 전면 제거 (B안) 금지
- ❌ admin endpoint 공개 금지
