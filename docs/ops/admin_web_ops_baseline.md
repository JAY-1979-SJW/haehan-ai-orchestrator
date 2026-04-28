# admin-web 운영 기준선 (Stage 11-UI-6)

## 1. 목적

Next.js 기반 admin-web 관리자 UI의 운영 기준선 문서.
기존 FastAPI admin 화면(`/orchestrator/api/v1/admin/local-agents`)은 legacy fallback으로 유지한다.

---

## 2. 최종 기준 커밋

| 항목 | 값 |
|---|---|
| master / server HEAD | `40aaba1` |
| 기준일 | 2026-04-28 |

| PR | 내용 |
|---|---|
| PR #28 | local agent polling controls (Stage 11-UI-6B~6C) |
| PR #26 | role-aware local agent controls (auth/me + viewer/admin/owner UI) |
| PR #25 | capture screenshot actions 연동 (사전 점검 + Confirm Modal) |
| PR #24 | capture screenshot 타입/API client 추가 |
| PR #23 | API base path 보정 (`/orchestrator/api/v1`) |
| PR #22 | docker-compose.yml admin-web 서비스 추가 |
| PR #21 | admin-web standalone Dockerfile |
| (이전) PR #20 | Local Agent API 연동 |
| (이전) PR #19 | next-env.d.ts 추가 |
| (이전) PR #18 | admin-web scaffold |

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
| agents/tasks 15초 background polling | 구현 완료 |
| 자동 새로고침 ON/OFF 토글 | 구현 완료 |
| polling 상태 배지 (active/paused/error/off) | 구현 완료 |
| 마지막 갱신 시각 표시 | 구현 완료 |
| document.hidden pause | 구현 완료 |
| modal open 중 polling 보호 | 구현 완료 |
| in-flight guard | 구현 완료 |
| POST cancel/capture 자동 실행 금지 | 구현 완료 |

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

## 7-1. polling 운영 기준

### polling 대상

| 대상 | 주기 |
|---|---|
| GET `/orchestrator/api/v1/local-agents` | 15초 |
| GET `/orchestrator/api/v1/local-agents/{agent_id}/tasks` | 15초 |

### polling 제외

| 대상 | 사유 |
|---|---|
| GET `/auth/me` | 최초 1회만 (role 확인 전용) |
| POST `/cancel` | 사용자 명시 클릭으로만 실행 |
| POST `/capture-screenshot` | 사용자 명시 클릭으로만 실행 |

### OFF 상태

- `pollingEnabled=false` → `setInterval` 미생성 (interval 자체 없음)
- 수동 새로고침 버튼은 OFF 상태에서도 동작

### ON 복귀

- 즉시 background refresh 1회 수행 후 15초 주기 재개

### document.hidden 처리

- `document.hidden === true` → polling skip
- 탭 복귀 시 즉시 background refresh 1회 수행

### modal open 보호

| 상황 | 보호 범위 |
|---|---|
| cancel modal open (`cancelTargetTask !== null`) | tasks polling skip |
| capture modal open (`captureMode === "real" && captureTargetAgent !== null`) | agents + tasks polling skip 모두 |

### 배지 상태 판정

| 상태 | 조건 | 색상 |
|---|---|---|
| off | `pollingEnabled=false` | 회색 |
| error | `pollingError` 존재 | 빨강 |
| paused | `document.hidden` 또는 capture modal open | 앰버 |
| active | 그 외 | 초록 |

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

# polling UI 문자열 확인 (JS 번들)
# page chunk 경로 확인 후 해당 JS에서 아래 문자열 모두 존재 확인:
#   자동 새로고침 ON
#   자동 새로고침 OFF
#   자동 갱신 중
#   자동 갱신 꺼짐
#   자동 갱신 오류
#   마지막 갱신
#   일시중지
#   visibilitychange
PAGE_CHUNK=$(curl -sk -H 'Host: haehan-ai.kr' \
  https://127.0.0.1/orchestrator/admin-web/local-agents -k \
  | grep -oP '/_next/static/chunks/app/local-agents/[^"]+')
curl -sk "https://127.0.0.1${PAGE_CHUNK}" -k | grep -o '자동 새로고침 ON\|자동 갱신 중\|마지막 갱신\|visibilitychange'

# role-aware UI 문자열 확인 (JS 번들)
#   조회 전용, admin/owner 권한 필요, 권한 확인 실패 문자열 확인

# legacy route 유지 확인 (deprecated fallback smoke 전용)
#   - 운영 주 화면 검증이 아니라 deprecated fallback route 가용성 확인용 GET smoke이다.
#   - 운영 주 검증은 위쪽 admin-web /local-agents smoke가 담당한다.
#   - capture-screenshot/cancel POST는 이 절차에 포함되지 않는다.
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

## 13. legacy FastAPI admin — deprecated fallback 상태

### 경로 및 권한

