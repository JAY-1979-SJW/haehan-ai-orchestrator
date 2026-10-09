# 사이트 자동화 참조 인덱스

작성일: 2026-05-13

EUM과 하이웍스에서 확정한 브라우저, 승인, 감사, 문서화 기준을 다른 사이트 작업의 공통 기준으로 재사용한다.

## 먼저 읽을 문서

| 구분 | 문서 | 용도 |
| --- | --- | --- |
| 공통 아키텍처 | `docs/site-automation-architecture.md` | 사이트 자동화 계층, 커넥터 구조, 권한 정책 |
| 공통 실행 표준 | `docs/web_automation_standard.md` | fill/submit 분리, selector 작성, 민감정보 처리 |
| 실시간 감사/로그 | `docs/realtime_audit_logging.md` | 작업 시작/완료/실패 이벤트와 tail 감시 |
| 작업트리 관리 | `docs/worktree_management_index.md` | 변경 파일 분류, 인덱스 생성, 관리 규칙 |
| 공통 운영 인덱스 | `docs/common_operations_index.md`, `configs/common_operations_index.json` | 신규 작업 전 사이트/홈페이지 작업 순서, 공통 게이트, 다음 작업 확인 |
| 코드 레이어 분류 | `docs/layer_classification.md` | L0-L12 경계와 사이트 모듈 구조 |
| 품질 게이트 | `tools/quality/quality_gate.py` | 코드/문서/테스트/DB 스키마 변경 조건 검사 |
| Pre-change dry-run | `docs/pre_change_dry_run_policy_20260513.md` | 코드 수정 전 현재 동작/dry-run 증적 기록 |
| 배포 dry-run | `tools/deploy/deploy_dry_run.py` | 배포 관련 변경 전 dry-run 증적 기록 |
| 사이트 상태 취합 | `docs/site_automation_status_index.md` | 모든 사이트 완료/진행 상태 공통 인덱스 |
| EUM 기준 구현 | `docs/eum_logic_reference_20260513.md` | 현재 사이트에 검증한 실제 적용 패턴 |
| 하이웍스 기준 구현 | `docs/hiworks_logic_reference_20260513.md` | 섹션 입력/버튼 action catalog, 승인+확인문구 실행 기준, 메일 준비/발송 계획 패턴 |
| 스마트스토어 기준 구현 | `docs/smartstore_logic_reference_20260513.md` | action catalog, 상품 준비 dry-run, 승인+확인문구 submit, DB 등록 로그 인덱스 참조 |
| 네이버 라이브 안전 정책 | `docs/naver_live_safety_policy_20260513.md` | 공식 API 전제 없음, live 기본 차단, 로봇/보안 신호 즉시 중단, dry-run 우선 |

## 공통 설계 원칙

신규 사이트나 신규 workflow 작업을 시작하기 전에는 반드시 작업트리 인덱스를 먼저 생성한다.

```powershell
python scripts\ops\worktree_change_index.py
```

코드 수정 전에는 선택한 scope에 대한 pre-change dry-run 증적을 남긴다.

```powershell
python scripts\ops\pre_change_dry_run.py --scope <scope> --reason "<why>" -- <dry-run command>
```

작업 중 오류가 나거나 판단할 내용이 생기면 `data/worktree_change_index_latest.json`에서 해당 파일의 `owner`, `category`, `layer`를 확인하고, `docs/worktree_management_index.md`의 reference pack을 기준으로 다음 조치를 정한다.

모든 사이트 작업은 다음 단계로 분리한다.

```text
discover -> plan -> prepare -> submit -> verify -> log
```

| 단계 | 허용 동작 | 금지/주의 |
| --- | --- | --- |
| discover | 메뉴, 링크, 표, 입력 필드 읽기 | 제출/저장/삭제 클릭 금지 |
| plan | 입력값 검증, 실행계획 JSON 저장 | 사이트 상태 변경 금지 |
| prepare | 값 입력, 초안 작성, 파일 생성 | 최종 제출/발송 클릭 금지 |
| submit | 승인 게이트 통과 후 최종 클릭 | 승인 없는 상태 변경 금지 |
| verify | 결과 메시지, URL, 표 확인 | 민감 HTML 전체 저장 금지 |
| log | 요약 JSON, 감사 이벤트 저장 | 비밀번호, 쿠키, 토큰 저장 금지 |

