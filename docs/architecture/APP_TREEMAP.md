# Haehan AI Orchestrator — App Treemap

Status: LIVING DOCUMENT  
Last updated: 2026-09-29 (0번 섹션 추가)  
Generated from: 조사 에이전트 4개 병렬 분석 결과  
Related: `docs/architecture/APP_STRUCTURE.md`, `data/codebase_layer_audit_latest.json`

---

## 0. 최상위 폴더 맵 (2026-09-29 추가, docs/defect_index.json #22)

`configs/module_registry.json`이 코드 레이어 배치의 정본이고, 아래는 그걸 보완하는
최상위 디렉터리 1줄 요약(이 문서에 없던 폴더들 — #22가 지적한 "빈/미문서화 폴더"
16개를 실측 재확인한 결과, `config/`는 이미 삭제되어 없고 나머지는 전부 실제
사용 중인 폴더였음 — 아래 표에 실측 근거 명시):

| 폴더 | 용도 | 비고 |
|------|------|------|
| `adapters/` | L3 외부 연동 어댑터(예: command_adapter.py) | |
| `agent/` | action_registry.py 등 승인정책 기반 액션 레지스트리 | 자체 tests/ 보유 |
| `apps/` | L10 로컬 PC 앱(`*-standalone`) | |
| `audit-reports/` | `audit-kit std` 실행 리포트 산출물 | 최신 = `LATEST.txt` |
| `browser_api/`, `browser_worker/` | L4 브라우저 엔진(CDP 세션/워커) | |
| `configs/` | 정책·게이트·레지스트리 설정(JSON/YAML) | 레이어 배치 정본(`module_registry.json`) 포함 |
| `data/` | 런타임 데이터·캐시·리포트 산출물(런타임 생성, 350+ 항목) | |
| `docker/` | 원격 서버 배포용 compose 파일 | 로컬 Docker CLI 사용 금지(CLAUDE.md) |
| `local_agent/` | 로컬 에이전트(데스크톱 실행기) 구현 | |
| `logs/` | 실행 로그(런타임 생성) | |
| `media/` | 자동수집 이미지/텍스트(svg)/영상 캐시 | 2026-09-29 재확인: 실제 파일 존재, 비어있지 않음 |
| `memory/` | 세션 간 피드백/정책 메모(md) | |
| `migrations/` | DB 스키마 마이그레이션 스크립트 | #14(스키마 버전 장치 부재)와 연관 |
| `notice_radar/` | 공고 수집·분석 파이프라인(collector/parsers/analyzer) | |
| `policies/` | `default_policy.yaml` 등 정책 파일 | |
| `services/` | `file_map_executor` 등 백그라운드 서비스 | |
| `storage/` | 실행 이력·후보 데이터(jsonl, 런타임 생성) | 2026-09-29 재확인: candidates/execution_history/inbox 모두 활발히 갱신 중(실데이터) |
| `tmp/` | 테스트/작업 세션 임시 산출물 | |
| `config/`(단수) | ~~2026-05월경 존재~~ | 2026-09-29 확인: 이미 삭제됨, git ls-files 에도 없음 — #22 원 제보 시점엔 있었을 수 있으나 현재는 해소됨 |

이 아래 섹션들(1~)은 폴더 트리가 아니라 **런타임 프로세스/통신/레이어** 관점의 맵이다.

---

## 1. 프로세스 맵 (런타임)

```
PC 부팅
  └─ scripts/start_haehan_ai.ps1 (시작프로그램 등록)
       │
       ├─[1] haehan-server.exe  → :8401 (FastAPI)
       │       HAEHAN_DATA_DIR = C:\work\...\data
       │
       ├─[2] node server.js     → :3000 (Next.js standalone)
       │       OWNER_MODE=true, HOSTNAME=0.0.0.0
       │
       ├─[3] chrome.exe         → :9222 (CDP)
       │       --remote-debugging-port=9222
       │       --user-data-dir=data/cdp_profile/ai_chrome
       │
       └─[4] Haehan AI.exe (Electron)
               lib/fastapi_server.js  → 헬스체크 :8401 (이미 실행 중이면 스킵)
               lib/nextjs_server.js   → 헬스체크 :3000 (이미 실행 중이면 스킵)
               lib/cdp_manager.js     → 헬스체크 :9222 (이미 실행 중이면 스킵)
               lib/agent.js           → spawn local-agent.exe
               lib/mainWindow.js      → webview :3000
               ※ 중복 기동 방지: 헬스체크 통과 시 기존 프로세스 재사용
```

---

## 2. 통신 경로 맵