| 항목 | 값 |
|---|---|
| legacy route | `/orchestrator/api/v1/admin/local-agents` |
| 상태 | **deprecated fallback** |
| 표준 관리자 UI | `/orchestrator/admin-web/local-agents` |
| 권한 | `require_role("admin", "owner")` — viewer 403 차단 |
| 구현 방식 | FastAPI `HTMLResponse` (Jinja2 미사용, 순수 HTML 문자열) |

### 운영 원칙

- 운영자는 **admin-web 우선 사용**
- legacy route는 admin-web 장애 시 fallback 용도로 유지
- 신규 기능은 admin-web에서만 추가 — legacy에 기능 추가 금지
- legacy route 즉시 삭제 금지 — 제거 여부는 별도 Stage에서 판단
- legacy 화면 상단에 deprecated banner 표시 (Stage 11-UI-7B 적용)

### legacy / admin-web 기능 비교

| 기능 | legacy admin | admin-web |
|---|---|---|
| agent 목록 조회 | ✓ | ✓ |
| agent 상태 배지 | ✓ | ✓ |
| task 목록 조회 | ✓ (토글) | ✓ |
| task status filter | ✓ | ✓ |
| capture dry_run | ✓ | ✓ |
| capture real request | ✓ (window.confirm) | ✓ (Modal) |
| cancel | ✗ | ✓ |
| role-aware UI | ✗ | ✓ |
| polling 15초 자동 갱신 | ✗ | ✓ |
| 마지막 갱신 표시 | ✗ | ✓ |
| auth/me 연동 | ✗ | ✓ |
| 401/403 UX | 최소 | ✓ role-aware |

### deprecated banner smoke 기준

배포/재기동 후 아래를 추가로 확인한다:

```bash
# legacy route 200 확인
curl -fsS -o /dev/null -w '%{http_code}' -H 'Host: haehan-ai.kr' \
  https://127.0.0.1/orchestrator/api/v1/admin/local-agents -k
# → 200 (viewer는 403)

# deprecated banner 문자열 확인
curl -sk -H 'Host: haehan-ai.kr' \
  https://127.0.0.1/orchestrator/api/v1/admin/local-agents -k \
  | grep -o "legacy 관리 화면\|fallback 용도\|신규 기능은 admin-web\|/orchestrator/admin-web/local-agents"
# → 4개 문자열 모두 존재해야 함

# 기존 capture 버튼 문자열 유지 확인
curl -sk -H 'Host: haehan-ai.kr' \
  https://127.0.0.1/orchestrator/api/v1/admin/local-agents -k \
  | grep -o "화면 캡처 사전 점검\|실제 1회 화면 캡처 요청"
# → 두 문자열 모두 존재해야 함
```

**확인 항목**
- legacy route → 200 ✓
- "legacy 관리 화면" 포함 ✓
- "/orchestrator/admin-web/local-agents" 링크 포함 ✓
- "fallback 용도" 포함 ✓
- "신규 기능은 admin-web" 포함 ✓
- 기존 capture 버튼 문자열 유지 ✓

---

## 14. 남은 후속 작업

| 단계 | 내용 |
|---|---|
| Stage 11-UI-7D | legacy deprecated banner 커밋/PR/서버 반영/smoke |
| Stage 12-GABIA-1 | 가비아 자동화 설계 |
| 보안 | Next.js 14.2.29 보안 경고 후속 업데이트 검토 |

### 선택 고도화 (우선순위 낮음)


| 항목 | 내용 |
|---|---|
| 작업 상세 모달 | task 행 클릭 → 상세 정보 모달 표시 |
| capture 결과 조회 | 캡처 task 결과 확인 UI |
| polling interval env override | `NEXT_PUBLIC_POLLING_INTERVAL_MS` 환경변수로 주기 조정 |

---

## 15. Stage 11-UI-6E 검증 결과

| 항목 | 결과 |
|---|---|
| PR #28 fast-forward merge | PASS |
| origin/master = 40aaba1 | PASS |
| 서버 HEAD = 40aaba1 | PASS |
| admin-web typecheck | PASS |
| admin-web lint | PASS |
| admin-web build | PASS |
| ai-orchestrator-api Up (healthy) | PASS |
| admin-web Up | PASS |
| GET http://172.18.0.12:3000/local-agents | 200 PASS |
| GET /orchestrator/api/v1/health | 200 `{"status":"ok"}` PASS |
| GET /orchestrator/api/v1/local-agents | 200 PASS |
| JS 번들 문자열: 자동 새로고침 ON/OFF | PASS |
| JS 번들 문자열: 자동 갱신 중/꺼짐/오류 | PASS |
| JS 번들 문자열: 마지막 갱신 | PASS |
| JS 번들 문자열: 일시중지 | PASS |
| JS 번들 문자열: visibilitychange | PASS |
| POST /cancel 미수행 | PASS |
| POST /capture-screenshot 미수행 | PASS |
| nginx/compose 미수정 | PASS |
| secret/env 노출 | 없음 |

---

## 16. Stage 11-UI-5F 검증 결과

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

## 17. Stage 11-UI-3F 검증 결과 (이전 기준선)

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
