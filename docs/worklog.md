# 작업 로그 (Work Log)

> 최신 항목이 맨 위. 세션 시작 시 SessionStart 훅이 이 파일 상단을 보여줌.
> 각 세션 끝에 "한 일 / 다음 할 일"을 기록한다.

---

## 2026-06-02 (오후 재개) — P1 사이트 카탈로그 + 로컬 설정

### 한 일
- **P1-1 완료**: `GET /api/v1/sites/catalog` (커밋 08b0e19)
  - `external_work_registry.list_site_catalog()` provider별 그룹핑, `sites/router.py`(JWT), 민감필드 미노출
  - `tests/test_site_catalog.py` 4종, STOP 0
- **P1-2 완료**: `config.js` 로컬 저장 헬퍼 (커밋 직후)
  - getEnabledSites/setEnabledSites/getSiteSettings/setSiteSettings
  - enabled_sites(중복제거) / site_settings(병합) / 민감키 저장 차단 / 순수 로컬
  - 기능검증(electron 스텁): round-trip·병합·민감키차단·평문미저장 통과
- 작업 로그 훅 활성화(SessionStart → worklog 상단 자동 표시)

### P1-3 (IPC 브리지) 완료
- 설계 확정 + **원격화면 기능 보류**(보안위험 해소, 로컬 UI 전용) — docs/architecture/P1_3_IPC_BRIDGE_PLAN.md
- 구현: `webview_preload.js`(window.haehanLocal 4개), main.js ipcMain.handle 4개, shell.html preload 부착, mainWindow preload 경로 전달
- 검증: STOP 0, 게이트 통과, asar 반영(webview_preload 포함, 핸들러 4개)

### P1-3 화면 완료
- `localConfig.ts`(브리지 가드 래퍼), `sitesCatalog.ts`(카탈로그 JWT fetch), `/settings/sites` 토글 페이지, nav 추가
- tsc 0, STOP 0, 게이트 통과
- 실앱 검증(webview window.haehanLocal 왕복)은 앱 재시작 시 확인 — 미수행

### P1-4 완료
- local_agent.py: `_TOOL_SITE` 매핑 + `_site_allowed` 게이트 + `--enabled-sites` 인자
  - enabled_sites 비면 제한없음(owner/기존 보존), 값 있으면 해당 사이트 tool만, 미등록 tool 항상 허용
  - 미활성 tool → `site_not_enabled` 거부 반환
- agent.js: getEnabledSites() → `--enabled-sites` 전달
- tests/test_local_agent_site_gate.py 4종, STOP 0, 게이트 통과

### P1-5 부분 완료 (운영 라이브) + 502 인시던트 해소
- push(a2a9c6e) → **복구된 데몬이 자동 배포** (api+admin-web 재빌드)
- **카탈로그 운영 라이브**: `GET /orchestrator/api/v1/sites/catalog` → 401(JWT보호) 확인 ✅
- local-agent.exe 재빌드+설치본 반영(--enabled-sites 인식 확인), asar에 P1-4 agent.js 반영
- ⚠️ **502 인시던트(약 5분)**: 컨테이너 재빌드로 docker IP 변경 → nginx 옛 IP 캐시 → 502. `nginx -s reload`로 해소(health 200 복구)
- **원인 수정 커밋(미push)**: `server_deploy.py`에 `_reload_nginx()` 추가 — compose up 후 nginx 재해결
  - ⚠️ 지금 push하면 데몬이 또 재빌드→첫 배포는 여전히 502(실행중 스크립트는 git_sync 전 버전). 다음 의도된 배포 때 push + 배포 후 수동 nginx reload로 처리
  - 로컬 master가 origin보다 1커밋 앞섬(이 수정)