```
[Electron]
  ├─ IPC (ipcMain)
  │    youtube-status  → renderer (youtube 연결 상태)
  │    youtube-connect → ensureYouTubeAuth()
  │
  ├─ spawn: local-agent.exe
  │    --server ws://127.0.0.1:8401
  │    --license KEY
  │    --parent-pid PID
  │
  ├─ spawn: haehan-server.exe (:8401)
  │    env: HAEHAN_PORT, HAEHAN_HOST, HAEHAN_DATA_DIR
  │
  └─ fork: node server.js (:3000)
       env: PORT, HOSTNAME, NODE_ENV
       OWNER_MODE: main.js:62에서 process.env로 설정 → fork 시 상속됨

[Next.js :3000]
  ├─ middleware.ts
  │    OWNER_MODE=true → 인증 우회
  │    JWT 쿠키 만료: 30일
  │
  ├─ /api/proxy/[...path]  → http://127.0.0.1:8401 (Basic Auth)
  └─ next.config.mjs rewrites (FASTAPI_BASE_URL 설정 시만 활성)
       /api/v1/* → FASTAPI_BASE_URL/api/v1/*
       ※ 로컬 개발환경에서 FASTAPI_BASE_URL 미설정 시 rewrites 비활성
          → 모든 FastAPI 호출은 /api/proxy/ 경로 사용

[local-agent.exe]
  ├─ WS Client → ws://127.0.0.1:8401/api/v1/smartstore/agent/ws?license=KEY
  │    프로토콜: {type:connected} → {type:tool_call} → {type:tool_result}
  │
  └─ Playwright CDP → http://127.0.0.1:9222
       connect_over_cdp() → 실제 브라우저 DOM 조작

[FastAPI :8401]
  ├─ /api/v1/health                    GET (헬스체크)
  ├─ /api/v1/smartstore/agent/ws       WS (local-agent CDP 브릿지)
  ├─ /api/v1/local-agents/ws           WS (device_token 인증, 신규 프로토콜)
  ├─ /api/v1/local-agents/register     POST (admin/owner 권한)
  ├─ /api/v1/users/login               POST (JWT 발급)
  ├─ /api/v1/tasks                     POST (작업 제출)
  ├─ /api/v1/tasks/{id}/approve        POST (승인)
  └─ /api/v1/oauth/youtube/callback    GET (YouTube OAuth)
```

---

## 3. 레이어 맵 (L1~L12)

```
L1  Shared Contracts   ai_orchestrator/models.py
                       ai_orchestrator/*/schemas.py
                       scripts/*/schemas.py             (1,353파일)

L2  Policy/Gate        ai_orchestrator/auth.py
                       ai_orchestrator/approval.py
                       ai_orchestrator/browser_gate_middleware.py
                       scripts/common/gate.py                  (53파일)

L3  Connectors         ai_orchestrator/connectors/*
                       admin-web/electron/lib/agent.js
                       admin-web/electron/lib/fastapi_server.js
                       admin-web/electron/lib/nextjs_server.js
                       admin-web/electron/lib/cdp_manager.js
                       admin-web/electron/lib/remote_config.js
                       admin-web/electron/lib/youtube.js
                       admin-web/electron/lib/bus.js
                       admin-web/electron/lib/nextjs_wrapper.js  (76파일)

L4  Browser Engine     scripts/browser/agent/
                       scripts/cdp_*.py                  (482파일)

L5  Site Modules       scripts/eum/
                       scripts/gabia/
                       scripts/hiworks/
                       scripts/naver/
                       scripts/google/
                       scripts/g2b/
                       scripts/kakao/
                       scripts/youtube/                  (399파일)

L6  Workflows          scripts/*/workflows.py
                       scripts/hiworks/mail_batch.py     (5파일)

L7  Persistence/Audit  ai_orchestrator/audit/audit_logger.py
                       ai_orchestrator/persistence/user_db.py
                       scripts/browser/cdp/cdp_db.py
                       scripts/common/op_log.py                 (940파일)

L8  Server API         ai_orchestrator/asgi.py
                       ai_orchestrator/router.py
                       ai_orchestrator/*/*_router.py     (274파일)

L9  Admin UI           admin-web/src/app/**
                       admin-web/src/components/**
                       admin-web/electron/lib/mainWindow.js
                       admin-web/electron/lib/licenseWindow.js
                       admin-web/electron/lib/tray.js       (391파일)

L10 Local PC App       admin-web/electron/main.js
                       admin-web/electron/lib/config.js     (191파일)

L11 Tests              tests/
                       */test_*.py
                       admin-web/src/**/__tests__/       (974파일)

L12 Docs/Reports       docs/
                       data/*_report*.json               (759파일)
```

---

## 4. 게이트 맵

