# R1 API 계약 감사 — 최신 실행 결과

- 프런트 fetch 호출 스캔: 33건 (정적 대조 가능 29건, 동적 경로 4건)
- 백엔드 런타임 라우트: 427건
- 끊긴 호출(backend 없음): 6건
- 501 미구현 라우트: 2건

## 끊긴 호출 (404 후보)

- `POST /api/v1/naver/marketing-ops/approve-channel` — admin-web/src/app/api/naver/marketing-ops/approve-channel/route.ts:10 (원본: `/api/v1/naver/marketing-ops/approve-channel`)
- `POST /api/v1/naver/marketing-ops/generate-package` — admin-web/src/app/api/naver/marketing-ops/generate-package/route.ts:10 (원본: `/api/v1/naver/marketing-ops/generate-package`)
- `POST /api/v1/naver/marketing-ops/neighbors/refresh` — admin-web/src/app/api/naver/marketing-ops/neighbors/refresh/route.ts:9 (원본: `/api/v1/naver/marketing-ops/neighbors/refresh`)
- `GET /api/v1/naver/marketing-ops/neighbors` — admin-web/src/app/api/naver/marketing-ops/neighbors/route.ts:9 (원본: `/api/v1/naver/marketing-ops/neighbors`)
- `POST /api/v1/naver/marketing-ops/publish-blog` — admin-web/src/app/api/naver/marketing-ops/publish-blog/route.ts:10 (원본: `/api/v1/naver/marketing-ops/publish-blog`)
- `GET /api/v1/naver/marketing-ops/state` — admin-web/src/app/api/naver/marketing-ops/state/route.ts:9 (원본: `/api/v1/naver/marketing-ops/state`)

## 501 미구현 라우트

- `POST /compose` — ai_orchestrator/connectors/naver_mail_router.py:98
- `POST /send` — ai_orchestrator/connectors/naver_mail_router.py:137

## 동적 경로(자동 대조 불가, 수동 확인 필요)

- admin-web/src/app/site-map/api.ts:206 — 원본 `${path}`
- admin-web/src/lib/assistant/api.ts:76 — 원본 `${path}`
- admin-web/src/lib/assistant/api.ts:84 — 원본 `${path}`
- admin-web/src/lib/userAuth.ts:40 — 원본 `${path}`
