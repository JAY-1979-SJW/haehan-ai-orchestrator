# admin-web 운영 기준선 (Stage 11-UI-3)

## 1. 목적

Next.js 기반 admin-web 관리자 UI의 운영 기준선 문서.
기존 FastAPI admin 화면(`/orchestrator/api/v1/admin/local-agents`)은 legacy fallback으로 유지한다.

---

## 2. 최종 기준 커밋

| 항목 | 값 |
|---|---|
| master / server HEAD | `d5bf862` |
| 기준일 | 2026-04-28 |

| PR | 내용 |
|---|---|
| PR #21 | admin-web standalone Dockerfile |
| PR #22 | docker-compose.yml admin-web 서비스 추가 |
| PR #23 | API base path 보정 (`/orchestrator/api/v1`) |
| (이전) PR #18 | admin-web scaffold |
| (이전) PR #19 | next-env.d.ts 추가 |
| (이전) PR #20 | Local Agent API 연동 |

---

## 3. 운영 접속 경로

| 용도 | 경로 |
|---|---|
| admin-web root | `/orchestrator/admin-web/` |
| 로컬 에이전트 관리 | `/orchestrator/admin-web/local-agents` |
| FastAPI API | `/orchestrator/api/v1/` |
| health check | `/orchestrator/api/v1/health` |
| legacy FastAPI admin | `/orchestrator/api/v1/admin/local-agents` |

---

## 4. 서비스 구조

| 항목 | 값 |
|---|---|
| FastAPI 서비스명 | `ai-orchestrator-api` |
| Next.js 서비스명 | `admin-web` |
| 컨테이너명 | `haehan-ai-orchestrator-admin-web` |
| 이미지 | `haehan-ai-orchestrator-admin-web:local` |
| 네트워크 | `default` + `app_web` (external) |
| expose | `3000` |
| 외부 ports | 없음 (nginx 경유만) |
| nginx proxy | `/orchestrator/admin-web/` → `admin-web:3000/` |

---

## 5. admin-web 기능 범위

| 기능 | 상태 |
|---|---|
| agent 목록 조회 | 구현 완료 |
| agent 상태 표시 (StatusBadge) | 구현 완료 |
| task 목록 조회 | 구현 완료 |
| task status filter | 구현 완료 |
| KPI cards (total/idle/busy/offline) | 구현 완료 |
| cancel modal + POST /cancel 연동 | 구현 완료 |
| capture 버튼 | placeholder (Stage 11-UI-4 예정) |

---

## 6. API base path 기준

- 운영 기본값: `/orchestrator/api/v1`
- 환경변수 override: `NEXT_PUBLIC_API_BASE_PATH` (로컬 개발용)
- `.env` / `.env.local` 파일은 커밋하지 않음
- `FASTAPI_BASE_URL`은 운영 컨테이너에서 사용하지 않음 (nginx same-origin 경유)

### buildApiUrl 동작

| 입력 | 결과 |
|---|---|
| `/local-agents` | `/orchestrator/api/v1/local-agents` |
| `/api/v1/local-agents` | `/orchestrator/api/v1/local-agents` |
| `/orchestrator/api/v1/local-agents` | 그대로 (중복 방지) |
| `https://...` | 그대로 |

---

## 7. Smoke Checklist

배포/재기동 후 아래 항목을 순서대로 확인한다.