```
git commit
  ├─ ruff check --fix (린트 자동 수정)
  ├─ ruff format
  └─ quality_gate.py --staged --enforce --allow-existing-code-change
       ├─ NO_LOCAL_DOCKER_CLI    → subprocess docker 호출 금지
       ├─ DESTRUCTIVE_SQL        → DROP/DELETE/TRUNCATE 금지
       ├─ SCHEMA_CHANGE          → doc+test 필수
       ├─ EXISTING_CODE_MODIFIED → 플래그 필요
       └─ CODE_WITHOUT_TEST      → 경고

git push
  └─ ai_code_review_gate.py (Claude Haiku 검수)
       → BLOCK 판정 시 푸시 차단

작업 후 수동 의무 (CLAUDE.md 규칙):
  ├─ python tools/repo_gates/codebase_layer_audit.py
  ├─ pytest tests/test_codebase_layer_audit.py -q
  └─ python tools/quality/quality_gate.py --staged --enforce --allow-existing-code-change

  STOP 조건:
    FORBIDDEN_IMPORT > 0  → STOP
    CIRCULAR_IMPORT  > 0  → STOP
    SECURITY_PATTERN > 0  → STOP
```

---

## 5. FastAPI 라우터 트리

```
/api/v1
 ├─ /health
 ├─ /auth
 ├─ /users/signup, /login, /me, /me/password
 ├─ /local-agents
 │    ├─ /register          POST  (admin/owner)
 │    ├─ /registration-codes POST  (admin/owner)
 │    ├─ /register-with-code POST  (코드 기반 등록)
 │    ├─ /{id}/tasks        POST  (작업 제출)
 │    └─ /ws                WS    (device_token 인증)
 ├─ /smartstore
 │    ├─ /products, /orders, /settlements, /reviews, /stats
 │    ├─ /agent/ws          WS    (license 인증, CDP 브릿지)
 │    └─ /chat
 ├─ /naver-search, /naver-news, /naver-cafe, /naver-mail
 ├─ /naver-session
 ├─ /hiworks-mail, /gmail
 ├─ /youtube
 ├─ /google
 ├─ /gabia
 ├─ /kakao-setup
 ├─ /grant-radar
 ├─ /cad, /cad-ai
 ├─ /file-map  ※ FastAPI 라우터 없음 — Next.js API 라우트만 존재 (admin-web/src/app/api/file-map/)
 ├─ /ops
 ├─ /approval-records/requests/{id}/approve   POST (approval_record_router)
 ├─ /tasks/{task_id}/approve                 POST (router.py 직접 등록)
 │    ※ /local-agents/{id}/tasks/{task_id}/approve 도 별도 존재 (task_router)
 ├─ /deployments          (GitHub webhook)
 └─ /config               (원격 환경변수 주입)
```

---

## 6. 주요 설정 파일 맵

```
프로젝트 루트
  ├─ CLAUDE.md                   AI 작업 규칙 (게이트, 레이어, 운영규칙)
  ├─ .env                        시크릿 (원문 출력 금지)
  ├─ configs/quality_gate.json   품질 게이트 설정
  ├─ haehan-server.spec          FastAPI PyInstaller 빌드 설정
  ├─ local-agent.spec            local-agent PyInstaller 빌드 설정
  │
  ├─ data/
  │    ├─ licenses.json          라이선스 DB (HAEHAN_DATA_DIR 기준)
  │    ├─ cdp_profile/ai_chrome  CDP 브라우저 세션
  │    └─ codebase_layer_audit_latest.json  최신 감사 결과
  │
  ├─ admin-web/electron/
  │    ├─ lib/config.js          SERVER_URL(:3000), FASTAPI_URL(:8401)
  │    ├─ lib/agent.js           --server FASTAPI_URL (ws://)
  │    ├─ lib/fastapi_server.js  HAEHAN_DATA_DIR 주입
  │    └─ lib/nextjs_server.js   OWNER_MODE=true 주입
  │
  └─ admin-web/.next/standalone/
       ├─ server.js              Next.js 프로덕션 서버
       └─ wrapper.js             Electron WebSocket 오류 필터
```

---

## 7. 현재 알려진 이슈

| # | 항목 | 파일 | 상태 |
|---|------|------|------|
| 1 | local-agent WS 403 (license.py HAEHAN_DATA_DIR) | `connectors/smartstore/license.py` | ✅ 해결 (exe 재빌드 완료 23:03) |
| 2 | haehan-server.exe HAEHAN_DATA_DIR 경로 오류 | `fastapi_server.js` | ✅ 해결 (asar 패치 완료) |
| 3 | STORAGE_BOUNDARY 11개 (sqlite3 직접 import) | `user_db.py` 외 10개 | 미해결 |
| 4 | UNKNOWN_LAYER 3,630개 | dist/, node_modules | 감사 제외 규칙 추가 필요 |

---

## 갱신 절차

이 파일은 다음 시점에 갱신한다:
1. 새 라우터/모듈 추가 시
2. 포트/서버 구성 변경 시
3. 레이어 분류 변경 시
4. `python tools/repo_gates/codebase_layer_audit.py` 실행 후 주요 변화 시
