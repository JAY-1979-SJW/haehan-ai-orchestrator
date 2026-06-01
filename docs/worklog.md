# 작업 로그 (Work Log)

> 최신 항목이 맨 위. 세션 시작 시 SessionStart 훅이 이 파일 상단을 보여줌.
> 각 세션 끝에 "한 일 / 다음 할 일"을 기록한다.

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