```bash
# 컨테이너 상태
docker compose ps admin-web
# → haehan-ai-orchestrator-admin-web  Up  3000/tcp

# admin-web root
curl -fsS -o /dev/null -w '%{http_code}' -H 'Host: haehan-ai.kr' https://127.0.0.1/orchestrator/admin-web/ -k
# → 200

# local-agents page
curl -fsS -o /dev/null -w '%{http_code}' -H 'Host: haehan-ai.kr' https://127.0.0.1/orchestrator/admin-web/local-agents -k
# → 200

# _next/static asset
curl -fsS -o /dev/null -w '%{http_code}' -H 'Host: haehan-ai.kr' \
  https://127.0.0.1/orchestrator/admin-web/_next/static/chunks/webpack-*.js -k
# → 200 (Cache-Control: public, max-age=31536000, immutable)

# FastAPI health
curl -fsS -H 'Host: haehan-ai.kr' https://127.0.0.1/orchestrator/api/v1/health -k
# → {"status":"ok","service":"haehan-ai-orchestrator"}

# local-agents API (인증 정책에 따라 200 또는 허용 응답, 404 아님)
curl -fsS -o /dev/null -w '%{http_code}' -H 'Host: haehan-ai.kr' \
  https://127.0.0.1/orchestrator/api/v1/local-agents -k
# → 200 (또는 인증 정책상 허용 응답, 404이면 경로 문제)

# legacy route 유지 확인
curl -fsS -o /dev/null -w '%{http_code}' -H 'Host: haehan-ai.kr' \
  https://127.0.0.1/orchestrator/api/v1/admin/local-agents -k
# → 200 또는 기존 인증 정책 응답

# secret/env 로그 노출 없음 (로그 확인)
docker compose logs --tail=20 admin-web | grep -iE 'password|token|secret|key' || echo 'no secret in log'
```

---

## 8. Rollback 절차

**우선순위 (상위부터 시도)**

1. **nginx route 제거 (가장 안전)**
   ```bash
   # 백업 conf 복구
   cp /home/ubuntu/app/nginx/conf.d/default.conf.bak.stage11-ui-3e-* \
      /home/ubuntu/app/nginx/conf.d/default.conf
   docker exec nginx nginx -t
   docker exec nginx nginx -s reload
   # → legacy FastAPI admin으로 폴백
   ```

2. **admin-web 컨테이너만 중지**
   ```bash
   docker compose stop admin-web
   # ai-orchestrator-api는 건드리지 않음
   ```

3. **legacy FastAPI admin 사용**
   - `/orchestrator/api/v1/admin/local-agents` 경로로 직접 접근

**금지 사항**

- `nginx restart` 금지 → `nginx -s reload`만 허용
- `docker compose down` 금지
- `docker compose up -d` 전체 금지
- `ai-orchestrator-api` 재생성 금지

---

## 9. 운영 주의사항

- `location /orchestrator/admin-web/` 블록은 `location /orchestrator/` 블록보다 앞에 위치해야 함
- `proxy_pass` 끝의 trailing slash(`/`) 제거 금지
- `_next/static` 별도 location 유지 (Cache-Control immutable 적용)
- Basic Auth / RBAC 최종 권한은 FastAPI가 강제 — UI 버튼은 UX 보조일 뿐 보안 기준이 아님
- `cancel_requested` 상태는 즉시 중단이 아니라 취소 요청 상태 (agent가 수신·처리 전일 수 있음)
- admin-web 재빌드 시 `docker compose build admin-web` 후 `docker compose up -d --no-deps admin-web`만 허용

---

## 10. 남은 후속 작업

| 단계 | 내용 |
|---|---|
| Stage 11-UI-4 | capture 버튼 실제 연동 |
| Stage 11-UI-5 | role-aware UI / auth /me 설계 |
| Stage 11-UI-6 | auto refresh 또는 polling |
| Stage 11-UI-7 | legacy FastAPI admin deprecated 계획 |
| 보안 | Next.js 14.2.29 보안 경고 후속 업데이트 검토 |

---

## 11. Stage 11-UI-3F 검증 결과

| 항목 | 결과 |
|---|---|
| admin-web container Up | PASS |
| GET /orchestrator/admin-web/ | 200 PASS |
| GET /orchestrator/admin-web/local-agents | 200 PASS |
| _next/static asset + Cache-Control immutable | PASS |
| GET /orchestrator/api/v1/health | 200 PASS |
| GET /orchestrator/api/v1/local-agents | 200 PASS |
| legacy route `/orchestrator/api/v1/admin/local-agents` | 200 PASS |
| secret/env 로그 노출 | 없음 |
| nginx 추가 수정 | 없음 |
| FastAPI 수정 | 없음 |
| docker-compose.yml 수정 | 없음 |