## 위험 등급

| 위험 등급 | 예 | 기본 정책 |
| --- | --- | --- |
| `read` | 조회, 목록 추출, 상태 확인, 다운로드 후보 확인 | 자동 실행 가능 |
| `prepare` | 값 입력, 초안 작성, 계획 생성 | 제출 없이 실행 가능 |
| `approval` | 등록, 삭제, 발송, 신청, 업로드 | 승인 게이트 필수 |
| `blocked` | 결제, CAPTCHA 우회, 권한 우회 | 기본 차단 |

## 사이트별 인덱스

| site_id | 사이트 | 기준 문서 | 주요 workflow | 상태 |
| --- | --- | --- | --- | --- |
| `eum` | 건설근로자공제회 EUM | `docs/eum_logic_reference_20260513.md` | 단말기 조회, 신규 등록 준비, 철거/말소 준비, 영업메일 큐 | 완료(`complete_baseline`) |
| `hiworks` | 하이웍스 | `docs/hiworks_logic_reference_20260513.md` | 대시보드/앱 탐색, 17개 섹션 입력/버튼 분류, 승인 실행 게이트, 메일 작성 준비, 발송 dry-run 계획 | 완료(`complete_baseline`) |
| `naver` | 네이버 서비스 | `docs/NAVER_SERVICES_EXPANSION_PLAN.md` | 블로그, 카페, 메일, 개인 서비스 | 부분 구현 |
| `smartstore` | 네이버 스마트스토어 | `docs/smartstore_logic_reference_20260513.md` | 상품 action catalog, dry-run prepare, 승인 submit, 상품/주문/통계 조회 기준 | 완료(`complete_baseline`) |
| `g2b` | 나라장터 | `docs/reports/g2b_public_notice_readonly_matrix_20260507.md`, `docs/reports/g2b_completion_report_20260513.md` | 공고 조회/첨부 확인, 인증/입찰/계약 차단 게이트 | 검증 완료(`verified`) |
| `google` | Google/Gmail/YouTube | `docs/google_surface_catalog_reference_20260513.md`, `docs/google_business_workflow_reference_20260513.md`, `docs/reports/google_surface_exploration_completion_report_20260513.md` | 50개 surface catalog/read-only 탐색, 96개 work action, approval-gated execution adapter | 구현됨(`implemented`) |

새 사이트 문서를 추가하면 `docs/site_automation_status_index.md`, `configs/site_automation_status_index.json`, 이 참조 인덱스에 반드시 반영한다.

## 코드 위치 인덱스

| 영역 | 경로 |
| --- | --- |
| 공통 CDP 진입 | `scripts/cdp_client.py`, `scripts/browser/cdp/cdp_daemon.py` |
| 사이트 라우터 | `scripts/site_engine/command_router.py`, `scripts/<site>/router.py` |
| 브라우저 재사용 | `scripts/browser/cdp/connection.py` |
| 로그인/세션 | `scripts/<site>/auth.py`, `scripts/site_engine/site_access.py` |
| 팝업/비정상 접근 | `scripts/browser/popup/popup_watcher.py`, `scripts/browser/popup/popup_classifier.py`, `scripts/<site>/access_handler.py` |
| 작업 계획 | `scripts/<site>/work_plan.py` |
| 실행 로그 | `scripts/<site>/run_log.py` |
| 실시간 감사 | `scripts/common/realtime_audit.py`, `tools/runtime/watch_log.py` |
| 승인 게이트 | `scripts/common/gate.py`, `scripts/<site>/gates.py` |
| 작업트리 분류 | `tools/devflow/worktree_change_index.py` |

## Common Session Safety Update

Updated: 2026-05-13

All live site workflows must apply login/session integrity checks before
navigation, scanning, preparation, or submit execution.

- Policy: `docs/common_login_session_safety_policy_20260513.md`
- Common module: `scripts/site_engine/site_session_safety.py`

Hard-stop examples:

- `different_user_logged_in`
- `session_user_mismatch`
- `stale_session`
- `expired_session`
- `invalid_session`
- expected user and actual user mismatch

