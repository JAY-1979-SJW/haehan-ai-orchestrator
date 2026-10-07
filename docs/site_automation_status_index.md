# 사이트 자동화 상태 인덱스

작성일: 2026-05-13

모든 사이트 자동화 진행 상태를 같은 기준으로 취합한다. 사이트별 상세 구현 논리는 각 `logic_reference` 문서에 두고, 이 문서는 완료 상태와 다음 작업 판단 기준만 관리한다.

## 상태 체계

| 상태 | 의미 |
| --- | --- |
| `planned` | 대상 사이트만 식별됨 |
| `discovered` | read-only 탐색/사이트맵 수집 완료 |
| `designed` | 설계 문서와 workflow 분류 완료 |
| `implemented` | 코드 구현 완료 |
| `verified` | 단위/정책 테스트 통과 |
| `complete_baseline` | 공통 기준 구현 완료. 상태 변경 submit은 승인 필요 |
| `complete_live` | 승인된 실제 E2E까지 완료 |
| `blocked` | 계정/권한/CAPTCHA/정책 문제로 중단 |

상태 변경 업무가 있는 사이트는 `complete_live`가 아니어도 `complete_baseline`으로 완료 처리할 수 있다. 이때 실제 submit, 발송, 삭제는 별도 승인 항목으로 남긴다.

## 사이트별 현황

| site_id | 사이트 | 상태 | 완료 보고 | 기준 문서 | 비고 |
| --- | --- | --- | --- | --- | --- |
| `eum` | 건설근로자공제회 EUM | `complete_baseline` | `docs/reports/eum_completion_report_20260513.md` | `docs/eum_logic_reference_20260513.md` | 실제 등록/말소 submit E2E는 승인 후 |
| `hiworks` | 하이웍스 | `complete_baseline` | `docs/reports/hiworks_completion_report_20260513.md` | `docs/hiworks_logic_reference_20260513.md` | 17개 업무 서비스 표면 탐색 및 입력/버튼 action catalog 완료. 실제 메일 발송/결재/신청은 승인+확인문구 후 |
| `naver` | 네이버 서비스 | `implemented` | - | `docs/NAVER_SERVICES_EXPANSION_PLAN.md` | 기능 범위가 넓어 서비스별 분리 필요 |
| `g2b` | 나라장터 | `verified` | `docs/reports/g2b_completion_report_20260513.md` | `docs/reports/g2b_public_notice_readonly_matrix_20260507.md` | 공개 공고/첨부 목록 read-only 검증 완료. 인증/입찰/계약/다운로드는 차단 또는 사용자 직접 처리 |
| `google` | Google/Gmail | `implemented` | `docs/reports/google_surface_exploration_completion_report_20260513.md` | `docs/google_surface_catalog_reference_20260513.md` | 50개 surface read-only 탐색 완료, API/브라우저 경로 병행 |
| `kakao` | Kakao | `planned` | - | `docs/KAKAO_DESKTOP_DESIGN.md` | 데스크톱 자동화 별도 |
| `smartstore` | 네이버 스마트스토어 | `complete_baseline` | `docs/reports/smartstore_completion_report_20260513.md` | `docs/smartstore_logic_reference_20260513.md` | action catalog, dry-run prepare, approval-gated submit baseline complete; live E2E paused after Naver robot detection |

## 공통 취합 규칙

사이트를 완료 처리할 때는 다음을 모두 갱신한다.

1. `configs/site_automation_status_index.json`
2. 이 문서의 사이트별 현황 표
3. `docs/site_automation_reference_index.md`의 사이트별 인덱스
4. 사이트별 로직 참조 문서
5. 완료 보고서 `docs/reports/<site>_completion_report_YYYYMMDD.md`

필수 완료 보고 항목:

- site_id
- 완료 판정
- 완료 workflow 목록
- 미완료/승인 대기 workflow 목록
- 검증 명령과 결과
- 공통화 반영 위치

## Google Update - 2026-05-13

`google` now has a surface catalog and approval-gated business workflow
baseline.

- Status artifact: `data/google_surface_catalog_latest.json`
- Work artifact: `data/google_work_action_catalog_latest.json`
- Adapter artifact: `data/google_execution_adapter_catalog_latest.json`
- Reference: `docs/google_surface_catalog_reference_20260513.md`
- Workflow reference: `docs/google_business_workflow_reference_20260513.md`
- Completion report:
  `docs/reports/google_surface_exploration_completion_report_20260513.md`
- Router command: `python scripts\entry\cdp_cli.py google surfaces catalog`
- Workflow command: `python scripts\entry\cdp_cli.py google work catalog`
- Adapter command: `python scripts\entry\cdp_cli.py google work adapters`
- Included: 50 Google surfaces, 96 work actions, and 96 execution adapter
  profiles.
- Gate: live browser work is read-only first. Writes, publishing, billing,
  IAM, upload, API key, release, indexing, comments, and channel edits require
  dry-run and explicit approval.

Live read report:

- `docs/reports/google_live_surface_read_report_20260513.md`

## Homepage Operations Update - 2026-05-13

The homepage repository is now included in the common operations index as
`homepage`.

- Common index: `docs/common_operations_index.md`
- Machine index: `configs/common_operations_index.json`
- Homepage reference: `docs/security-audit.md` in the homepage repository
- Homepage work log: `docs/work-log.md` in the homepage repository
- Status: `security_watch_active`
- Production watch: quick audit every 5 minutes, full audit daily at 03:40 KST
- Production latest status: `/home/ubuntu/logs/security-audit/latest.status`

## Naver Developed Tools Update - 2026-05-27

Naver remains `implemented_partial`, but the developed tools are now indexed in
`docs/naver_developed_tools_index.md`.

Verified or implemented Naver tool groups:

- `keyword-tools`: catalog, research plan, Datalab/shopping/SearchAd planning,
  and paid-action block policy.
- `cafe`: list, home, topic-search, join-request, join-submit approval gate,
  joined-cafe home collection, and board collection.
- `naver_mail`: background read, settings inspection, and approval gates for
  send/delete/move/settings-save.
- `browser_cdp_selection_gate`: common CDP tab isolation for parallel browser
  work.

Latest focused verification:

```powershell
python -m pytest tests\test_browser_cdp_selection_gate.py tests\test_naver_cafe_list_collector.py tests\test_naver_mail_background_runner.py tests\test_naver_service_router.py -q
```

Result: `52 passed`.

Remaining:

- Actual visible-form cafe join final click remains a separate approval-gated
  adapter.
- Paid Naver API/search-ad/payment/ad-publish actions remain blocked.
