# admin-web 운영 기준선 (Stage 11-UI-5)

## 1. 목적

Next.js 기반 admin-web 관리자 UI의 운영 기준선 문서.
기존 FastAPI admin 화면(`/orchestrator/api/v1/admin/local-agents`)은 legacy fallback으로 유지한다.

---

## 2. 최종 기준 커밋

| 항목 | 값 |
|---|---|
| master / server HEAD | `7e21318` |
| 기준일 | 2026-04-28 |

| PR | 내용 |
|---|---|
| PR #21 | admin-web standalone Dockerfile |
| PR #22 | docker-compose.yml admin-web 서비스 추가 |
| PR #23 | API base path 보정 (`/orchestrator/api/v1`) |
| PR #24 | capture screenshot 타입/API client 추가 |
| PR #25 | capture screenshot actions 연동 (사전 점검 + Confirm Modal) |
| PR #26 | role-aware local agent controls (auth/me + viewer/admin/owner UI) |
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
| auth/me | `/orchestrator/api/v1/auth/me` |
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
| capture 사전 점검 (dry_run=true) | 구현 완료 |
| capture Confirm Modal + POST /capture-screenshot | 구현 완료 |
| GET /auth/me 연동 (getCurrentUser) | 구현 완료 |
| viewer/admin/owner role-aware UI | 구현 완료 |
| 401/403 role-aware 오류 UX | 구현 완료 |

---

## 6. auth/me endpoint 기준

| 항목 | 값 |
|---|---|
| endpoint | `GET /orchestrator/api/v1/auth/me` |
| 인증 방식 | `Depends(get_current_user)` — `require_role` 미사용 |
| 반환 필드 | `actor` (string), `role` (string) |
| 반환 금지 필드 | `password`, `password_hash`, `token`, `session`, `cookie`, `secret`, `salt` |
| AUTH_ENABLED=False | `{"actor": "system", "role": "owner"}` 반환 |
| 인증 없음 (AUTH_ENABLED=True) | `401` 반환 |
| viewer 접근 | 허용 (자기 role 조회 전용 read-only) |

---

## 7. 권한 정책 (UI role-aware)

| 역할 | 조회 | cancel | capture |
|---|---|---|---|
| owner | 가능 | 가능 (status 조건 충족 시) | 가능 (agent idle/busy 시) |
| admin | 가능 | 가능 (status 조건 충족 시) | 가능 (agent idle/busy 시) |
| viewer | 가능 | disabled (`title="admin/owner 권한 필요"`) | disabled (`title="admin/owner 권한 필요"`) |
| unknown/error | 가능 | disabled | disabled |
| userLoading 중 | 가능 | disabled | disabled |

**보안 원칙**: UI role 제어는 UX 보조이며, **최종 권한은 FastAPI `require_role`이 강제**한다.

### 401/403 오류 메시지 정책

| 상황 | 메시지 |
|---|---|
| 401 | "로그인이 필요합니다. 브라우저 인증 상태를 확인하세요." |
| 403 + viewer | "조회 전용 권한입니다. admin/owner 권한이 필요합니다." |
| 403 + unknown | "권한 확인이 필요합니다. admin/owner 권한이 필요합니다." |
| 403 + admin·owner | "권한이 없습니다. 서버 권한 정책을 확인하세요." |

---

## 8. 보안 기준

- **UI role 제어는 UX 보조** — 서버 `require_role`이 최종 기준
- 실제 cancel/capture POST는 사용자 명시 클릭으로만 실행 (자동/주기 실행 금지)
- 비밀번호/OTP/인증서/카드정보 화면 캡처 금지 안내는 Confirm Modal에 유지
- `actor` 표시 허용, `password`/`hash`/`token`/`session`/`cookie`/`secret` 표시 금지
- raw payload/이미지 data/token_id/device_token 표시 금지
- `console.log(currentUser)` / `console.log(result)` 금지

---

## 9. API base path 기준

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

## 10. Smoke Checklist

배포/재기동 후 아래 항목을 순서대로 확인한다.

