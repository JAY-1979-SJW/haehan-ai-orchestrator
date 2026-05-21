# 로컬 에이전트 공개 WebSocket — nginx 변경 계획서 (dry-run)

문서 종류: **nginx 변경 계획서** (적용 전 승인용)
연관 정책: `local_agent_ip_allowlist_policy.md` 의 C안 채택
상태: **DRY-RUN — 실제 적용은 본 문서 OUT_OF_SCOPE**

## 1. 변경 요약

| location | 현재 | 변경 후 |
|----------|------|--------|
| `/orchestrator/api/v1/local-agents/ws` | IP allowlist | **public + device_token auth** |
| `/orchestrator/api/v1/local-agents/register-with-code` | IP allowlist | **public + rate limit** |
| `/orchestrator/api/v1/local-agents/registration-codes` | IP allowlist | **유지 (admin only)** |
| `/orchestrator/api/v1/local-agents/` (그 외) | IP allowlist | **유지 (admin only)** |
| `/orchestrator/api/` | IP allowlist | **유지** |
| `/orchestrator/admin-web/`, `/orchestrator/` | IP allowlist | **유지** |

## 2. nginx 변경 절차 (적용 시 — 본 공정 미수행)

### 2.1 백업
```bash
ssh haehan-app "docker exec nginx cat /etc/nginx/conf.d/default.conf > /tmp/default.conf.pre-public-la.$(date +%Y%m%d-%H%M%S).bak"
```

### 2.2 신규 설정 추가 (http 블록)
```nginx
# rate limit zone (1IP 분당 10회)
limit_req_zone $binary_remote_addr zone=la_register:10m rate=10r/m;
```

### 2.3 location 분리 (server 블록)

**A. 공개 location — register-with-code**
```nginx
location = /orchestrator/api/v1/local-agents/register-with-code {
    limit_req zone=la_register burst=20 nodelay;
    limit_req_status 429;

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
```

**B. 공개 location — WebSocket**
```nginx
location = /orchestrator/api/v1/local-agents/ws {
    # public — device_token auth 가 보안 layer

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
```

**C. 보호 유지 — 그 외 /orchestrator/api/v1/local-agents/***
```nginx
location /orchestrator/api/v1/local-agents/ {
    allow 220.79.246.190;
    allow 127.0.0.1;
    allow 172.18.0.1;
    deny  all;

    proxy_pass         http://haehan-ai-orchestrator-api:8400/api/v1/local-agents/;
    # ... (기존 설정 동일)
}
```

> ⚠️ nginx location 우선순위: `=` 정확 일치 > prefix 매칭. 따라서 A, B 가 C 보다 우선 적용됨.

### 2.4 검증 + reload
```bash
ssh haehan-app "docker exec nginx nginx -t"   # syntax check
ssh haehan-app "docker exec nginx nginx -s reload"  # graceful reload
```

### 2.5 적용 후 즉시 확인
```bash
# 1) 내부 IP — 모든 endpoint 정상
ssh haehan-app "docker exec haehan-ai-orchestrator-api python -c 'import urllib.request; print(urllib.request.urlopen(\"http://127.0.0.1:8400/api/v1/health\",timeout=3).status)'"

# 2) 외부 IP 시뮬레이션 — register-with-code 공개 확인
#   (실제는 별도 외부 IP 에서 curl)
#   외부 IP 에서:  curl -v https://<server>/orchestrator/api/v1/local-agents/register-with-code -X POST -H 'Content-Type: application/json' -d '{"registration_code":"INVALID"}'
#   기대: 200 path 도달 → 400 (잘못된 코드)
```

## 3. rollback 절차 (실패 시)

```bash
# 1) 백업 복원
ssh haehan-app "docker cp /tmp/default.conf.pre-public-la.<timestamp>.bak nginx:/etc/nginx/conf.d/default.conf"

# 2) syntax 검증
ssh haehan-app "docker exec nginx nginx -t"

# 3) reload
ssh haehan-app "docker exec nginx nginx -s reload"

# 4) 확인 — 외부 IP 에서 register-with-code 호출 시 403 반환되는지
```

rollback 트리거 (자동 감지 기준):
- `limit_req` 로그에서 동일 IP 가 분당 50회 이상 차단 → 비정상 트래픽
- 4401 close 가 5분간 100건 이상 → bad token 공격 의심
- 정상 사용자 인증 성공률 80% 미만 → 정책 잘못 적용

## 4. 모니터링 (적용 후 1주간 필수)

| 지표 | 임계 | 조치 |
|------|------|------|
| `/register-with-code` 분당 요청 수 | > 1000 | rate limit 강화 검토 |
| 4401 close 횟수 (24h) | > 1000 | IP 차단 정책 추가 검토 |
| 신규 agent 등록 수 (정상) | (baseline) | 정상 사용자 유입 확인 |
| nginx error.log | "limit_req" 빈도 | 정상 사용자 영향 여부 |
| `audit_log` (server-side) | bad token 빈도 | 의심 IP 차단 후보 |

## 5. 본 문서가 OUT_OF_SCOPE 인 항목

- 실제 nginx config 변경 / reload
- `limit_req_zone` 실 적용
- rate limit 임계값 final tuning
- 데스크앱 패키징 (.exe/.dmg)
- D안 (URL 경로 변경 `/public/local-agent/`) 구현
- admin endpoint IP 정책 변경

## 6. 다음 공정 후보 (별도)

1. **`IP_ALLOWLIST_RELAX_DEPLOY_01`** — 본 계획서 승인 후 실제 nginx 변경 적용 + reload + live smoke
2. **`LIVE_PUBLIC_WS_FROM_USER_IP_01`** — 적용 후 외부 IP 에서 실 사용자 시뮬레이션
3. **`PUBLIC_AGENT_GATEWAY_SCAFFOLD_01`** — D안 (URL 분리) 중장기 설계 + 코드 변경
4. **`LOCAL_AGENT_INSTALLER_PACKAGE_01`** — 데스크앱 .exe/.dmg 패키징
