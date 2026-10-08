# 하이웍스 로직 참조

작성일: 2026-05-13  
상태: 완료(`complete_baseline`)

하이웍스는 현재 브라우저 기반 업무 탐색 및 메일 준비 baseline으로 완료 처리한다. 공식 API 연동은 `docs/hiworks_integration_plan.md`에 남겨 둔 별도 장기 트랙이며, 이 문서는 현재 사이트 작업과 다음 사이트 재사용 기준을 설명한다.

## 완료 범위

| workflow | 명령 | 위험 | 완료 기준 |
| --- | --- | --- | --- |
| `dashboard` | `python scripts/entry/cdp_cli.py hiworks dashboard` | `read` | 대시보드 열기와 앱 후보 출력 |
| `apps` | `python scripts/entry/cdp_cli.py hiworks apps` | `read` | 앱 목록을 `data/hiworks_apps_latest.json`에 저장 |
| `mail` | `python scripts/entry/cdp_cli.py hiworks mail` | `read` | 메일 화면 열기와 보이는 동작 목록 출력 |
| `compose` | `python scripts/entry/cdp_cli.py hiworks compose` | `read` | 작성 화면 진입 후보와 입력 요소 요약 저장 |
| `service_scan` | `python scripts/entry/cdp_cli.py hiworks service all --limit=60` | `read` | 하이웍스 주요 업무 서비스 17개 표면 구조 저장 |
| `action_catalog` | `python scripts/entry/cdp_cli.py hiworks actions all` | `read` | 17개 섹션의 입력 필드와 버튼을 prepare/read/submit_gated로 분류 |
| `prepare_section` | `python scripts/entry/cdp_cli.py hiworks prepare-section all --dry-run` | `prepare` | 모든 섹션의 입력 가능 필드와 버튼 게이트 계획 저장 |
| `prepare_sales_mail` | `python scripts/entry/cdp_cli.py hiworks prepare-sales-mail <index>` | `prepare` | 큐의 1건을 작성창에 채우고 발송하지 않음 |
| `send_batch_plan` | `python scripts/entry/cdp_cli.py hiworks send-batch <limit> --dry-run` | `prepare` | 1인 1통 발송 계획만 생성하고 실제 발송하지 않음 |
| `submit_section` | `python scripts/entry/cdp_cli.py hiworks submit-section <service> <control_id> --approved --confirm=HIWORKS_APPROVED_SUBMIT` | `send` | 승인과 확인문구가 모두 있을 때 해당 버튼 1회 실행 |

전체 탐색 보고: `docs/reports/hiworks_full_exploration_report_20260513.md`

## 모듈 구조

| 파일 | 책임 |
| --- | --- |
| `scripts/hiworks/router.py` | CLI dispatch 전용 |
| `scripts/hiworks/schemas.py` | URL, 큐 경로, workflow/service catalog |
| `scripts/hiworks/gates.py` | read/prepare/send 위험 게이트 |
| `scripts/hiworks/explorer.py` | 대시보드, 앱, 메일 화면 read-only 탐색 |
| `scripts/hiworks/service_explorer.py` | 하이웍스 업무 서비스 표면 read-only 탐색 |
| `scripts/hiworks/actions.py` | 모든 섹션 입력/버튼 카탈로그, prepare 계획, submit 게이트 분리 |
| `scripts/hiworks/mail.py` | 작성 화면 탐지와 fill-only 입력 |
| `scripts/hiworks/mail_batch.py` | 1인 1통 발송 dry-run 계획 생성 |
| `scripts/hiworks/workflows.py` | 큐 로드, 작성 준비, 계획 저장 |
| `scripts/hiworks/run_log.py` | 실행 로그와 실시간 감사 이벤트 |

## 공통화 기준

- 라우터는 명령 분기만 담당한다.
- 사이트 URL, workflow catalog, service target catalog는 `schemas.py`에 둔다.
- 업무 표면 탐색은 링크/버튼/입력 필드 구조만 저장하고 클릭/제출하지 않는다.
- 모든 섹션의 입력/버튼은 `actions.py`에서 공통 분류한다.
- 입력 필드는 명시 값이 제공될 때만 prepare 대상으로 삼고, password/file/token/session/cookie 계열은 차단한다.
- 버튼은 기본 상태에서 자동 클릭하지 않는다. 저장/등록/상신/발송/신청/삭제/업로드/공유 등 상태 변경 후보는 `submit_gated`로 두고, 승인과 확인문구가 모두 있을 때만 `submit_section`에서 1회 실행한다.
- 실제 발송은 `gates.check_send()` 뒤에서도 아직 구현하지 않는다.
- `prepare_sales_mail`은 작성창을 채우지만 send 버튼을 누르지 않는다.
- `send_batch_plan`은 `dry_run_plan`, `send_status=not_sent`, `one_recipient_per_message`를 고정한다.
- 실행 명령은 `data/hiworks_runs/<workflow>/`에 기록하고 `HIWORKS_WORK_*` 감사 이벤트를 남긴다.

## 남은 항목

- 실제 메일 발송 E2E는 승인 게이트, 운영자 확인, 발송 대상 재검증 이후 별도 구현한다.
- 결재 상신, 휴가 신청, 예약 등록, 게시글 작성 등 submit 계열은 승인 게이트 없이는 실행하지 않는다.
- 승인 실행 표준은 상시 적용한다. 명령에는 `--approved`와 `--confirm=HIWORKS_APPROVED_SUBMIT`가 모두 필요하며, 검증은 먼저 `--dry-run`으로 버튼 매칭과 증적 저장을 확인한다.
- 공식 Hiworks API는 개발자 포털/토큰/scope 확인 후 별도 baseline으로 진행한다.