## Common Page Completion Rule

Fast exploration is acceptable after a verified login, but speed is subordinate
to accuracy.

Before moving to the next page, the current page must have:

- visible controls classified
- state-changing controls gated
- required data and dependencies identified
- dry-run behavior verified when applicable
- audit/log artifacts recorded
- unresolved items documented as deferred

If the site appears monitored, challenged, or inconsistent, slow down, narrow
the scope, or stop the live workflow.

## Google Surface Catalog

Updated: 2026-05-13

Google/YouTube exploration is catalog-first. Console, AI Studio, Android,
Play Console, Firebase, YouTube, and YouTube Studio are recorded in the common
surface index before live work.

- Reference: `docs/google_surface_catalog_reference_20260513.md`
- Business workflow reference: `docs/google_business_workflow_reference_20260513.md`
- Latest artifact: `data/google_surface_catalog_latest.json`
- Latest action artifact: `data/google_work_action_catalog_latest.json`
- Latest adapter artifact: `data/google_execution_adapter_catalog_latest.json`
- Command: `python scripts\entry\cdp_cli.py google surfaces catalog`
- Action command: `python scripts\entry\cdp_cli.py google work catalog`
- Adapter command: `python scripts\entry\cdp_cli.py google work ai_orchestrator.connectors.g2b`
- Rule: read-only live exploration first; write, publish, release, billing,
  IAM, API key, upload, comment, and indexing actions require dry-run and
  explicit approval.
- Coverage: 50 surfaces, 96 work actions, 46 approval-gated state-changing
  action contracts, 96 execution adapter profiles.

## Full Business Workflow Rule

Updated: 2026-05-13

When a site is requested for business use, all workflows must be developed
through the full pipeline:

```text
discover -> plan -> prepare -> approval -> execute -> verify -> log
```

Approval gating is not a reason to omit the final execution path. The execute
path must exist, but it must run only after the user explicitly approves the
prepared artifact.

- Policy: `docs/business_workflow_full_development_policy_20260513.md`

## Common Security Redaction

Updated: 2026-05-13

All site automation modules share one security/redaction baseline.

- Root security implementation: `security_utils.py`
- `scripts.common.security` compatibility wrapper: `scripts/common/security.py`
- Logging compatibility facade: `logging_utils.py`
- Credential storage and masked CLI output: `scripts/auth/credentials.py`

## YouTube Recording And Upload

Updated: 2026-05-13

Local work recording and YouTube upload are now modeled as separate gated
workflows.

- Router: `scripts/youtube/router.py`
- Recording workflow: `scripts/youtube/recording.py`
- Upload workflow: `scripts/youtube/uploader.py`
- Reference: `docs/youtube_recording_upload_workflow_20260513.md`
- Command entry: `python scripts\entry\cdp_cli.py youtube ...`

Recording, upload, and public publishing are separate approval decisions.
- Policy reference: `docs/common_login_session_safety_policy_20260513.md`

New site work must reuse the common helpers before writing logs, audit events,
DB-safe records, or CLI status output. Site-specific sensitive-key lists should
not be created unless the shared module is updated first.

## Naver Developed Tools Update

Updated: 2026-05-27

Naver developed tools are indexed separately:

- Tool index: `docs/naver_developed_tools_index.md`
- Service catalog: `scripts/naver/service_catalog.py`
- Cafe tools: `scripts/naver/cafe/`
- Keyword tools: `scripts/naver/keyword_tools.py`
- Mail background/tools: `scripts/naver_mail/`, `scripts/naver/mail_read/`
- Common tab isolation gate: `scripts/browser/session/browser_cdp_selection_gate.py`

Current verified Naver tool groups:

- service catalog
- keyword tools and free-only paid-action blocks
- cafe list/home/topic-search
- cafe join-request and join-submit approval gate
- joined cafe home and board collection
- Naver Mail background read and settings inspection

Policy:

- CDP browser work must use existing sessions and common tab isolation.
- Cafe join-request is prepare-only. Final join submit requires
  `NAVER_APPROVED_CAFE_JOIN`.
- Naver Mail send/delete/move/settings-save remain approval-gated.
- Paid Naver API, search-ad campaign/budget, payment registration, and ad
  publish actions remain blocked.