```bash
# 컨테이너 상태
docker compose ps ai-orchestrator-api admin-web
# → ai-orchestrator-api: Up (healthy)
# → admin-web: Up

# API health
curl -fsS -H 'Host: haehan-ai.kr' https://127.0.0.1/orchestrator/api/v1/health -k
# → {"status":"ok","service":"haehan-ai-orchestrator"}

# auth/me (인증 정책에 따라 200 또는 401)
curl -sk -w '\nHTTP:%{http_code}' -H 'Host: haehan-ai.kr' https://127.0.0.1/orchestrator/api/v1/auth/me -k
# 200 시: {"actor":"...","role":"..."} — actor/role 2필드만 있는지 확인
# password/hash/token/session/cookie 필드 있으면 FAIL
# 404이면 경로 문제 → FAIL

# admin-web local-agents page
curl -fsS -o /dev/null -w '%{http_code}' -H 'Host: haehan-ai.kr' \
  https://127.0.0.1/orchestrator/admin-web/local-agents -k
# → 200

# local-agents API
curl -fsS -o /dev/null -w '%{http_code}' -H 'Host: haehan-ai.kr' \
  https://127.0.0.1/orchestrator/api/v1/local-agents -k
# → 200 (404이면 경로 문제)

# role-aware UI 문자열 확인 (JS 번들)
curl -sk -H 'Host: haehan-ai.kr' https://127.0.0.1/orchestrator/admin-web/local-agents -k \
  | grep -o 'script src="/_next/static/chunks/app/local-agents/[^"]*"'
# → page chunk 경로 확인 후 해당 JS에서:
#   조회 전용, admin/owner 권한 필요, 권한 확인 실패 문자열 확인

# legacy route 유지 확인
curl -fsS -o /dev/null -w '%{http_code}' -H 'Host: haehan-ai.kr' \
  https://127.0.0.1/orchestrator/api/v1/admin/local-agents -k
# → 200 또는 기존 인증 정책 응답

# secret/env 로그 노출 없음
docker compose logs --tail=20 admin-web | grep -iE 'password|token|secret|key' || echo 'no secret in log'
```

**금지 항목 (smoke 중 절대 실행 금지)**

- `POST /cancel` 실제 호출 금지
- `POST /capture-screenshot` 실제 호출 금지
- Authorization/Cookie/session/token 값 출력 금지

---

## 11. Rollback 절차

**우선순위 (상위부터 시도)**

1. **nginx route 제거 (가장 안전)**
   ```bash
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

## 12. 운영 주의사항

- `location /orchestrator/admin-web/` 블록은 `location /orchestrator/` 블록보다 앞에 위치해야 함
- `proxy_pass` 끝의 trailing slash(`/`) 제거 금지
- `_next/static` 별도 location 유지 (Cache-Control immutable 적용)
- Basic Auth / RBAC 최종 권한은 FastAPI가 강제 — UI 버튼은 UX 보조일 뿐 보안 기준이 아님
- `cancel_requested` 상태는 즉시 중단이 아니라 취소 요청 상태 (agent가 수신·처리 전일 수 있음)
- admin-web 재빌드 시 `docker compose build admin-web` 후 `docker compose up -d --no-deps admin-web`만 허용
- FastAPI + admin-web 동시 변경 시 두 서비스 모두 재빌드: `docker compose build ai-orchestrator-api admin-web`

---

## 13. 남은 후속 작업

| 단계 | 내용 |
|---|---|
| Stage 11-UI-6 | 자동 새로고침 / polling |
| Stage 11-UI-7 | legacy FastAPI admin deprecated 계획 |
| Stage 12-GABIA-1 | 가비아 자동화 설계 |
| 보안 | Next.js 14.2.29 보안 경고 후속 업데이트 검토 |

---

## 14. Stage 11-UI-5F 검증 결과

| 항목 | 결과 |
|---|---|
| PR #26 fast-forward merge | PASS |
| origin/master = 7e21318 | PASS |
| 서버 HEAD = 7e21318 | PASS |
| backend tests (136/136) | PASS |
| admin-web typecheck | PASS |
| admin-web lint | PASS |
| admin-web build | PASS |
| ai-orchestrator-api Up (healthy) | PASS |
| admin-web Up | PASS |
| GET /orchestrator/api/v1/health | 200 PASS |
| GET /orchestrator/api/v1/auth/me | 200 `{"actor":"system","role":"owner"}` PASS |
| auth/me 응답 actor·role 2필드만 | PASS |
| GET /orchestrator/admin-web/local-agents | 200 PASS |
| GET /orchestrator/api/v1/local-agents | 200 PASS |
| role-aware UI 문자열 JS 번들 확인 | PASS |
| POST /cancel 미수행 | PASS |
| POST /capture-screenshot 미수행 | PASS |
| nginx/compose 미수정 | PASS |
| secret/env 노출 | 없음 |

---

## 15. Stage 11-UI-3F 검증 결과 (이전 기준선)

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