### 다음 할 일 (NEXT)
- **P1-5 잔여**: 데스크톱 실앱 E2E — 앱 실행 → /settings/sites 토글 → config.json 저장 → 에이전트 --enabled-sites 반영. (로컬 Next.js standalone 빌드가 이번 세션 불안정했음 → 서버 UI는 owner IP로 접근해 페이지 렌더 확인 가능, 단 window.haehanLocal 저장은 데스크톱 webview 필요)
- **server_deploy nginx-reload 수정 push** (배포 502 영구 방지) — 다음 배포 시 함께
- 정리정돈(미착수): 루트 스크립트 39개, STORAGE_BOUNDARY 11개, UNKNOWN 레이어
- 카탈로그 사이트 추가 = external_work_registry 항목 추가 (현재 naver/google/gabia)
- 참고: 카탈로그는 현재 naver/google/gabia만. 사이트 추가 = external_work_registry 항목 추가
- 결정사항: 원격화면 보류 → 화면은 로컬 전용. 청사진 P2(원격 UI) 보류 표기됨
- 피드백 반영: 단계마다 "중단할까요" 묻지 않고 자동 진행 (feedback.md)

---

## 2026-06-02 — 멀티유저 제품 방향 확정 + 운영 회원승인 배포

### 한 일
- **디스크 정리**: C드라이브 82GB→352GB (Chrome AI모델·OneDrive로그·빌드아티팩트 등 ~270GB)
- **앱 실행 복구**: local-agent WS를 8401(FastAPI)로 수정, 번들 서버 경로, OWNER_MODE 상시로그인
- **앱 트리맵 작성**: `docs/architecture/APP_TREEMAP.md` (오류 7개 정정)
- **회원 승인 게이트(P0)**: 가입(enabled=0 대기)→관리자 승인→로그인
  - 서버: `user_db.py`(approve_user/list_pending_users/is_pending_login), `user_auth_router.py`(signup 대기응답 + /pending + /{id}/approve, require_role)
  - 화면: signup "승인 대기" 안내, 승인 콘솔 `/admin/users`
  - 테스트: `tests/test_user_approval_gate.py` 5종
- **배포 파이프라인 복구**: 데몬이 삭제된 스크립트 호출 → `scripts/ops/server_deploy.py`(신규, docker scoped 예외+로컬가드) + 데몬 경로 수정
- **운영 반영 완료**: 서버 코드 ea12a56 동기화, api·admin-web 재빌드, nginx에 signup/login 공개 예외, **E2E 검증**(가입→대기→로그인차단)
- **제품 방향 확정**: "Claude 데스크앱형 멀티유저 배포 앱". 데이터 격리 = **순수 로컬 per-user**(서버 멀티테넌트 폐기)
- 설계 문서: TARGET_PRODUCT_ARCHITECTURE, MULTIUSER_UI_ACCESS_PLAN, THIN_CLIENT_PLAN, PROD_DEPLOY_PLAN, DEPLOY_PIPELINE_REPAIR, SITE_CATALOG_LOCAL_CONFIG_PLAN

### 커밋
4d04362(앱복구) · 0b1372b(승인게이트) · 32894dc(가입화면) · ebfa86a(승인콘솔) · ea12a56(배포복구) · 7ff6721(청사진) — origin/master push 완료

### 운영 상태
- haehan-ai.kr: 가입·승인·로그인 라이브. users.db 0명(깨끗). 롤백 기준 코드 530a88b. 백업 /home/ubuntu/backups/
- SSH: `ssh haehan-app` (1.201.176.236). nginx 호스트 conf: /home/ubuntu/app/nginx/conf.d/default.conf

### 다음 할 일 (NEXT)
- **P1(신) 구현**: 사이트 카탈로그 + 로컬 설정 — 기준서 `docs/architecture/SITE_CATALOG_LOCAL_CONFIG_PLAN.md` 승인됨, 구현 1단계(서버 `GET /sites/catalog`)부터
  1. 서버 카탈로그 엔드포인트(external_work_registry 그룹핑) + 테스트
  2. 로컬 저장 헬퍼(config.js: enabled_sites/site_settings)
  3. 사이트 선택 화면
  4. local-agent 선택분만 실행
  5. E2E
- 이후: P2(사용자 UI 접근+JWT검증), P3(사용자별 agent), P4(경량 배포앱), P5(온보딩 이메일)
- 미해결 정리정돈: 루트 스크립트 39개, STORAGE_BOUNDARY 11개(sqlite 직접), UNKNOWN 레이어 분류
